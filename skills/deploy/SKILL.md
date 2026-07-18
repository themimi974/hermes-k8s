---
name: hermes-k8s-deploy
description: "Deploy and manage hermes-k8s — per-user isolated Hermes Agent subdomains with LiteLLM gateway and local LLM."
version: 1.1.0
author: hermes-k8s
platforms: [linux]
metadata:
  hermes:
    tags: [deploy, k3s, litellm, ollama, infrastructure, self-hosted]
    related_skills: [hermes-agent, k3s-per-user-isolated-subdomains]
---

# hermes-k8s Deployment Skill

You are an infrastructure deployment agent. Your job is to deploy and manage the hermes-k8s stack on a Linux machine.

## What This System Is

hermes-k8s deploys:
- **k3s** single-node cluster
- **Traefik** reverse proxy with TLS (Let's Encrypt or self-signed)
- **PostgreSQL** for dashboard and LiteLLM databases
- **LiteLLM** API gateway with per-user virtual keys and budget controls
- **Dashboard** (FastAPI + React) for managing friends, groups, usage
- **Friend pods** — isolated terminal shells via ttyd
- **Ollama + Qwen 3.5** — local LLM inference (optional)
- **NVIDIA NIM** — free cloud inference with `deepseek-ai/deepseek-v4-pro` (default when no local model)

Each "friend" gets their own Kubernetes namespace, persistent storage, and a unique subdomain behind Traefik.

## Deployment Flow

When the user says "deploy hermes-k8s", follow these steps IN ORDER:

### Phase 1: Prerequisites Check

1. **OS detection** — check `/etc/os-release`
2. **Docker** — `docker --version`, install if missing
3. **Docker Compose** — `docker compose version`
4. **Git** — `git --version`
5. **Disk** — need ≥15GB free
6. **RAM** — need ≥4GB
7. **Ollama** — `ollama --version`, install if missing
8. **Qwen model** — `ollama pull qwen3.5:0.8b`

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

#### Step 2: DNS Provider

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

#### Step 3: TLS Method (based on DNS choice)

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

# Create k8s TLS secret
kubectl create secret tls hermes-tls \
  --cert="*.${DOMAIN}"*pem \
  --key="*.${DOMAIN}"*-key.pem \
  -n traefik --dry-run=client -o yaml | kubectl apply -f -
```

**If Let's Encrypt (Cloudflare):** use `certResolver: cfresolver` as before (requires Cloudflare API token in Traefik static config).

**If HTTP only:** use `entryPoints: [web]` in IngressRoutes, no TLS section.

#### Step 4: Other Credentials

Ask for these values — NEVER hardcode or assume:

| Question | Default | Notes |
|----------|---------|-------|
| PostgreSQL password | auto-generated | Can use `openssl rand -base64 24` |
| LiteLLM master key | auto-generated | Format: `sk-master-...` |
| OpenAI API key | optional | For GPT models |
| Anthropic API key | optional | For Claude models |

### Phase 3: Build & Deploy

1. **Clone repo** — `git clone https://github.com/themimi974/hermes-k8s.git`
2. **Build images** — podman/docker build 3 images
3. **Import to k3s** — `docker save | k3s ctr images import`
4. **Deploy manifests** — `kubectl apply -f dashboard/manifests/`
5. **Deploy gateway** — `kubectl apply -f gateway/`
6. **Configure LiteLLM** — create/update ConfigMap
7. **Configure TLS** — apply self-signed certs OR configure Let's Encrypt resolver
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

## Credential Management

**NEVER** echo back raw credentials in conversation. Show only:
- First 8 + last 4 characters: `sk-mas...ere`
- Or mask completely: `***`

Store credentials in:
- k8s Secrets (for pods)
- `.env` file (for scripts, gitignored)
- `/root/.hermes/.env` (for Hermes Agent)

## Troubleshooting Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| Pod `ErrImageNeverPull` | Image not in k3s | `docker save \| k3s ctr images import` |
| Pod `CrashLoopBackOff` | App error | `kubectl logs <pod>` |
| TLS cert not issuing (Let's Encrypt) | DNS not propagating | Check Cloudflare, patch Traefik DNS |
| Self-signed cert browser warning | Expected — CA not trusted | Install CA with `mkcert -install` or accept warning |
| DuckDNS not resolving | IP not updated | Re-run `curl "https://www.duckdns.org/update?domains=...&token=...&ip=..."` |
| LiteLLM 401 on health | No auth header | Add `Authorization: Bearer *** |
| Dashboard 502 | API pod down | `kubectl rollout restart deployment dashboard-api -n dashboard` |
| Disk full | Image/pod accumulation | `podman system prune -af` |
| Friend pod Pending | PVC or image issue | Check PVC status, import image |

## File Locations

| Path | Purpose |
|------|---------|
| `/home/admin/workspace/hermes-friends/` | Repo root |
| `deploy.sh` | Main deployment script |
| `skills/deploy/SKILL.md` | This file |
| `dashboard/` | API + Frontend + Manifests |
| `gateway/` | Landing page deployment |
| `scripts/` | Friend management scripts |
| `docs/` | Detailed documentation |
