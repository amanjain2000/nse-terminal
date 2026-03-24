import { useState, useCallback } from 'react'
import IndexBar from './components/IndexBar'
import Sidebar from './components/Sidebar'
import StockDetail from './components/StockDetail'
import MarketOverview from './components/MarketOverview'
import { fetchStock } from './api/client'

export default function App() {
  const [stockData, setStockData] = useState(null)
  const [selectedSym, setSelectedSym] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [watchlist, setWatchlist] = useState(() => {
    try { return JSON.parse(localStorage.getItem('nse_watchlist') || '[]') }
    catch { return [] }
  })

  const loadStock = useCallback(async (symbol) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchStock(symbol)
      setStockData(data)
      setSelectedSym(symbol)
    } catch {
      setError(`Could not load data for ${symbol}. Check the symbol and try again.`)
      setStockData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const addToWatchlist = useCallback((stock) => {
    setWatchlist(prev => {
      if (prev.find(s => s.symbol === stock.symbol)) return prev
      const next = [...prev, { symbol: stock.symbol, name: stock.name }]
      localStorage.setItem('nse_watchlist', JSON.stringify(next))
      return next
    })
  }, [])

  const removeFromWatchlist = useCallback((symbol) => {
    setWatchlist(prev => {
      const next = prev.filter(s => s.symbol !== symbol)
      localStorage.setItem('nse_watchlist', JSON.stringify(next))
      return next
    })
  }, [])

  return (
    <div className="app">
      <IndexBar />
      <div className="main-layout">
        <Sidebar
          onSelectStock={loadStock}
          watchlist={watchlist}
          onRemoveWatchlist={removeFromWatchlist}
          activeSymbol={selectedSym}
        />
        <main className="content">
          {loading && (
            <div className="loading-state">
              <div className="loading-spinner" />
              <span>Fetching market data...</span>
            </div>
          )}
          {!loading && error && (
            <div style={{ padding: 24, color: 'var(--red)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
              {error}
            </div>
          )}
          {!loading && !error && stockData && (
            <StockDetail
              data={stockData}
              onAddWatchlist={() => addToWatchlist(stockData)}
              isWatchlisted={watchlist.some(s => s.symbol === stockData.symbol)}
            />
          )}
          {!loading && !error && !stockData && (
            <MarketOverview onSelectStock={loadStock} />
          )}
        </main>
      </div>
    </div>
  )
}
