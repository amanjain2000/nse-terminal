import { useState, useEffect } from 'react'
import { fetchShareholding } from '../api/client'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'

function DonutRing({ pct, color, label, value }) {
  const r = 36
  const circ = 2 * Math.PI * r
  const fill = pct != null ? Math.min(100, Math.max(0, pct)) : 0
  const dash = (fill / 100) * circ
  const gap  = circ - dash

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <svg width="88" height="88" viewBox="0 0 88 88">
        <circle cx="44" cy="44" r={r} fill="none" stroke="var(--bg-3)" strokeWidth="10" />
        <circle
          cx="44" cy="44" r={r} fill="none"
          stroke={color} strokeWidth="10"
          strokeDasharray={`${dash} ${gap}`}
          strokeLinecap="round"
          transform="rotate(-90 44 44)"
          style={{ transition: 'stroke-dasharray 0.6s ease' }}
        />
        <text x="44" y="44" textAnchor="middle" dominantBaseline="central"
          style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, fill: 'var(--text-1)' }}>
          {pct != null ? `${pct.toFixed(1)}%` : '—'}
        </text>
      </svg>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {label}
      </div>
    </div>
  )
}

const COLORS = {
  promoter:    '#58a6ff',
  fii:         '#3fb950',
  dii:         '#e3b341',
  mutual_fund: '#bc8cff',
  public:      '#6e7681',
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-2)', border: '1px solid var(--border)',
      borderRadius: 6, padding: '8px 12px', fontSize: 12,
    }}>
      <div style={{ color: 'var(--text-3)', marginBottom: 4, fontFamily: 'var(--font-mono)', fontSize: 11 }}>{label}</div>
      {payload.map(p => (
        <div key={p.name} style={{ color: p.color, fontFamily: 'var(--font-mono)' }}>
          {p.name}: {p.value != null ? `${p.value.toFixed(2)}%` : '—'}
        </div>
      ))}
    </div>
  )
}

export default function ShareholdingTab({ symbol }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchShareholding(symbol)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [symbol])

  if (loading) return (
    <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-3)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
      Loading shareholding data...
    </div>
  )

  if (error || !data?.history?.length) return (
    <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
      <div style={{ fontSize: 24, marginBottom: 8 }}>📋</div>
      Shareholding data not available for this stock.
      <div style={{ fontSize: 11, marginTop: 8, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
        NSE may not publish this data for the selected symbol
      </div>
    </div>
  )

  // Latest quarter for the donut rings
  const latest   = data.history[0] || {}
  const chartData = [...data.history].reverse()
  const hasHistory = chartData.length > 1

  return (
    <div style={{ padding: '20px 24px' }}>

      {/* Donut rings — latest snapshot */}
      <div className="section-title">
        Latest snapshot {latest.date ? `— ${latest.date}` : ''}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-around', flexWrap: 'wrap', gap: 20, marginBottom: 28, marginTop: 16 }}>
        <DonutRing pct={latest.promoter}    color={COLORS.promoter}    label="Promoter" />
        <DonutRing pct={latest.fii}         color={COLORS.fii}         label="FII / FPI" />
        <DonutRing pct={latest.dii}         color={COLORS.dii}         label="DII" />
        <DonutRing pct={latest.mutual_fund} color={COLORS.mutual_fund} label="Mutual Fund" />
        <DonutRing pct={latest.public}      color={COLORS.public}      label="Public" />
      </div>

      {/* Trend chart */}
      {hasHistory && (
        <>
          <div className="section-title">Shareholding trend</div>
          <div style={{ height: 220, marginBottom: 28, marginTop: 12 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} width={44} />
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontFamily: 'var(--font-mono)', fontSize: 11 }} />
                {latest.promoter    != null && <Area type="monotone" dataKey="promoter"    name="Promoter"    stroke={COLORS.promoter}    fill="none" strokeWidth={2} dot={{ r: 3 }} />}
                {latest.fii         != null && <Area type="monotone" dataKey="fii"         name="FII/FPI"     stroke={COLORS.fii}         fill="none" strokeWidth={2} dot={{ r: 3 }} />}
                {latest.dii         != null && <Area type="monotone" dataKey="dii"         name="DII"         stroke={COLORS.dii}         fill="none" strokeWidth={2} dot={{ r: 3 }} />}
                {latest.mutual_fund != null && <Area type="monotone" dataKey="mutual_fund" name="Mutual Fund" stroke={COLORS.mutual_fund} fill="none" strokeWidth={2} dot={{ r: 3 }} />}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {/* Table */}
      <div className="section-title">Quarterly breakdown</div>
      <div style={{ overflowX: 'auto', marginTop: 12 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Quarter', 'Promoter', 'FII/FPI', 'DII', 'Mutual Fund', 'Public'].map(h => (
                <th key={h} style={{
                  padding: '8px 12px', textAlign: h === 'Quarter' ? 'left' : 'right',
                  color: 'var(--text-3)', fontWeight: 500, fontSize: 10,
                  textTransform: 'uppercase', letterSpacing: '0.04em',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.history.map((row, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border-light)' }}>
                <td style={{ padding: '8px 12px', color: 'var(--text-2)' }}>{row.date}</td>
                {[row.promoter, row.fii, row.dii, row.mutual_fund, row.public].map((v, j) => (
                  <td key={j} style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-1)' }}>
                    {v != null ? `${v.toFixed(2)}%` : '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
