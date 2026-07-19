# hermes-k8s Production Pitfalls

Critical issues discovered during real deployments that are NOT documented in the main hermes-k8s-deploy skill. Load this alongside hermes-k8s-deploy when deploying.

## Pitfall 1: Dashboard API __DOMAIN__ Placeholder Not Substituted

The `apply-manifest.sh` script ONLY processes ingressroute manifests. The dashboard-api deployment (`dashboard/manifests/30-dashboard-api-deployment.yaml`) has `__DOMAIN__` and `__TLS_RESOLVER__` placeholders that the script never touches.

**Symptom:** Friends get `Host(`name.__DOMAIN__`)` in their IngressRoute. Frontend shows literal `__DOMAIN__`.

**Fix (after deploying all manifests):**
```bash
kubectl set env deployment/dashboard-api -n dashboard \
  FRIEND_DOMAIN="$DOMAIN" \
  TLS_CERT_RESOLVER="hermes-tls"
kubectl rollout restart deployment/dashboard-api -n dashboard
```

**Verify:** `kubectl get deployment dashboard-api -n dashboard -o jsonpath='{.spec.template.spec.containers[0].env}' | jq .`

## Pitfall 2: TLS Secret Missing in Friend Namespaces

The `hermes-tls` secret must exist in EVERY namespace with an IngressRoute. The deploy skill creates it in `dashboard`, `auth`, `litellm` — but NOT in `friend-*` namespaces. Traefik fails to serve HTTPS without it.

**Fix for existing friends:**
```bash
CERT_FILE="/path/to/_wildcard.${DOMAIN}+3.pem"
KEY_FILE="/path/to/_wildcard.${DOMAIN}+3-key.pem"
for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep ^friend-); do
  kubectl create secret tls hermes-tls --cert="$CERT_FILE" --key="$KEY_FILE" -n "$ns" --dry-run=client -o yaml | kubectl apply -f -
done
```

**Long-term:** `create_friend()` in `k8s.py` should create the secret during provisioning.

## Pitfall 3: FRIEND_DOMAIN Defaults to Empty

`dashboard/api/config.py` has `friend_domain: str = ""`. Without the env var, hosts become `name.` (trailing dot). Always set `FRIEND_DOMAIN` in the deployment.

## Pitfall 4: get_ingressroute_host() Reads Literal from k8s

`k8s.py:get_ingressroute_host()` extracts the host from the actual IngressRoute via regex. If the IngressRoute has `__DOMAIN__`, the API returns that literal to the frontend. Fix the FRIEND_DOMAIN env var so new IngressRoutes are correct.

## Pitfall 5: Docker Conflicts with k3s

Docker iptables rules break k3s flannel. `cni0` disappears, all pods lose networking.

**Fix:** `systemctl disable --now docker docker.socket && reboot`

## Pitfall 6: Firewalld Blocks Pod Traffic (Fedora/RHEL)

Firewalld drops traffic on untrusted interfaces. k3s creates `cni0` and `flannel.1` which get blocked.

**Fix (BEFORE k3s install):**
```bash
firewall-cmd --zone=trusted --add-interface=cni0 --permanent
firewall-cmd --zone=trusted --add-interface=flannel.1 --permanent
firewall-cmd --reload
```

## Pitfall 7: Ollama Assumption in NIM-Only Deploys

Agent tries to install Ollama when user wants NVIDIA NIM only. The skill lists Ollama as a prerequisite without marking it clearly optional.

**Fix:** If user says "no ollama" or "NIM only", skip Ollama installation entirely. Update config.yaml with NVIDIA provider only.

## Pitfall 8: DuckDNS Local-Only IP Mismatch

DuckDNS update command uses `curl -s https://api.ipify.org` for public IP, but local-only deploys need the LAN IP.

**Fix:** For local-only deploys, always use the machine's LAN IP:
```bash
curl -s "https://www.duckdns.org/update?domains=<SUBDOMAIN>&token=<TOKEN>&ip=192.168.1.62"
```

## Pitfall 9: Dev Agent Code Not Pushed to Remote

