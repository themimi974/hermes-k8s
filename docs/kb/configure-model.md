# How to Configure a Model

## Via Dashboard (recommended)

1. Go to `https://dashboard.hermiz.duckdns.org/models`
2. Click **+ Add Model**
3. Fill in:

| Field | Example | Notes |
|-------|---------|-------|
| Name | `mimo-v2.5` | Display name, used in budget groups |
| Model ID | `mimo-v2.5` | Actual model name sent to the API |
| API Type | `openai` | `openai` or `anthropic` |
| API Key | `tp-sk...` | Your provider's API key |
| API Base | `https://token-plan-sgp.xiaomimimo.com/v1` | Provider's endpoint |
| Context Length | `1000000` | Max context window |
| Max Tokens | `128000` | Max output tokens |

4. Click **Save**

The model is auto-synced to LiteLLM. No restart needed.

## What Happens Under the Hood

```
Dashboard saves to DB → generate_config() builds litellm_config.yaml
  → kubectl patches ConfigMap litellm-config in litellm namespace
  → kubectl rollout restart deployment litellm
  → LiteLLM picks up new config on startup
```

The generated config looks like:

```yaml
model_list:
  - model_name: mimo-v2.5
    litellm_params:
      model: openai/mimo-v2.5    # openai/ prefix auto-added
      api_key: tp-sk...
      api_base: https://token-plan-sgp.xiaomimimo.com/v1
  model_info:
    context_length: 1000000
    max_tokens: 128000

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL

litellm_settings:
  drop_params: true
```

## API Type Prefixes

| API Type | LiteLLM Prefix | Example |
|----------|---------------|---------|
| `openai` | `openai/` | `openai/mimo-v2.5` |
| `anthropic` | `anthropic/` | `anthropic/claude-3-opus` |

## Testing a Model

From the dashboard Models page, click **🧪 Test** on any model card.

Or from inside a friend pod:
```bash
curl -s -X POST \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  -H "Content-Type: application/json" \
  http://litellm.litellm.svc.cluster.local:4000/v1/chat/completions \
  -d '{"model":"mimo-v2.5","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```

## File Locations

| What | Where |
|------|-------|
| Model DB records | PostgreSQL `hermes_dashboard` → `models` table |
| LiteLLM config | k8s ConfigMap `litellm-config` in `litellm` namespace |
| LiteLLM logs | `kubectl logs -n litellm deployment/litellm` |
| Dashboard API source | `/opt/hermes-k8s/dashboard/api/` |
| Config generator | `/opt/hermes-k8s/dashboard/api/services/litellm_config.py` |
