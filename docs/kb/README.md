# hermes-k8s Knowledge Base

Quick reference for managing the hermes-k8s deployment.

## Contents

- [How to Configure a Model](./configure-model.md)
- [What's Saved and Where](./saved-data.md)

## Quick Facts

| Item | Value |
|------|-------|
| Dashboard URL | `https://dashboard.hermiz.duckdns.org` |
| LiteLLM URL | `https://litellm.hermiz.duckdns.org` |
| Repo | `/opt/hermes-k8s` |
| K3s config | `/etc/rancher/k3s/k3s.yaml` |
| Hermes config | `/root/.hermes/config.yaml` |

## Architecture (30 seconds)

```
User → Dashboard → k8s API → creates friend pod (ttyd + hermes)
                ↘ LiteLLM → friend pod uses LiteLLM for model inference
                ↘ PostgreSQL → dashboard DB + LiteLLM DB (separate!)
                ↘ MinIO → snapshot storage
```

Each friend gets:
- Own k8s namespace (`friend-<name>`)
- Own PVC mounted at `/root/.hermes` (writable)
- Own subdomain (`<name>.hermiz.duckdns.org`)
- Own LiteLLM virtual key (budget-limited)
