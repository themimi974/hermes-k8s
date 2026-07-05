# HLD — Hermes Multi-Friend Platform

**Status:** live on 192.168.1.174 · 2 friends provisioned · 2026-07-05

See [architecture.svg](architecture.svg) for the precise stack diagram with real resource names.

## Purpose

A test/lab environment giving a handful of named friends isolated Hermes Agent workspaces on a single k3s node. Each friend gets a web terminal (ttyd), persistent storage, and runs `hermes setup` themselves. A central gateway at `hermes.caron.fun` lists each friend's subdomain and credentials on a single page.

**Not trying to be:** production-hardened, multi-tenant billing, shared backend, or enterprise SSO.

## Architecture Overview

```
Internet
  → Cloudflare DNS (*.hermes.caron.fun → 192.168.1.174, A record, DNS-only)
  → Traefik (k3s, cfresolver DNS-01 certs)
      ├── friend-cyprien-iov: IR + MW(basicAuth) → Service → ttyd pod + PVC
      ├── friend-abricot:     IR + MW(basicAuth) → Service → ttyd pod + PVC
      └── auth/gateway:       IR + MW(basicAuth) → Service → nginx pod (landing page)
```

## Component List

| Component | Real deployment | Notes |
|---|---|---|
| k3s | v1.36.2+k3s1, single node `host-005` on Debian Trixie | Fedora host existed and was retired over firewalld/br_netfilter/kube-router networking saga |
| Traefik | traefik-7795df7f88-l4q9p, k3s bundled | Entrypoints: web=:80, websecure=:443 |
| ttyd image | `localhost/hermes-friends/ttyd:latest` | Built with podman, imported to containerd |
| Gateway | nginx:1.27-alpine in `auth` namespace | Static HTML listing friends + creds |

## Trust & Security Model (accepted tradeoffs for test env)

| Tradeoff | Why accepted |
|---|---|
| **Root inside containers** | Friends need to install packages. Boundary is the container: no `privileged:true`, no hostPath, no socket mounts |
| **Basic Auth over bare origin** | No Cloudflare proxy — real public exposure. Accepted for this test environment |
| **No credential rotation** | Explicitly decided, not an oversight |

## Non-Goals

- No OIDC/SSO, no multi-tenant billing/quotas, no shared backend
- Every friend is fully isolated and self-configures their own LLM key

## Decisions Log

| Decision | Why |
|---|---|
| **Root over sudo** | Dockerfile has no gosu/privilege drop; ttyd runs as root so friends can `apt install` freely |
| **Per-friend namespace** (not shared) | Traefik IR + Middleware scoping needs namespace isolation; also prevents friend A from seeing friend B's pods |
| **Basic Auth** (not OIDC) | PKCE/oauth2-proxy/Keycloak was fully built and then dropped — no token exchange, confirmed by user |
| **PVC over emptyDir** | emptyDir doesn't survive pod reschedule — caused a real bug during testing |
