# What's Saved and Where

## Friend Pod Filesystem

Each friend pod has this layout:

```
/root/
├── .hermes/                    ← PVC-mounted, WRITABLE
│   ├── config.yaml             ← Hermes agent config (model, provider, etc.)
│   ├── memory/                 ← Persistent memory across sessions
│   ├── sessions/               ← Conversation history
│   ├── skills/                 ← User-defined skills
│   └── .env                    ← Secrets (API keys, etc.)
├── .bashrc                     ← Shell config
└── .profile                    ← Shell profile
```

## What Each File Does

| File | Purpose | Backed Up? |
|------|---------|-----------|
| `.hermes/config.yaml` | Model, provider, terminal backend, memory settings | ✅ |
| `.hermes/memory/` | Agent's long-term memory (user prefs, facts) | ✅ |
| `.hermes/sessions/` | Conversation history | ✅ |
| `.hermes/skills/` | Custom skills the agent learned | ✅ |
| `.hermes/.env` | API keys, secrets | ✅ |
| `.bashrc` | Shell aliases, PATH | ✅ |
| `.profile` | Login shell config | ✅ |

## Where Data Lives in k8s

| Resource | Location |
|----------|----------|
| Friend PVC | `friend-<name>` namespace, claim `friend-data` (2Gi default) |
| PVC mount | `/root/.hermes` in the pod |
| Config source | ConfigMap `hermes-config` (legacy) → now written directly to PVC |
| LiteLLM key | Secret `friend-litellm-key` in friend namespace |

## Snapshots (Save/Restore)

Snapshots are tarballs of `/root/.hermes`, `/root/.bashrc`, `/root/.profile`.

| Item | Detail |
|------|--------|
| Storage | MinIO bucket `hermes-states` |
| Endpoint | `minio.dashboard.svc.cluster.local:9000` |
| Key format | `<friend-name>/backup-<timestamp>.tar.gz` |
| Save command | `tar czf - -C /root .hermes .bashrc .profile` |
| Restore command | `tar xzf - -C /root` |
| Size | ~1KB per snapshot (only hermes state, no caches) |

### Save/Restore via API

```bash
# Save
curl -X POST https://dashboard.hermiz.duckdns.org/api/friends/<name>/save

# List snapshots
curl https://dashboard.hermiz.duckdns.org/api/friends/<name>/snapshots

# Restore latest
curl -X POST https://dashboard.hermiz.duckdns.org/api/friends/<name>/restore

# Restore specific snapshot
curl -X POST "https://dashboard.hermiz.duckdns.org/api/friends/<name>/restore?snapshot_key=<key>"
```

## Databases

| Database | Namespace | Purpose |
|----------|-----------|---------|
| `hermes_dashboard` | `dashboard` | Friends, budget groups, models, config |
| `litellm_db` | `dashboard` | LiteLLM spend logs, virtual keys, usage |

**CRITICAL:** These are separate databases. LiteLLM will drop dashboard tables if they share a database.

## Source Code Paths

| Path | Purpose |
|------|---------|
| `/opt/hermes-k8s/` | Repo root |
| `dashboard/api/` | Dashboard API (FastAPI) |
| `dashboard/api/services/k8s.py` | k8s resource management |
| `dashboard/api/services/state_manager.py` | Snapshot save/restore |
| `dashboard/api/services/minio_client.py` | MinIO operations |
| `dashboard/api/services/litellm_config.py` | LiteLLM config generation |
| `litellm/` | LiteLLM Dockerfile + manifests |
| `scripts/` | Friend management scripts |
| `skills/deploy/` | Deployment skill + pitfalls |
