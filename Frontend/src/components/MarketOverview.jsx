import { useState, useEffect } from 'react'
import { fetchSectors } from '../api/client'

const NIFTY50_QUICK = [
  'RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'INFY',
  'BHARTIARTL', 'KOTAKBANK', 'ITC', 'LT', 'AXISBANK',
  'SBIN', 'WIPRO', 'NTPC', 'MARUTI', 'BAJFINANCE',
]

export default function MarketOverview({ onSelectStock }) {
  const [sectors, setSectors] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchSectors()
      .then(d => { setSectors(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  return (
    <div className="market-overview">

      {/* Sector heatmap */}
      <div className="overview-title">Sector performance (today)</div>
      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8, marginBottom: 24 }}>
          {[...Array(10)].map((_, i) => (
            <div key={i} style={{
              height: 80, borderRadius: 8, background: 'var(--bg-2)',
              animation: 'pulse 1.5s ease-in-out infinite',
              animationDelay: `${i * 0.1}s`
            }} />
          ))}
        </div>
      ) : (
        <div className="sector-grid">
          {sectors.map(s => {
            const up = s.change_pct >= 0
            return (
              <div key={s.name} className={`sector-card ${up ? 'up' : 'down'}`}>
                <div className="sector-name">{s.name}</div>
                <div className={`sector-change ${up ? 'up' : 'down'}`}>
                  {up ? '+' : ''}{s.change_pct.toFixed(2)}%
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Quick access */}
      <div className="overview-title" style={{ marginTop: 8 }}>Quick access — NIFTY 50 highlights</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 24 }}>
        {NIFTY50_QUICK.map(sym => (
          <button
            key={sym}
            onClick={() => onSelectStock(sym)}
            style={{
              background: 'var(--bg-2)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '6px 14px',
              color: 'var(--blue)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'var(--blue)'
              e.currentTarget.style.background = 'var(--blue-dim)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.background = 'var(--bg-2)'
            }}
          >
            {sym}
          </button>
        ))}
      </div>

      {/* Help hint */}
      <div className="overview-hint">
        <div style={{ fontSize: 28, marginBottom: 10 }}>⌕</div>
        <div style={{ color: 'var(--text-2)', marginBottom: 8 }}>
          Search for any NSE listed stock using the sidebar
        </div>
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>
          Type a symbol like <strong>RELIANCE</strong>, <strong>TCS</strong> or <strong>HDFC</strong><br />
          or search by company name
        </div>
      </div>
    </div>
  )
}
