---
name: hermes-k8s-deploy
description: "Deploy and manage hermes-k8s — per-user isolated Hermes Agent subdomains with LiteLLM gateway and local LLM."
version: 1.7.0
author: hermes-k8s
platforms: [linux]
metadata:
  hermes:
    tags: [deploy, k3s, litellm, infrastructure, self-hosted]
    related_skills: [hermes-agent, k3s-per-user-isolated-subdomains]
---

# hermes-k8s Deployment Skill

You are an infrastructure deployment agent. Your job is to deploy and manage the hermes-k8s stack on a Linux machine.

## What This System Is

hermes-k8s deploys:
- **k3s** single-node cluster
- **Traefik** reverse proxy with TLS (Let's Encrypt or self-signed)
- **PostgreSQL** for dashboard and LiteLLM databases (SEPARATE databases — see Pitfall 13)
- **LiteLLM** API gateway with per-user virtual keys and budget controls
- **Dashboard** (FastAPI + React) for managing friends, groups, usage
- **Friend pods** — isolated terminal shells via ttyd
- **NVIDIA NIM** — cloud inference with `deepseek-ai/deepseek-v4-pro` or custom models (default when no local model)
- **Xiaomi MiMo** — `mimo-v2.5-pro` via `xiaomimimo.com` (user-configurable)

Each "friend" gets their own Kubernetes namespace, persistent storage, and a unique subdomain behind Traefik.

**Key Architecture Decision:** Friend pod config is NOT baked into the Docker image. Each friend gets their own ConfigMap and Secret injected at runtime via the dashboard API. This ensures per-friend model/budget isolation.

## Deployment Flow

When the user says "deploy hermes-k8s", follow these steps IN ORDER:

### Phase 1: Prerequisites Check

1. **OS detection** — check `/etc/os-release`
2. **Podman** — `podman --version`, install if missing (NOT Docker — it conflicts with k3s networking)
3. **Firewalld** (Fedora/RHEL only) — see below
4. **Git** — `git --version`
5. **Disk** — need ≥10GB free
6. **RAM** — need ≥4GB
7. **Ollama** (OPTIONAL) — `ollama --version`, install ONLY if user wants local model. Skip entirely for NVIDIA NIM-only deployments.

**NVIDIA NIM-only deployments:** If user says "no ollama" or "NIM only", skip step 7 entirely. The system works with cloud inference only.

#### Firewalld (Fedora/RHEL — CRITICAL)

On Fedora/RHEL, `firewalld` runs by default and blocks pod-to-pod traffic on `cni0`. This causes Traefik 502 / `no route to host` errors. **Must be fixed BEFORE k3s install.**

```bash
# Check if firewalld is running
systemctl is-active firewalld

# If active, trust the k3s bridge interfaces BEFORE installing k3s
firewall-cmd --zone=trusted --add-interface=cni0 --permanent
firewall-cmd --zone=trusted --add-interface=flannel.1 --permanent
firewall-cmd --reload

# Verify
firewall-cmd --list-interfaces --zone=trusted
# Should show: cni0 flannel.1
```

**Why this happens:** Firewalld's default zone drops traffic on interfaces not explicitly trusted. k3s creates `cni0` (pod bridge) and `flannel.1` (overlay) — both get blocked until trusted.

**If you forgot and already installed k3s:** Same fix works, but you'll need to restart affected pods or reboot:
```bash
firewall-cmd --zone=trusted --add-interface=cni0 --permanent
firewall-cmd --zone=trusted --add-interface=flannel.1 --permanent
firewall-cmd --reload
# Then either reboot, or restart Traefik + all deployments
kubectl rollout restart deployment traefik -n kube-system
```

### Phase 2: Configuration (ASK USER)

#### Step 1: Cloud Provider (if no local model)

If user declined local model, ask about NVIDIA NIM:

| Option | Description | Notes |
|--------|-------------|-------|
| **NVIDIA NIM** | Free cloud inference, needs free API key from build.nvidia.com | Default model: `deepseek-ai/deepseek-v4-pro` (131k context) |
| **Manual** | User will configure their own provider later | Skip — user runs `hermes setup` afterwards |

**NVIDIA NIM config written to `/root/.hermes/config.yaml`:**
```yaml
model:
  default: deepseek-ai/deepseek-v4-pro
  provider: nvidia
  context_length: 131072
```

#### Step 2: Network Reachability

Ask BEFORE DNS setup:

> "Will this be reached only from your local network, or also from the public internet?"

| Option | Behavior |
|--------|----------|
| **Local only** | Use the machine's LAN IP (e.g. `192.168.1.x`) for domain/IP purposes. Skip public IP lookup entirely. DuckDNS still works but points to LAN IP. |
| **Public** | Look up public IP via `curl -s https://api.ipify.org` if needed (e.g. for DuckDNS record update). |

This prevents the agent from silently using a public IP on a LAN-only deploy.

#### Step 3: DNS Provider

Ask the user which DNS setup they have:

| Option | Description | TLS Method |
|--------|-------------|------------|
| **Cloudflare** | User has a domain managed by Cloudflare | Let's Encrypt via DNS-01 challenge (trusted certs) |
| **DuckDNS** | User has no domain or no DNS provider — DuckDNS is free (`*.duckdns.org`) | Self-signed certs (browser warning, but works immediately) |
| **None / IP only** | User wants to access via raw IP (e.g. `192.168.1.62`) | Self-signed certs or HTTP only |

**Recommendation when user has no DNS provider:**
> "If you don't have a domain or DNS provider, you can use **DuckDNS** — it's free and takes 2 minutes to set up. Go to https://www.duckdns.org, sign in with GitHub/Google, create a domain (e.g. `myserver.duckdns.org`), and give me the domain + your DuckDNS token."

**DuckDNS subdomain flow:**
- User picks a subdomain: `<name>.duckdns.org`
- User gets a DuckDNS token from the website
- The agent updates the DuckDNS record to point to the server's public IP
- Self-signed certs are generated — no Let's Encrypt needed (DuckDNS doesn't support ACME DNS-01 wildcard)

