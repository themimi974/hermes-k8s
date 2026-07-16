---
name: hermes-k8s-deploy
description: "Deploy and manage hermes-k8s — per-user isolated Hermes Agent subdomains with LiteLLM gateway and local LLM."
version: 1.0.0
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
- **Traefik** reverse proxy with Let's Encrypt wildcard TLS
- **PostgreSQL** for dashboard and LiteLLM databases
- **LiteLLM** API gateway with per-user virtual keys and budget controls
- **Dashboard** (FastAPI + React) for managing friends, groups, usage
- **Friend pods** — isolated terminal shells via ttyd
- **Ollama + Qwen 3.5** — local LLM inference (optional)

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

Ask for these values — NEVER hardcode or assume:

| Question | Default | Notes |
|----------|---------|-------|
| Domain name | — | e.g. `hermes.example.com` |
| Email for Let's Encrypt | — | TLS cert registration |
| Cloudflare API token | — | DNS-01 challenge |
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
7. **Configure DNS** — guide user through Cloudflare setup
8. **Verify** — check all pods running, HTTPS working

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

## Credential Management

**NEVER** echo back raw credentials in conversation. Show only:
- First 8 + last 4 characters: `sk-mas...ere`
- Or mask completely: `***`

Store credentials in:
- k8s Secrets (for pods)
- `.env` file (for scripts, gitignored)
- `~/.hermes/.env` (for Hermes Agent)

## Troubleshooting Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| Pod `ErrImageNeverPull` | Image not in k3s | `docker save \| k3s ctr images import` |
| Pod `CrashLoopBackOff` | App error | `kubectl logs <pod>` |
| TLS cert not issuing | DNS not propagating | Check Cloudflare, patch Traefik DNS |
| LiteLLM 401 on health | No auth header | Add `Authorization: Bearer <master_key>` |
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