Bot says "Done. All code compiles" but `git pull` shows no new commits. The dev agent made changes locally but didn't push.

**Fix:** After dev agent completes work, always verify:
```bash
git log --oneline -5
git status
```
Before attempting to deploy changes that aren't in the repo.

## Pitfall 10: /api/config Verification

After deployment, always verify the API config endpoint returns the correct domain:
```bash
curl -sk --resolve dashboard.$DOMAIN:443:<IP> https://dashboard.$DOMAIN/api/config
```
Should return `{"domain":"<your-domain>","tls_method":"selfsigned",...}` — NOT `{"domain":""}` or `{"domain":"__DOMAIN__"}`.

## Pitfall 11: Dev Agent Works in Wrong Directory

Bot says "Done" and pushes, but `git pull` shows no new commits. The dev agent made changes in its own workspace (e.g. `/home/admin/workspace/hermes-friends/`) not the actual repo (`/home/admin/hermes-k8s/`).

**Symptom:** Bot reports commit pushed, but `git log` doesn't show it. Expected files (like `merge.py`) don't exist.

**Fix:** After dev agent completes:
```bash
# Check what repo the bot actually used
git remote -v
git log --oneline -5

# If changes aren't here, ask bot to push to the correct repo
# or copy files manually from bot's workspace
```

## Pitfall 12: Database Migration Needed for Schema Changes

New features (multi-group, resource overrides) add columns/tables to PostgreSQL. `Base.metadata.create_all()` only creates NEW tables — it does NOT alter existing ones.

**Symptom:** API errors like `column friend.cpu_request does not exist` or `relation friend_budget_groups does not exist`.

**Fix:** Run migration after deploying new API image:
```bash
PG_USER=$(kubectl get secret postgres-credentials -n dashboard -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)

kubectl exec -n dashboard deployment/postgresql -- psql -U "$PG_USER" -d hermes_dashboard -c "
-- Create junction table
CREATE TABLE IF NOT EXISTS friend_budget_groups (
    friend_id INTEGER REFERENCES friends(id) ON DELETE CASCADE,
    group_id INTEGER REFERENCES budget_groups(id) ON DELETE CASCADE,
    PRIMARY KEY (friend_id, group_id)
);

-- Add per-friend resource columns
ALTER TABLE friends ADD COLUMN IF NOT EXISTS cpu_request VARCHAR(16);
ALTER TABLE friends ADD COLUMN IF NOT EXISTS cpu_limit VARCHAR(16);
ALTER TABLE friends ADD COLUMN IF NOT EXISTS memory_request VARCHAR(16);
ALTER TABLE friends ADD COLUMN IF NOT EXISTS memory_limit VARCHAR(16);
ALTER TABLE friends ADD COLUMN IF NOT EXISTS storage_size VARCHAR(16);

-- Migrate existing single-group assignments
INSERT INTO friend_budget_groups (friend_id, group_id)
SELECT id, budget_group_id FROM friends WHERE budget_group_id IS NOT NULL
ON CONFLICT DO NOTHING;
"
```

**Verify:** `kubectl exec -n dashboard deployment/postgresql -- psql -U "$PG_USER" -d hermes_dashboard -c "\dt"` should show `friend_budget_groups`.

## Pitfall 13: LiteLLM Official Image Drops Dashboard Tables (CRITICAL)

When LiteLLM uses `DATABASE_URL` and the official image (`ghcr.io/berriai/litellm`), it runs Prisma migrations on startup. If LiteLLM and the dashboard share the same database, **Prisma drops ALL non-Prisma tables** — `friends`, `budget_groups`, `models`, `friend_budget_groups` vanish.

**Symptom:** `relation "friends" does not exist` after LiteLLM restarts.

**Fix — ALWAYS use separate databases:**
```bash
PG_USER=$(kubectl get secret postgres-credentials -n dashboard -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)

kubectl exec -n dashboard deployment/postgresql -- psql -U "$PG_USER" -d hermes_dashboard \
  -c "CREATE DATABASE litellm_db;"
kubectl exec -n dashboard deployment/postgresql -- psql -U "$PG_USER" -d hermes_dashboard \
  -c "GRANT ALL PRIVILEGES ON DATABASE litellm_db TO \"$PG_USER\";"

# Set DATABASE_URL in litellm-credentials secret to point to litellm_db
```

