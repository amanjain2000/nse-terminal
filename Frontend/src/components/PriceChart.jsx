import { useState, useEffect } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { fetchHistory } from '../api/client'

const PERIODS = ['1d', '1w', '1m', '3m', '1y', '5y']

function formatTime(iso, period) {
  const d = new Date(iso)
  if (period === '1d') return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })
  if (period === '1w') return d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric' })
  if (period === '5y') return d.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

function CustomTooltip({ active, payload, label, period }) {
  if (!active || !payload?.length) return null
  const d = payload[0].value
  return (
    <div style={{
      background: 'var(--bg-2)',
      border: '1px solid var(--border)',
      borderRadius: '6px',
      padding: '8px 12px',
    }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>
        {formatTime(label, period)}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--text-1)' }}>
        ₹{d?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
    </div>
  )
}

export default function PriceChart({ symbol, isUp }) {
  const [period, setPeriod] = useState('1m')
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  const color = isUp ? 'var(--green)' : 'var(--red)'
  const colorFill = isUp ? 'rgba(63,185,80,0.15)' : 'rgba(248,81,73,0.15)'

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchHistory(symbol, period)
      .then(raw => {
        if (!alive) return
        setData(raw.map(r => ({ time: r.time, close: r.close, volume: r.volume })))
        setLoading(false)
      })
      .catch(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [symbol, period])

  return (
    <div className="chart-section">
      <div className="chart-header">
        <span className="chart-title">Price chart</span>
        <div className="period-selector">
          {PERIODS.map(p => (
            <button
              key={p}
              className={`period-btn ${period === p ? 'active' : ''}`}
              onClick={() => setPeriod(p)}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="chart-loading">Loading chart...</div>
      ) : (
        <div className="chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={isUp ? '#3fb950' : '#f85149'} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={isUp ? '#3fb950' : '#f85149'} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
              <XAxis
                dataKey="time"
                tickFormatter={v => formatTime(v, period)}
                tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-3)' }}
                axisLine={false}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={['auto', 'auto']}
                tickFormatter={v => `₹${v.toLocaleString('en-IN')}`}
                tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-3)' }}
                axisLine={false}
                tickLine={false}
                width={80}
              />
              <Tooltip content={<CustomTooltip period={period} />} />
              <Area
                type="monotone"
                dataKey="close"
                stroke={color}
                strokeWidth={1.5}
                fill="url(#chartGrad)"
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0, fill: color }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
