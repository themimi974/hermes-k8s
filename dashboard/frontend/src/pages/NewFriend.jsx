import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'

const API_BASE = '/api'

function NewFriend() {
  const navigate = useNavigate()
  const [formData, setFormData] = useState({
    name: '',
    username: '',
    password: '',
  })
  const [availableGroups, setAvailableGroups] = useState([])
  const [selectedGroups, setSelectedGroups] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/budget-groups`)
      .then(r => r.json())
      .then(data => setAvailableGroups(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const toggleGroup = (groupId) => {
    setSelectedGroups(prev =>
      prev.includes(groupId)
        ? prev.filter(id => id !== groupId)
        : [...prev, groupId]
    )
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      // 1. Create friend
      const response = await fetch(`${API_BASE}/friends`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(formData),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to create friend')
      }

      // 2. Assign budget groups (if any selected)
      if (selectedGroups.length > 0) {
        await fetch(`${API_BASE}/friends/${formData.name}/groups`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ group_ids: selectedGroups }),
        })
      }

      navigate(`/friends/${formData.name}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto">
      <Link to="/" className="text-blue-400 hover:text-blue-300 mb-6 inline-block">
        ← Back to Dashboard
      </Link>

      <div className="bg-gray-800 rounded-xl shadow-xl border border-gray-700 p-8">
        <h1 className="text-2xl font-bold text-white mb-6">Create New Friend</h1>

        {error && (
          <div className="bg-red-900/50 border border-red-500 text-red-200 px-4 py-3 rounded-lg mb-6">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-300 mb-2">
              Friend Name *
            </label>
            <input
              type="text"
              id="name"
              name="name"
              value={formData.name}
              onChange={handleChange}
              required
              pattern="[a-z0-9-]+"
              title="Lowercase letters, numbers, and hyphens only"
              className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="my-friend"
            />
            <p className="mt-1 text-sm text-gray-500">
              Lowercase letters, numbers, and hyphens only. This will be your subdomain.
            </p>
          </div>

          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-300 mb-2">
              Username *
            </label>
            <input
              type="text"
              id="username"
              name="username"
              value={formData.username}
              onChange={handleChange}
              required
              className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="admin"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-2">
              Password *
            </label>
            <input
              type="password"
              id="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              required
              minLength={8}
              className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="••••••••"
            />
            <p className="mt-1 text-sm text-gray-500">
              Minimum 8 characters
            </p>
          </div>

          {/* Budget Groups */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Budget Groups
            </label>
            <p className="text-xs text-gray-500 mb-2">
              Optional — assign groups to give this friend access to specific models and limits.
            </p>
            {availableGroups.length === 0 ? (
              <p className="text-gray-500 text-sm">
                No groups yet.{' '}
                <Link to="/budget-groups" className="text-blue-400 hover:underline">Create one first</Link>{' '}
                or skip for now.
              </p>
            ) : (
              <div className="space-y-2">
                {availableGroups.map(group => (
                  <label
                    key={group.id}
                    className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      selectedGroups.includes(group.id)
                        ? 'bg-blue-900/30 border-blue-600'
                        : 'bg-gray-700 border-gray-600 hover:border-gray-500'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedGroups.includes(group.id)}
                      onChange={() => toggleGroup(group.id)}
                      className="rounded"
                    />
                    <div className="flex-1">
                      <span className="text-white font-medium text-sm">{group.name}</span>
                      {group.description && (
                        <span className="text-gray-400 text-xs ml-2">— {group.description}</span>
                      )}
                      <div className="flex flex-wrap gap-1 mt-1">
                        {(group.models || []).map(m => (
                          <span key={m} className="bg-gray-600 text-gray-300 text-xs px-1.5 py-0.5 rounded">{m}</span>
                        ))}
                      </div>
                    </div>
                    <div className="text-right text-xs text-gray-400">
                      <div>${group.max_budget}/{group.budget_duration}</div>
                      <div>{group.friend_count} friend{group.friend_count !== 1 ? 's' : ''}</div>
                    </div>
                  </label>
                ))}
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white font-medium py-3 px-4 rounded-lg transition-colors"
          >
            {loading ? (
              <span className="flex items-center justify-center">
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Creating...
              </span>
            ) : (
              '🤖 Create Friend' + (selectedGroups.length > 0 ? ` (${selectedGroups.length} group${selectedGroups.length > 1 ? 's' : ''})` : '')
            )}
          </button>
        </form>
      </div>
    </div>
  )
}

export default NewFriend
