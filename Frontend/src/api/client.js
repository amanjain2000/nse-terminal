const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function req(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export const fetchIndices = () => req('/api/indices')
export const fetchSectors = () => req('/api/sectors')
export const searchStocks = (q) => req(`/api/search?q=${encodeURIComponent(q)}`)
export const fetchStock = (sym) => req(`/api/stock/${sym}`)
export const fetchHistory = (sym, period = '1m') =>
  req(`/api/stock/${sym}/history?period=${period}`)
