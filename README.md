# hermes-k8s

Per-user isolated Hermes Agent subdomains on a single node. Each friend gets their own terminal shell behind `<friend>.domain.com`, with a central dashboard, LiteLLM gateway, and per-friend dynamic configuration.

## Quick Deploy

**Requirements:** Linux (Ubuntu 22.04+, Debian 12+, Fedora 40+), 4GB RAM, 20GB disk.

### One-liner (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/themimi974/hermes-k8s/main/deploy.sh | sudo bash
```

This installs everything: Podman, Git, Hermes Agent, k3s, and the deployment skill. It will interactively ask you about:
- Local model (Ollama + Qwen) or cloud (NVIDIA NIM — free tier, needs API key)

DNS/domain/TLS is configured later, interactively, when you tell the running agent to **"deploy hermes-k8s"**.

Once done, run `sudo hermes` and tell it: **"deploy hermes-k8s"**

> **Why `sudo`?** Hermes config lives at `/root/.hermes/` (not your user's home) because `sudo hermes` resolves `~` as root's home. k3s also requires root. Always launch with `sudo hermes`.

### Manual install

If you prefer step-by-step:

```bash
# 1. Install Podman (if not present — NOT Docker, it conflicts with k3s)
sudo dnf install -y podman  # or: sudo apt-get install -y podman

# 2. Clone the repo
git clone https://github.com/themimi974/hermes-k8s.git && cd hermes-k8s

# 3. Install Hermes Agent
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# 4. Copy deployment skill to Hermes (root-owned)
sudo mkdir -p /root/.hermes/skills
sudo cp -r skills/deploy /root/.hermes/skills/

# 5. Start Hermes as root — it will guide you through the rest
sudo hermes
```

Once Hermes is running, tell it: **"deploy hermes-k8s"** — it will read the deployment skill and walk you through everything.

---

## What You Get

| Component | URL | Description |
|-----------|-----|-------------|
| Dashboard | `https://dashboard.domain.com` | Manage friends, budget groups, usage analytics |
| LiteLLM | `https://litellm.domain.com` | LLM API gateway with per-user keys |
| Friends | `https://<name>.domain.com` | Individual terminal shells |

### Usage Analytics

The dashboard tracks per-friend, per-model usage with detailed token breakdown:

- **Input tokens** — prompt tokens sent to the model
- **Output tokens** — completion tokens generated
- **Cached tokens** — prompt tokens served from cache (saves cost)
- **Cache hit %** — `cached / input × 100` (shown in Matrix tab)

All data comes from LiteLLM's `SpendLogs` table — no additional logging needed.

## Stack

```
DuckDNS (*.domain.com → your-ip)
    │
    ▼
Traefik (self-signed or Let's Encrypt TLS)
  ┌──────────┬───────────────┬──────────────────┐
  │          │               │                  │
dashboard  api            litellm          <friend>
frontend   :8000          :4000             :7681
(React)    (FastAPI)      (LiteLLM)         (ttyd)
                │               │
            PostgreSQL      PostgreSQL
           (dashboard)      (litellm_db)
```

**Key Architecture:** Friend pods get dynamic ConfigMap/Secret injection — NOT baked-in config. Each friend's model, API key, and budget are configured at runtime via the dashboard API.

---

## Deployment Documentation

The full deployment guide lives in `skills/deploy/` and is readable by Hermes Agent:

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

---

## Requirements

### Minimum

| Resource | Value |
|----------|-------|
| OS | Ubuntu 22.04+, Debian 12+, Fedora 40+, RHEL 9+ |
| CPU | 2 cores |
| RAM | 4 GB |
| Disk | 20 GB |
| Network | Public IP or LAN with domain/DuckDNS |

### Software

| Tool | Why | Install |
|------|-----|---------|
| Podman | Container runtime (NOT Docker) | `dnf install podman` / `apt-get install podman` |
| Git | Clone repo | Pre-installed on most distros |
| curl | Download scripts | Pre-installed on most distros |
| k3s | Kubernetes | Auto-installed by deploy script |
| mkcert | Self-signed TLS certs | Auto-installed by deploy script |

