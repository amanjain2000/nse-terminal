import { useState, useEffect, useRef, useCallback } from 'react'
import { searchStocks } from '../api/client'

export default function Sidebar({ onSelectStock, watchlist, onRemoveWatchlist, activeSymbol }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [showResults, setShowResults] = useState(false)
  const [searching, setSearching] = useState(false)
  const searchRef = useRef(null)
  const timerRef = useRef(null)

  const doSearch = useCallback(async (q) => {
    if (!q.trim()) { setResults([]); setShowResults(false); return }
    setSearching(true)
    try {
      const data = await searchStocks(q)
      setResults(data)
      setShowResults(true)
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }, [])

  function handleInput(e) {
    const val = e.target.value
    setQuery(val)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => doSearch(val), 300)
  }

  function selectResult(stock) {
    onSelectStock(stock.symbol)
    setQuery('')
    setResults([])
    setShowResults(false)
  }

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e) {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setShowResults(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <aside className="sidebar">
      {/* Search */}
      <div className="sidebar-section">
        <div className="sidebar-label">Search stocks</div>
        <div className="search-wrap" ref={searchRef}>
          <span className="search-icon">⌕</span>
          <input
            className="search-input"
            placeholder="Symbol or company name..."
            value={query}
            onChange={handleInput}
            onFocus={() => results.length > 0 && setShowResults(true)}
          />
          {showResults && results.length > 0 && (
            <div className="search-results">
              {results.map(r => (
                <div
                  key={r.symbol}
                  className="search-result-item"
                  onMouseDown={() => selectResult(r)}
                >
                  <div className="result-symbol">{r.symbol}</div>
                  <div className="result-name">{r.name}</div>
                  <div className="result-sector">{r.sector}</div>
                </div>
              ))}
            </div>
          )}
          {showResults && query && !searching && results.length === 0 && (
            <div className="search-results">
              <div className="search-result-item">
                <div className="result-name" style={{ color: 'var(--text-3)' }}>
                  No results — try typing the NSE symbol directly
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Watchlist */}
      <div className="sidebar-section" style={{ borderBottom: 'none', paddingBottom: 0 }}>
        <div className="sidebar-label">
          Watchlist ({watchlist.length})
        </div>
      </div>

      <div className="watchlist-list">
        {watchlist.length === 0 ? (
          <div className="watchlist-empty">
            Search for a stock and add it<br />
            to your watchlist
          </div>
        ) : (
          watchlist.map(item => (
            <div
              key={item.symbol}
              className={`watchlist-item ${activeSymbol === item.symbol ? 'active' : ''}`}
              onClick={() => onSelectStock(item.symbol)}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="watchlist-sym">{item.symbol}</div>
                <div className="watchlist-name">{item.name}</div>
              </div>
              <button
                className="watchlist-remove"
                onClick={e => { e.stopPropagation(); onRemoveWatchlist(item.symbol) }}
                title="Remove"
              >×</button>
            </div>
          ))
        )}
      </div>
    </aside>
  )
}
