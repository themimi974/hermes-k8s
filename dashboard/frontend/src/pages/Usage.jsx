import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'

const API = '/api'

function formatTokens(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toString()
}

// ── Tab components ──────────────────────────────────────────────

function OverviewTab({ period }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch(`${API}/usage?period=${period}`).then(r => r.json()).then(setData).catch(() => {})
  }, [period])

  if (!data) return <div className="text-center text-gray-400 py-8">Loading...</div>

  return (
    <>
      {data.note && (
        <div className="bg-yellow-900 border border-yellow-700 text-yellow-200 px-4 py-3 rounded-lg mb-4 text-sm">
          {data.note}
        </div>
      )}

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
                  <th className="text-right text-sm text-gray-400 px-4 py-3">Cost</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.by_model).map(([model, stats]) => (
                  <tr key={model} className="border-b border-gray-700 last:border-0">
                    <td className="text-white px-4 py-3 font-medium text-sm">{model}</td>
                    <td className="text-gray-300 px-4 py-3 text-sm text-right">{stats.requests.toLocaleString()}</td>
                    <td className="text-gray-300 px-4 py-3 text-sm text-right">{formatTokens(stats.tokens)}</td>
                    <td className="text-green-400 px-4 py-3 text-sm text-right">${stats.cost?.toFixed(4) || '0.0000'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {Object.keys(data.by_friend).length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-white mb-3">By Friend</h3>
          <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left text-sm text-gray-400 px-4 py-3">Friend</th>
                  <th className="text-right text-sm text-gray-400 px-4 py-3">Requests</th>
                  <th className="text-right text-sm text-gray-400 px-4 py-3">Tokens</th>
                  <th className="text-right text-sm text-gray-400 px-4 py-3">Cost</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.by_friend).map(([name, stats]) => (
                  <tr key={name} className="border-b border-gray-700 last:border-0">
                    <td className="text-white px-4 py-3 font-medium text-sm">{name}</td>
                    <td className="text-gray-300 px-4 py-3 text-sm text-right">{stats.requests.toLocaleString()}</td>
                    <td className="text-gray-300 px-4 py-3 text-sm text-right">{formatTokens(stats.tokens)}</td>
                    <td className="text-green-400 px-4 py-3 text-sm text-right">${stats.cost?.toFixed(4) || '0.0000'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {Object.keys(data.by_model).length === 0 && Object.keys(data.by_friend).length === 0 && (
        <div className="text-center text-gray-400 py-8">
          No usage data for this period. Usage will appear after API calls through LiteLLM.
        </div>
      )}
    </>
  )
}


function FriendsTab({ period }) {
  const [friends, setFriends] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    fetch(`${API}/usage/friends?period=${period}`).then(r => r.json()).then(d => setFriends(d.friends || [])).catch(() => {})
    setSelected(null)
    setDetail(null)
  }, [period])

  const selectFriend = async (name) => {
    setSelected(name)
    try {
      const res = await fetch(`${API}/usage/friends/${name}?period=${period}`)
      setDetail(await res.json())
    } catch { setDetail(null) }
  }

  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Friend list */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-700">
            <h3 className="text-sm font-semibold text-gray-300">Friends ({friends.length})</h3>
          </div>
          <div className="divide-y divide-gray-700 max-h-96 overflow-y-auto">
            {friends.length === 0 ? (
              <div className="px-4 py-6 text-center text-gray-400 text-sm">No friend usage data</div>
            ) : (
              friends.map(f => (
                <button key={f.name} onClick={() => selectFriend(f.name)}
                        className={`w-full text-left px-4 py-3 hover:bg-gray-700 transition-colors ${
                          selected === f.name ? 'bg-blue-900/30 border-l-2 border-blue-500' : ''
                        }`}>
                  <div className="flex justify-between items-center">
                    <Link to={`/friends/${f.name}`} onClick={(e) => e.stopPropagation()}
                          className="text-white font-medium text-sm hover:text-blue-400">
                      {f.name}
                    </Link>
                    <span className="text-gray-400 text-xs">{formatTokens(f.tokens)} tokens</span>
                  </div>
                  <div className="flex justify-between items-center mt-1">
                    <span className="text-gray-500 text-xs">{f.requests} requests</span>
                    <span className="text-green-400 text-xs">${f.cost.toFixed(4)}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Detail panel */}
        <div className="lg:col-span-2">
          {!selected ? (
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center text-gray-400">
              Select a friend to see their model usage breakdown
            </div>
          ) : !detail ? (
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center text-gray-400">Loading...</div>
          ) : (
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="px-4 py-3 border-b border-gray-700 flex justify-between items-center">
                <h3 className="text-white font-semibold">{detail.friend} — Usage by Model</h3>
                <div className="flex gap-3 text-sm">
                  <span className="text-gray-400">{detail.total?.requests || 0} req</span>
                  <span className="text-gray-400">{formatTokens(detail.total?.tokens || 0)} tokens</span>
                  <span className="text-green-400">${(detail.total?.cost || 0).toFixed(4)}</span>
                </div>
              </div>
              {detail.by_model?.length > 0 ? (
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left text-xs text-gray-400 px-4 py-2">Model</th>
                      <th className="text-right text-xs text-gray-400 px-4 py-2">Requests</th>
                      <th className="text-right text-xs text-gray-400 px-4 py-2">Tokens</th>
                      <th className="text-right text-xs text-gray-400 px-4 py-2">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.by_model.map(m => (
                      <tr key={m.model} className="border-b border-gray-700 last:border-0">
                        <td className="text-white px-4 py-2 text-sm">{m.model}</td>
                        <td className="text-gray-300 px-4 py-2 text-sm text-right">{m.requests.toLocaleString()}</td>
                        <td className="text-gray-300 px-4 py-2 text-sm text-right">{formatTokens(m.tokens)}</td>
                        <td className="text-green-400 px-4 py-2 text-sm text-right">${m.cost.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="px-4 py-6 text-center text-gray-400 text-sm">No model usage data</div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}


function ModelsTab({ period }) {
  const [models, setModels] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    fetch(`${API}/usage/models?period=${period}`).then(r => r.json()).then(d => setModels(d.models || [])).catch(() => {})
    setSelected(null)
    setDetail(null)
  }, [period])

  const selectModel = async (modelId) => {
    setSelected(modelId)
    try {
      const res = await fetch(`${API}/usage/models/${encodeURIComponent(modelId)}?period=${period}`)
      setDetail(await res.json())
    } catch { setDetail(null) }
  }

  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Model list */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-700">
            <h3 className="text-sm font-semibold text-gray-300">Models ({models.length})</h3>
          </div>
          <div className="divide-y divide-gray-700 max-h-96 overflow-y-auto">
            {models.length === 0 ? (
              <div className="px-4 py-6 text-center text-gray-400 text-sm">No model usage data</div>
            ) : (
              models.map(m => (
                <button key={m.model} onClick={() => selectModel(m.model)}
                        className={`w-full text-left px-4 py-3 hover:bg-gray-700 transition-colors ${
                          selected === m.model ? 'bg-blue-900/30 border-l-2 border-blue-500' : ''
                        }`}>
                  <div className="text-white font-medium text-sm truncate">{m.model}</div>
                  <div className="flex justify-between items-center mt-1">
                    <span className="text-gray-500 text-xs">{m.requests} requests</span>
                    <span className="text-green-400 text-xs">${m.cost.toFixed(4)}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Detail panel */}
        <div className="lg:col-span-2">
          {!selected ? (
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center text-gray-400">
              Select a model to see which friends used it
            </div>
          ) : !detail ? (
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center text-gray-400">Loading...</div>
          ) : (
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="px-4 py-3 border-b border-gray-700">
                <h3 className="text-white font-semibold text-sm truncate">{detail.model}</h3>
                <div className="flex gap-3 text-xs mt-1">
                  <span className="text-gray-400">{detail.total?.requests || 0} requests</span>
                  <span className="text-gray-400">{formatTokens(detail.total?.tokens || 0)} tokens</span>
                  <span className="text-green-400">${(detail.total?.cost || 0).toFixed(4)}</span>
                </div>
              </div>
              {detail.by_friend?.length > 0 ? (
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left text-xs text-gray-400 px-4 py-2">Friend</th>
                      <th className="text-right text-xs text-gray-400 px-4 py-2">Requests</th>
                      <th className="text-right text-xs text-gray-400 px-4 py-2">Tokens</th>
                      <th className="text-right text-xs text-gray-400 px-4 py-2">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.by_friend.map(f => (
                      <tr key={f.name} className="border-b border-gray-700 last:border-0">
                        <td className="text-white px-4 py-2 text-sm">
                          <Link to={`/friends/${f.name}`} className="hover:text-blue-400">{f.name}</Link>
                        </td>
                        <td className="text-gray-300 px-4 py-2 text-sm text-right">{f.requests.toLocaleString()}</td>
                        <td className="text-gray-300 px-4 py-2 text-sm text-right">{formatTokens(f.tokens)}</td>
                        <td className="text-green-400 px-4 py-2 text-sm text-right">${f.cost.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="px-4 py-6 text-center text-gray-400 text-sm">No friend usage data for this model</div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}


function MatrixTab({ period }) {
  const [matrix, setMatrix] = useState(null)

  useEffect(() => {
    fetch(`${API}/usage/matrix?period=${period}`).then(r => r.json()).then(setMatrix).catch(() => {})
  }, [period])

  if (!matrix) return <div className="text-center text-gray-400 py-8">Loading matrix...</div>
  if (matrix.note) {
    return (
      <div className="bg-yellow-900 border border-yellow-700 text-yellow-200 px-4 py-3 rounded-lg text-sm">
        {matrix.note}
      </div>
    )
  }

  const { friends, models, cells } = matrix

  if (friends.length === 0 || models.length === 0) {
    return <div className="text-center text-gray-400 py-8">No data for matrix view.</div>
  }

  // Find max tokens for color scaling
  let maxTokens = 1
  for (const val of Object.values(cells)) {
    if (val.tokens > maxTokens) maxTokens = val.tokens
  }

  const getColor = (tokens) => {
    if (tokens === 0) return 'bg-gray-800 text-gray-600'
    const ratio = tokens / maxTokens
    if (ratio > 0.7) return 'bg-blue-900 text-blue-200'
    if (ratio > 0.3) return 'bg-blue-900/50 text-blue-300'
    return 'bg-blue-900/20 text-blue-400'
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className="text-left text-xs text-gray-400 px-3 py-2 sticky left-0 bg-gray-900">Friend ↓ / Model →</th>
            {models.map(m => (
              <th key={m} className="text-center text-xs text-gray-400 px-3 py-2 min-w-[100px] truncate max-w-[150px]"
                  title={m}>
                {m.length > 20 ? m.slice(0, 20) + '…' : m}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {friends.map(f => (
            <tr key={f}>
              <td className="text-white text-sm font-medium px-3 py-2 sticky left-0 bg-gray-900 whitespace-nowrap">
                <Link to={`/friends/${f}`} className="hover:text-blue-400">{f}</Link>
              </td>
              {models.map(m => {
                const cell = cells[`${f}|${m}`]
                const tokens = cell?.tokens || 0
                const inputTok = cell?.input_tokens || 0
                const outputTok = cell?.output_tokens || 0
                const cachedTok = cell?.cached_tokens || 0
                const cachePct = cell?.cache_hit_pct || 0
                return (
                  <td key={m} className={`text-center text-xs px-2 py-2 rounded ${getColor(tokens)}`}
                      title={`${f} × ${m}: ${tokens} tokens, ${cell?.requests || 0} req, $${(cell?.cost || 0).toFixed(4)}`}>
                    {tokens > 0 ? (
                      <div className="leading-tight">
                        <div className="font-semibold">{formatTokens(tokens)}</div>
                        <div className="opacity-70 text-[10px]">↓{formatTokens(outputTok)} ↑{formatTokens(inputTok)}</div>
                        {cachedTok > 0 && <div className="opacity-60 text-[10px]">⚡{cachePct}%</div>}
                      </div>
                    ) : '—'}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}


// ── Main Usage page ─────────────────────────────────────────────

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'friends', label: 'By Friend' },
  { id: 'models', label: 'By Model' },
  { id: 'matrix', label: 'Matrix' },
]

export default function Usage() {
  const [tab, setTab] = useState('overview')
  const [period, setPeriod] = useState('24h')

  const renderTab = () => {
    switch (tab) {
      case 'overview': return <OverviewTab period={period} />
      case 'friends': return <FriendsTab period={period} />
      case 'models': return <ModelsTab period={period} />
      case 'matrix': return <MatrixTab period={period} />
      default: return null
    }
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">Usage</h2>
          <p className="text-gray-400 text-sm mt-1">API usage analytics from LiteLLM</p>
        </div>
        <select value={period} onChange={(e) => setPeriod(e.target.value)}
                className="bg-gray-700 text-white rounded px-3 py-2 border border-gray-600">
          <option value="1h">Last 1 hour</option>
          <option value="6h">Last 6 hours</option>
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-gray-700">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
                  className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                    tab === t.id
                      ? 'bg-gray-800 text-white border-b-2 border-blue-500'
                      : 'text-gray-400 hover:text-white hover:bg-gray-800'
                  }`}>
            {t.label}
          </button>
        ))}
      </div>

      {renderTab()}
    </div>
  )
}
