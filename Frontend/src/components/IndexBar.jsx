import { useState, useEffect } from 'react'
import { fetchIndices } from '../api/client'

export default function IndexBar() {
  const [indices, setIndices] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const data = await fetchIndices()
        if (alive) { setIndices(data); setLoading(false) }
      } catch {
        if (alive) setLoading(false)
      }
    }
    load()
    const iv = setInterval(load, 60000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  return (
    <div className="index-bar">
      <div className="index-bar-brand">
        <div className="brand-icon">N</div>
        <span className="brand-name">NSE TERMINAL</span>
      </div>

      {loading ? (
        <div className="index-loading">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="index-skeleton" />
          ))}
        </div>
      ) : (
        indices.map(idx => {
          const up = idx.change_pct >= 0
          return (
            <div key={idx.name} className="index-item">
              <span className="index-name">{idx.name}</span>
              <span className="index-price">{idx.price.toLocaleString('en-IN')}</span>
              <span className={`index-change ${up ? 'up' : 'down'}`}>
                {up ? '+' : ''}{idx.change_pct.toFixed(2)}%
              </span>
            </div>
          )
        })
      )}
    </div>
  )
}
