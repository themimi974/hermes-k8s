import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'

const API_BASE = '/api'

function StatusBadge({ status }) {
  const colors = {
    Running: 'bg-green-500',
    Error: 'bg-red-500',
    Stopped: 'bg-gray-500',
    Unknown: 'bg-yellow-500'
  }
  
  return (
    <span className={`inline-block px-3 py-1 rounded-full text-sm font-medium text-white ${colors[status] || colors.Unknown}`}>
      {status}
    </span>
  )
}

function FriendDetail() {
  const { name } = useParams()
  const navigate = useNavigate()
  const [friend, setFriend] = useState(null)
  const [snapshots, setSnapshots] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)

  const fetchFriend = async () => {
    try {
      const response = await fetch(`${API_BASE}/friends/${name}`)
      if (!response.ok) throw new Error('Friend not found')
      const data = await response.json()
      setFriend(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchSnapshots = async () => {
    try {
      const response = await fetch(`${API_BASE}/friends/${name}/snapshots`)
      if (response.ok) {
        const data = await response.json()
        setSnapshots(data.snapshots || data)
      }
    } catch (err) {
      console.error('Failed to fetch snapshots:', err)
    }
  }

  useEffect(() => {
    fetchFriend()
    fetchSnapshots()
  }, [name])

  const handleSave = async () => {
    setActionLoading(true)
    try {
      const response = await fetch(`${API_BASE}/friends/${name}/save`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to save')
      await fetchSnapshots()
      alert('Snapshot saved successfully!')
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setActionLoading(false)
    }
  }

  const handleRestore = async (snapshotId) => {
    if (!confirm('Are you sure you want to restore this snapshot?')) return
    setActionLoading(true)
    try {
      const url = snapshotId
        ? `${API_BASE}/friends/${name}/restore?snapshot_key=${encodeURIComponent(snapshotId)}`
        : `${API_BASE}/friends/${name}/restore`
      const response = await fetch(url, { method: 'POST' })
      if (!response.ok) throw new Error('Failed to restore')
      await fetchFriend()
      alert('Restored successfully!')
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setActionLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to delete ${name}? This cannot be undone.`)) return
    setActionLoading(true)
    try {
      const response = await fetch(`${API_BASE}/friends/${name}`, {
        method: 'DELETE'
      })
      if (!response.ok) throw new Error('Failed to delete')
      navigate('/')
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-xl text-gray-400">Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-900/50 border border-red-500 text-red-200 px-6 py-4 rounded-lg">
        <h3 className="font-bold mb-2">Error</h3>
        <p>{error}</p>
        <Link to="/" className="mt-3 inline-block text-blue-400 hover:text-blue-300">
          ← Back to Dashboard
        </Link>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto">
      <Link to="/" className="text-blue-400 hover:text-blue-300 mb-6 inline-block">
        ← Back to Dashboard
      </Link>
      
      <div className="bg-gray-800 rounded-xl shadow-xl border border-gray-700 p-8">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">{friend.name}</h1>
            <StatusBadge status={friend.status} />
          </div>
          <a 
            href={`https://${friend.name}.hermes.community`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300 underline"
          >
            {friend.name}.hermes.community ↗
          </a>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Status</div>
            <div className="text-xl font-semibold">{friend.status}</div>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Uptime</div>
            <div className="text-xl font-semibold font-mono">{friend.uptime || 'N/A'}</div>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">CPU</div>
            <div className="text-xl font-semibold">{friend.cpu || 'N/A'}</div>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Memory</div>
            <div className="text-xl font-semibold">{friend.memory || 'N/A'}</div>
          </div>
        </div>

        <div className="flex space-x-4 mb-8">
          <button
            onClick={handleSave}
            disabled={actionLoading}
            className="bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white px-6 py-3 rounded-lg font-medium transition-colors"
          >
            💾 Save Snapshot
          </button>
          <button
            onClick={() => handleRestore()}
            disabled={actionLoading}
            className="bg-yellow-600 hover:bg-yellow-700 disabled:bg-gray-600 text-white px-6 py-3 rounded-lg font-medium transition-colors"
          >
            ↩️ Restore Latest
          </button>
          <button
            onClick={handleDelete}
            disabled={actionLoading}
            className="bg-red-600 hover:bg-red-700 disabled:bg-gray-600 text-white px-6 py-3 rounded-lg font-medium transition-colors"
          >
            🗑️ Delete Friend
          </button>
        </div>

        <div>
          <h2 className="text-xl font-bold text-white mb-4">State Snapshots</h2>
          {snapshots.length === 0 ? (
            <p className="text-gray-400">No snapshots yet</p>
          ) : (
            <div className="space-y-3">
              {snapshots.map(snapshot => (
                <div key={snapshot.key} className="bg-gray-700 rounded-lg p-4 flex items-center justify-between">
                  <div>
                    <div className="font-medium text-white">{snapshot.key}</div>
                    <div className="text-sm text-gray-400">{new Date(snapshot.last_modified).toLocaleString()}</div>
                  </div>
                  <button
                    onClick={() => handleRestore(snapshot.key)}
                    disabled={actionLoading}
                    className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                  >
                    Restore
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default FriendDetail
