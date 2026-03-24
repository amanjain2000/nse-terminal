from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import httpx
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from stocks_list import NSE_STOCKS

app = FastAPI(title="NSE Stock Terminal API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
executor = ThreadPoolExecutor(max_workers=3)

# ── Cache ────────────────────────────────────────────────────────────────────
_cache: dict = {}

def cache_get(key):
    e = _cache.get(key)
    if e and time.time() < e["exp"]:
        return e["val"]
    return None

def cache_set(key, val, ttl):
    _cache[key] = {"val": val, "exp": time.time() + ttl}

# ── NSE Session ───────────────────────────────────────────────────────────────
NSE_BASE = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Origin": "https://www.nseindia.com",
    "DNT": "1",
    "Connection": "keep-alive",
}

_nse_session: httpx.Client | None = None
_nse_session_time: float = 0
SESSION_TTL = 300

def get_nse_session() -> httpx.Client:
    global _nse_session, _nse_session_time
    if _nse_session and time.time() - _nse_session_time < SESSION_TTL:
        return _nse_session
    if _nse_session:
        try: _nse_session.close()
        except: pass
    client = httpx.Client(headers=NSE_HEADERS, follow_redirects=True, timeout=15)
    try:
        client.get(NSE_BASE + "/", timeout=10)
        time.sleep(0.3)
    except: pass
    _nse_session = client
    _nse_session_time = time.time()
    return client

def nse_get(path: str) -> dict | list:
    import json, gzip
    client = get_nse_session()
    url = NSE_BASE + path

    def _decode(r):
        content = r.content
        enc = r.headers.get("Content-Encoding", "").lower()
        try:
            if "br" in enc:
                import brotli
                content = brotli.decompress(content)
            elif "gzip" in enc:
                content = gzip.decompress(content)
        except: pass
        try:
            return json.loads(content.decode("utf-8", errors="ignore"))
        except:
            raise Exception(f"Invalid NSE response: {content[:120]}")

    try:
        r = client.get(url, timeout=12)
        r.raise_for_status()
        return _decode(r)
    except:
        global _nse_session_time
        _nse_session_time = 0
        client = get_nse_session()
        r = client.get(url, timeout=12)
        r.raise_for_status()
        return _decode(r)

# ── Index maps ────────────────────────────────────────────────────────────────
DISPLAY_INDICES = ["NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA", "INDIA VIX"]
DISPLAY_SECTORS = ["NIFTY IT", "NIFTY BANK", "NIFTY PHARMA", "NIFTY AUTO",
                   "NIFTY FMCG", "NIFTY METAL", "NIFTY REALTY",
                   "NIFTY ENERGY", "NIFTY PSU BANK", "NIFTY MEDIA"]
