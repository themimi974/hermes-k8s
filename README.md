# hermes-k8s

Per-user isolated Hermes Agent subdomains on a single k3s node. Each friend gets their own terminal shell behind `<friend>.hermes.caron.fun`, with a central dashboard, LiteLLM gateway, and optional local LLM.

## Stack

```
Cloudflare (*.hermes.caron.fun → 192.168.1.174)
    │
    ▼
Traefik (Let's Encrypt wildcard TLS)
  ┌──────────┬───────────────┬──────────────────┐
  │          │               │                  │
dashboard  api            litellm          <friend>
frontend   :8000          :4000             :7681
(nginx)    (FastAPI)      (LiteLLM)         (ttyd)
```

- **TLS**: Wildcard cert `*.hermes.caron.fun` via Let's Encrypt DNS-01
- **DNS**: Cloudflare (DNS only, no proxy)
- **Auth**: Per-friend basicAuth via Traefik CRD Middlewares
- **Storage**: 2Gi `local-path` PVC per friend
- **LLM Gateway**: LiteLLM proxy with virtual keys per user
- **Local LLM**: SmolLM2-135M via podman-compose on host

---

## Services

| Service | URL | Description |
|---------|-----|-------------|
| Dashboard | `https://dashboard.hermes.caron.fun` | React UI for managing friends, budget groups, usage |
| Dashboard API | `https://dashboard.hermes.caron.fun/api/` | FastAPI backend |
| LiteLLM | `https://litellm.hermes.caron.fun` | LLM API gateway |
| Friends | `https://<name>.hermes.caron.fun` | Individual terminal shells |

---

## Prerequisites

- Fedora 44 (or similar) with k3s
- Cloudflare account + domain
- Cloudflare API Token (Zone > DNS > Edit)
- podman (for building images)
- Sudo access

---

## Quick Start

### 1. Install k3s

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--write-kubeconfig-mode 0640" sh -
sudo chown root:$(id -gn) /etc/rancher/k3s/k3s.yaml
kubectl get nodes --watch
```

### 2. Build and import images

```bash
# ttyd image (for friends)
podman build -t localhost/hermes-friends/ttyd:latest .
podman save localhost/hermes-friends/ttyd:latest | sudo k3s ctr images import -

# Dashboard API
cd dashboard/api
podman build -t localhost/hermes-dashboard-api:latest .
podman save localhost/hermes-dashboard-api:latest | sudo k3s ctr images import -

# Dashboard Frontend
cd dashboard/frontend
podman build -t localhost/hermes-dashboard-frontend:latest .
podman save localhost/hermes-dashboard-frontend:latest | sudo k3s ctr images import -
```

### 3. Deploy

```bash
kubectl apply -f dashboard/manifests/
kubectl apply -f gateway/
```

### 4. Start local LLM (optional)

```bash
cd ~/llama-compose
podman-compose up -d
```

### 5. Configure LiteLLM

```bash
# Update the ConfigMap with your model config
kubectl create configmap litellm-config -n litellm \
  --from-file=config.yaml=litellm-config.yaml \
  -o yaml --dry-run=client | kubectl replace -f -

# Restart LiteLLM
kubectl rollout restart deployment litellm -n litellm
```

---

## Dashboard

Access at `https://dashboard.hermes.caron.fun`. Features:

- **Friends**: Create, delete, view status of friend pods
- **Budget Groups**: Define model access, rate limits, budgets
- **Usage**: Track API calls, tokens, costs by model and friend
- **Virtual Keys**: Auto-provisioned per friend via LiteLLM

### API Endpoints

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
GET    /api/usage/models                    → list models from LiteLLM
```

---

## LiteLLM Gateway

LLM API gateway with per-user virtual keys and budget controls.

### Configured Models

| Model | Provider | Status |
|-------|----------|--------|
| smolm2 | Local (llama.cpp) | ✅ Healthy |
| gpt-4o | OpenAI | ⚠️ Needs API key |
| gpt-4o-mini | OpenAI | ⚠️ Needs API key |
| gpt-3.5-turbo | OpenAI | ⚠️ Needs API key |

### Adding Models

Edit the LiteLLM ConfigMap. LiteLLM supports multiple providers:

```yaml
model_list:
  # Local (llama.cpp)
  - model_name: smolm2
    litellm_params:
      model: openai/smollm2
      api_base: http://192.168.1.174:8080/v1
      api_key: none

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

  # Ollama
  - model_name: llama3
    litellm_params:
      model: ollama/llama3
      api_base: http://host:11434
