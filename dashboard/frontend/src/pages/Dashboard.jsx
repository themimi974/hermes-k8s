import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

const API_BASE = '/api'

function StatusBadge({ status }) {
  const colors = {
    Running: 'bg-green-500 text-white',
    Error: 'bg-red-500 text-white',
    Stopped: 'bg-gray-500 text-white',
    Unknown: 'bg-yellow-500 text-white'
  }
  
  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${colors[status] || colors.Unknown}`}>
      {status}
    </span>
  )
}

function FriendCard({ friend, onSave, onRestore, onDelete }) {
  return (
    <div className="bg-gray-800 rounded-xl shadow-xl border border-gray-700 p-6 hover:border-blue-500 transition-colors">
      <div className="flex items-start justify-between mb-4">
        <Link to={`/friends/${friend.name}`} className="text-xl font-bold text-white hover:text-blue-400 transition-colors">
          {friend.name}
        </Link>
        <StatusBadge status={friend.status} />
      </div>
      
      <div className="space-y-2 text-gray-300 mb-4">
        <div className="flex items-center">
          <span className="text-gray-500 w-20">Uptime:</span>
          <span className="font-mono">{friend.uptime || 'N/A'}</span>
        </div>
        <div className="flex items-center">
          <span className="text-gray-500 w-20">Subdomain:</span>
          <a 
            href={`https://${friend.name}.hermes.community`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300 underline"
          >
            {friend.name}.hermes.community
          </a>
        </div>
      </div>
      
      <div className="flex space-x-2 pt-4 border-t border-gray-700">
        <button
          onClick={() => onSave(friend.name)}
          className="flex-1 bg-green-600 hover:bg-green-700 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          💾 Save
        </button>
        <button
          onClick={() => onRestore(friend.name)}
          className="flex-1 bg-yellow-600 hover:bg-yellow-700 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          ↩️ Restore
        </button>
        <button
          onClick={() => onDelete(friend.name)}
          className="flex-1 bg-red-600 hover:bg-red-700 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          🗑️ Delete
        </button>
      </div>
    </div>
  )
}

function Dashboard() {
  const [friends, setFriends] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionLoading, setActionLoading] = useState(null)

  const fetchFriends = async () => {
    try {
      const response = await fetch(`${API_BASE}/friends`)
      if (!response.ok) throw new Error('Failed to fetch friends')
      const data = await response.json()
      setFriends(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchFriends()
  }, [])

  const handleSave = async (name) => {
    setActionLoading(name)
    try {
      const response = await fetch(`${API_BASE}/friends/${name}/save`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to save')
      await fetchFriends()
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setActionLoading(null)
    }
  }

  const handleRestore = async (name) => {
    setActionLoading(name)
    try {
      const response = await fetch(`${API_BASE}/friends/${name}/restore`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to restore')
      await fetchFriends()
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setActionLoading(null)
    }
  }

  const handleDelete = async (name) => {
    if (!confirm(`Are you sure you want to delete ${name}?`)) return
    setActionLoading(name)
    try {
      const response = await fetch(`${API_BASE}/friends/${name}`, {
        method: 'DELETE'
      })
      if (!response.ok) throw new Error('Failed to delete')
      await fetchFriends()
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setActionLoading(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-xl text-gray-400 flex items-center">
          <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Loading friends...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-900/50 border border-red-500 text-red-200 px-6 py-4 rounded-lg">
        <h3 className="font-bold mb-2">Error</h3>
        <p>{error}</p>
        <button 
          onClick={fetchFriends}
          className="mt-3 bg-red-600 hover:bg-red-700 px-4 py-2 rounded text-white"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h2 className="text-2xl font-bold text-white">Your Friends</h2>
        <Link
          to="/friends/new"
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
        >
          + New Friend
        </Link>
      </div>
      
      {friends.length === 0 ? (
        <div className="text-center py-16 bg-gray-800 rounded-xl border border-gray-700">
          <p className="text-xl text-gray-400 mb-4">No friends yet</p>
          <Link
            to="/friends/new"
            className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium transition-colors"
          >
            Create your first friend
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {friends.map(friend => (
            <FriendCard
              key={friend.name}
              friend={friend}
              onSave={handleSave}
              onRestore={handleRestore}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default Dashboard
