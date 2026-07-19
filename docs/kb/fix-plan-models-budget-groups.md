# Fix Plan: Dashboard Model & Budget Group Management

## Issues Found

### 1. Model Enable/Disable — No Toggle on Card
The Models page shows an "Enabled" badge but has NO toggle button.
Users must click Edit → toggle checkbox → Save to enable/disable.
This is clunky and non-obvious.

### 2. Budget Groups — Model Selector Shows Nothing if No Enabled Models
`fetchModels()` filters to `m.enabled === true` only. If all models are
disabled, the checkbox list is empty with just a link to "/models".

### 3. Friend Stuck with 1 Model — Config Only Sets Default
`_build_hermes_config()` generates:
```yaml
model:
  default: mimo-v2.5
```
This tells Hermes to use ONE model. But the LiteLLM key may have access
to multiple models. The friend should be able to switch models.

### 4. No Way to See Which Friends Use Which Models
No visibility into model usage per friend from the dashboard.

---

## Plan

### Fix 1: Add Enable/Disable Toggle to Model Card

**File:** `dashboard/frontend/src/pages/Models.jsx`

Add a toggle button next to the Edit/Delete buttons:
```jsx
<button onClick={() => handleToggle(model)}>
  {model.enabled ? '🟢 Enabled' : '🔴 Disabled'}
</button>
```

Add `handleToggle` function:
```jsx
const handleToggle = async (model) => {
  await fetch(`${API}/models/${model.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: !model.enabled }),
  })
  fetchModels()
}
```

This toggles enable/disable with one click, no form needed.

### Fix 2: Budget Group Model Selector — Show All Models

**File:** `dashboard/frontend/src/pages/BudgetGroups.jsx`

Change `fetchModels` to show ALL models (enabled + disabled) with a
visual indicator:
```jsx
const fetchModels = async () => {
  const res = await fetch(`${API}/models/`)
  const data = await res.json()
  setAvailableModels(Array.isArray(data) ? data : [])  // no filter
}
```

In the checkbox list, show disabled models with strikethrough:
```jsx
<span className={m.enabled ? '' : 'line-through opacity-50'}>
  {m.name}
</span>
```

### Fix 3: Hermes Config — Support Multiple Models

**File:** `dashboard/api/services/k8s.py`

Change `_build_hermes_config` to list all available models:
```yaml
model:
  default: mimo-v2.5
  models:
    - name: mimo-v2.5
      provider: custom
      base_url: http://litellm.litellm.svc.cluster.local:4000/v1
      api_key: sk-xxx
    - name: minimax-m3
      provider: custom
      base_url: http://litellm.litellm.svc.cluster.local:4000/v1
      api_key: sk-xxx
```

Actually, Hermes config doesn't support a `models` list like this.
The correct approach is:

**Option A:** Keep single default model, but let user change it via `hermes setup`
**Option B:** Use Hermes's model selection — friend runs `hermes model` to pick

**Recommended:** Option A + document how to switch models.
The default model comes from the first model in the budget group.
Friend can run `hermes setup` to change it.

### Fix 4: Show Assigned Models on Friend Detail

**File:** `dashboard/frontend/src/pages/FriendDetail.jsx`

Add a section showing:
- Budget group(s) assigned
- Models available (from merged groups)
- Current default model

---

## Files to Change

| File | Change |
|------|--------|
| `dashboard/frontend/src/pages/Models.jsx` | Add enable/disable toggle button |
| `dashboard/frontend/src/pages/BudgetGroups.jsx` | Show all models, not just enabled |
| `dashboard/frontend/src/pages/FriendDetail.jsx` | Show assigned models |
| `dashboard/api/services/k8s.py` | Fix `_build_hermes_config` default model logic |

## Verification

1. Models page: click toggle → model enabled/disabled instantly
2. Budget Groups: create group with 2+ models → both appear in checkbox
3. Assign group to friend → friend pod gets correct default model
4. Friend can run `hermes model` to see available models
