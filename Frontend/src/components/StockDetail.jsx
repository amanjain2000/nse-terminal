import PriceChart from './PriceChart'

function fmt(v, decimals = 2) {
  if (v == null) return '—'
  return Number(v).toFixed(decimals)
}

function fmtLargeNum(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (n >= 1e12) return `₹${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9) return `₹${(n / 1e9).toFixed(2)}B`
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`
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

function fmtPct(v) {
  if (v == null) return '—'
  return `${(Number(v) * 100).toFixed(2)}%`
}

function MetricCard({ label, value }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${value === '—' ? 'null-val' : ''}`}>{value}</div>
    </div>
  )
}

export default function StockDetail({ data, onAddWatchlist, isWatchlisted }) {
  const isUp = (data.change_pct || 0) >= 0

  const week52Pct = data.week_52_high && data.week_52_low && data.price
    ? ((data.price - data.week_52_low) / (data.week_52_high - data.week_52_low)) * 100
    : null

  return (
    <div className="stock-detail fade-in">

      {/* Header */}
      <div className="stock-header">
        <div className="stock-header-left">
          <div className="stock-symbol">{data.symbol}</div>
          <div className="stock-full-name">{data.name}</div>
          <div className="stock-meta-row">
            <span className="meta-tag">NSE</span>
            {data.sector && <span className="meta-tag">{data.sector}</span>}
            {data.industry && <span className="meta-tag">{data.industry}</span>}
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
          <button
            className={`watchlist-btn ${isWatchlisted ? 'active' : ''}`}
            onClick={onAddWatchlist}
          >
            {isWatchlisted ? '★ Watchlisted' : '☆ Add to watchlist'}
          </button>
        </div>
      </div>

      {/* Chart */}
      <PriceChart symbol={data.symbol} isUp={isUp} />

      {/* Key Metrics */}
      <div className="metrics-section">
        <div className="section-title">Key metrics</div>
        <div className="metrics-grid">
          <MetricCard label="Open" value={`₹${fmt(data.open)}`} />
          <MetricCard label="High (today)" value={`₹${fmt(data.high)}`} />
          <MetricCard label="Low (today)" value={`₹${fmt(data.low)}`} />
          <MetricCard label="Prev close" value={`₹${fmt(data.prev_close)}`} />
          <MetricCard label="Volume" value={fmtVolume(data.volume)} />
          <MetricCard label="Avg volume" value={fmtVolume(data.avg_volume)} />
          <MetricCard label="Market cap" value={fmtLargeNum(data.market_cap)} />
          <MetricCard label="P/E ratio" value={fmt(data.pe_ratio)} />
          <MetricCard label="P/B ratio" value={fmt(data.pb_ratio)} />
          <MetricCard label="EPS (TTM)" value={data.eps != null ? `₹${fmt(data.eps)}` : '—'} />
          <MetricCard label="Book value" value={data.book_value != null ? `₹${fmt(data.book_value)}` : '—'} />
          <MetricCard label="Debt / Equity" value={fmt(data.debt_to_equity)} />
          <MetricCard label="ROE" value={fmtPct(data.roe)} />
          <MetricCard label="ROA" value={fmtPct(data.roa)} />
          <MetricCard label="Dividend yield" value={data.dividend_yield != null ? `${(data.dividend_yield * 100).toFixed(2)}%` : '—'} />
          <MetricCard label="Employees" value={data.employees?.toLocaleString('en-IN') || '—'} />
        </div>
      </div>

      {/* 52-week range */}
      {data.week_52_high && data.week_52_low && (
        <div className="week52-section">
          <div className="section-title">52-week range</div>
          <div className="week52-bar-wrap">
            <div className="week52-labels">
              <span>₹{fmt(data.week_52_low)} Low</span>
              <span>
                Current: ₹{data.price?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
              <span>High ₹{fmt(data.week_52_high)}</span>
            </div>
            <div className="week52-bar-track">
              <div
                className="week52-bar-fill"
                style={{ width: `${Math.min(100, Math.max(0, week52Pct))}%` }}
              />
              {week52Pct !== null && (
                <div
                  className="week52-marker"
                  style={{ left: `${Math.min(100, Math.max(0, week52Pct))}%` }}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Company info */}
      {(data.description || data.website || data.sector) && (
        <div className="company-section">
          <div className="section-title">Company info</div>
          {data.description && (
            <p className="company-desc">{data.description}</p>
          )}
          <div className="company-meta-grid">
            {data.sector && (
              <div className="company-meta-item">
                <span className="company-meta-label">Sector</span>
                <span className="company-meta-value">{data.sector}</span>
              </div>
            )}
            {data.industry && (
              <div className="company-meta-item">
                <span className="company-meta-label">Industry</span>
                <span className="company-meta-value">{data.industry}</span>
              </div>
            )}
            {data.exchange && (
              <div className="company-meta-item">
                <span className="company-meta-label">Exchange</span>
                <span className="company-meta-value">{data.exchange}</span>
              </div>
            )}
            {data.website && (
              <div className="company-meta-item">
                <span className="company-meta-label">Website</span>
                <a href={data.website} target="_blank" rel="noreferrer" className="company-link">
                  {data.website.replace(/^https?:\/\//, '')}
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
