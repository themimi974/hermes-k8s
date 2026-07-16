# hermes-k8s

Per-user isolated Hermes Agent subdomains on a single node. Each friend gets their own terminal shell behind `<friend>.domain.com`, with a central dashboard, LiteLLM gateway, and optional local LLM.

## Quick Deploy

**Requirements:** Linux (Ubuntu 22.04+, Debian 12+, Fedora 40+), Docker, 4GB RAM, 20GB disk.

```bash
# 1. Install Docker (if not present)
curl -fsSL https://get.docker.com | sudo sh

# 2. Clone the repo
git clone https://github.com/themimi974/hermes-k8s.git && cd hermes-k8s

# 3. Install Ollama + pull Qwen 3.5
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5:0.8b

# 4. Install Hermes Agent
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# 5. Copy deployment skill to Hermes
cp -r skills/deploy ~/.hermes/skills/

# 6. Start Hermes — it will guide you through the rest
hermes
```

Once Hermes is running, tell it: **"deploy hermes-k8s"** — it will read the deployment skill and walk you through everything.

---

## What You Get

| Component | URL | Description |
|-----------|-----|-------------|
| Dashboard | `https://dashboard.domain.com` | Manage friends, budget groups, usage |
| LiteLLM | `https://litellm.domain.com` | LLM API gateway with per-user keys |
| Friends | `https://<name>.domain.com` | Individual terminal shells |
| Local LLM | `http://localhost:11434` | Qwen 3.5 via Ollama |

## Stack

```
Cloudflare (*.domain.com → your-ip)
    │
    ▼
Traefik (Let's Encrypt wildcard TLS)
  ┌──────────┬───────────────┬──────────────────┐
  │          │               │                  │
dashboard  api            litellm          <friend>
frontend   :8000          :4000             :7681
(React)    (FastAPI)      (LiteLLM)         (ttyd)
                │               │
            PostgreSQL      PostgreSQL
           (dashboard)      (litellm)
```

---

## Deployment Documentation

The full deployment guide lives in `skills/deploy/` and is readable by Hermes Agent:

| Document | Purpose |
|----------|---------|
| [skills/deploy/SKILL.md](skills/deploy/SKILL.md) | Agent-facing deployment entry point |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and data flow |
| [docs/PREREQUISITES.md](docs/PREREQUISITES.md) | Hardware/software requirements |
| [docs/INSTALL-OS.md](docs/INSTALL-OS.md) | Multi-OS installation (Ubuntu, Fedora, etc.) |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Step-by-step deployment guide |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Config reference and provider setup |
| [docs/CREDENTIALS.md](docs/CREDENTIALS.md) | API keys and secrets management |
| [docs/DNS-SETUP.md](docs/DNS-SETUP.md) | Cloudflare domain configuration |
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
| Network | Public IP or Cloudflare-proxied domain |

### Software

| Tool | Why | Install |
|------|-----|---------|
| Docker | Container runtime | `curl -fsSL https://get.docker.com \| sh` |
| Docker Compose | Multi-container orchestration | Included with Docker |
| Git | Clone repo | `apt install git` / `dnf install git` |
| curl | Download scripts | Pre-installed on most distros |

### Optional

| Tool | Why |
|------|-----|
| Ollama | Local LLM inference |
| Hermes Agent | AI-assisted deployment and management |
| Cloudflare account | DNS + TLS wildcard certs |

---

## Configuration

### Environment Variables

Create `.env` in the repo root:

```bash
# Domain
DOMAIN=yourdomain.com
EMAIL=you@example.com

# Cloudflare
CF_API_TOKEN=your-cloudflare-api-token

# PostgreSQL
PG_PASSWORD=your-secure-password

# LiteLLM
LITELLM_MASTER_KEY=sk-master-your-key-here

# OpenAI (optional — for GPT models)
OPENAI_API_KEY=sk-your-key-here
```

### Adding More LLM Providers

Edit `litellm-config.yaml`:

```yaml
model_list:
  # Local Qwen via Ollama
  - model_name: qwen3.5
    litellm_params:
      model: ollama/qwen3.5:0.8b
      api_base: http://host.docker.internal:11434

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

---

## API Reference

```
GET    /api/friends                         → list friends
GET    /api/friends/{name}                  → friend details
POST   /api/friends                         → create friend
DELETE /api/friends/{name}                  → delete friend
POST   /api/friends/{name}/assign-group     → assign budget group
GET    /api/budget-groups                   → list budget groups
POST   /api/budget-groups                   → create group
PUT    /api/budget-groups/{id}              → update group
DELETE /api/budget-groups/{id}              → delete group
GET    /api/usage                           → usage stats
GET    /api/usage/models                    → list models
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

### Disk full

```bash
podman system prune -af
```

---

## License

MIT
