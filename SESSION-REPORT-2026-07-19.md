# hermes-k8s — Session Report (July 19, 2026)

## Summary

Fixed critical LiteLLM database connection issues that prevented the Usage tab from working. All changes committed and pushed to `github.com/themimi974/hermes-k8s`.

## Changes Made

### 1. LiteLLM DATABASE_URL Fix
**Problem:** `litellm-credentials` secret had placeholder `REPLACE_ME` credentials.
**Fix:** Updated secret with actual PostgreSQL credentials, both in `litellm` and `dashboard` namespaces.

### 2. Usage Endpoint Database Connection
**Problem:** `_get_litellm_db()` in `usage.py` had three bugs:
- Used hardcoded `***` literal instead of `settings.postgres_password`
- Connected to wrong database (`litellm` instead of `litellm_db`)
- Table/column names not quoted for Prisma-created mixed-case identifiers

**Fix:** Rewrote connection logic with correct credentials, database name, and quoted identifiers.

### 3. Prisma Table Name Case Sensitivity
**Problem:** Prisma creates tables with mixed-case names (`LiteLLM_SpendLogs`) using quoted identifiers. PostgreSQL stores them case-sensitively, but unquoted references are lowercased.

**Fix:** Quoted all table names:
- `"LiteLLM_SpendLogs"` (not `litellm_spendlogs`)
- `"LiteLLM_VerificationToken"` (not `litellm_verificationtokens` — also fixed pluralization)

### 4. Prisma Column Name Case Sensitivity
**Problem:** `startTime` column stored as mixed case by Prisma.

**Fix:** Quoted as `"startTime"` in all SQL queries.

### 5. Ambiguous Column References
**Problem:** `spend` and `total_tokens` columns exist in both `LiteLLM_SpendLogs` and `LiteLLM_VerificationToken` tables. JOIN queries had ambiguous references.

**Fix:** Added `s.` table alias prefix in JOIN queries.

## Commits Pushed

```
89a17d8 fix: usage endpoint - correct DB connection, table names, column names
42834d6 docs: update README and deployment skill for recent changes
9cd03de feat: auto-refresh stale LiteLLM keys on group assignment
3100691 feat: inject LiteLLM config into friend pods (no baked-in NIM)
1982f82 feat: add group selection to NewFriend + group badges on Dashboard
```

## Current System State

### Running Services
- **gateway** — auth gateway, serving `*.nainar.duckdns.org`
- **dashboard-api** — REST API, latest image with all fixes
- **dashboard-frontend** — UI, latest image
- **postgresql** — databases: `hermes_dashboard` (dashboard), `litellm_db` (LiteLLM)
- **litellm** — proxy, official image `ghcr.io/berriai/litellm:main-latest`, 2Gi memory
- **minio** — object storage

### Friend Pods
- **friend-beta** — running, group 2 (mimo-v2.5-pro) assigned, config verified
- **friend-test** — was being recreated (namespace deletion may still be pending)

### Usage Data
- 18 total requests, 26,441 tokens tracked
- 6 models: mimo-v2.5-pro, openai/mimo-v2.5-pro, deepseek-v4-pro, openai/deepseek-ai/deepseek-v4-pro, mimo-v2.5, unknown
- Friends showing as "unknown" — virtual keys lack `key_alias` field

## Known Issues (For Tomorrow)

### 1. "Unknown" Friend Names in Usage Tab
Virtual keys in LiteLLM don't have `key_alias` set, so the Usage tab shows "unknown" for all friends.

**Fix needed:** When creating virtual keys via `litellm_client.py`, include `key_alias` parameter (e.g., `friend-beta`). Then update existing keys or recreate friends.

### 2. Dashboard API Image Not Rebuilt Since `friends.py` Patch
The `friends.py` and `litellm_client.py` patches (auto-refresh stale keys) were copied to the repo but the dashboard-api image may not have been rebuilt with them.

**Action:** Rebuild and redeploy dashboard-api to include the refresh_key logic.

### 3. RBAC Manifests Not Committed
ClusterRole `friend-manager` and ClusterRoleBinding were applied directly via `kubectl` but not committed to the repo manifests.

**Action:** Create YAML file in `dashboard/manifests/` and commit.

## Architecture Reference

```
┌─────────────────────────────────────────────────────┐
│                   DNS (DuckDNS)                      │
│            nainar.duckdns.org → 192.168.1.62         │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│              Traefik (k3s Ingress)                   │
│         TLS termination (*.nainar.duckdns.org)       │
└──────┬──────────────┬──────────────┬────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼─────┐
│  gateway    │ │ dashboard │ │  litellm  │
│  :8081      │ │  :8000    │ │  :4000    │
│  (auth)     │ │  (API)    │ │  (proxy)  │
└─────────────┘ └─────┬─────┘ └─────┬─────┘
                      │              │
                      │              │
               ┌──────▼──────┐      │
               │ postgresql  │      │
               │  :5432      │      │
               │ hermes_db   │      │
               │ litellm_db  │◄─────┘
               └─────────────┘

Friend Pods (dynamic per friend):
┌─────────────────────────────────┐
│  friend-{name} namespace        │
│  ┌────────────┐ ┌────────────┐  │
│  │ ttyd       │ │ hermes     │  │
│  │ (shell)    │ │ (agent)    │  │
│  │ :7681      │ │            │  │
│  └────────────┘ └────────────┘  │
│  ConfigMap: hermes-config       │
│  Secret: hermes-credentials     │
│  IngressRoute: name.domain.com  │
└─────────────────────────────────┘
```

## Key Configuration

- **Domain:** nainar.duckdns.org
- **IP:** 192.168.1.62
- **TLS:** Self-signed via mkcert
- **Models:** openai/mimo-v2.5-pro, openai/deepseek-ai/deepseek-v4-pro
- **NVIDIA NIM:** requires `openai/` prefix (not `nvidia/`)
- **LiteLLM DB:** litellm_db (separate from hermes_dashboard)
- **Virtual keys:** 25 chars with literal `...` (e.g., `sk-DEF...K1oQ`)

## Next Steps

1. Fix "unknown" friend names by setting `key_alias` on virtual keys
2. Rebuild dashboard-api with friends.py/litellm_client.py patches
3. Commit RBAC manifests to repo
4. End-to-end test: friend pod → LiteLLM → NVIDIA NIM chat completion
5. Document litellm_db backup strategy
