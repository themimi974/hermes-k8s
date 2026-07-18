import { useState, useEffect } from 'react'

const API_BASE = '/api'

export function useConfig() {
  const [config, setConfig] = useState({ domain: 'localhost', tls_cert_resolver: '' })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_BASE}/config`, { credentials: 'include' })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setConfig(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return { ...config, loading }
}