SECTOR_LABELS = {
    "NIFTY IT": "IT", "NIFTY BANK": "Bank", "NIFTY PHARMA": "Pharma",
    "NIFTY AUTO": "Auto", "NIFTY FMCG": "FMCG", "NIFTY METAL": "Metal",
    "NIFTY REALTY": "Realty", "NIFTY ENERGY": "Energy",
    "NIFTY PSU BANK": "PSU Bank", "NIFTY MEDIA": "Media",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def fn(v):
    try: return round(float(v), 2) if v not in (None, "", "–", "-", "--") else None
    except: return None

def fn_int(v):
    try: return int(float(v)) if v not in (None, "", "–", "-", "--") else None
    except: return None

def _fetch_all_indices():
    data = nse_get("/api/allIndices")
    rows = data.get("data", [])
    result = {}
    for row in rows:
        name = row.get("index", "")
        result[name] = {
            "price":      round(float(row.get("last", 0) or 0), 2),
            "change":     round(float(row.get("variation", 0) or 0), 2),
            "change_pct": round(float(row.get("percentChange", 0) or 0), 2),
        }
    return result

def _fetch_nse_quote(symbol: str) -> dict:
    """Full stock quote: basic info + trade_info for volume/mcap."""
    # Fetch both endpoints
    data       = nse_get(f"/api/quote-equity?symbol={symbol}")
    try:
        trade_data = nse_get(f"/api/quote-equity?symbol={symbol}&section=trade_info")
    except:
        trade_data = {}

    price_info = data.get("priceInfo", {})
    metadata   = data.get("metadata",  {})
    industry   = data.get("industryInfo", {})
    securities = data.get("securityInfo", {})

    # Trade info fields
    trade_info = trade_data.get("marketDeptOrderBook", {})
    trade_summary = trade_data.get("securityWiseDP", {})
    market_cap_raw = (
        metadata.get("totalMarketCap")
        or metadata.get("ffmc")
        or trade_data.get("marketCapFull")
    )

    ltp        = price_info.get("lastPrice", 0)
    prev_close = price_info.get("previousClose", 0)
    change     = price_info.get("change", 0)
    change_pct = price_info.get("pChange", 0)
    week52     = price_info.get("weekHighLow", {})
    vwap       = price_info.get("vwap")

    # Volume from trade info
    volume     = fn_int(trade_summary.get("quantityTraded") or trade_info.get("totalBuyQuantity"))
    delivery_qty = fn_int(trade_summary.get("deliveryQuantity"))
    delivery_pct = fn(trade_summary.get("deliveryToTradedQuantity"))

    return {
        "symbol":         symbol,
        "name":           metadata.get("companyName", symbol),
        "price":          fn(ltp),
        "change":         fn(change),
        "change_pct":     fn(change_pct),
        "open":           fn(price_info.get("open")),
        "high":           fn(price_info.get("intraDayHighLow", {}).get("max")),
        "low":            fn(price_info.get("intraDayHighLow", {}).get("min")),
        "prev_close":     fn(prev_close),
        "vwap":           fn(vwap),
        "volume":         volume,
        "delivery_qty":   delivery_qty,
        "delivery_pct":   delivery_pct,
        "avg_volume":     None,
        "market_cap":     fn_int(market_cap_raw) if market_cap_raw else None,
        "pe_ratio":       fn(metadata.get("pdSymbolPe")),
        "pb_ratio":       None,
        "dividend_yield": None,
        "week_52_high":   fn(week52.get("max")),
        "week_52_low":    fn(week52.get("min")),
        "sector":         industry.get("macro", ""),
        "industry":       industry.get("sector", ""),
        "description":    "",
        "eps":            None,
        "book_value":     None,
        "debt_to_equity": None,
        "roe":            None,
        "roa":            None,
        "employees":      None,
        "website":        "",
        "exchange":       "NSE",
        "currency":       "INR",
        "isin":           securities.get("isin", ""),
        "face_value":     fn(securities.get("faceVal")),
        "series":         metadata.get("series", "EQ"),
    }

def _fetch_financials(symbol: str) -> dict:
    """Quarterly P&L results from NSE financials API."""
    try:
        data = nse_get(f"/api/financials-results?index=equities&symbol={symbol}")
    except Exception as e:
        return {"error": str(e), "quarters": []}

    # NSE returns a list of result objects
    results = data if isinstance(data, list) else data.get("data", [])

    quarters = []
    for item in results[:8]:   # last 8 quarters
        period = item.get("period") or item.get("toDate") or item.get("fromDate", "")
        income = (
            item.get("totalIncome")
            or item.get("netSales")
            or item.get("income")
            or item.get("revenue")
        )
        profit = (
            item.get("netProfit")
            or item.get("profitAfterTax")
            or item.get("pat")
        )
        ebitda = item.get("ebitda") or item.get("operatingProfit")
        eps    = item.get("eps") or item.get("basicEps") or item.get("dilutedEps")

        quarters.append({
            "period":  str(period)[:10],
            "income":  fn(income),
            "profit":  fn(profit),
            "ebitda":  fn(ebitda),
            "eps":     fn(eps),
        })

    return {"quarters": quarters}

def _fetch_shareholding(symbol: str) -> dict:
    """Promoter / FII / DII / Public shareholding pattern."""
    try:
        data = nse_get(f"/api/shareholding-patterns?index=equities&symbol={symbol}")
    except Exception as e:
        return {"error": str(e), "history": []}

    # NSE returns {"data": [...]} where each item is a quarter's snapshot
    records = data if isinstance(data, list) else data.get("data", [])

    history = []
    for rec in records[:6]:  # last 6 quarters
        date = rec.get("date") or rec.get("period") or ""
        sh = rec.get("shareholding", {}) or rec

        def pct(keys):
            for k in keys:
                v = sh.get(k)
                if v is not None:
                    try: return round(float(v), 2)
                    except: pass
            return None

        history.append({
            "date":     str(date)[:10],
            "promoter": pct(["promoter", "promoterAndPromoterGroup", "Promoter & Promoter Group"]),
            "fii":      pct(["fii", "fpi", "FIIs", "Foreign Institutional Investors"]),
            "dii":      pct(["dii", "DIIs", "Domestic Institutional Investors"]),
            "public":   pct(["public", "Public"]),
            "mutual_fund": pct(["mutualFunds", "Mutual Funds"]),
        })

    return {"history": history}

def _fetch_history_yf(yf_sym: str, period: str, interval: str):
    t = yf.Ticker(yf_sym)
    return t.history(period=period, interval=interval)

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/indices")
async def get_indices():
    cached = cache_get("indices")
    if cached: return cached
    loop = asyncio.get_event_loop()
    try:
        all_idx = await loop.run_in_executor(executor, _fetch_all_indices)
    except Exception as e:
        raise HTTPException(502, f"NSE API error: {e}")
    result = [{"name": n, "symbol": n, **d} for n in DISPLAY_INDICES if (d := all_idx.get(n))]
    cache_set("indices", result, ttl=90)
    return result

@app.get("/api/sectors")
async def get_sectors():
    cached = cache_get("sectors")
    if cached: return cached
    loop = asyncio.get_event_loop()
    try:
        all_idx = await loop.run_in_executor(executor, _fetch_all_indices)
    except Exception as e:
        raise HTTPException(502, f"NSE API error: {e}")
    result = [
        {"name": SECTOR_LABELS.get(n, n), "change_pct": d["change_pct"], "price": d["price"]}
        for n in DISPLAY_SECTORS if (d := all_idx.get(n))
    ]
    cache_set("sectors", result, ttl=90)
    return result

@app.get("/api/search")
async def search(q: str = Query(...)):
    q_lower = q.strip().lower()
    if not q_lower: return []
    return [s for s in NSE_STOCKS if q_lower in s["symbol"].lower() or q_lower in s["name"].lower()][:20]

@app.get("/api/stock/{symbol}")
async def get_stock(symbol: str):
    sym = symbol.upper().strip()
    cached = cache_get(f"stock:{sym}")
    if cached: return cached
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _fetch_nse_quote, sym)
        cache_set(f"stock:{sym}", data, ttl=60)
        return data
    except Exception as e:
        raise HTTPException(500, f"Could not fetch {sym}: {e}")