**DuckDNS update command (to set in cron or run once):**
```bash
curl -s "https://www.duckdns.org/update?domains=<SUBDOMAIN>&token=<TOKEN>&ip=<SERVER_IP>"
```

#### Step 4: TLS Method (based on DNS choice)

| DNS Provider | Recommended TLS | Why |
|--------------|----------------|-----|
| Cloudflare | Let's Encrypt (DNS-01) | Proper trusted certs, wildcard support |
| DuckDNS | Self-signed | DuckDNS doesn't support ACME DNS-01; self-signed works out of the box |
| None | Self-signed or HTTP | No domain = no Let's Encrypt; self-signed if user wants HTTPS, HTTP if not |

**If self-signed:** use `mkcert` (if available) or `openssl req -x509` to generate a CA + cert. Store as a k8s TLS secret (`hermes-tls`) and reference via `tls.secretName` in IngressRoutes instead of `certResolver`.

**Self-signed cert generation (bash):**
```bash
# Install mkcert if available
if ! command -v mkcert &>/dev/null; then
  apt-get install -y mkcert 2>/dev/null || dnf install -y mkcert 2>/dev/null || (
    curl -JLO "https://dl.filippo.io/mkcert/latest?for=linux/amd64" &&
    chmod +x mkcert-linux-amd64 &&
    mv mkcert-linux-amd64 /usr/local/bin/mkcert
  )
fi

mkcert -install  # installs local CA (optional, removes browser warnings)
mkcert "*.${DOMAIN}" "${DOMAIN}" "localhost" "127.0.0.1"

# Create k8s TLS secret in ALL namespaces that have IngressRoutes
# Traefik requires the secret to be in the SAME namespace as the IngressRoute.
for ns in dashboard auth litellm; do
  kubectl create secret tls hermes-tls \
    --cert="*.${DOMAIN}"*pem \
    --key="*.${DOMAIN}"*-key.pem \
    -n "$ns" --dry-run=client -o yaml | kubectl apply -f -
done
```

