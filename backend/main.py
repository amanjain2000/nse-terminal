from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from stocks_list import NSE_STOCKS

app = FastAPI(title="NSE Stock Terminal API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single-threaded executor — serializes Yahoo calls, avoids rate limits
executor = ThreadPoolExecutor(max_workers=3)

# ── In-memory cache ──────────────────────────────────────────────────────────
_cache: dict = {}

def cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() < entry["exp"]:
        return entry["val"]
    return None

def cache_set(key: str, val, ttl: int):
    _cache[key] = {"val": val, "exp": time.time() + ttl}

# ── Indices & Sectors ────────────────────────────────────────────────────────
INDICES = {
    "NIFTY 50":   "^NSEI",
    "SENSEX":     "^BSESN",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY IT":   "^CNXIT",
    "NIFTY PHARMA": "^CNXPHARMA",
}

SECTOR_INDICES = {
    "IT":       "^CNXIT",
    "Bank":     "^NSEBANK",
    "Pharma":   "^CNXPHARMA",
    "Auto":     "^CNXAUTO",
    "FMCG":     "^CNXFMCG",
    "Metal":    "^CNXMETAL",
    "Realty":   "^CNXREALTY",
    "Energy":   "^CNXENERGY",
    "PSU Bank": "^CNXPSUBANK",
    "Media":    "^CNXMEDIA",
}

# ── Helpers ──────────────────────────────────────────────────────────────────
def _history_price(symbol: str):
    """Get price+change using history() — far less rate-limited than info()."""
    t = yf.Ticker(symbol)
    hist = t.history(period="5d", interval="1d")
    if hist.empty:
        return None
    cur  = float(hist["Close"].iloc[-1])
    prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cur
    chg      = cur - prev
    chg_pct  = (chg / prev * 100) if prev else 0
    return {"price": round(cur, 2), "change": round(chg, 2), "change_pct": round(chg_pct, 2)}


def _fetch_batch_history(symbols: list[str]):
    """Download history for multiple symbols in one call — much more efficient."""
    yf_syms = " ".join(symbols)
    df = yf.download(yf_syms, period="5d", interval="1d",
                     group_by="ticker", auto_adjust=True, progress=False)
    results = {}
    for sym in symbols:
        try:
            if len(symbols) == 1:
                closes = df["Close"]
            else:
                closes = df[sym]["Close"]
            closes = closes.dropna()
            if len(closes) < 1:
                continue
            cur  = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) >= 2 else cur
            chg     = cur - prev
            chg_pct = (chg / prev * 100) if prev else 0
            results[sym] = {"price": round(cur, 2), "change": round(chg, 2), "change_pct": round(chg_pct, 2)}
        except Exception:
            continue
    return results