```

### Virtual Key Lifecycle

Keys are auto-managed by the dashboard:
1. **Create friend** → LiteLLM key created, stored in DB
2. **Assign group** → Key updated with group's models/limits
3. **Delete friend** → Key deleted from LiteLLM + DB

---

## Local LLM (SmolLM2)

Runs on the host via podman-compose, accessible from k3s pods.

```bash
# Start
cd ~/llama-compose && podman-compose up -d

# Stop
podman-compose down

# Check status
curl http://localhost:8080/health
```

| Item | Value |
|------|-------|
| Model | SmolLM2-135M-Instruct Q4_K_M (101MB) |
| Server | llama.cpp on host:8080 |
| Compose file | `/home/admin/llama-compose/docker-compose.yml` |
| Model file | `/home/admin/models/SmolLM2-135M-Instruct-Q4_K_M.gguf` |

---

## Adding Friends

### Via Dashboard

Go to `https://dashboard.hermes.caron.fun` → Friends → Add Friend

### Via API

```bash
curl -X POST https://dashboard.hermes.caron.fun/api/friends \
  -H "Content-Type: application/json" \
  -d '{"name": "alice", "username": "alice", "password": "your-password"}'

# Assign budget group
curl -X POST "https://dashboard.hermes.caron.fun/api/friends/alice/assign-group?group_id=1"
```

### What Gets Created

- Kubernetes namespace `friend-alice`
- PersistentVolumeClaim (2Gi)
- htpasswd Secret + Traefik Middleware
- ttyd Deployment + Service
- IngressRoute (`alice.hermes.caron.fun`)
- LiteLLM virtual key

---

## Budget Groups

Pre-configured groups with model access and rate limits:

| Group | Models | Budget | TPM | RPM |
|-------|--------|--------|-----|-----|
| basic | smolm2 | $10 | 100K | 1K |
| standard | smolm2 | $50 | 100K | 1K |
| premium | smolm2 | $200 | 100K | 1K |
| unlimited | smolm2 | $999K | 100K | 1K |

---

## File Layout

```
hermes-friends/
├── README.md
├── Dockerfile                       ← ttyd image
├── .gitignore
├── docs/                            ← reports, plans (gitignored)
├── gateway/                         ← hermes.caron.fun landing page
├── dashboard/
│   ├── manifests/                   ← k8s manifests
│   ├── api/                         ← FastAPI backend
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── routers/
│   │   │   ├── friends.py
│   │   │   ├── budget_groups.py
│   │   │   ├── usage.py
│   │   │   └── health.py
│   │   └── services/
│   │       ├── litellm_client.py    ← LiteLLM API client
│   │       ├── friend_manager.py    ← k8s resource management
│   │       └── k8s.py               ← k8s API wrapper
│   └── frontend/                    ← React + Vite + Tailwind
│       └── src/pages/
│           ├── Dashboard.jsx
│           ├── BudgetGroups.jsx
│           ├── Usage.jsx
│           └── FriendDetail.jsx
├── manifests/                       ← friend templates
└── scripts/
    ├── add-friend.sh
    └── remove-friend.sh
```

---

## Troubleshooting

### Pod stuck in ErrImageNeverPull

Image not in k3s containerd. Import it:
```bash
podman save localhost/hermes-friends/ttyd:latest -o /tmp/img.tar
sudo k3s ctr images import /tmp/img.tar
# Then delete the stuck pod to force recreate
kubectl delete pod <pod-name> -n friend-<name>
```

### TLS cert not issuing

```bash
kubectl -n kube-system logs deployment/traefik --tail=50 | grep -i acme
```

Fix: Patch Traefik with external DNS (k3s CoreDNS doesn't return SOA):
```bash
kubectl patch deployment traefik -n kube-system --type json -p '[
  {"op": "replace", "path": "/spec/template/spec/dnsPolicy", "value": "None"},
  {"op": "add", "path": "/spec/template/spec/dnsConfig/nameservers", "value": ["1.1.1.1", "8.8.8.8"]}
]'
```

### LiteLLM models unhealthy

Check API key:
```bash
kubectl get secret litellm-config -n litellm -o jsonpath='{.data.OPENAI_API_KEY}' | base64 -d
```

### Disk full

```bash
podman system prune -af
sudo k3s ctr images prune --all  # CAUTION: removes all images
kubectl get pods --all-namespaces -o json | jq '.items[] | select(.status.containerStatuses[]?.restartCount > 5) | .metadata.name'
```
