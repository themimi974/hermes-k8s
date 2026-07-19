import { useState, useEffect } from 'react'

const API = '/api'

function ModelCard({ model, onEdit, onDelete, onTest, onToggle }) {
  const [testing, setTesting] = useState(null)

  const handleTest = async () => {
    setTesting('running')
    try {
      const resp = await fetch(`${API}/models/${model.id}/test`, { method: 'POST' })
      const result = await resp.json()
      setTesting(result.success ? 'success' : 'failed')
      setTimeout(() => setTesting(null), 3000)
    } catch {
      setTesting('failed')
      setTimeout(() => setTesting(null), 3000)
    }
  }

  return (
    <div className={`bg-gray-800 rounded-xl shadow-xl border p-6 transition-colors ${model.enabled ? 'border-gray-700 hover:border-blue-500' : 'border-gray-600 opacity-60'}`}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-xl font-bold text-white">{model.name}</h3>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${model.enabled ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}`}>
              {model.enabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>
          <p className="text-gray-400 font-mono text-sm mt-1">{model.model_id}</p>
        </div>
        <span className={`px-2 py-1 rounded text-xs font-medium ${model.api_type === 'anthropic' ? 'bg-orange-900 text-orange-300' : 'bg-blue-900 text-blue-300'}`}>
          {model.api_type}
        </span>
      </div>

      <div className="space-y-2 text-sm text-gray-300 mb-4">
        {model.api_base && (
          <div className="flex items-center">
            <span className="text-gray-500 w-24">Endpoint:</span>
            <span className="font-mono text-xs truncate">{model.api_base}</span>
          </div>
        )}
        <div className="flex items-center">
          <span className="text-gray-500 w-24">API Key:</span>
          <span className="font-mono text-xs">{model.api_key || '(from env)'}</span>
        </div>
        <div className="flex items-center">
          <span className="text-gray-500 w-24">Context:</span>
          <span>{model.context_length.toLocaleString()} tokens</span>
        </div>
        <div className="flex items-center">
          <span className="text-gray-500 w-24">Max output:</span>
          <span>{model.max_tokens.toLocaleString()} tokens</span>
        </div>
      </div>

      <div className="flex space-x-2 pt-4 border-t border-gray-700">
        <button
          onClick={handleTest}
          disabled={testing === 'running' || !model.enabled}
          className="flex-1 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {testing === 'running' ? '⏳ Testing...' : testing === 'success' ? '✅ OK' : testing === 'failed' ? '❌ Failed' : '🧪 Test'}
        </button>
        <button
          onClick={() => onEdit(model)}
          className="flex-1 bg-yellow-600 hover:bg-yellow-700 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          ✏️ Edit
        </button>
        <button
          onClick={() => onDelete(model)}
          className="flex-1 bg-red-600 hover:bg-red-700 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          🗑️ Delete
        </button>
        <button
          onClick={() => onToggle(model)}
          className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
            model.enabled
              ? 'bg-green-600 hover:bg-green-700 text-white'
              : 'bg-gray-600 hover:bg-gray-500 text-gray-300'
          }`}
        >
          {model.enabled ? '🟢 On' : '🔴 Off'}
        </button>
      </div>
    </div>
  )
}

function ModelForm({ model, onClose, onSave }) {
  const [form, setForm] = useState({
    name: '',
    model_id: '',
    api_type: 'openai',
    api_key: '',
    api_base: '',
    context_length: 128000,
    max_tokens: 4096,
    enabled: true,
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (model) {
      setForm({
        name: model.name,
        model_id: model.model_id,
        api_type: model.api_type,
        api_key: model.api_key || '',
        api_base: model.api_base || '',
        context_length: model.context_length,
        max_tokens: model.max_tokens,
        enabled: model.enabled,
      })
    }
  }, [model])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const url = model ? `${API}/models/${model.id}` : `${API}/models/`
      const resp = await fetch(url, {
        method: model ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!resp.ok) {
        const err = await resp.json()
        throw new Error(err.detail || 'Failed to save model')
      }
      onSave()
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  const set = (k, v) => setForm(prev => ({ ...prev, [k]: v }))

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-gray-800 rounded-xl shadow-2xl border border-gray-700 p-8 w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-2xl font-bold text-white mb-6">{model ? 'Edit Model' : 'Add Model'}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-300 text-sm font-medium mb-1">Name *</label>
            <input type="text" required value={form.name} onChange={e => set('name', e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
              placeholder="MiniMax M3" />
          </div>

          <div>
            <label className="block text-gray-300 text-sm font-medium mb-1">Model ID *</label>
            <input type="text" required value={form.model_id} onChange={e => set('model_id', e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white font-mono focus:border-blue-500 focus:outline-none"
              placeholder="minimaxai/minimax-m3" />
            <p className="text-gray-500 text-xs mt-1">Provider's model identifier (e.g. gpt-4o, anthropic/claude-3-sonnet)</p>
          </div>

          <div>
            <label className="block text-gray-300 text-sm font-medium mb-1">API Type</label>
            <select value={form.api_type} onChange={e => set('api_type', e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none">
              <option value="openai">OpenAI-compatible</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </div>

          <div>
            <label className="block text-gray-300 text-sm font-medium mb-1">API Base URL</label>
            <input type="text" value={form.api_base} onChange={e => set('api_base', e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white font-mono focus:border-blue-500 focus:outline-none"
              placeholder="https://api.minimax.chat/v1" />
            <p className="text-gray-500 text-xs mt-1">Leave empty for default provider URL</p>
          </div>

          <div>
            <label className="block text-gray-300 text-sm font-medium mb-1">API Key</label>
            <input type="password" value={form.api_key} onChange={e => set('api_key', e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white font-mono focus:border-blue-500 focus:outline-none"
              placeholder="sk-..." />
            <p className="text-gray-500 text-xs mt-1">Leave empty to reference from environment variable</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 text-sm font-medium mb-1">Context Size</label>
              <input type="number" value={form.context_length} onChange={e => set('context_length', parseInt(e.target.value) || 0)}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none" />
            </div>
            <div>
              <label className="block text-gray-300 text-sm font-medium mb-1">Max Output Tokens</label>
              <input type="number" value={form.max_tokens} onChange={e => set('max_tokens', parseInt(e.target.value) || 0)}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:border-blue-500 focus:outline-none" />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input type="checkbox" checked={form.enabled} onChange={e => set('enabled', e.target.checked)}
              className="rounded bg-gray-700 border-gray-600" />
            <label className="text-gray-300 text-sm">Enabled</label>
          </div>

          <div className="flex space-x-3 pt-4">
            <button type="button" onClick={onClose}
              className="flex-1 bg-gray-600 hover:bg-gray-500 text-white px-4 py-2 rounded-lg font-medium transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white px-4 py-2 rounded-lg font-medium transition-colors">
              {saving ? 'Saving...' : model ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Models() {
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editModel, setEditModel] = useState(null)

  const fetchModels = async () => {
    try {
      const resp = await fetch(`${API}/models/`)
      const data = await resp.json()
      setModels(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error('Failed to fetch models:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchModels() }, [])

  const handleDelete = async (model) => {
    if (!confirm(`Delete model "${model.name}"? This will remove it from LiteLLM.`)) return
    try {
      await fetch(`${API}/models/${model.id}`, { method: 'DELETE' })
      await fetchModels()
    } catch (err) {
      alert(`Error: ${err.message}`)
    }
  }

  const handleToggle = async (model) => {
    try {
      await fetch(`${API}/models/${model.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !model.enabled }),
      })
      await fetchModels()
    } catch (err) {
      alert(`Error: ${err.message}`)
    }
  }

  const handleSave = () => {
    setShowForm(false)
    setEditModel(null)
    fetchModels()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-xl text-gray-400">Loading models...</div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-white">Models</h2>
          <p className="text-gray-400 text-sm mt-1">Configure LLM providers and models for LiteLLM</p>
        </div>
        <button
          onClick={() => { setEditModel(null); setShowForm(true) }}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
        >
          + Add Model
        </button>
      </div>

      {models.length === 0 ? (
        <div className="text-center py-16 bg-gray-800 rounded-xl border border-gray-700">
          <p className="text-xl text-gray-400 mb-4">No models configured</p>
          <p className="text-gray-500 mb-6">Add a model to get started with LiteLLM</p>
          <button
            onClick={() => { setEditModel(null); setShowForm(true) }}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium transition-colors"
          >
            + Add your first model
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {models.map(model => (
            <ModelCard
              key={model.id}
              model={model}
              onEdit={(m) => { setEditModel(m); setShowForm(true) }}
              onDelete={handleDelete}
              onToggle={handleToggle}
            />
          ))}
        </div>
      )}

      {showForm && (
        <ModelForm
          model={editModel}
          onClose={() => { setShowForm(false); setEditModel(null) }}
          onSave={handleSave}
        />
      )}
    </div>
  )
}

export default Models
