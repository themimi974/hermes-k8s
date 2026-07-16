import { useState, useEffect } from 'react'

const API = '/api'

export default function Usage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [period, setPeriod] = useState('24h')

  const fetchUsage = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/usage?period=${period}`)
      const json = await res.json()
      setData(json)
    } catch (e) {
      console.error('Failed to fetch usage:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchUsage() }, [period])

  const formatTokens = (n) => {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
    return n.toString()
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">Usage</h2>
          <p className="text-gray-400 text-sm mt-1">API usage analytics from LiteLLM</p>
        </div>
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          className="bg-gray-700 text-white rounded px-3 py-2 border border-gray-600"
        >
          <option value="1h">Last 1 hour</option>
          <option value="6h">Last 6 hours</option>
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      </div>

      {loading ? (
        <div className="text-center text-gray-400 py-8">Loading...</div>
      ) : !data ? (
        <div className="text-center text-gray-400 py-8">No data available</div>
      ) : (
        <>
          {data.note && (
            <div className="bg-yellow-900 border border-yellow-700 text-yellow-200 px-4 py-3 rounded-lg mb-4 text-sm">
              {data.note}
            </div>
          )}

          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div className="bg-gray-800 rounded-lg p-5 border border-gray-700">
              <p className="text-gray-400 text-sm">Total Requests</p>
              <p className="text-3xl font-bold text-white mt-1">{data.total_requests.toLocaleString()}</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-5 border border-gray-700">
              <p className="text-gray-400 text-sm">Total Tokens</p>
              <p className="text-3xl font-bold text-white mt-1">{formatTokens(data.total_tokens)}</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-5 border border-gray-700">
              <p className="text-gray-400 text-sm">Total Cost</p>
              <p className="text-3xl font-bold text-green-400 mt-1">${data.total_cost.toFixed(4)}</p>
            </div>
          </div>

          {/* By Model */}
          {Object.keys(data.by_model).length > 0 && (
            <div className="mb-8">
              <h3 className="text-lg font-semibold text-white mb-3">By Model</h3>
              <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left text-sm text-gray-400 px-4 py-3">Model</th>
                      <th className="text-right text-sm text-gray-400 px-4 py-3">Requests</th>
                      <th className="text-right text-sm text-gray-400 px-4 py-3">Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.by_model).map(([model, stats]) => (
                      <tr key={model} className="border-b border-gray-700 last:border-0">
                        <td className="text-white px-4 py-3 font-medium">{model}</td>
                        <td className="text-gray-300 px-4 py-3 text-right">{stats.requests.toLocaleString()}</td>
                        <td className="text-gray-300 px-4 py-3 text-right">{formatTokens(stats.tokens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* By Friend */}
          {Object.keys(data.by_friend).length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-white mb-3">By Friend (API Key)</h3>
              <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left text-sm text-gray-400 px-4 py-3">API Key Name</th>
                      <th className="text-right text-sm text-gray-400 px-4 py-3">Requests</th>
                      <th className="text-right text-sm text-gray-400 px-4 py-3">Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.by_friend).map(([name, stats]) => (
                      <tr key={name} className="border-b border-gray-700 last:border-0">
                        <td className="text-white px-4 py-3 font-medium">{name}</td>
                        <td className="text-gray-300 px-4 py-3 text-right">{stats.requests.toLocaleString()}</td>
                        <td className="text-gray-300 px-4 py-3 text-right">{formatTokens(stats.tokens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {Object.keys(data.by_model).length === 0 && Object.keys(data.by_friend).length === 0 && (
            <div className="text-center text-gray-400 py-8">
              No usage data for this period. Usage will appear after API calls are made through LiteLLM.
            </div>
          )}
        </>
      )}
    </div>
  )
}