@app.get("/api/stock/{symbol}/financials")
async def get_financials(symbol: str):
    sym = symbol.upper().strip()
    cached = cache_get(f"fin:{sym}")
    if cached: return cached
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _fetch_financials, sym)
        cache_set(f"fin:{sym}", data, ttl=3600)  # 1hr — financials don't change often
        return data
    except Exception as e:
        raise HTTPException(500, f"Financials error for {sym}: {e}")

@app.get("/api/stock/{symbol}/shareholding")
async def get_shareholding(symbol: str):
    sym = symbol.upper().strip()
    cached = cache_get(f"sh:{sym}")
    if cached: return cached
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _fetch_shareholding, sym)
        cache_set(f"sh:{sym}", data, ttl=3600)
        return data
    except Exception as e:
        raise HTTPException(500, f"Shareholding error for {sym}: {e}")

@app.get("/api/stock/{symbol}/history")
async def get_history(symbol: str, period: str = "1m"):
    sym = symbol.upper().strip()
    yf_sym = f"{sym}.NS"
    cached = cache_get(f"hist:{sym}:{period}")
    if cached: return cached
    period_map = {
        "1d": ("1d", "5m"), "1w": ("5d", "30m"),
        "1m": ("1mo", "1d"), "3m": ("3mo", "1d"),
        "1y": ("1y", "1wk"), "5y": ("5y", "1mo"),
    }
    yf_period, yf_interval = period_map.get(period, ("1mo", "1d"))
    loop = asyncio.get_event_loop()
    try:
        hist = await loop.run_in_executor(executor, _fetch_history_yf, yf_sym, yf_period, yf_interval)
        if hist.empty: raise HTTPException(404, "No history data")
        result = [
            {"time": idx.isoformat(), "open": round(float(r["Open"]), 2),
             "high": round(float(r["High"]), 2), "low": round(float(r["Low"]), 2),
             "close": round(float(r["Close"]), 2), "volume": int(r["Volume"])}
            for idx, r in hist.iterrows()
        ]
        ttl = 300 if period in ("1m", "3m", "1y", "5y") else 60
        cache_set(f"hist:{sym}:{period}", result, ttl=ttl)
        return result
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, str(e))
