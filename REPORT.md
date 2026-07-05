# hermes-k8s — Project Report

**Date:** 2026-07-05  
**Repository:** https://github.com/themimi974/hermes-k8s  
**Infrastructure:** Single-node k3s on Fedora 44 (Host-004, 192.168.1.174)

---

## Objective

Build a multi-friend per-user-isolated Hermes Agent environment on a single k3s cluster, where each friend gets their own terminal shell behind a unique subdomain (`<friend>.hermes.caron.fun`), with a central gateway at `hermes.caron.fun`.

---

## Architecture

```
Cloudflare DNS (*.hermes.caron.fun → 192.168.1.174)
        │
   Traefik (k3s IngressRouteCRDs, TLS via cfresolver DNS-01)
        │
   ┌────┴────┐
   │         │
gateway   friend pods
nginx     ttyd (bash -l over WebSocket :7681)
```

- **TLS**: Wildcard cert `*.hermes.caron.fun` via Cloudflare DNS-01 challenge
- **Auth**: Per-friend basicAuth Middleware (CRD), per-friend htpasswd Secret
- **Storage**: `local-path` StorageClass, 2Gi PVC per friend, mounted at `/opt/data`
- **Image**: Custom `debian:trixie` + Node 20 + ttyd + Hermes (built with podman, imported to k3s containerd)

---

## What Was Built

### Per-Friend Stack (8 Kubernetes resources)
| Resource | Purpose |
|---|---|
| Namespace `friend-<name>` | Isolation boundary with traefik=enabled label |
| ResourceQuota | Caps: 1Gi-2Gi mem, 4 CPU, 5 pods |
| PersistentVolumeClaim | 2Gi `local-path` for `/opt/data` |
| Secret `friend-htpasswd` | APR1 htpasswd hash for basic auth |
| Middleware `friend-basic` | Traefik CRD basicAuth referencing the secret |
| Deployment `ttyd` | ttyd pod (strategy: Recreate for RWO PVC) |
| Service `ttyd` | ClusterIP :7681 |
| IngressRoute `vanity` | `Host(<friend>.hermes.caron.fun)` → ttyd:7681 + TLS |

### Gateway Stack (5 resources in `auth` namespace)
| Resource | Purpose |
|---|---|
| ConfigMap `gateway-index` | Static HTML landing page with per-friend list |
| Deployment `gateway` | nginx:alpine serving the landing page |
| Service `gateway` | ClusterIP :80 |
| IngressRoute `hermes-gateway-vanity` | `Host(hermes.caron.fun)` → gateway:80 + TLS |
| ConfigMap `friends-registry` | JSON array of friends (updated by scripts) |

### Helper Scripts
| Script | Usage |
|---|---|
| `add-friend.sh <name> <user> <pass>` | Idempotent: creates all resources + updates registry |
| `remove-friend.sh <name>` | Deletes namespace + removes from registry |
| `gateway-sync.sh` | Regenerates nginx ConfigMap from registry, restarts gateway |
| `import-image.sh` | Exports podman image → imports to k3s containerd (needs sudo) |

---

## Implementation Steps

### 1. Cluster Verification
- Confirmed k3s single-node (`host-005`, v1.36.2+k3s1, Ready 43h)
- Fixed kubeconfig permissions: `chown root:admin /etc/rancher/k3s/k3s.yaml` (mode 0640)
- Verified existing POC stack (IR `hermes-vanity`, Secret `hermes-htpasswd`)

### 2. Image Build
- Wrote Dockerfile: `debian:trixie` + tini + ttyd (tsl0922/ttyd static x86_64) + Node 20 + Hermes CLI (--skip-setup --skip-browser)
- Built with podman: `podman build -t hermes-friends/ttyd:latest .`
- Imported to k3s: `podman save | k3s ctr images import` (required sudo)

### 3. Manifest Authoring
- Wrote per-friend template with `__NAME__`, `__HOST__`, `__B64USERS__` placeholders
- Wrote cyprien_iov-specific manifests (first friend)
- Wrote gateway stack manifests

### 4. Deployment + Bug Fixes
- Applied manifests; hit two issues:
  - **Underscore in namespace name**: Kubernetes rejects `friend-cyprien_iov` (RFC 1123). Fixed to `friend-cyprien-iov`. DNS subdomain `cyprien_iov.hermes.caron.fun` kept as-is.
  - **Middleware `@file` reference**: Traefik has no file provider (only `kubernetescrd`). `friend-basic@file` → `friend-basic` with `namespace:` field. Same fix for `hermes-basic@file` → `hermes-basic namespace: auth`.
- After fixes: both endpoints respond correctly.

### 5. Persistence Test
- Wrote marker file to `/opt/data/.persistence-test` inside ttyd pod
- Killed pod, waited for respawn
- Verified marker file survived → PVC persistence confirmed

### 6. Git Push
- Installed git (was missing on host)
- Configured SSH key (`~/.ssh/githubkey`) for GitHub auth
- Committed 27 files, pushed to `github.com/themimi974/hermes-k8s` (main branch)

---

## Key Gotchas Discovered

1. **K8s namespace names** don't allow underscores (RFC 1123 lowercase alphanumeric + hyphens). DNS subdomains CAN have underscores.
2. **Traefik CRD middleware references** use `name` + `namespace` (NOT `@file`). The `@file` suffix is for file-provider middlewares only.
3. **`sudo -S` via non-TTY SSH** pipes fails on this system. `echo PASS | sudo -S` works, but heredoc/printf patterns don't.
4. **Locally imported containerd images** need `localhost/` prefix + `imagePullPolicy: Never` in deployment specs.
5. **PVC RWO constraint** requires `strategy: Recreate` on Deployments (not RollingUpdate).
6. **htpasswd not installed** on Fedora host — use `openssl passwd -apr1 -salt <salt> <pass>` as alternative.

---

## Current State

| Endpoint | Status | Auth |
|---|---|---|
| `https://hermes.caron.fun/` | ✅ Running | admin:Test1234 |
| `https://cyprien_iov.hermes.caron.fun/` | ✅ Running | cyprien_iov:Test1234 |
| Cloudflare DNS-01 wildcard cert | ⏳ Propagating | — |

---

## Files Committed (27)

```
.gitignore
Dockerfile
README.md
gateway/configmap-index.yaml
gateway/deployment.yaml
gateway/ingressroute.yaml
gateway/registry.yaml
gateway/service.yaml
manifests/_template/00-namespace.yaml
manifests/_template/01-data-pvc.yaml
manifests/_template/02-htpasswd.yaml
manifests/_template/03-middleware.yaml
manifests/_template/04-deployment.yaml
manifests/_template/05-service.yaml
manifests/_template/06-ingressroute.yaml
manifests/cyprien_iov/00-namespace.yaml
manifests/cyprien_iov/01-quota.yaml
manifests/cyprien_iov/02-data-pvc.yaml
manifests/cyprien_iov/03-htpasswd.yaml
manifests/cyprien_iov/04-middleware.yaml
manifests/cyprien_iov/05-deployment.yaml
manifests/cyprien_iov/06-service.yaml
manifests/cyprien_iov/07-ingressroute.yaml
scripts/add-friend.sh
scripts/gateway-sync.sh
scripts/import-image.sh
scripts/remove-friend.sh
```

---

## Next Steps

- [ ] Add more friends via `bash scripts/add-friend.sh <name> <user> <pass>`
- [ ] Monitor Cloudflare cert issuance for wildcard domain
- [ ] Test end-to-end from public internet (after DNS propagation)
- [ ] Consider: resource monitoring, log aggregation, backup strategy for PVCs
