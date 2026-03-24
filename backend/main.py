from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import time
import json
import gzip
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from stocks_list import NSE_STOCKS

app = FastAPI(title="NSE Stock Terminal API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
executor = ThreadPoolExecutor(max_workers=3)

# ── Cache ─────────────────────────────────────────────────────────────────────
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
    "DNT": "1",
    "Connection": "keep-alive",
}

_nse_client: httpx.Client | None = None
_nse_client_ts: float = 0
SESSION_TTL = 240   # 4 min — refresh before NSE kills idle sessions

def _make_client() -> httpx.Client:
    client = httpx.Client(headers=NSE_HEADERS, follow_redirects=True, timeout=20)
    # Warm up: hit main page to get cookies, then the market-status page
    for warm_url in ["/", "/market-data/live-equity-market"]:
        try:
            client.get(NSE_BASE + warm_url, timeout=10)
            time.sleep(0.4)
        except:
            pass
    return client

def get_client() -> httpx.Client:
    global _nse_client, _nse_client_ts
    if _nse_client and time.time() - _nse_client_ts < SESSION_TTL:
        return _nse_client
    if _nse_client:
        try: _nse_client.close()
        except: pass
    _nse_client = _make_client()
    _nse_client_ts = time.time()
    return _nse_client

def _decode(r: httpx.Response):
    content = r.content
    enc = r.headers.get("Content-Encoding", "").lower()
    try:
        if "br" in enc:
            import brotli
            content = brotli.decompress(content)
        elif "gzip" in enc:
            content = gzip.decompress(content)
    except:
        pass
    text = content.decode("utf-8", errors="replace").strip()
    if not text:
        raise ValueError(f"Empty response from NSE (status {r.status_code})")
    return json.loads(text)

def nse_get(path: str, retry: bool = True):
    client = get_client()
    try:
        r = client.get(NSE_BASE + path, timeout=15)
        r.raise_for_status()
        return _decode(r)
    except Exception as e:
        if not retry:
            raise
        # Session expired — rebuild and retry once
        global _nse_client_ts
        _nse_client_ts = 0
        client = get_client()
        r = client.get(NSE_BASE + path, timeout=15)
        r.raise_for_status()
        return _decode(r)

# ── Helpers ───────────────────────────────────────────────────────────────────
def fn(v):
    try:
        if v in (None, "", "–", "-", "--", "NA", "N/A"): return None
        return round(float(str(v).replace(",", "")), 2)
    except:
        return None

def fn_int(v):
    try:
        if v in (None, "", "–", "-", "--", "NA", "N/A"): return None
        return int(float(str(v).replace(",", "")))
    except:
        return None

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

# ── Data fetchers ─────────────────────────────────────────────────────────────
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
    data = nse_get(f"/api/quote-equity?symbol={symbol}")
    try:
        trade_data = nse_get(f"/api/quote-equity?symbol={symbol}&section=trade_info")
    except:
        trade_data = {}

    price_info  = data.get("priceInfo", {})
    metadata    = data.get("metadata", {})
    industry    = data.get("industryInfo", {})
    securities  = data.get("securityInfo", {})
    trade_sum   = trade_data.get("securityWiseDP", {})

    week52 = price_info.get("weekHighLow", {})

    return {
        "symbol":       symbol,
        "name":         metadata.get("companyName", symbol),
        "price":        fn(price_info.get("lastPrice")),
        "change":       fn(price_info.get("change")),
        "change_pct":   fn(price_info.get("pChange")),
        "open":         fn(price_info.get("open")),
        "high":         fn(price_info.get("intraDayHighLow", {}).get("max")),
        "low":          fn(price_info.get("intraDayHighLow", {}).get("min")),
        "prev_close":   fn(price_info.get("previousClose")),
        "vwap":         fn(price_info.get("vwap")),
        "volume":       fn_int(trade_sum.get("quantityTraded")),
        "delivery_qty": fn_int(trade_sum.get("deliveryQuantity")),
        "delivery_pct": fn(trade_sum.get("deliveryToTradedQuantity")),
        "market_cap":   fn_int(metadata.get("totalMarketCap") or metadata.get("ffmc")),
        "pe_ratio":     fn(metadata.get("pdSymbolPe")),
        "week_52_high": fn(week52.get("max")),
        "week_52_low":  fn(week52.get("min")),
        "sector":       industry.get("macro", ""),
        "industry":     industry.get("sector", ""),
        "isin":         securities.get("isin", ""),
        "face_value":   fn(securities.get("faceVal")),
        "series":       metadata.get("series", "EQ"),
        "exchange":     "NSE",
        "currency":     "INR",
        # placeholders — not in NSE quote
        "pb_ratio": None, "dividend_yield": None, "eps": None,
        "book_value": None, "debt_to_equity": None,
        "roe": None, "roa": None, "employees": None,
        "avg_volume": None, "description": "", "website": "",
    }


def _fetch_financials(symbol: str) -> dict:
    """
    Correct NSE endpoint:
    GET /api/financial-results?index=equities&symbol=RELIANCE&period=Quarterly
    Returns list of quarterly result objects.
    """
    try:
        data = nse_get(
            f"/api/financial-results?index=equities&symbol={symbol}&period=Quarterly"
        )
    except Exception as e:
        return {"quarters": [], "error": str(e)}

    # Response shape: {"data": [...]} or directly a list
    rows = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return {"quarters": [], "error": "Unexpected response shape"}

    quarters = []
    for item in rows[:8]:
        # NSE uses camelCase keys in financial-results
        period = (
            item.get("toDate") or item.get("period") or
            item.get("to_date") or item.get("fromDate", "")
        )
        # Try multiple key variants NSE has used over time
        income = fn(
            item.get("totalIncome") or item.get("netSales") or
            item.get("income") or item.get("revenue") or
            item.get("totalRevenue") or item.get("netRevenue")
        )
        profit = fn(
            item.get("netProfit") or item.get("profitAfterTax") or
            item.get("pat") or item.get("profit")
        )
        ebitda = fn(item.get("ebitda") or item.get("operatingProfit") or item.get("pbdt"))
        eps    = fn(item.get("eps") or item.get("basicEps") or item.get("dilutedEps"))

        quarters.append({
            "period": str(period)[:10] if period else "—",
            "income": income,
            "profit": profit,
            "ebitda": ebitda,
            "eps":    eps,
        })

    return {"quarters": quarters}