### Optional

| Tool | Why |
|------|-----|
| NVIDIA API key | Free cloud inference (default) |
| Cloudflare account | DNS + TLS wildcard certs |
| DuckDNS account | Free dynamic DNS (no domain needed) |

---

## Configuration

### Adding LLM Providers

Edit `litellm-config.yaml` ConfigMap:

```yaml
model_list:
  # NVIDIA NIM (default — free)
  - model_name: deepseek-v4-pro
    litellm_params:
      model: openai/deepseek-ai/deepseek-v4-pro
      api_key: os.environ/NVIDIA_API_KEY
      api_base: https://integrate.api.nvidia.com/v1
    model_info:
      context_length: 131072

  # Xiaomi MiMo
  - model_name: mimo-v2.5-pro
    litellm_params:
      model: openai/mimo-v2.5-pro
      api_key: os.environ/XIAOMI_API_KEY
      api_base: https://xiaomimimo.com/v1
    model_info:
      context_length: 131072

  # OpenAI
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

  # Anthropic
  - model_name: claude-sonnet
    litellm_params:
      model: anthropic/claude-sonnet-4-20250514
      api_key: os.environ/ANTHROPIC_API_KEY
```

**Important:** For ANY OpenAI-compatible API (NVIDIA NIM, MiMo, vLLM, custom servers), use the `openai/` provider prefix in LiteLLM. Do NOT use the provider's own name (e.g. `nvidia/`, `xiaomi/`).

---

## API Reference

```
# Friends
GET    /api/friends                         → list friends
GET    /api/friends/{name}                  → friend details
POST   /api/friends                         → create friend
DELETE /api/friends/{name}                  → delete friend

# Multi-group assignment
POST   /api/friends/{name}/groups/{group_id}   → assign group
DELETE /api/friends/{name}/groups/{group_id}    → remove group
PUT    /api/friends/{name}/groups               → set all groups (replace)

# Budget groups
GET    /api/budget-groups                   → list budget groups
POST   /api/budget-groups                   → create group
PUT    /api/budget-groups/{id}              → update group
DELETE /api/budget-groups/{id}              → delete group

# Usage
GET    /api/usage                           → global overview (input/output/cached tokens)
GET    /api/usage/friends                   → per-friend breakdown
GET    /api/usage/friends/{name}            → per-friend by model
GET    /api/usage/models                    → per-model breakdown
GET    /api/usage/models/{model_id}         → per-model by friend
GET    /api/usage/matrix                    → friend × model matrix with cache hit %
```

---

## Troubleshooting

### Pod stuck in ErrImageNeverPull

```bash
# Import image to k3s
podman save localhost/hermes-friends/ttyd:latest -o /tmp/img.tar
sudo k3s ctr images import /tmp/img.tar
kubectl delete pod <pod-name> -n friend-<name>
```

### TLS cert not issuing

Patch Traefik with external DNS:
```bash
kubectl patch deployment traefik -n kube-system --type json -p '[
  {"op": "replace", "path": "/spec/template/spec/dnsPolicy", "value": "None"},
  {"op": "add", "path": "/spec/template/spec/dnsConfig/nameservers", "value": ["1.1.1.1", "8.8.8.8"]}
]'
```

### Friend pod crashes with "Read-only file system"

ConfigMap mounted over entire `/root/.hermes` directory. Fix: use `subPath: config.yaml` in volume mount (see Pitfall 19).

### Friend can't make API calls (Authentication Error)

LiteLLM virtual key is stale. Fix: delete and recreate friend, or use auto-refresh on group assignment (see Pitfall 21/24).

### LiteLLM drops dashboard tables (CRITICAL)

LiteLLM Prisma migrations destroy shared database. Fix: ALWAYS use separate databases (`hermes_dashboard` for dashboard, `litellm_db` for LiteLLM). See Pitfall 13.

### Model shows "LLM Provider NOT provided"

Wrong provider prefix in LiteLLM config. Fix: use `openai/` prefix for ANY OpenAI-compatible API. See Pitfall 17.

### Disk full

```bash
podman system prune -af
```

---

## License

MIT
