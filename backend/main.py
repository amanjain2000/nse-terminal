from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import httpx
import asyncio
import time
import random
from concurrent.futures import ThreadPoolExecutor
from stocks_list import NSE_STOCKS

app = FastAPI(title="NSE Stock Terminal API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# ── NSE Direct Client ────────────────────────────────────────────────────────
# NSE India's own public API — works from cloud IPs, no auth needed.
# Pattern: hit the homepage first to get cookies, then call the API.

NSE_BASE    = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/",
    "Origin":          "https://www.nseindia.com",
    "DNT":             "1",
    "Connection":      "keep-alive",
}

_nse_session: httpx.Client | None = None
_nse_session_time: float = 0
SESSION_TTL = 300   # refresh session every 5 min


def get_nse_session() -> httpx.Client:
    global _nse_session, _nse_session_time
    if _nse_session and time.time() - _nse_session_time < SESSION_TTL:
        return _nse_session
    if _nse_session:
        try: _nse_session.close()
        except: pass
    client = httpx.Client(
        headers=NSE_HEADERS,
        follow_redirects=True,
        timeout=15,
    )
    try:
        # Hit homepage to acquire session cookies
        client.get(NSE_BASE + "/", timeout=10)
        time.sleep(0.3)
    except Exception:
        pass
    _nse_session = client
    _nse_session_time = time.time()
    return client


def nse_get(path: str) -> dict | list:
    client = get_nse_session()
    url = NSE_BASE + path
    try:
        r = client.get(url, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception:
        # Session may have expired — refresh once and retry
        global _nse_session_time
        _nse_session_time = 0
        client = get_nse_session()
        r = client.get(url, timeout=12)
        r.raise_for_status()
        return r.json()


# ── Index name map ───────────────────────────────────────────────────────────
NSE_INDEX_NAMES = {
    "NIFTY 50":          "NIFTY 50",
    "NIFTY BANK":        "NIFTY BANK",
    "NIFTY IT":          "NIFTY IT",
    "NIFTY PHARMA":      "NIFTY PHARMA",
    "NIFTY AUTO":        "NIFTY AUTO",
    "NIFTY FMCG":        "NIFTY FMCG",
    "NIFTY METAL":       "NIFTY METAL",
    "NIFTY REALTY":      "NIFTY REALTY",
    "NIFTY ENERGY":      "NIFTY ENERGY",
    "NIFTY PSU BANK":    "NIFTY PSU BANK",
    "NIFTY MEDIA":       "NIFTY MEDIA",
    "NIFTY MIDCAP 100":  "NIFTY MIDCAP 100",
    "INDIA VIX":         "INDIA VIX",
}

DISPLAY_INDICES  = ["NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA", "INDIA VIX"]
DISPLAY_SECTORS  = ["NIFTY IT", "NIFTY BANK", "NIFTY PHARMA", "NIFTY AUTO",
                    "NIFTY FMCG", "NIFTY METAL", "NIFTY REALTY",
                    "NIFTY ENERGY", "NIFTY PSU BANK", "NIFTY MEDIA"]

SECTOR_LABELS = {
    "NIFTY IT":      "IT",
    "NIFTY BANK":    "Bank",
    "NIFTY PHARMA":  "Pharma",
    "NIFTY AUTO":    "Auto",
    "NIFTY FMCG":    "FMCG",
    "NIFTY METAL":   "Metal",
    "NIFTY REALTY":  "Realty",
    "NIFTY ENERGY":  "Energy",
    "NIFTY PSU BANK":"PSU Bank",
    "NIFTY MEDIA":   "Media",
}


def _fetch_all_indices():
    """Fetch all NSE indices in one call."""
    data = nse_get("/api/allIndices")
    # Response: {"data": [...], "timestamp": "..."}
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
    """Get full stock quote from NSE."""
    data = nse_get(f"/api/quote-equity?symbol={symbol}")
    price_info  = data.get("priceInfo", {})
    metadata    = data.get("metadata",  {})
    industry    = data.get("industryInfo", {})
    securities  = data.get("securityInfo", {})

    ltp         = price_info.get("lastPrice", 0)
    prev_close  = price_info.get("previousClose", 0)
    change      = price_info.get("change", 0)
    change_pct  = price_info.get("pChange", 0)
    week52      = price_info.get("weekHighLow", {})

    def fn(v):
        try: return round(float(v), 2) if v not in (None, "", "–", "-") else None
        except: return None

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
        "volume":         None,   # not in this endpoint
        "avg_volume":     None,
        "market_cap":     None,   # NSE quote doesn't include mcap directly
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
    }


