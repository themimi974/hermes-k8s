# hermes-friends — Per-user isolated subdomains on k3s

## Architecture

```
*.hermes.caron.fun  →  Cloudflare DNS →  Traefik (k3s IngressRouteCRD)
                                            │
                    ┌───────────────────────┤
                    │                       │
              hermes.caron.fun       <friend>.hermes.caron.fun
              (gateway pod)          (friend ttyd pod)
              nginx + index.html     bash -l via ttyd :7681
              hermes-basic mw        friend-basic mw
```

- **Cloudflare DNS-01** certs via `cfresolver` (wildcard `*.hermes.caron.fun`).
- **Traefik IngressRouteCRD** (not Ingress): per-friend IR + per-friend Middleware (labelled `traefik=enabled`).
- **No shared PVCs.** Each friend gets 2Gi `local-path` PVC mounted at `/opt/data` inside the ttyd container.
- **Gateway** at `hermes.caron.fun` is a static nginx ConfigMap-served HTML page listing all friends + their creds. Authenticated with the original `hermes-basic` middleware.

## File layout

```
~/workspace/hermes-friends/
├── README.md                          ← this file
├── manifests/
│   ├── cyprien_iov/                   ← first-friend (POC migration)
│   │   ├── 00-namespace.yaml
│   │   ├── 01-quota.yaml
│   │   ├── 02-data-pvc.yaml
│   │   ├── 03-htpasswd.yaml
│   │   ├── 04-middleware.yaml
│   │   ├── 05-deployment.yaml
│   │   ├── 06-service.yaml
│   │   └── 07-ingressroute.yaml
│   └── _template/                     ← generic; sed'd by add-friend.sh
│       ├── 00-namespace.yaml          (__NAME__, __HOST__, __B64USERS__)
│       ├── 01-data-pvc.yaml
│       ├── 02-htpasswd.yaml
│       ├── 03-middleware.yaml
│       ├── 04-deployment.yaml
│       ├── 05-service.yaml
│       └── 06-ingressroute.yaml
├── gateway/
│   ├── configmap-index.yaml           ← base template (empty friends)
│   ├── deployment.yaml                ← nginx pod
│   ├── service.yaml                   ← ClusterIP :80
│   ├── ingressroute.yaml              ← hermes.caron.fun → gateway
│   └── registry.yaml                  ← friends-registry ConfigMap (JSON array)
└── scripts/
    ├── add-friend.sh <name> <user> <pass>   ← idempotent full provision
    ├── remove-friend.sh <name>              ← teardown (namespace + registry)
    └── gateway-sync.sh                      ← registry → nginx ConfigMap → restart
```

## Quick start — adding a friend

```bash
cd ~/workspace/hermes-friends
bash scripts/add-friend.sh alice alice 'hunter2'
```

What it does (fully idempotent):
1. Creates namespace `friend-alice` with resource quota (1Gi/2Gi mem, 4 CPU, 5 pods)
2. PVC `friend-data` (2Gi, `local-path`)
3. Secret `friend-htpasswd` with `alice:$apr1$...`
4. Middleware `friend-basic` (labelled `traefik=enabled`)
5. Deployment `ttyd` (`hermes-friends/ttyd:latest`) → PVC `/opt/data`
6. Service `ttyd` (ClusterIP :7681)
7. IngressRoute `vanity` → `alice.hermes.caron.fun` → `friend-basic@file` → `ttyd:7681` + `cfresolver` TLS
8. Updates `friends-registry` ConfigMap → re-syncs gateway nginx → restarts gateway pod

## Removing a friend

```bash
bash scripts/remove-friend.sh alice
```

Deletes the entire `friend-alice` namespace (cascading: svc, deploy, pvc, secret, middleware, IR). Removes from registry. Restarts gateway.

## Provisioning cyprien_iov (first friend, migration from POC)

```bash
# 1. Apply cyprien_iov manifests
kubectl apply -f manifests/cyprien_iov/

# 2. Wait for pod
kubectl -n friend-cyprien_iov rollout status deployment/ttyd --timeout=120s

# 3. Remove cyprien_iov from the old hermes-htpasswd secret in auth namespace
kubectl -n auth get secret hermes-htpasswd -o json | \
  jq 'del(.data.users)' | kubectl replace -f -
# (or just delete the secret if hermes-basic middleware can tolerate empty —
#  the middleware definition in hermes-vanity will 401 everyone, which is fine
#  since cyprien_iov now has its own middleware)

# 4. Verify
curl -u 'cyprien_iov:Test1234' -kI https://cyprien_iov.hermes.caron.fun/
# Expect: HTTP/2 200 (after basic-auth challenge)
```

## Persistence test

```bash
# From the ttyd shell:
hermes setup   # walk through first-time config, confirm /opt/data is used

# Kill the pod:
kubectl -n friend-cyprien_iov delete pod -l app=ttyd

# Wait for respawn, re-open ttyd at https://cyprien_iov.hermes.caron.fun/
# hermes config is still in /opt/data — PVC persisted the data.
```

## Gotchas

1. **`sudo -S` doesn't work in this SSH shell** — use the kubeconfig at `/etc/rancher/k3s/k3s.yaml` directly (group `admin`, mode `0640`).
2. **Recreate strategy** — PVC is RWO (`local-path`); the Deployment uses `strategy: Recreate` so the old pod releases the volume before the new one binds.
3. **No credential rotation** — test environment, explicitly accepted.
4. **No TLS on ttyd port 7681** — TLS termination is at Traefik. All traffic to ttyd is in-cluster.
5. **Image push required** — `hermes-friends/ttyd:latest` must exist in the k3s containerd store. Load it via: `sudo k3s ctr images import ttyd.tar` or use a local registry.
6. **Single-node k3s** — no scheduling constraints. PVCs and pods always land on the same node.