def _fetch_shareholding(symbol: str) -> dict:
    """
    Correct NSE endpoint:
    GET /api/shareholding-patterns?index=equities&symbol=RELIANCE
    Returns {"data": [...]} where each item has a 'shareHolding' list.
    """
    try:
        data = nse_get(
            f"/api/shareholding-patterns?index=equities&symbol={symbol}"
        )
    except Exception as e:
        return {"history": [], "error": str(e)}

    rows = data.get("data", []) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return {"history": [], "error": "Unexpected response shape"}

    history = []
    for rec in rows[:6]:
        date = rec.get("date") or rec.get("period") or rec.get("quarter", "")

        # NSE nests shareholding under a 'shareHolding' array
        # Each element has 'category' and 'percentage'
        sh_list = rec.get("shareHolding") or rec.get("shareholding") or []

        def find_pct(keywords):
            """Search shareHolding list for a category matching any keyword."""
            for item in sh_list:
                cat = str(item.get("category", "") or item.get("name", "")).lower()
                if any(k in cat for k in keywords):
                    return fn(item.get("percentage") or item.get("per") or item.get("pct"))
            # Fallback: direct keys on the record itself
            for k in keywords:
                v = rec.get(k) or rec.get(k.title()) or rec.get(k.upper())
                if v is not None:
                    return fn(v)
            return None

        history.append({
            "date":        str(date)[:10],
            "promoter":    find_pct(["promoter"]),
            "fii":         find_pct(["fii", "fpi", "foreign institutional", "foreign portfolio"]),
            "dii":         find_pct(["dii", "domestic institutional"]),
            "mutual_fund": find_pct(["mutual fund", "mutual funds"]),
            "public":      find_pct(["public", "retail"]),
        })

    return {"history": history}


def _date_str(d: datetime) -> str:
    """NSE historical API wants dd-mm-yyyy format."""
    return d.strftime("%d-%m-%Y")


def _fetch_nse_history(symbol: str, days: int) -> list:
    """
    NSE historical price data:
    GET /api/historical/cm/equity?symbol=RELIANCE&series=["EQ"]&from=DD-MM-YYYY&to=DD-MM-YYYY
    Returns {"data": [...]} with OHLCV rows.
    """
    to_date   = datetime.now()
    from_date = to_date - timedelta(days=days)
    from_str  = _date_str(from_date)
    to_str    = _date_str(to_date)

    path = (
        f'/api/historical/cm/equity?symbol={symbol}'
        f'&series=["EQ"]&from={from_str}&to={to_str}'
    )
    data = nse_get(path)
    rows = data.get("data", []) if isinstance(data, dict) else []

    result = []
    for row in rows:
        # NSE field names
        date_str = row.get("CH_TIMESTAMP") or row.get("mTIMESTAMP", "")
        try:
            dt = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        except:
            continue
        result.append({
            "time":   dt.isoformat(),
            "open":   fn(row.get("CH_OPENING_PRICE") or row.get("open")),
            "high":   fn(row.get("CH_TRADE_HIGH_PRICE") or row.get("high")),
            "low":    fn(row.get("CH_TRADE_LOW_PRICE") or row.get("low")),
            "close":  fn(row.get("CH_CLOSING_PRICE") or row.get("close") or row.get("CH_LAST_TRADED_PRICE")),
            "volume": fn_int(row.get("CH_TOT_TRADED_QTY") or row.get("volume")),
        })

    # NSE returns newest first — reverse for charting
    result.sort(key=lambda x: x["time"])
    return result


def _fetch_history(symbol: str, period: str) -> list:
    """Route to NSE historical API. Period → days mapping."""
    days_map = {
        "1d": 2,    # NSE intraday not available here; use 2-day OHLC
        "1w": 7,
        "1m": 35,
        "3m": 95,
        "1y": 370,
        "5y": 1830,
    }
    days = days_map.get(period, 35)
    return _fetch_nse_history(symbol, days)


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
        raise HTTPException(502, f"NSE error: {e}")
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
        raise HTTPException(502, f"NSE error: {e}")
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
    return [s for s in NSE_STOCKS
            if q_lower in s["symbol"].lower() or q_lower in s["name"].lower()][:20]


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
        cache_set(f"fin:{sym}", data, ttl=3600)
        return data
    except Exception as e:
        raise HTTPException(500, f"Financials error {sym}: {e}")


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
        raise HTTPException(500, f"Shareholding error {sym}: {e}")


@app.get("/api/stock/{symbol}/history")
async def get_history(symbol: str, period: str = "1m"):
    sym = symbol.upper().strip()
    cached = cache_get(f"hist:{sym}:{period}")
    if cached: return cached
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(executor, _fetch_history, sym, period)
        if not result:
            raise HTTPException(404, f"No history data for {sym}")
        ttl = 300 if period in ("1m", "3m", "1y", "5y") else 120
        cache_set(f"hist:{sym}:{period}", result, ttl=ttl)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