def _fetch_history_yf(yf_sym: str, period: str, interval: str):
    """Price history from yfinance — download endpoint is far less restricted."""
    t = yf.Ticker(yf_sym)
    return t.history(period=period, interval=interval)


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/indices")
async def get_indices():
    cached = cache_get("indices")
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    try:
        all_idx = await loop.run_in_executor(executor, _fetch_all_indices)
    except Exception as e:
        raise HTTPException(502, f"NSE API error: {e}")

    result = []
    for name in DISPLAY_INDICES:
        d = all_idx.get(name)
        if d:
            result.append({"name": name, "symbol": name, **d})

    cache_set("indices", result, ttl=90)
    return result


@app.get("/api/sectors")
async def get_sectors():
    cached = cache_get("sectors")
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    try:
        all_idx = await loop.run_in_executor(executor, _fetch_all_indices)
    except Exception as e:
        raise HTTPException(502, f"NSE API error: {e}")

    result = []
    for nse_name in DISPLAY_SECTORS:
        d = all_idx.get(nse_name)
        if d:
            result.append({
                "name":       SECTOR_LABELS.get(nse_name, nse_name),
                "change_pct": d["change_pct"],
                "price":      d["price"],
            })

    cache_set("sectors", result, ttl=90)
    return result


@app.get("/api/search")
async def search(q: str = Query(...)):
    q_lower = q.strip().lower()
    if not q_lower:
        return []
    matches = [
        s for s in NSE_STOCKS
        if q_lower in s["symbol"].lower() or q_lower in s["name"].lower()
    ]
    return matches[:20]


@app.get("/api/stock/{symbol}")
async def get_stock(symbol: str):
    sym       = symbol.upper().strip()
    cache_key = f"stock:{sym}"
    cached    = cache_get(cache_key)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _fetch_nse_quote, sym)
        cache_set(cache_key, data, ttl=60)
        return data
    except Exception as e:
        raise HTTPException(500, f"Could not fetch {sym}: {str(e)}")


@app.get("/api/stock/{symbol}/history")
async def get_history(symbol: str, period: str = "1m"):
    sym       = symbol.upper().strip()
    yf_sym    = f"{sym}.NS"
    cache_key = f"hist:{sym}:{period}"
    cached    = cache_get(cache_key)
    if cached:
        return cached

    period_map = {
        "1d": ("1d",  "5m"),
        "1w": ("5d",  "30m"),
        "1m": ("1mo", "1d"),
        "3m": ("3mo", "1d"),
        "1y": ("1y",  "1wk"),
        "5y": ("5y",  "1mo"),
    }
    yf_period, yf_interval = period_map.get(period, ("1mo", "1d"))

    loop = asyncio.get_event_loop()
    try:
        hist = await loop.run_in_executor(
            executor, _fetch_history_yf, yf_sym, yf_period, yf_interval
        )
        if hist.empty:
            raise HTTPException(404, "No history data")

        result = [
            {
                "time":   idx.isoformat(),
                "open":   round(float(row["Open"]),  2),
                "high":   round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
            for idx, row in hist.iterrows()
        ]
        ttl = 300 if period in ("1m", "3m", "1y", "5y") else 60
        cache_set(cache_key, result, ttl=ttl)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
