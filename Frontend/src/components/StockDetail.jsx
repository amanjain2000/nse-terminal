import { useState } from 'react'
import PriceChart from './PriceChart'
import FinancialsTab from './FinancialsTab'
import ShareholdingTab from './ShareholdingTab'
import NewsTab from './NewsTab'

function fmt(v, decimals = 2) {
  if (v == null) return '—'
  return Number(v).toFixed(decimals)
}

function fmtLargeNum(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (n >= 1e12) return `₹${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9)  return `₹${(n / 1e9).toFixed(2)}B`
  if (n >= 1e7)  return `₹${(n / 1e7).toFixed(2)}Cr`
  if (n >= 1e5)  return `₹${(n / 1e5).toFixed(2)}L`
  return `₹${n.toLocaleString('en-IN')}`
}

function fmtVolume(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)}Cr`
  if (n >= 1e5) return `${(n / 1e5).toFixed(2)}L`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toString()
}

function MetricCard({ label, value, highlight }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${value === '—' ? 'null-val' : ''}`}
        style={highlight ? { color: highlight } : {}}>
        {value}
      </div>
    </div>
  )
}

const TABS = ['Overview', 'Financials', 'Shareholding', 'News & PESTEL']

export default function StockDetail({ data, onAddWatchlist, isWatchlisted }) {
  const [activeTab, setActiveTab] = useState('Overview')
  const isUp = (data.change_pct || 0) >= 0

  const week52Pct = data.week_52_high && data.week_52_low && data.price
    ? ((data.price - data.week_52_low) / (data.week_52_high - data.week_52_low)) * 100
    : null

  return (
    <div className="stock-detail fade-in">

      {/* Header — always visible */}
      <div className="stock-header">
        <div className="stock-header-left">
          <div className="stock-symbol">{data.symbol}</div>
          <div className="stock-full-name">{data.name}</div>
          <div className="stock-meta-row">
            <span className="meta-tag">NSE</span>
            {data.series && <span className="meta-tag">{data.series}</span>}
            {data.sector && <span className="meta-tag">{data.sector}</span>}
            {data.industry && <span className="meta-tag">{data.industry}</span>}
            {data.isin && <span className="meta-tag" style={{ color: 'var(--text-3)' }}>{data.isin}</span>}
          </div>
        </div>
        <div className="stock-header-right">
          <div className="stock-price">
            <span className="stock-price-unit">₹</span>
            {data.price?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="stock-change-row">
            <span className={`stock-change ${isUp ? 'up' : 'down'}`}>
              {isUp ? '+' : ''}{fmt(data.change)} ({isUp ? '+' : ''}{fmt(data.change_pct)}%)
            </span>
          </div>
          {data.vwap && (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
              VWAP ₹{fmt(data.vwap)}
            </div>
          )}
          <button className={`watchlist-btn ${isWatchlisted ? 'active' : ''}`} onClick={onAddWatchlist}>
            {isWatchlisted ? '★ Watchlisted' : '☆ Add to watchlist'}
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{
        display: 'flex', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-1)', paddingLeft: 24, gap: 0,
      }}>
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '10px 20px',
              fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 500,
              color: activeTab === tab ? 'var(--text-1)' : 'var(--text-3)',
              borderBottom: activeTab === tab ? '2px solid var(--blue)' : '2px solid transparent',
              transition: 'all 0.15s',
              marginBottom: '-1px',
            }}
          >{tab}</button>
        ))}
      </div>

      {/* ── Overview Tab ── */}
      {activeTab === 'Overview' && (
        <>
          <PriceChart symbol={data.symbol} isUp={isUp} />

          {/* Key metrics */}
          <div className="metrics-section">
            <div className="section-title">Price & volume</div>
            <div className="metrics-grid">
              <MetricCard label="Open"          value={`₹${fmt(data.open)}`} />
              <MetricCard label="High (today)"  value={`₹${fmt(data.high)}`} />
              <MetricCard label="Low (today)"   value={`₹${fmt(data.low)}`} />
              <MetricCard label="Prev close"    value={`₹${fmt(data.prev_close)}`} />
              <MetricCard label="VWAP"          value={data.vwap ? `₹${fmt(data.vwap)}` : '—'} />
              <MetricCard label="Volume"        value={fmtVolume(data.volume)} />
              <MetricCard label="Delivery vol"  value={fmtVolume(data.delivery_qty)} />
              <MetricCard label="Delivery %"
                value={data.delivery_pct != null ? `${fmt(data.delivery_pct)}%` : '—'}
                highlight={data.delivery_pct > 60 ? 'var(--green)' : data.delivery_pct < 25 ? 'var(--red)' : undefined}
              />
            </div>
          </div>

          <div className="metrics-section">
            <div className="section-title">Valuation & fundamentals</div>
            <div className="metrics-grid">
              <MetricCard label="Market cap"    value={fmtLargeNum(data.market_cap)} />
              <MetricCard label="P/E ratio"     value={fmt(data.pe_ratio)} />
              <MetricCard label="P/B ratio"     value={fmt(data.pb_ratio)} />
              <MetricCard label="EPS (TTM)"     value={data.eps != null ? `₹${fmt(data.eps)}` : '—'} />
              <MetricCard label="Dividend yield" value={data.dividend_yield != null ? `${(data.dividend_yield * 100).toFixed(2)}%` : '—'} />
              <MetricCard label="Face value"    value={data.face_value != null ? `₹${fmt(data.face_value)}` : '—'} />
              <MetricCard label="Book value"    value={data.book_value != null ? `₹${fmt(data.book_value)}` : '—'} />
              <MetricCard label="Debt / Equity" value={fmt(data.debt_to_equity)} />
              <MetricCard label="ROE"           value={data.roe != null ? `${(data.roe * 100).toFixed(2)}%` : '—'} />
              <MetricCard label="ROA"           value={data.roa != null ? `${(data.roa * 100).toFixed(2)}%` : '—'} />
              <MetricCard label="ROCE"          value={data.roce != null ? `${(data.roce * 100).toFixed(2)}%` : '—'} />
            </div>
          </div>

          {/* 52-week range */}
          {data.week_52_high && data.week_52_low && (
            <div className="week52-section">
              <div className="section-title">52-week range</div>
              <div className="week52-bar-wrap">
                <div className="week52-labels">
                  <span>₹{fmt(data.week_52_low)} Low</span>
                  <span>Current ₹{data.price?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                  <span>High ₹{fmt(data.week_52_high)}</span>
                </div>
                <div className="week52-bar-track">
                  <div className="week52-bar-fill" style={{ width: `${Math.min(100, Math.max(0, week52Pct))}%` }} />
                  {week52Pct !== null && (
                    <div className="week52-marker" style={{ left: `${Math.min(100, Math.max(0, week52Pct))}%` }} />
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Company info */}
          {(data.sector || data.industry || data.isin) && (
            <div className="company-section">
              <div className="section-title">Company info</div>
              <div className="company-meta-grid">
                {data.sector   && <div className="company-meta-item"><span className="company-meta-label">Sector</span><span className="company-meta-value">{data.sector}</span></div>}
                {data.industry && <div className="company-meta-item"><span className="company-meta-label">Industry</span><span className="company-meta-value">{data.industry}</span></div>}
                {data.exchange && <div className="company-meta-item"><span className="company-meta-label">Exchange</span><span className="company-meta-value">{data.exchange}</span></div>}
                {data.isin     && <div className="company-meta-item"><span className="company-meta-label">ISIN</span><span className="company-meta-value" style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{data.isin}</span></div>}
                {data.face_value && <div className="company-meta-item"><span className="company-meta-label">Face value</span><span className="company-meta-value">₹{fmt(data.face_value)}</span></div>}
                {data.series   && <div className="company-meta-item"><span className="company-meta-label">Series</span><span className="company-meta-value">{data.series}</span></div>}
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Financials Tab ── */}
      {activeTab === 'Financials' && <FinancialsTab symbol={data.symbol} />}

      {/* ── News & PESTEL Tab ── */}
      {activeTab === 'News & PESTEL' && <NewsTab symbol={data.symbol} />}

      {/* ── Shareholding Tab ── */}
      {activeTab === 'Shareholding' && <ShareholdingTab symbol={data.symbol} />}

    </div>
  )
}
