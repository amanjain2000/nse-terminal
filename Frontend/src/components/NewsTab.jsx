import { useState, useEffect } from 'react'
import { fetchNews } from '../api/client'

const PESTEL_META = {
  Political:      { color: '#7c5cbf', icon: '🏛️', desc: 'Government, policy, regulation' },
  Economic:       { color: '#2ea44f', icon: '📈', desc: 'GDP, rates, earnings, macro' },
  Social:         { color: '#f0883e', icon: '👥', desc: 'Consumer, workforce, sentiment' },
  Technological:  { color: '#58a6ff', icon: '⚙️', desc: 'Innovation, AI, digital, R&D' },
  Environmental:  { color: '#3fb950', icon: '🌿', desc: 'ESG, climate, sustainability' },
  Legal:          { color: '#e3b341', icon: '⚖️', desc: 'Courts, compliance, penalties' },
}

const SENTIMENT_STYLE = {
  positive: { color: 'var(--green)', bg: 'var(--green-dim)', label: '▲ Positive' },
  negative: { color: 'var(--red)',   bg: 'var(--red-dim)',   label: '▼ Negative' },
  neutral:  { color: 'var(--text-3)', bg: 'var(--bg-3)',    label: '● Neutral'  },
}

function PestelGauge({ category, data }) {
  const meta   = PESTEL_META[category]
  const score  = data?.normalized ?? 50
  const signal = data?.signal ?? 'neutral'
  const count  = data?.count ?? 0

  const barColor = score > 60 ? '#3fb950' : score < 40 ? '#f85149' : '#8b949e'
  const pct      = `${score}%`

  return (
    <div style={{
      background: 'var(--bg-2)', border: '1px solid var(--border)',
      borderRadius: 8, padding: '14px 16px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>
            {category}
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>
            {meta.desc}
          </div>
        </div>
        <div style={{
          fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 600,
          padding: '2px 8px', borderRadius: 4,
          color: barColor, background: score > 60 ? 'var(--green-dim)' : score < 40 ? 'var(--red-dim)' : 'var(--bg-3)',
        }}>
          {signal.toUpperCase()}
        </div>
      </div>

      {/* Bar track */}
      <div style={{ background: 'var(--bg-3)', borderRadius: 4, height: 6, position: 'relative', marginBottom: 8 }}>
        {/* Center line */}
        <div style={{
          position: 'absolute', left: '50%', top: -2, width: 1, height: 10,
          background: 'var(--border)', zIndex: 1,
        }} />
        <div style={{
          position: 'absolute', left: 0, top: 0, height: '100%',
          width: pct, background: barColor, borderRadius: 4,
          transition: 'width 0.6s ease',
        }} />
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontFamily: 'var(--font-mono)' }}>
        <span style={{ color: 'var(--red)' }}>Bearish</span>
        <span style={{ color: 'var(--text-3)' }}>{count} signals • score {score}</span>
        <span style={{ color: 'var(--green)' }}>Bullish</span>
      </div>
    </div>
  )
}