**If Let's Encrypt (Cloudflare):** use `certResolver: cfresolver` as before (requires Cloudflare API token in Traefik static config).

**If HTTP only:** use `entryPoints: [web]` in IngressRoutes, no TLS section.

**Verifying self-signed certs:** Do NOT use `curl -H "Host: ..." https://<ip>` — TLS SNI happens before the HTTP Host header, so curl sends no SNI for a bare IP and you'll always see Traefik's fallback default cert. Use `--resolve` instead:
```bash
curl -sk --resolve dashboard.example.com:443:192.168.1.62 https://dashboard.example.com
```
This makes curl treat the domain as resolving to the IP while still sending the domain as SNI — matching what a real browser does.

#### Step 5: Other Credentials

Ask for these values — NEVER hardcode or assume:

| Question | Default | Notes |
|----------|---------|-------|
| PostgreSQL password | auto-generated | Can use `openssl rand -base64 24` |
| LiteLLM master key | auto-generated | Format: `sk-master-...` |
| OpenAI API key | optional | For GPT models |
| Anthropic API key | optional | For Claude models |

### Phase 3: Build & Deploy

1. **Clone repo** — `git clone https://github.com/themimi974/hermes-k8s.git`
2. **Build images** — podman build 4 images (gateway, dashboard-api, dashboard-frontend, litellm). Use `--no-cache` if frontend shows placeholder HTML (Vite build cache issue).
3. **Import to k3s** — `podman save | k3s ctr images import` for each image
4. **Apply manifests with substitution** — use `scripts/apply-manifest.sh` to substitute `__DOMAIN__` and `__TLS__` in each manifest:
   ```bash
   DOMAIN="myserver.duckdns.org"   # or hermes.example.com, or 192.168.1.62
   TLS="selfsigned"                 # or letsencrypt, or http

   bash scripts/apply-manifest.sh gateway/ingressroute.yaml "$DOMAIN" "$TLS"
   bash scripts/apply-manifest.sh dashboard/manifests/50-ingressroute.yaml "$DOMAIN" "$TLS"
   kubectl apply -f dashboard/manifests/  # all non-templated manifests (namespace, postgres, frontend, RBAC)
   ```
5. **Deploy gateway** — `kubectl apply -f gateway/` (non-templated manifests like deployment, service, configmap)
6. **Configure LiteLLM** — create/update ConfigMap
7. **Configure TLS** — if self-signed: run `mkcert` + create `hermes-tls` secret (see Step 3 above)
8. **Configure DNS** — if Cloudflare: guide through setup; if DuckDNS: update record with `curl`
9. **Verify** — check all pods running, HTTPS working

### Phase 4: Validation

1. `kubectl get pods --all-namespaces` — all Running
2. `curl -sk https://dashboard.<domain>` — returns 200
3. `curl -sk https://litellm.<domain>` — returns 200
4. Create test friend — verify pod starts
5. Assign budget group — verify key created
6. Test LLM call — verify response
7. Delete test friend — verify cleanup

### Phase 5: Handoff

Print summary:
- Dashboard URL
- LiteLLM URL
- How to add friends
- How to access the terminal
- TLS method used and any caveats (e.g. "self-signed — browser will warn, install CA cert to dismiss")

## Git Push Authentication

After deploying, the dev agent will push code changes. If pushing via HTTPS fails with "Username for 'https://github.com'", switch to SSH:

```bash
cd /home/admin/hermes-k8s

# Use the user's GitHub SSH key
git config core.sshCommand "ssh -i /home/admin/github-key -o IdentitiesOnly=yes"

# Switch remote to SSH
git remote set-url origin git@github.com:themimi974/hermes-k8s.git

# Test auth
ssh -i /home/admin/github-key -o StrictHostKeyChecking=no -T git@github.com

# Push
git push origin main
```

