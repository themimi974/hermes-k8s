import { useState, useEffect } from 'react'

const API = '/api'

export default function BudgetGroups() {
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [editGroup, setEditGroup] = useState(null)
  const [form, setForm] = useState({
    name: '',
    description: '',
    models: ['gpt-3.5-turbo'],
    tpm_limit: 100000,
    rpm_limit: 1000,
    max_parallel: 5,
    max_budget: 50.0,
    budget_duration: '30d',
  })

  const fetchGroups = async () => {
    try {
      const res = await fetch(`${API}/budget-groups`)
      const data = await res.json()
      setGroups(data)
    } catch (e) {
      console.error('Failed to fetch groups:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchGroups() }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      const url = editGroup ? `${API}/budget-groups/${editGroup.id}` : `${API}/budget-groups`
      const method = editGroup ? 'PUT' : 'POST'
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (res.ok) {
        setShowCreate(false)
        setEditGroup(null)
        setForm({ name: '', description: '', models: ['gpt-3.5-turbo'], tpm_limit: 100000, rpm_limit: 1000, max_parallel: 5, max_budget: 50.0, budget_duration: '30d' })
        fetchGroups()
      }
    } catch (e) {
      console.error('Failed to save group:', e)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this budget group? Friends will be unassigned.')) return
    try {
      await fetch(`${API}/budget-groups/${id}`, { method: 'DELETE' })
      fetchGroups()
    } catch (e) {
      console.error('Failed to delete group:', e)
    }
  }

  const startEdit = (group) => {
    setEditGroup(group)
    setForm({
      name: group.name,
      description: group.description || '',
      models: group.models || ['gpt-3.5-turbo'],
      tpm_limit: group.tpm_limit,
      rpm_limit: group.rpm_limit,
      max_parallel: group.max_parallel,
      max_budget: group.max_budget,
      budget_duration: group.budget_duration,
    })
    setShowCreate(true)
  }

  const modelOptions = ['gpt-3.5-turbo', 'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'claude-3-sonnet', 'claude-3-haiku']

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">Budget Groups</h2>
          <p className="text-gray-400 text-sm mt-1">Manage API rate limits and budgets per friend group</p>
        </div>
        <button
          onClick={() => { setShowCreate(true); setEditGroup(null) }}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium"
        >
          + New Group
        </button>
      </div>

      {loading ? (
        <div className="text-center text-gray-400 py-8">Loading...</div>
      ) : groups.length === 0 ? (
        <div className="text-center text-gray-400 py-8">No budget groups yet. Create one to get started.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {groups.map((group) => (
            <div key={group.id} className="bg-gray-800 rounded-lg p-5 border border-gray-700">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h3 className="text-lg font-semibold text-white">{group.name}</h3>
                  <p className="text-gray-400 text-sm">{group.description || 'No description'}</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => startEdit(group)} className="text-gray-400 hover:text-white text-sm">Edit</button>
                  <button onClick={() => handleDelete(group.id)} className="text-red-400 hover:text-red-300 text-sm">Delete</button>
                </div>
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between text-gray-300">
                  <span>Budget:</span>
                  <span className="font-medium">${group.max_budget} / {group.budget_duration}</span>
                </div>
                <div className="flex justify-between text-gray-300">
                  <span>TPM / RPM:</span>
                  <span className="font-medium">{group.tpm_limit.toLocaleString()} / {group.rpm_limit.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-gray-300">
                  <span>Max Parallel:</span>
                  <span className="font-medium">{group.max_parallel}</span>
                </div>
                <div className="flex justify-between text-gray-300">
                  <span>Friends:</span>
                  <span className="font-medium">{group.friend_count}</span>
                </div>
                <div className="mt-2">
                  <span className="text-gray-400 text-xs">Models:</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {(group.models || []).map((m) => (
                      <span key={m} className="bg-gray-700 text-gray-300 text-xs px-2 py-0.5 rounded">{m}</span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-md border border-gray-700">
            <h3 className="text-lg font-semibold text-white mb-4">{editGroup ? 'Edit Budget Group' : 'Create Budget Group'}</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-300 mb-1">Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-300 mb-1">Description</label>
                <input
                  type="text"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Max Budget ($)</label>
                  <input
                    type="number"
                    value={form.max_budget}
                    onChange={(e) => setForm({ ...form, max_budget: parseFloat(e.target.value) })}
                    className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Duration</label>
                  <select
                    value={form.budget_duration}
                    onChange={(e) => setForm({ ...form, budget_duration: e.target.value })}
                    className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
                  >
                    <option value="1d">Daily</option>
                    <option value="7d">Weekly</option>
                    <option value="30d">Monthly</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-1">TPM Limit</label>
                  <input
                    type="number"
                    value={form.tpm_limit}
                    onChange={(e) => setForm({ ...form, tpm_limit: parseInt(e.target.value) })}
                    className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">RPM Limit</label>
                  <input
                    type="number"
                    value={form.rpm_limit}
                    onChange={(e) => setForm({ ...form, rpm_limit: parseInt(e.target.value) })}
                    className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm text-gray-300 mb-1">Models</label>
                <div className="flex flex-wrap gap-2">
                  {modelOptions.map((m) => (
                    <label key={m} className="flex items-center gap-1 text-sm text-gray-300">
                      <input
                        type="checkbox"
                        checked={form.models.includes(m)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setForm({ ...form, models: [...form.models, m] })
                          } else {
                            setForm({ ...form, models: form.models.filter((x) => x !== m) })
                          }
                        }}
                        className="rounded"
                      />
                      {m}
                    </label>
                  ))}
                </div>
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => { setShowCreate(false); setEditGroup(null) }}
                  className="flex-1 bg-gray-700 hover:bg-gray-600 text-white py-2 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-lg"
                >
                  {editGroup ? 'Update' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
