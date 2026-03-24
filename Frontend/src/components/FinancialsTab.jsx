import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, Legend,
} from 'recharts'
import { fetchFinancials } from '../api/client'

function fmt(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(1)}L Cr`
  if (Math.abs(n) >= 1e3) return `₹${(n / 1e3).toFixed(1)}K Cr`
  return `₹${n.toFixed(1)} Cr`
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-2)', border: '1px solid var(--border)',
      borderRadius: 6, padding: '8px 12px', fontSize: 12,
    }}>
      <div style={{ color: 'var(--text-3)', marginBottom: 4, fontFamily: 'var(--font-mono)', fontSize: 11 }}>
        {label}
      </div>
      {payload.map(p => (
        <div key={p.name} style={{ color: p.color, fontFamily: 'var(--font-mono)' }}>
          {p.name}: {p.value != null ? fmt(p.value) : '—'}
        </div>
      ))}
    </div>
  )
}

export default function FinancialsTab({ symbol }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchFinancials(symbol)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [symbol])

  if (loading) return (
    <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-3)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
      Loading financials...
    </div>
  )

  if (error || !data?.quarters?.length) return (
    <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
      <div style={{ fontSize: 24, marginBottom: 8 }}>📊</div>
      Quarterly financials not available for this stock yet.
      <div style={{ fontSize: 11, marginTop: 8, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
        NSE may not publish results for this symbol
      </div>
    </div>
  )

  const quarters = [...data.quarters].reverse()

  return (
    <div style={{ padding: '20px 24px' }}>

      {/* Revenue chart */}
      <div style={{ marginBottom: 28 }}>
        <div className="section-title">Revenue (₹ Cr) — quarterly</div>
        <div style={{ height: 200 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={quarters} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
              <XAxis dataKey="period" tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={v => fmt(v)} tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} width={70} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="income" name="Revenue" fill="#58a6ff" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Profit chart */}
      <div style={{ marginBottom: 28 }}>
        <div className="section-title">Net profit (₹ Cr) — quarterly</div>
        <div style={{ height: 200 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={quarters} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
              <XAxis dataKey="period" tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={v => fmt(v)} tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} width={70} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="profit" name="Net Profit"
                fill="transparent"
                stroke="#3fb950"
                strokeWidth={1.5}
                radius={[3, 3, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* EPS line */}
      {quarters.some(q => q.eps != null) && (
        <div style={{ marginBottom: 28 }}>
          <div className="section-title">EPS (₹) — quarterly</div>
          <div style={{ height: 160 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={quarters} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
                <XAxis dataKey="period" tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} width={50} />
                <Tooltip content={<ChartTooltip />} />
                <Line type="monotone" dataKey="eps" name="EPS" stroke="#e3b341" strokeWidth={2} dot={{ fill: '#e3b341', strokeWidth: 0, r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="section-title">Quarterly results table</div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{
          width: '100%', borderCollapse: 'collapse',
          fontFamily: 'var(--font-mono)', fontSize: 12,
        }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Quarter', 'Revenue', 'Net Profit', 'EBITDA', 'EPS'].map(h => (
                <th key={h} style={{
                  padding: '8px 12px', textAlign: h === 'Quarter' ? 'left' : 'right',
                  color: 'var(--text-3)', fontWeight: 500, fontSize: 10,
                  textTransform: 'uppercase', letterSpacing: '0.04em',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...quarters].reverse().map((q, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border-light)' }}>
                <td style={{ padding: '8px 12px', color: 'var(--text-2)' }}>{q.period}</td>
                <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-1)' }}>{fmt(q.income)}</td>
                <td style={{ padding: '8px 12px', textAlign: 'right', color: (q.profit ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {fmt(q.profit)}
                </td>
                <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-1)' }}>{fmt(q.ebitda)}</td>
                <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--amber)' }}>
                  {q.eps != null ? `₹${q.eps.toFixed(2)}` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