**Note:** The SSH key must be added to the user's GitHub account (Settings → SSH keys).

## Credential Management

**NEVER** echo back raw credentials in conversation. Show only:
- First 8 + last 4 characters: `sk-mas...ere`
- Or mask completely: `***`

**Generated secrets must be consumed in a single command** — never printed to stdout, stored in a shell variable that gets echoed, or written to a file that's later `cat`'d. The agent's secret-redaction truncates displayed values, so re-displaying a generated key produces a different (wrong) string.

Correct pattern — generate and apply in one shot:
```bash
kubectl create secret generic litellm-credentials -n litellm \
  --from-literal=LITELLM_MASTER_KEY="sk-master-$(openssl rand -hex 24)" \
  --from-literal=NVIDIA_API_KEY="$NVIDIA_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
```

If a value must be reused across multiple manifests, generate it once into a variable within a single command block and reference the variable directly — never print it in between.

Store credentials in:
- k8s Secrets (for pods)
- `.env` file (for scripts, gitignored)
- `/root/.hermes/.env` (for Hermes Agent)

## Troubleshooting Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| Pod `ErrImageNeverPull` | Image not in k3s | `podman save \| k3s ctr images import` |
| Pod `CrashLoopBackOff` | App error | `kubectl logs <pod>` |
| TLS cert not issuing (Let's Encrypt) | DNS not propagating | Check Cloudflare, patch Traefik DNS |
| Self-signed cert browser warning | Expected — CA not trusted | Install CA with `mkcert -install` or accept warning |
| DuckDNS not resolving | IP not updated | Re-run `curl "https://www.duckdns.org/update?domains=...&token=...&ip=..."` |
| LiteLLM 401 on health | No auth header | Add `Authorization: Bearer ***` |
| Dashboard 502 | API pod down | `kubectl rollout restart deployment dashboard-api -n dashboard` |
| Dashboard frontend shows "Infrastructure deployed. Frontend coming soon" | Wrong image in manifest — using nginx:1.27-alpine + ConfigMap HTML instead of built image | Ensure `42-frontend-deployment.yaml` uses `localhost/hermes-dashboard-frontend:latest` with `imagePullPolicy: Never` |
| Dashboard API 500 on /api/friends | dashboard-api ServiceAccount has no cluster permissions | Apply `dashboard/manifests/60-dashboard-rbac.yaml` (ClusterRole + ClusterRoleBinding) |
| Disk full | Image/pod accumulation | `podman system prune -af` |
| Friend pod Pending | PVC or image issue | Check PVC status, import image |
| Traefik 502, `dial tcp ... no route to host` | kube-router netpol iptables blocking pod traffic | Add `--disable-network-policy` to k3s install; if already installed, reboot to clear stale rules |
| Traefik 502, `dial tcp ... no route to host` (Fedora/RHEL) | firewalld not trusted on cni0/flannel.1 | `firewall-cmd --zone=trusted --add-interface=cni0 --permanent && firewall-cmd --zone=trusted --add-interface=flannel.1 --permanent && firewall-cmd --reload` |
| cni0 missing / all pods broken networking | Docker iptables conflicting with k3s flannel | `systemctl disable --now docker docker.socket` then reboot — Docker must not run alongside k3s |
| Middleware "auth secret must be set" or "allowCrossNamespace is disabled" | `hermes-basic` middleware referenced but not defined | Single-node deploys: no auth middleware needed (Traefik/network boundary is sufficient). For public deploys: create real htpasswd middleware in each namespace. |
| Friend pod: `OSError: [Errno 30] Read-only file system: '/root/.hermes/cron'` | ConfigMap mounted over entire `/root/.hermes` directory as read-only | Use `subPath: config.yaml` to mount only the file. See Pitfall 19. |
| Friend pod: `Authentication Error, Invalid proxy server token passed` | LiteLLM virtual key is stale (DB recreation, key not in LiteLLM) | Delete and recreate friends, or use auto-refresh on group assignment. See Pitfall 21/24. |
| LiteLLM model: `LLM Provider NOT provided` | Wrong provider prefix for custom APIs | Use `openai/` prefix for ANY OpenAI-compatible API (NVIDIA NIM, MiMo, vLLM, custom). See Pitfall 17. |
| Friend pod: friend runs but can't make API calls | ConfigMap not created, or RBAC missing | Check dashboard-api logs for 403 errors; ensure ClusterRole `friend-manager` exists. See Pitfall 14. |
| LiteLLM drops dashboard tables (CRITICAL) | LiteLLM Prisma migrations run on shared database | ALWAYS use separate databases: `hermes_dashboard` for dashboard, `litellm_db` for LiteLLM. See Pitfall 13. |
| Usage tab: `password authentication failed for user "REPLACE_ME"` | Usage endpoint has hardcoded `***` password or wrong DB name | Fix `_get_litellm_db()` in `usage.py` to use `settings.postgres_password` and database `litellm_db`. See Pitfall 27. |
| Usage tab: `relation "litellm_spendlogs" does not exist` | Prisma table names are mixed-case, unquoted references are lowercased | Quote ALL Prisma table names: `"LiteLLM_SpendLogs"`, `"LiteLLM_VerificationToken"`. See Pitfall 28. |
| Usage tab: `column "spend" is ambiguous` | JOIN query references column without table alias | Prefix with `s.` for SpendLogs alias: `s.spend`, `s.total_tokens`. See Pitfall 29. |
| Usage tab shows "unknown" for all friends | Virtual keys missing `key_alias` field | Set `key_alias=friend_name` when creating keys. See Pitfall 28. |

**Note on authentication:** This repo does NOT deploy auth middleware for single-node LAN use. Dashboard, LiteLLM, and gateway are accessible without authentication on the local network. This is a deliberate design choice — the network boundary (LAN + no port forwarding) is sufficient for a single friend group. For public-facing deploys, add per-namespace basicAuth middleware.

## File Locations

| Path | Purpose |
|------|---------|
| `/home/admin/hermes-k8s/` | Repo root |
| `deploy.sh` | Main deployment script |
| `skills/deploy/SKILL.md` | This file |
| `skills/deploy/references/hermes-k8s-pitfalls.md` | Production pitfalls and fixes |
| `litellm/` | LiteLLM Dockerfile + manifests |
| `dashboard/` | API + Frontend + Manifests |
| `gateway/` | Landing page deployment |
| `scripts/` | Friend management + apply-manifest.sh |
| `docs/` | Detailed documentation |

## Related Documents

| Document | Purpose |
|----------|---------|
| [skills/deploy/SKILL.md](skills/deploy/SKILL.md) | Agent-facing deployment entry point |
| [skills/deploy/references/hermes-k8s-pitfalls.md](skills/deploy/references/hermes-k8s-pitfalls.md) | Production pitfalls and fixes |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and data flow |
| [docs/PREREQUISITES.md](docs/PREREQUISITES.md) | Hardware/software requirements |
| [docs/INSTALL-OS.md](docs/INSTALL-OS.md) | Multi-OS installation (Ubuntu, Fedora, etc.) |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Step-by-step deployment guide |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Config reference and provider setup |
| [docs/CREDENTIALS.md](docs/CREDENTIALS.md) | API keys and secrets management |
| [docs/DNS-SETUP.md](docs/DNS-SETUP.md) | DNS configuration (Cloudflare, DuckDNS) |
| [docs/MODELS.md](docs/MODELS.md) | Adding LLM providers |
| [docs/USAGE.md](docs/USAGE.md) | How to use the system |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and fixes |