**Rule:** `hermes_dashboard` = dashboard tables only. `litellm_db` = LiteLLM tables only. NEVER share.

**Recovery:** Dashboard-api recreates its tables via `Base.metadata.create_all()` on restart, but all friend/budget data is lost.

## Pitfall 14: dashboard-api RBAC — Cannot Patch ConfigMaps in Friend Namespaces

The dashboard-api ServiceAccount (`dashboard:default`) has no ClusterRole. It can create namespaces but **cannot patch ConfigMaps, Secrets, or Deployments** in `friend-*` namespaces. This breaks dynamic config injection silently.

**Symptom:** `Failed to update config for 'beta': (403) ... cannot patch resource "configmaps"` in logs.

**Fix — apply ClusterRole + ClusterRoleBinding BEFORE creating friends:**
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: friend-manager
rules:
- apiGroups: [""]
  resources: ["namespaces", "secrets", "configmaps", "services", "persistentvolumeclaims", "resourcequotas"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["networking.traefik.io"]
  resources: ["ingressroutes"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: friend-manager-binding
subjects:
- kind: ServiceAccount
  name: default
  namespace: dashboard
roleRef:
  kind: ClusterRole
  name: friend-manager
  apiGroup: rbac.authorization.k8s.io
```

## Pitfall 15: LiteLLM Dockerfile Missing `prisma generate`

Default LiteLLM Dockerfile installs `prisma` Python package but never runs `prisma generate`. LiteLLM crashes with `Unable to find Prisma binaries` when `DATABASE_URL` is set.

**Fix — update Dockerfile:**
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "litellm[proxy]" prisma
RUN cd /usr/local/lib/python3.11/site-packages/litellm/proxy && prisma generate
RUN apt-get remove -y curl nodejs && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
EXPOSE 4000
ENTRYPOINT ["litellm"]
```

**OOMKilled warning:** Even after removing Node.js, the image may be too heavy for 512Mi. Increase memory limit to ≥1Gi if using Prisma-enabled or official LiteLLM image.

**Alternative:** Use official LiteLLM image `ghcr.io/berriai/litellm:main-latest` with ≥2Gi memory limit.

## Pitfall 16: litellm-credentials Secret Must Exist in dashboard Namespace

The `litellm-credentials` secret is created in `litellm` namespace but dashboard-api runs in `dashboard` namespace. Kubernetes secrets are namespace-scoped — dashboard-api reads empty `LITELLM_MASTER_KEY`.

**Symptom:** `Illegal header value b'Bearer '` in dashboard-api logs.

**Fix:**
```bash
kubectl get secret litellm-credentials -n litellm -o yaml | \
  sed 's/namespace: litellm/namespace: dashboard/' | \
  kubectl apply -n dashboard -f -
kubectl rollout restart deployment/dashboard-api -n dashboard
```

## Pitfall 17: LiteLLM Model Name and Provider Prefix Must Match Config

Two related issues:

**17a: Budget group models must match `model_name` in LiteLLM's `model_list` exactly.**
Budget group `models` list may use prefixed names (`nvidia_nim/xiaomi/mimo-v2.5`) but LiteLLM's `model_list` uses short names (`mimo-v2.5`). Mismatch causes `LLM Provider NOT provided`.

**17b: Custom OpenAI-compatible APIs require `openai/` prefix.**
Any API using OpenAI-compatible endpoints (NVIDIA NIM, Xiaomi MiMo, vLLM, custom servers) needs the `openai/` provider prefix in LiteLLM. Using the provider's own name (`nvidia/`, `xiaomi/`, etc.) causes `LLM Provider NOT provided` or `There are no healthy deployments for this model` with 0 healthy endpoints.

**Correct litellm_config.yaml for ANY OpenAI-compatible API:**
```yaml
model_list:
  - model_name: my-model           # Short name used by budget groups
    litellm_params:
      model: openai/my-model       # ALWAYS use openai/ prefix for compatible APIs
      api_key: os.environ/MY_API_KEY
      api_base: https://my-api.example.com/v1
    model_info:
      context_length: 131072

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL

litellm_settings:
  drop_params: true
```

**Verify model is healthy:**
```bash
kubectl exec -n litellm deployment/litellm -- python3 -c "
import httpx, os
key = os.environ.get('LITELLM_MASTER_KEY', '')
r = httpx.get('http://localhost:4000/health', headers={'Authorization': f'Bearer {key}'}, timeout=10)
print(r.json())  # healthy_count should be > 0
"
```

**Known working models on NVIDIA NIM** (as of 2026-07):
- `deepseek-ai/deepseek-v4-pro` (131k context) — recommended
- `deepseek-ai/deepseek-v4-flash`
- `deepseek-ai/deepseek-coder-6.7b-instruct`
- `xiaomi/mimo-v2.5` does NOT exist on NVIDIA NIM (but `mimo-v2.5-pro` works via Xiaomi's own API)

## Pitfall 18: Force-Deleting Stuck Namespaces

Namespace may get stuck in `Terminating`. Dashboard API returns success but namespace lingers, preventing recreation.

**Fix:**
```bash
kubectl delete namespace friend-NAME --force --grace-period=0
# If still stuck:
kubectl get namespace friend-NAME -o json | \
  python3 -c "import sys,json; d=json.load(sys.stdin); d['spec']['finalizers']=None; json.dump(d,sys.stdout)" | \
  kubectl replace --raw "/api/v1/namespaces/friend-NAME/finalize" -f -
# Also clean DB:
PG_USER=$(kubectl get secret postgres-credentials -n dashboard -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)
kubectl exec -n dashboard deployment/postgresql -- psql -U "$PG_USER" -d hermes_dashboard \
  -c "DELETE FROM friends WHERE name='NAME';"
```

## Pitfall 19: hermes-config ConfigMap Mount Must Use subPath (CRITICAL)

The hermes-config ConfigMap contains `config.yaml`. If mounted as a volume over `/root/.hermes`, the **entire directory becomes read-only** — Hermes cannot create `cron/`, `skills/`, `sessions/`, `memories/`, `hooks/`, etc.

**Symptom:** Friend pod starts but `hermes` command crashes immediately with `OSError: [Errno 30] Read-only file system: '/root/.hermes/cron'`.

**Wrong mount (breaks everything):**
```python
# BAD — replaces entire directory with read-only ConfigMap
client.V1VolumeMount(
    name="hermes-config",
    mount_path="/root/.hermes",
    read_only=True,
)
```

**Correct mount (only the file):**
```python
# GOOD — mounts only config.yaml, directory stays writable
client.V1VolumeMount(
    name="hermes-config",
    mount_path="/root/.hermes/config.yaml",
    sub_path="config.yaml",
    read_only=True,
)
```

**Why:** Kubernetes ConfigMap volume mounts replace the entire target directory. Using `subPath` mounts a single key from the ConfigMap as a file, leaving the parent directory writable.

**Verify after deploy:**
```bash
kubectl get deployment ttyd -n friend-NAME -o json | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  [print(f'{m[\"name\"]} -> {m[\"mountPath\"]} subPath={m.get(\"subPath\",\"MISSING\")}') \
   for m in d['spec']['template']['spec']['containers'][0]['volumeMounts'] \
   if 'hermes' in m['name']]"
# Should show: hermes-config -> /root/.hermes/config.yaml subPath=config.yaml
```

## Pitfall 20: In-Memory Code Patches Don't Persist Across Restarts

Patching files inside a running container (e.g. `kubectl exec ... -- sed -i ...`) only affects the current pod. When the pod restarts or is rescheduled, the original image content is restored.

**Symptom:** You patch `k8s.py` inside the dashboard-api pod, test it, it works — then the next friend creation uses the old code.

**Fix:** Always rebuild the image, import to k3s, and restart:
```bash
podman build -t localhost/hermes-dashboard-api:latest -f dashboard/api/Dockerfile dashboard/api/
podman save localhost/hermes-dashboard-api:latest | k3s ctr images import -
kubectl rollout restart deployment/dashboard-api -n dashboard
```

## Pitfall 21: Friend Virtual Keys Stale After LiteLLM DB Recreation

When `litellm_db` is dropped and recreated (e.g. after Pitfall 13 recovery), all LiteLLM virtual keys are lost. But friend pods still have the old keys mounted in their ConfigMaps/Secrets. The dashboard database still has the old key strings, but LiteLLM doesn't recognize them.

**Symptom:** Friend pod runs fine, config looks correct, but API calls fail with `Authentication Error, Invalid proxy server token passed`.

**Fix:** Delete and recreate all friends after DB recreation:
```bash
# Delete friend namespaces
kubectl delete namespace friend-NAME --force --grace-period=0

# Clean DB
PG_USER=$(kubectl get secret postgres-credentials -n dashboard -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)
kubectl exec -n dashboard deployment/postgresql -- psql -U "$PG_USER" -d hermes_dashboard \
  -c "DELETE FROM friend_budget_groups; DELETE FROM friends;"

# Recreate via API
curl -sk --resolve dashboard.$DOMAIN:443:$IP https://dashboard.$DOMAIN/api/friends \
  -H "Content-Type: application/json" \
  -d '{"name":"NAME","username":"USER","password":"PASS","group_ids":[1]}'
```

**Rule:** After ANY operation that recreates `litellm_db`, ALL friends must be recreated to get fresh virtual keys.

## Pitfall 22: LiteLLM DATABASE_URL May Have Placeholder Credentials

The `litellm-credentials` secret is created with a `DATABASE_URL` that may contain placeholder values like `REPLACE_ME` for username/password. LiteLLM connects successfully (Prisma migrations run) but virtual key operations fail silently.

**Symptom:** LiteLLM starts fine, health endpoint returns 200, but creating/listing keys returns empty or authentication errors. `POST /key/generate` returns a key, but `POST /chat/completions` with that key returns `Authentication Error, Invalid proxy server token passed`.

**Fix — ensure DATABASE_URL matches actual PostgreSQL credentials:**
```bash
# Get actual credentials
PG_USER=$(kubectl get secret postgres-credentials -n dashboard -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)
PG_PASS=$(kubectl get secret postgres-credentials -n dashboard -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)

# Rebuild DATABASE_URL and update secret
DATABASE_URL="postgresql://${PG_USER}:${PG_PASS}@postgresql.dashboard.svc.cluster.local:5432/litellm_db"

kubectl create secret generic litellm-credentials -n litellm \
  --from-literal=DATABASE_URL="$DATABASE_URL" \
  --from-literal=LITELLM_MASTER_KEY="$(kubectl get secret litellm-credentials -n litellm -o jsonpath='{.data.LITELLM_MASTER_KEY}' | base64 -d)" \
  --from-literal=NVIDIA_API_KEY="$(kubectl get secret litellm-credentials -n litellm -o jsonpath='{.data.NVIDIA_API_KEY}' | base64 -d)" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/litellm -n litellm
```

**Verify keys persist across restarts:**
```bash
# Create a test key
kubectl exec -n litellm deployment/litellm -- python3 -c "
import httpx, os
key = os.environ.get('LITELLM_MASTER_KEY', '')
r = httpx.post('http://localhost:4000/key/generate',
    json={'key_name':'test','models':['mimo-v2.5-pro'],'tpm_limit':100000},
    headers={'Authorization': f'Bearer {key}'}, timeout=10)
print(f'Generated: {r.json().get(\"key\", \"\")}')
"

# Restart LiteLLM and verify key still works
kubectl rollout restart deployment/litellm -n litellm
sleep 30
# If key works after restart, DATABASE_URL is correct
```

## Pitfall 23: LiteLLM Virtual Keys Are 25 Characters with Literal `...`

LiteLLM generates virtual keys that are 25 characters long and contain literal `...` in the middle (e.g., `sk-DEF...K1oQ`). This is NOT truncation — it's the actual key format. Do not attempt to "fix" or look up the full key.

**Key format:** `sk-` prefix + 15 chars + `...` + 4 chars = 25 chars total

**Rule:** Store and use the key exactly as returned by `/key/generate`. The `...` is part of the key.

## Pitfall 24: Auto-Refresh Stale LiteLLM Keys on Group Assignment

When a budget group is assigned to a friend, the system should validate the existing LiteLLM virtual key before updating it. If the key is stale (e.g., after DB recreation), automatically create a fresh one.

**Implementation pattern (in `litellm_client.py`):**
```python
async def validate_key(key: str) -> bool:
    """Check if a virtual key exists in LiteLLM."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{LITELLM_BASE}/key/info",
            json={"key": key},
            headers=HEADERS,
        )
        return resp.status_code == 200

async def refresh_key(
    friend_name: str,
    models: list[str],
    old_key: str = None,
    **kwargs,
) -> dict:
    """Refresh a key: update if valid, create new if stale."""
    if old_key:
        if await validate_key(old_key):
            await update_virtual_key(token=old_key, models=models, **kwargs)
            return {"key": old_key, "was_refreshed": False}
        else:
            await delete_virtual_key(old_key)
    return await create_virtual_key(friend_name=friend_name, models=models, **kwargs)
```

**Integration in `friends.py` (add_group, assign_groups, remove_group):**
```python
key_data = await litellm_client.refresh_key(
    friend_name=name,
    models=merged["models"],
    old_key=friend.litellm_key,
    tpm_limit=merged["tpm_limit"],
    rpm_limit=merged["rpm_limit"],
    max_budget=merged["max_budget"],
    budget_duration=merged["budget_duration"],
)
new_key = key_data.get("key", friend.litellm_key)
was_refreshed = key_data.get("was_refreshed", False)

# Update DB if key changed
if was_refreshed and new_key != friend.litellm_key:
    record.litellm_key = new_key
    record.litellm_key_hash = key_data.get("key_hash", "")
    db.commit()
```

**Why this matters:** Without validation, stale keys cause silent failures where friend pods appear healthy but cannot make API calls. Auto-refresh on group assignment ensures keys are always valid.

## Pitfall 25: No Baked-In NVIDIA NIM Config in Friend Pod Images

The friend pod Docker image (`Dockerfile`) must NOT contain any NVIDIA NIM, LiteLLM, or provider-specific configuration. All config must be injected at runtime via ConfigMaps and Secrets.

**Why:** Different friends may have different models, API keys, and budget limits. Baking config into the image makes it impossible to have per-friend isolation.

**Correct architecture:**
1. Dashboard API creates a ConfigMap `hermes-config` per friend namespace
2. Dashboard API creates a Secret `hermes-credentials` per friend namespace (with LiteLLM virtual key)
3. Friend pod deployment mounts ConfigMap via `subPath` (see Pitfall 19)
4. Friend pod deployment mounts Secret as env vars

**Verify dynamic config is working:**
```bash
# Check ConfigMap exists and has correct content
kubectl get configmap hermes-config -n friend-NAME -o jsonpath='{.data.config\.yaml}'

# Check Secret exists
kubectl get secret hermes-credentials -n friend-NAME

# Check pod is using the mounted config
kubectl exec -n friend-NAME deployment/ttyd -- cat /root/.hermes/config.yaml
```

## Pitfall 26: Dev Agent SSH Key for Git Push

After deploying, the dev agent needs to push code changes. If pushing via HTTPS fails with "Username for 'https://github.com'", use SSH with the user's GitHub key.

**Fix:**
```bash
cd /home/admin/hermes-k8s

# Configure git to use SSH key
git config core.sshCommand "ssh -i /home/admin/github-key -o IdentitiesOnly=yes"

# Switch remote to SSH
git remote set-url origin git@github.com:themimi974/hermes-k8s.git

# Test auth
ssh -i /home/admin/github-key -o StrictHostKeyChecking=no -T git@github.com

# Push
git push origin main
```

**Note:** The SSH key must be added to the user's GitHub account (Settings → SSH keys).

## Pitfall 27: Usage Endpoint DB Connection — Hardcoded Password and Wrong DB Name

The `_get_litellm_db()` function in `dashboard/api/routers/usage.py` may have three bugs:
1. Hardcoded `***` literal instead of `settings.postgres_password`
2. Wrong database name (`litellm` instead of `litellm_db`)
3. Unquoted Prisma-created table/column names (see Pitfall 28)

**Symptom:** Usage tab shows `LiteLLM DB not ready: (psycopg2.OperationalError) ... password authentication failed for user "REPLACE_ME"`.

**Fix — update `_get_litellm_db()` in `usage.py`:**
```python
def _get_litellm_db():
    """Connect to the LiteLLM database (separate DB)."""
    url = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/litellm_db"
    )
    return create_engine(url, pool_pre_ping=True)
```

**Key points:**
- Use `settings.postgres_password` (from env var), NOT hardcoded `***`
- Database name must be `litellm_db` (the separate LiteLLM database), NOT `litellm`
- Also update `LITELLM_DB_URL` constant at module level if it exists

**Verify:**
```python
# Test connection from inside dashboard-api pod
kubectl exec -n dashboard deployment/dashboard-api -- python3 -c "
from routers.usage import _get_litellm_db
engine = _get_litellm_db()
print(f'URL: {engine.url}')
with engine.connect() as conn:
    result = conn.execute(text('SELECT 1'))
    print(f'Connection OK: {result.fetchone()}')
"
```

## Pitfall 28: LiteLLM Virtual Keys Missing key_alias Shows "unknown" in Usage

When creating LiteLLM virtual keys, the `key_alias` field must be set to the friend's name. Without it, the `LiteLLM_VerificationToken.key_alias` is NULL, and the Usage dashboard shows "unknown" for that friend because the JOIN `SpendLogs.api_key = VerificationToken.token` returns NULL alias.

**Symptom:** Usage tab shows "unknown" friend with token usage, but the actual friend name is missing.

**Fix — always set key_alias when creating keys:**
```python
payload = {
    "key_name": f"friend-{friend_name}",
    "key_alias": friend_name,  # REQUIRED for Usage tracking
    "models": models,
    ...
}
```

**Fix existing keys without key_alias:**
```bash
# Get the friend's token hash from dashboard DB
PG_USER=$(kubectl get secret postgres-credentials -n dashboard -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)
TOKEN_HASH=$(kubectl exec -n dashboard deployment/postgresql -- psql -U "$PG_USER" -d hermes_dashboard -t -A -c "SELECT litellm_key_hash FROM friends WHERE name='FRIEND_NAME';")

# Update key_alias via LiteLLM API
curl -sk https://litellm.EXAMPLE.COM/key/update \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"key\":\"$TOKEN_HASH\",\"key_alias\":\"FRIEND_NAME\"}"
```

**Note:** Old SpendLogs entries from deleted keys will permanently show as "unknown" — there's no way to retroactively resolve them since the key no longer exists in VerificationToken.

## Pitfall 29: Prisma Table/Column Names Require Quoting in PostgreSQL

Prisma creates tables with mixed-case names (e.g., `LiteLLM_SpendLogs`, `LiteLLM_VerificationToken`) using quoted identifiers. PostgreSQL stores them case-sensitively, but **unquoted SQL references are lowercased** — causing `relation "litellm_spendlogs" does not exist` errors.

**Affected tables:**
- `LiteLLM_SpendLogs` (NOT `litellm_spendlogs`)
- `LiteLLM_VerificationToken` (NOT `litellm_verificationtokens` — also note: singular, not plural)
- Any other Prisma-created tables

**Affected columns:**
- `startTime` (NOT `starttime` or `created_at`)
- `key_alias` (NOT `api_key_name`)
- Other mixed-case columns

**Symptom:** `psycopg2.errors.UndefinedTable: relation "litellm_spendlogs" does not exist` even though the table exists.

**Fix — quote ALL Prisma table and column names in SQL:**
```sql
-- WRONG (lowercased by PostgreSQL)
SELECT * FROM LiteLLM_SpendLogs WHERE created_at > NOW();

-- CORRECT (quoted preserves case)
SELECT * FROM "LiteLLM_SpendLogs" WHERE "startTime" > NOW();
```

**For JOIN queries, also prefix ambiguous columns:**
```sql
-- WRONG (ambiguous — both tables have 'spend' column)
SELECT spend FROM "LiteLLM_SpendLogs" s
LEFT JOIN "LiteLLM_VerificationToken" k ON s.api_key = k.token;

-- CORRECT (use table alias)
SELECT s.spend FROM "LiteLLM_SpendLogs" s
LEFT JOIN "LiteLLM_VerificationToken" k ON s.api_key = k.token;
```

**Complete fix for usage.py:**
```python
# Table names — ALWAYS quote
FROM "LiteLLM_SpendLogs"
JOIN "LiteLLM_VerificationToken"

# Column names — ALWAYS quote mixed-case
WHERE "startTime" > NOW()

# Ambiguous columns in JOINs — ALWAYS prefix with alias
SELECT s.spend, s.total_tokens
```

**Verify table/column names from psql:**
```bash
PG_USER=$(kubectl get secret postgres-credentials -n dashboard -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)
kubectl exec -n dashboard deployment/postgresql -- psql -U "$PG_USER" -d litellm_db -c "\dt"  # list tables
kubectl exec -n dashboard deployment/postgresql -- psql -U "$PG_USER" -d litellm_db -c "\d \"LiteLLM_SpendLogs\""  # list columns
```

## Pitfall 30: LiteLLM ENTRYPOINT Double-Invocation (CRITICAL)

`litellm/30-deployment.yaml` had `command: [litellm, --config, ...]` but the Dockerfile ENTRYPOINT is already `["litellm"]`. K8s `command` overrides ENTRYPOINT, so it becomes `litellm litellm --config ...` → crash loop.

**Symptom:** LiteLLM pod in CrashLoopBackOff, logs show "Unknown command: litellm".

**Fix:** Change `command` to `args` in `litellm/30-deployment.yaml`:
```yaml
# WRONG
command:
  - litellm
  - --config
  - /app/config/litellm_config.yaml

# CORRECT — ENTRYPOINT is ["litellm"], so use args
args:
  - --config
  - /app/config/litellm_config.yaml
```

## Pitfall 31: LiteLLM Dockerfile Missing libatomic1 (CRITICAL)

Prisma runtime requires `libatomic.so.1` at migration time. The `python:3.11-slim` base image doesn't include it. Without it, `prisma migrate deploy` fails silently and LiteLLM starts without database tables.

**Symptom:** LiteLLM starts but `litellm_db` has no tables. Usage tab shows "relation LiteLLM_SpendLogs does not exist".

**Fix:** Add `libatomic1` to Dockerfile AND keep Node.js (Prisma needs it at runtime):
```dockerfile
RUN apt-get update && apt-get install -y curl libatomic1 && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*
# ... pip install, prisma generate ...
# Do NOT remove nodejs — Prisma needs it for migrate deploy
```

**Memory warning:** Keeping Node.js increases image size. Ensure memory limit ≥ 2Gi.

## Pitfall 32: litellm_db Must Be Created Before LiteLLM Starts

LiteLLM config needs `database_url` pointing to `litellm_db`, but the database must exist FIRST. The deploy script creates PostgreSQL but not `litellm_db`.

**Fix — add to deploy.sh after PostgreSQL is running:**
```bash
kubectl exec -n dashboard deployment/postgresql -- \
  psql -U "$PG_USER" -d hermes_dashboard -c "CREATE DATABASE litellm_db;"
```

**Verify:**
```bash
kubectl exec -n dashboard deployment/postgresql -- psql -U "$PG_USER" -d litellm_db -c "\dt"
```

## Reference Files

- `references/deployment-checklist.md` — Quick-reference post-deploy verification checklist
- `references/database-migration.md` — Schema changes, migration SQL, and merge logic for multi-group feature
