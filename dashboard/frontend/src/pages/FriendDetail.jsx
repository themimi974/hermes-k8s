import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useConfig } from '../hooks/useConfig'

const API_BASE = '/api'

function StatusBadge({ status }) {
  const normalized = status ? status.charAt(0).toUpperCase() + status.slice(1) : 'Unknown'
  const colors = {
    Running: 'bg-green-500',
    Error: 'bg-red-500',
    Stopped: 'bg-gray-500',
    Unknown: 'bg-yellow-500'
  }
  return (
    <span className={`inline-block px-3 py-1 rounded-full text-sm font-medium text-white ${colors[normalized] || colors.Unknown}`}>
      {normalized}
    </span>
  )
}

function formatTokens(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toString()
}

function FriendDetail() {
  const { name } = useParams()
  const navigate = useNavigate()
  const { domain } = useConfig()
  const [friend, setFriend] = useState(null)
  const [snapshots, setSnapshots] = useState([])
  const [groups, setGroups] = useState([])          // all available groups
  const [assignedGroups, setAssignedGroups] = useState(null)  // friend's groups + merged
  const [usage, setUsage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [usagePeriod, setUsagePeriod] = useState('24h')

  // Resource overrides
  const [resources, setResources] = useState({
    cpu_request: '', cpu_limit: '',
    memory_request: '', memory_limit: '',
    storage_size: '',
  })
  const [resourceLoading, setResourceLoading] = useState(false)

  const fetchFriend = async () => {
    try {
      const res = await fetch(`${API_BASE}/friends/${name}`, { credentials: 'include' })
      if (!res.ok) throw new Error('Friend not found')
      setFriend(await res.json())
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchSnapshots = async () => {
    try {
      const res = await fetch(`${API_BASE}/friends/${name}/snapshots`, { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        setSnapshots(Array.isArray(data) ? data : (data.snapshots || []))
      }
    } catch (e) { console.error('Failed to fetch snapshots:', e) }
  }

  const fetchAllGroups = async () => {
    try {
      const res = await fetch(`${API_BASE}/budget-groups`)
      if (res.ok) setGroups(await res.json())
    } catch (e) { console.error('Failed to fetch groups:', e) }
  }

  const fetchAssignedGroups = async () => {
    try {
      const res = await fetch(`${API_BASE}/friends/${name}/groups`)
      if (res.ok) {
        const data = await res.json()
        setAssignedGroups(data)
        // Init resource overrides from friend data
        if (friend) {
          setResources({
            cpu_request: friend.cpu_request || '',
            cpu_limit: friend.cpu_limit || '',
            memory_request: friend.memory_request || '',
            memory_limit: friend.memory_limit || '',
            storage_size: friend.storage_size || '',
          })
        }
      }
    } catch (e) { console.error('Failed to fetch assigned groups:', e) }
  }

  const fetchUsage = async () => {
    try {
      const res = await fetch(`${API_BASE}/usage/friends/${name}?period=${usagePeriod}`)
      if (res.ok) setUsage(await res.json())
    } catch (e) { console.error('Failed to fetch usage:', e) }
  }

  useEffect(() => {
    fetchFriend()
    fetchSnapshots()
    fetchAllGroups()
  }, [name])

  useEffect(() => {
    if (friend) {
      fetchAssignedGroups()
      fetchUsage()
    }
  }, [friend?.name, usagePeriod])

  // ── Group assignment ──────────────────────────────────────────

  const handleToggleGroup = async (groupId, assigned) => {
    setActionLoading(true)
    try {
      const method = assigned ? 'DELETE' : 'POST'
      const url = assigned
        ? `${API_BASE}/friends/${name}/groups/${groupId}`
        : `${API_BASE}/friends/${name}/groups/${groupId}`
      await fetch(url, { method })
      await fetchAssignedGroups()
      fetchFriend()
    } catch (e) {
      alert(`Error: ${e.message}`)
    } finally {
      setActionLoading(false)
    }
  }

  // ── Resource overrides ────────────────────────────────────────

  const handleSaveResources = async () => {
    setResourceLoading(true)
    try {
      const body = {}
      for (const [k, v] of Object.entries(resources)) {
        body[k] = v === '' ? null : v
      }
      await fetch(`${API_BASE}/friends/${name}/resources`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      fetchFriend()
      alert('Resources updated!')
    } catch (e) {
      alert(`Error: ${e.message}`)
    } finally {
      setResourceLoading(false)
    }
  }

  // ── Snapshot actions ──────────────────────────────────────────

  const handleSave = async () => {
    setActionLoading(true)
    try {
      const res = await fetch(`${API_BASE}/friends/${name}/save`, { method: 'POST', credentials: 'include' })
      if (!res.ok) throw new Error('Failed to save')
      await fetchSnapshots()
      alert('Snapshot saved!')
    } catch (e) { alert(`Error: ${e.message}`) }
    finally { setActionLoading(false) }
  }

  const handleRestore = async (snapshotKey) => {
    if (!confirm('Restore this snapshot?')) return
    setActionLoading(true)
    try {
      const url = snapshotKey
        ? `${API_BASE}/friends/${name}/restore?snapshot_key=${encodeURIComponent(snapshotKey)}`
        : `${API_BASE}/friends/${name}/restore`
      const res = await fetch(url, { method: 'POST', credentials: 'include' })
      if (!res.ok) throw new Error('Failed to restore')
      fetchFriend()
      alert('Restored!')
    } catch (e) { alert(`Error: ${e.message}`) }
    finally { setActionLoading(false) }
  }

  const handleDelete = async () => {
    if (!confirm(`Delete ${name}? This cannot be undone.`)) return
    setActionLoading(true)
    try {
      const res = await fetch(`${API_BASE}/friends/${name}`, { method: 'DELETE', credentials: 'include' })
      if (!res.ok) throw new Error('Failed to delete')
      navigate('/')
    } catch (e) { alert(`Error: ${e.message}`) }
    finally { setActionLoading(false) }
  }

  // ── Render ────────────────────────────────────────────────────

  if (loading) {
    return <div className="flex items-center justify-center py-20"><div className="text-xl text-gray-400">Loading...</div></div>
  }

  if (error) {
    return (
      <div className="bg-red-900/50 border border-red-500 text-red-200 px-6 py-4 rounded-lg">
        <h3 className="font-bold mb-2">Error</h3>
        <p>{error}</p>
        <Link to="/" className="mt-3 inline-block text-blue-400 hover:text-blue-300">← Back</Link>
      </div>
    )
  }

  const assignedGroupIds = assignedGroups?.groups?.map(g => g.id) || []
  const merged = assignedGroups?.merged

  return (
    <div className="max-w-5xl mx-auto">
      <Link to="/" className="text-blue-400 hover:text-blue-300 mb-6 inline-block">← Back to Dashboard</Link>

      {/* ── Header ──────────────────────────────────────── */}
      <div className="bg-gray-800 rounded-xl shadow-xl border border-gray-700 p-8 mb-6">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">{friend.name}</h1>
            <StatusBadge status={friend.status} />
          </div>
          <a href={`https://${friend.name}.${domain}`} target="_blank" rel="noopener noreferrer"
             className="text-blue-400 hover:text-blue-300 underline">
            {friend.name}.{domain} ↗
          </a>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Pods</div>
            <div className="text-xl font-semibold font-mono">{friend.ready_pods}/{friend.pods}</div>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">PVC</div>
            <div className="text-xl font-semibold">{friend.pvc_size}</div>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Namespace</div>
            <div className="text-sm font-mono">{friend.namespace}</div>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">LiteLLM Key</div>
            <div className="text-sm font-mono">{friend.litellm_key || 'None'}</div>
          </div>
        </div>

        <div className="flex gap-3">
          <button onClick={handleSave} disabled={actionLoading}
                  className="bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white px-5 py-2 rounded-lg text-sm font-medium">
            💾 Save Snapshot
          </button>
          <button onClick={() => handleRestore()} disabled={actionLoading}
                  className="bg-yellow-600 hover:bg-yellow-700 disabled:bg-gray-600 text-white px-5 py-2 rounded-lg text-sm font-medium">
            ↩️ Restore Latest
          </button>
          <button onClick={handleDelete} disabled={actionLoading}
                  className="bg-red-600 hover:bg-red-700 disabled:bg-gray-600 text-white px-5 py-2 rounded-lg text-sm font-medium">
            🗑️ Delete
          </button>
        </div>
      </div>

      {/* ── Budget Groups ───────────────────────────────── */}
      <div className="bg-gray-800 rounded-xl shadow-xl border border-gray-700 p-6 mb-6">
        <h2 className="text-xl font-bold text-white mb-4">Budget Groups</h2>
        <p className="text-gray-400 text-sm mb-4">
          Assign this friend to one or more budget groups. Their effective models and limits are merged across all assigned groups.
        </p>

        {groups.length === 0 ? (
          <p className="text-gray-500 text-sm">
            No budget groups exist. <a href="/budget-groups" className="text-blue-400 hover:underline">Create one</a>.
          </p>
        ) : (
          <div className="space-y-2">
            {groups.map(group => {
              const isAssigned = assignedGroupIds.includes(group.id)
              return (
                <div key={group.id}
                     className={`flex items-center justify-between p-3 rounded-lg border ${
                       isAssigned ? 'bg-blue-900/30 border-blue-600' : 'bg-gray-700 border-gray-600'
                     }`}>
                  <div className="flex-1">
                    <span className="text-white font-medium">{group.name}</span>
                    {group.description && (
                      <span className="text-gray-400 text-sm ml-2">— {group.description}</span>
                    )}
                    <div className="flex flex-wrap gap-1 mt-1">
                      {(group.models || []).map(m => (
                        <span key={m} className="bg-gray-600 text-gray-300 text-xs px-2 py-0.5 rounded">{m}</span>
                      ))}
                    </div>
                  </div>
                  <button onClick={() => handleToggleGroup(group.id, isAssigned)}
                          disabled={actionLoading}
                          className={`ml-4 px-3 py-1 rounded text-sm font-medium ${
                            isAssigned
                              ? 'bg-red-600 hover:bg-red-700 text-white'
                              : 'bg-blue-600 hover:bg-blue-700 text-white'
                          }`}>
                    {isAssigned ? 'Remove' : 'Add'}
                  </button>
                </div>
              )
            })}
          </div>
        )}

        {/* Merged settings display */}
        {merged && assignedGroups?.groups?.length > 0 && (
          <div className="mt-4 p-4 bg-gray-700 rounded-lg border border-gray-600">
            <h3 className="text-sm font-semibold text-gray-300 mb-2">
              Effective Settings (merged from {assignedGroups.groups.length} group{assignedGroups.groups.length > 1 ? 's' : ''})
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div>
                <span className="text-gray-400">Models:</span>
                <div className="text-white font-medium">{merged.models?.length || 0} models</div>
              </div>
              <div>
                <span className="text-gray-400">Budget:</span>
                <div className="text-white font-medium">${merged.max_budget} / {merged.budget_duration}</div>
              </div>
              <div>
                <span className="text-gray-400">TPM / RPM:</span>
                <div className="text-white font-medium">{merged.tpm_limit?.toLocaleString()} / {merged.rpm_limit?.toLocaleString()}</div>
              </div>
              <div>
                <span className="text-gray-400">Max Parallel:</span>
                <div className="text-white font-medium">{merged.max_parallel}</div>
              </div>
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
              {(merged.models || []).map(m => (
                <span key={m} className="bg-blue-900/50 text-blue-300 text-xs px-2 py-0.5 rounded">{m}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Resource Overrides ──────────────────────────── */}
      <div className="bg-gray-800 rounded-xl shadow-xl border border-gray-700 p-6 mb-6">
        <h2 className="text-xl font-bold text-white mb-2">Resource Overrides</h2>
        <p className="text-gray-400 text-sm mb-4">
          Override CPU, memory, and storage for this friend's pod. Leave empty to use defaults.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            { key: 'cpu_request', label: 'CPU Request', placeholder: '250m' },
            { key: 'cpu_limit', label: 'CPU Limit', placeholder: '1' },
            { key: 'memory_request', label: 'Mem Request', placeholder: '256Mi' },
            { key: 'memory_limit', label: 'Mem Limit', placeholder: '512Mi' },
            { key: 'storage_size', label: 'Storage', placeholder: '2Gi' },
          ].map(field => (
            <div key={field.key}>
              <label className="block text-sm text-gray-300 mb-1">{field.label}</label>
              <input
                type="text"
                value={resources[field.key]}
                onChange={(e) => setResources({ ...resources, [field.key]: e.target.value })}
                placeholder={field.placeholder}
                className="w-full bg-gray-700 text-white rounded px-3 py-2 border border-gray-600 text-sm"
              />
            </div>
          ))}
        </div>
        <button onClick={handleSaveResources} disabled={resourceLoading}
                className="mt-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm font-medium">
          {resourceLoading ? 'Saving...' : 'Save Resources'}
        </button>
      </div>

      {/* ── Usage by Model ──────────────────────────────── */}
      <div className="bg-gray-800 rounded-xl shadow-xl border border-gray-700 p-6 mb-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-white">Usage</h2>
          <select value={usagePeriod} onChange={(e) => setUsagePeriod(e.target.value)}
                  className="bg-gray-700 text-white rounded px-3 py-1 border border-gray-600 text-sm">
            <option value="1h">1 hour</option>
            <option value="6h">6 hours</option>
            <option value="24h">24 hours</option>
            <option value="7d">7 days</option>
            <option value="30d">30 days</option>
          </select>
        </div>

        {usage ? (
          <>
            {usage.note && (
              <div className="bg-yellow-900 border border-yellow-700 text-yellow-200 px-3 py-2 rounded text-sm mb-3">
                {usage.note}
              </div>
            )}

            {/* Summary */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="bg-gray-700 rounded-lg p-3 text-center">
                <div className="text-gray-400 text-xs">Requests</div>
                <div className="text-white text-xl font-bold">{usage.total?.requests?.toLocaleString() || 0}</div>
              </div>
              <div className="bg-gray-700 rounded-lg p-3 text-center">
                <div className="text-gray-400 text-xs">Tokens</div>
                <div className="text-white text-xl font-bold">{formatTokens(usage.total?.tokens || 0)}</div>
              </div>
              <div className="bg-gray-700 rounded-lg p-3 text-center">
                <div className="text-gray-400 text-xs">Cost</div>
                <div className="text-green-400 text-xl font-bold">${(usage.total?.cost || 0).toFixed(4)}</div>
              </div>
            </div>

            {/* Per-model breakdown */}
            {usage.by_model?.length > 0 ? (
              <div className="bg-gray-700 rounded-lg overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-600">
                      <th className="text-left text-xs text-gray-400 px-4 py-2">Model</th>
                      <th className="text-right text-xs text-gray-400 px-4 py-2">Requests</th>
                      <th className="text-right text-xs text-gray-400 px-4 py-2">Tokens</th>
                      <th className="text-right text-xs text-gray-400 px-4 py-2">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.by_model.map(m => (
                      <tr key={m.model} className="border-b border-gray-600 last:border-0">
                        <td className="text-white px-4 py-2 text-sm font-medium">{m.model}</td>
                        <td className="text-gray-300 px-4 py-2 text-sm text-right">{m.requests.toLocaleString()}</td>
                        <td className="text-gray-300 px-4 py-2 text-sm text-right">{formatTokens(m.tokens)}</td>
                        <td className="text-green-400 px-4 py-2 text-sm text-right">${m.cost.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center text-gray-400 py-6">
                No usage data for this period.
              </div>
            )}
          </>
        ) : (
          <div className="text-center text-gray-400 py-6">Loading usage...</div>
        )}
      </div>

      {/* ── Snapshots ───────────────────────────────────── */}
      <div className="bg-gray-800 rounded-xl shadow-xl border border-gray-700 p-6">
        <h2 className="text-xl font-bold text-white mb-4">State Snapshots</h2>
        {snapshots.length === 0 ? (
          <p className="text-gray-400">No snapshots yet</p>
        ) : (
          <div className="space-y-2">
            {snapshots.map(snap => (
              <div key={snap.key} className="bg-gray-700 rounded-lg p-3 flex items-center justify-between">
                <div>
                  <div className="font-medium text-white text-sm">{snap.key}</div>
                  <div className="text-xs text-gray-400">{new Date(snap.last_modified).toLocaleString()}</div>
                </div>
                <button onClick={() => handleRestore(snap.key)} disabled={actionLoading}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm">
                  Restore
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default FriendDetail