def _fetch_stock_info(yf_sym: str):
    """Full stock info — uses info() only for individual stock pages."""
    t = yf.Ticker(yf_sym)
    info = t.info
    hist = t.history(period="5d", interval="1d")

    cur = (info.get("regularMarketPrice") or info.get("currentPrice"))
    if not cur and not hist.empty:
        cur = float(hist["Close"].iloc[-1])

    prev = (info.get("regularMarketPreviousClose") or info.get("previousClose"))
    if not prev and len(hist) >= 2:
        prev = float(hist["Close"].iloc[-2])
    elif not prev and not hist.empty:
        prev = float(hist["Close"].iloc[-1])

    if not cur:
        raise ValueError(f"No price data for {yf_sym}")

    def fmt(v):
        try: return round(float(v), 2) if v is not None else None
        except: return None
    def fmt_int(v):
        try: return int(v) if v is not None else None
        except: return None

    chg     = (cur - prev) if prev else 0
    chg_pct = (chg / prev * 100) if prev else 0

    return {
        "symbol":        yf_sym.replace(".NS", ""),
        "name":          info.get("longName") or info.get("shortName") or yf_sym,
        "price":         fmt(cur),
        "change":        fmt(chg),
        "change_pct":    fmt(chg_pct),
        "open":          fmt(info.get("open") or info.get("regularMarketOpen")),
        "high":          fmt(info.get("dayHigh") or info.get("regularMarketDayHigh")),
        "low":           fmt(info.get("dayLow") or info.get("regularMarketDayLow")),
        "prev_close":    fmt(prev),
        "volume":        fmt_int(info.get("volume") or info.get("regularMarketVolume")),
        "avg_volume":    fmt_int(info.get("averageVolume")),
        "market_cap":    fmt_int(info.get("marketCap")),
        "pe_ratio":      fmt(info.get("trailingPE")),
        "pb_ratio":      fmt(info.get("priceToBook")),
        "dividend_yield":fmt(info.get("dividendYield")),
        "week_52_high":  fmt(info.get("fiftyTwoWeekHigh")),
        "week_52_low":   fmt(info.get("fiftyTwoWeekLow")),
        "sector":        info.get("sector") or "",
        "industry":      info.get("industry") or "",
        "description":   (info.get("longBusinessSummary") or "")[:600],
        "eps":           fmt(info.get("trailingEps")),
        "book_value":    fmt(info.get("bookValue")),
        "debt_to_equity":fmt(info.get("debtToEquity")),
        "roe":           fmt(info.get("returnOnEquity")),
        "roa":           fmt(info.get("returnOnAssets")),
        "employees":     fmt_int(info.get("fullTimeEmployees")),
        "website":       info.get("website") or "",
        "exchange":      "NSE",
        "currency":      "INR",
    }


def _fetch_history(yf_sym: str, period: str, interval: str):
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
    symbols = list(INDICES.values())

    try:
        batch = await loop.run_in_executor(executor, _fetch_batch_history, symbols)
    except Exception:
        batch = {}

    result = []
    for name, sym in INDICES.items():
        d = batch.get(sym)
        if d:
            result.append({"name": name, "symbol": sym, **d})

    if result:
        cache_set("indices", result, ttl=120)   # 2 min cache
    return result


@app.get("/api/sectors")
async def get_sectors():
    cached = cache_get("sectors")
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    symbols = list(SECTOR_INDICES.values())

    try:
        batch = await loop.run_in_executor(executor, _fetch_batch_history, symbols)
    except Exception:
        batch = {}

    result = []
    for name, sym in SECTOR_INDICES.items():
        d = batch.get(sym)
        if d:
            result.append({"name": name, "change_pct": d["change_pct"], "price": d["price"]})

    if result:
        cache_set("sectors", result, ttl=120)
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
    sym     = symbol.upper().strip()
    yf_sym  = f"{sym}.NS"
    cache_key = f"stock:{sym}"

    cached = cache_get(cache_key)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _fetch_stock_info, yf_sym)
        cache_set(cache_key, data, ttl=60)   # 1 min cache per stock
        return data
    except Exception as e:
        raise HTTPException(500, f"Could not fetch {sym}: {str(e)}")


@app.get("/api/stock/{symbol}/history")
async def get_history(symbol: str, period: str = "1m"):
    sym    = symbol.upper().strip()
    yf_sym = f"{sym}.NS"
    cache_key = f"hist:{sym}:{period}"

    cached = cache_get(cache_key)
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
        hist = await loop.run_in_executor(executor, _fetch_history, yf_sym, yf_period, yf_interval)
        if hist.empty:
            raise HTTPException(404, "No history data")

        result = [
            {
                "time":   idx.isoformat(),
                "open":   round(float(row["Open"]),   2),
                "high":   round(float(row["High"]),   2),
                "low":    round(float(row["Low"]),    2),
                "close":  round(float(row["Close"]),  2),
                "volume": int(row["Volume"]),
            }
            for idx, row in hist.iterrows()
        ]
        # cache history longer — it doesn't change frequently
        ttl = 300 if period in ("1m", "3m", "1y", "5y") else 60
        cache_set(cache_key, result, ttl=ttl)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