function NewsCard({ item }) {
  const sent  = SENTIMENT_STYLE[item.sentiment] || SENTIMENT_STYLE.neutral
  const cats  = item.pestel_categories || []

  return (
    <div style={{
      background: 'var(--bg-2)', border: '1px solid var(--border)',
      borderRadius: 8, padding: '14px 16px', marginBottom: 8,
      transition: 'border-color 0.15s',
    }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border)'}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1 }}>
          {/* Title */}
          <a href={item.url} target="_blank" rel="noreferrer" style={{
            color: 'var(--text-1)', textDecoration: 'none',
            fontSize: 13, fontWeight: 500, lineHeight: 1.4,
            display: 'block', marginBottom: 6,
          }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--blue)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-1)'}
          >
            {item.title}
          </a>

          {/* Summary */}
          {item.summary && (
            <p style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, margin: '0 0 8px' }}>
              {item.summary}
            </p>
          )}

          {/* Meta row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {/* Source */}
            <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
              {item.source}
            </span>

            {/* Sentiment badge */}
            <span style={{
              fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 600,
              padding: '1px 7px', borderRadius: 3,
              color: sent.color, background: sent.bg,
            }}>
              {sent.label}
            </span>

            {/* PESTEL category badges */}
            {cats.map(cat => (
              <span key={cat} style={{
                fontSize: 10, fontFamily: 'var(--font-mono)',
                padding: '1px 7px', borderRadius: 3,
                color: PESTEL_META[cat]?.color || 'var(--text-3)',
                background: 'var(--bg-3)',
                border: `1px solid ${PESTEL_META[cat]?.color || 'var(--border)'}33`,
              }}>
                {cat}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

const FILTER_OPTIONS = ['All', 'Positive', 'Negative', ...Object.keys(PESTEL_META)]

export default function NewsTab({ symbol }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [filter, setFilter]   = useState('All')

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchNews(symbol)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [symbol])

  if (loading) return (
    <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
      <div style={{ marginBottom: 8 }}>Ingesting news feeds...</div>
      <div style={{ fontSize: 10, color: 'var(--text-3)' }}>Scanning ET, BS, Moneycontrol, Mint, BusinessLine</div>
    </div>
  )

  if (error) return (
    <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
      <div style={{ fontSize: 24, marginBottom: 8 }}>📡</div>
      Could not load news feeds. Check your connection.
    </div>
  )

  const news   = data?.news   || []
  const pestel = data?.pestel || {}

  const filtered = news.filter(item => {
    if (filter === 'All') return true
    if (filter === 'Positive') return item.sentiment === 'positive'
    if (filter === 'Negative') return item.sentiment === 'negative'
    return item.pestel_categories?.includes(filter)
  })

  const positive = news.filter(i => i.sentiment === 'positive').length
  const negative = news.filter(i => i.sentiment === 'negative').length
  const neutral  = news.filter(i => i.sentiment === 'neutral').length

  return (
    <div style={{ padding: '20px 24px' }}>

      {/* ── PESTEL Dashboard ── */}
      <div className="section-title" style={{ marginBottom: 14 }}>
        PESTEL signal analysis
        <span style={{ fontWeight: 400, color: 'var(--text-3)', marginLeft: 8 }}>
          — based on {news.length} news items
        </span>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
        gap: 8, marginBottom: 28,
      }}>
        {Object.entries(PESTEL_META).map(([cat]) => (
          <PestelGauge key={cat} category={cat} data={pestel[cat]} />
        ))}
      </div>

      {/* ── Sentiment summary ── */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {[
          { label: 'Positive', count: positive, color: 'var(--green)', bg: 'var(--green-dim)' },
          { label: 'Neutral',  count: neutral,  color: 'var(--text-3)', bg: 'var(--bg-3)' },
          { label: 'Negative', count: negative, color: 'var(--red)',   bg: 'var(--red-dim)' },
        ].map(s => (
          <div key={s.label} style={{
            flex: 1, background: s.bg, borderRadius: 8, padding: '10px 14px', textAlign: 'center',
          }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 600, color: s.color }}>
              {s.count}
            </div>
            <div style={{ fontSize: 10, color: s.color, fontFamily: 'var(--font-mono)', marginTop: 2 }}>
              {s.label.toUpperCase()}
            </div>
          </div>
        ))}
      </div>

      {/* ── News feed ── */}
      <div className="section-title" style={{ marginBottom: 12 }}>
        News feed
        {filtered.length !== news.length && (
          <span style={{ fontWeight: 400, color: 'var(--text-3)', marginLeft: 8 }}>
            {filtered.length} of {news.length} shown
          </span>
        )}
      </div>

      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 16 }}>
        {FILTER_OPTIONS.map(opt => (
          <button key={opt} onClick={() => setFilter(opt)} style={{
            background: filter === opt ? 'var(--blue-dim)' : 'var(--bg-2)',
            border: `1px solid ${filter === opt ? 'var(--blue)' : 'var(--border)'}`,
            color: filter === opt ? 'var(--blue)' : 'var(--text-2)',
            borderRadius: 5, padding: '4px 12px',
            fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer',
            transition: 'all 0.15s',
          }}>
            {opt}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
          No news items match the selected filter for <strong>{symbol}</strong>.<br />
          <span style={{ fontSize: 11, marginTop: 6, display: 'block' }}>
            Try "All" to see general market news, or check back during market hours.
          </span>
        </div>
      ) : (
        filtered.map((item, i) => <NewsCard key={i} item={item} />)
      )}
    </div>
  )
}
