from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import time
import json
import gzip
import re
import os
from datetime import datetime, timedelta, date
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
NSE_API  = "https://www.nseindia.com/api"

NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
    "DNT": "1",
    "Connection": "keep-alive",
}

_client: httpx.Client | None = None
_client_ts: float = 0
SESSION_TTL = 200

def _build_client() -> httpx.Client:
    c = httpx.Client(headers=NSE_HEADERS, follow_redirects=True, timeout=20)
    for url in ["/", "/market-data/live-equity-market"]:
        try:
            c.get(NSE_BASE + url, timeout=10)
            time.sleep(0.5)
        except:
            pass
    return c

def get_client() -> httpx.Client:
    global _client, _client_ts
    if _client and time.time() - _client_ts < SESSION_TTL:
        return _client
    if _client:
        try: _client.close()
        except: pass
    _client = _build_client()
    _client_ts = time.time()
    return _client

def _decode(r: httpx.Response) -> dict | list:
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
        raise ValueError(f"Empty NSE response (HTTP {r.status_code})")
    return json.loads(text)

def nse_get(path: str, params: dict | None = None) -> dict | list:
    client = get_client()
    url = NSE_API + path
    try:
        r = client.get(url, params=params, timeout=15)
        r.raise_for_status()
        return _decode(r)
    except Exception:
        global _client_ts
        _client_ts = 0
        client = get_client()
        r = client.get(url, params=params, timeout=15)
        r.raise_for_status()
        return _decode(r)

# ── Helpers ───────────────────────────────────────────────────────────────────
def fn(v):
    try:
        if v in (None, "", "–", "-", "--", "NA", "N/A"): return None
        return round(float(str(v).replace(",", "").replace("₹", "").strip()), 2)
    except: return None

def fn_int(v):
    try:
        if v in (None, "", "–", "-", "--", "NA", "N/A"): return None
        return int(float(str(v).replace(",", "").strip()))
    except: return None

# ── Screener client (separate, no NSE cookies needed) ─────────────────────────
SCREENER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

def _get_screener_html(symbol: str) -> str:
    """Fetch Screener.in page HTML for a symbol."""
    with httpx.Client(headers=SCREENER_HEADERS, follow_redirects=True, timeout=20) as c:
        for suffix in ["consolidated/", ""]:
            url = f"https://www.screener.in/company/{symbol}/{suffix}"
            r = c.get(url, timeout=15)
            if r.status_code == 200 and len(r.text) > 5000:
                return r.text
    return ""

def _parse_screener_ratios(html: str) -> dict:
    """
    Parse the key ratios from the top of Screener's company page.
    They appear in <li> tags inside a <ul class="flex-row ..."> block.
    Pattern: <span class="name">Label</span> <span class="value">Number</span>
    """
    ratios = {}

    # Try the top-level ratio list first (the #top section)
    # Screener emits: <li> <span class="name">Market Cap</span> <span class="number">4,12,345</span> Cr. </li>
    blocks = re.findall(
        r'<li[^>]*>\s*<span[^>]*class="[^"]*name[^"]*"[^>]*>(.*?)</span>\s*<span[^>]*class="[^"]*(?:number|value)[^"]*"[^>]*>(.*?)</span>',
        html, re.DOTALL | re.IGNORECASE
    )
    for label_raw, val_raw in blocks:
        label = re.sub(r'<[^>]+>', '', label_raw).strip().lower()
        val   = re.sub(r'<[^>]+>', '', val_raw).strip().replace(',', '')
        ratios[label] = val

    return ratios

def _parse_screener_quarters(html: str) -> list:
    """Parse quarterly results table from Screener."""
    qr_match = re.search(
        r'<section[^>]*id=["\']quarters["\'][^>]*>(.*?)</section>',
        html, re.DOTALL | re.IGNORECASE
    )
    if not qr_match:
        return []

    section = qr_match.group(1)

    # Headers (quarter labels)
    header_matches = re.findall(r'<th[^>]*>(.*?)</th>', section, re.DOTALL)
    headers = [re.sub(r'<[^>]+>', '', h).strip() for h in header_matches]
    period_headers = [h for h in headers if re.search(r'\d{4}', h)]

    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', section, re.DOTALL)

    def parse_val(s):
        s = re.sub(r'<[^>]+>', '', s).strip().replace(',', '').replace('%', '')
        return fn(s)

    row_data = {}
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if not cells: continue
        label = re.sub(r'<[^>]+>', '', cells[0]).strip().lower()
        vals  = [parse_val(c) for c in cells[1:]]
        if label:
            row_data[label] = vals

    def get_row(*keys):
        for k in keys:
            for rk, rv in row_data.items():
                if k in rk:
                    return rv
        return []

    sales   = get_row("sales", "revenue", "net sales")
    profit  = get_row("net profit", "profit after tax", "pat")
    ebitda  = get_row("operating profit", "ebitda", "ebidt")
    eps_row = get_row("eps", "earning per share")

    quarters = []
    for i, period in enumerate(period_headers[:8]):
        quarters.append({
            "period": period,
            "income": sales[i]   if i < len(sales)   else None,
            "profit": profit[i]  if i < len(profit)  else None,
            "ebitda": ebitda[i]  if i < len(ebitda)  else None,
            "eps":    eps_row[i] if i < len(eps_row) else None,
        })
    return quarters

def _screener_full(symbol: str) -> dict:
    """Fetch Screener page and return both ratios and quarterly data."""
    html = _get_screener_html(symbol)
    if not html:
        return {"ratios": {}, "quarters": []}
    return {
        "ratios":   _parse_screener_ratios(html),
        "quarters": _parse_screener_quarters(html),
    }

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

def _fetch_all_indices() -> dict:
    data = nse_get("/allIndices")
    return {
        row.get("index", ""): {
            "price":      round(float(row.get("last", 0) or 0), 2),
            "change":     round(float(row.get("variation", 0) or 0), 2),
            "change_pct": round(float(row.get("percentChange", 0) or 0), 2),
        }
        for row in data.get("data", [])
    }


def _fetch_quote(symbol: str) -> dict:
    """NSE quote + augment with Screener ratios."""
    data       = nse_get("/quote-equity", {"symbol": symbol})
    trade_data = {}
    try:
        trade_data = nse_get("/quote-equity", {"symbol": symbol, "section": "trade_info"})
    except: pass

    pi  = data.get("priceInfo", {})
    md  = data.get("metadata", {})
    ind = data.get("industryInfo", {})
    sec = data.get("securityInfo", {})
    td  = trade_data.get("securityWiseDP", {})
    w52 = pi.get("weekHighLow", {})

    base = {
        "symbol":        symbol,
        "name":          md.get("companyName", symbol),
        "price":         fn(pi.get("lastPrice")),
        "change":        fn(pi.get("change")),
        "change_pct":    fn(pi.get("pChange")),
        "open":          fn(pi.get("open")),
        "high":          fn(pi.get("intraDayHighLow", {}).get("max")),
        "low":           fn(pi.get("intraDayHighLow", {}).get("min")),
        "prev_close":    fn(pi.get("previousClose")),
        "vwap":          fn(pi.get("vwap")),
        "volume":        fn_int(td.get("quantityTraded")),
        "delivery_qty":  fn_int(td.get("deliveryQuantity")),
        "delivery_pct":  fn(td.get("deliveryToTradedQuantity")),
        "pe_ratio":      fn(md.get("pdSymbolPe")),
        "week_52_high":  fn(w52.get("max")),
        "week_52_low":   fn(w52.get("min")),
        "sector":        ind.get("macro", ""),
        "industry":      ind.get("sector", ""),
        "isin":          sec.get("isin", ""),
        "face_value":    fn(sec.get("faceVal")),
        "series":        md.get("series", "EQ"),
        "exchange": "NSE", "currency": "INR",
        # Will be filled from Screener below
        "market_cap": None, "pb_ratio": None, "dividend_yield": None,
        "eps": None, "book_value": None, "debt_to_equity": None,
        "roe": None, "roa": None, "roce": None,
        "avg_volume": None, "employees": None,
        "description": "", "website": "",
    }

    # ── Screener augmentation ──────────────────────────────────────────────
    # Screener key ratio labels (lowercase) → our field names
    RATIO_MAP = {
        "market cap":         ("market_cap",    fn_int),
        "stock p/e":          ("pb_ratio",       fn),    # screener shows P/E as "Stock P/E"
        "book value":         ("book_value",     fn),
        "dividend yield":     ("dividend_yield", fn),
        "roce":               ("roce",           fn),
        "roe":                ("roe",            fn),
        "eps":                ("eps",            fn),
        "debt / equity":      ("debt_to_equity", fn),
        "debt to equity":     ("debt_to_equity", fn),
        "face value":         ("face_value",     fn),
    }
    # Only fetch Screener if we're missing key data
    try:
        scr_cache_key = f"scr:{symbol}"
        scr = cache_get(scr_cache_key)
        if scr is None:
            scr = _screener_full(symbol)
            cache_set(scr_cache_key, scr, ttl=7200)

        ratios = scr.get("ratios", {})
        for label, (field, converter) in RATIO_MAP.items():
            if label in ratios and ratios[label]:
                v = converter(ratios[label])
                if v is not None:
                    base[field] = v

        # Screener shows "Stock P/E" — distinguish from NSE's P/E
        # If NSE already gave us pe_ratio, keep it; Screener's is a fallback
        if base["pe_ratio"] is None and "stock p/e" in ratios:
            base["pe_ratio"] = fn(ratios["stock p/e"])

        # Market cap from Screener comes in Cr — convert to absolute
        if base["market_cap"] and base["market_cap"] < 1_000_000:
            base["market_cap"] = int(base["market_cap"] * 1e7)  # Cr → absolute

        # Dividend yield in %
        if base["dividend_yield"] and base["dividend_yield"] > 1:
            base["dividend_yield"] = base["dividend_yield"] / 100

        # ROE/ROCE come as percentage strings like "18.5 %" → store as decimal
        for field in ("roe", "roa", "roce"):
            if base.get(field) and base[field] > 1:
                base[field] = round(base[field] / 100, 4)

    except Exception:
        pass  # Screener failed — just show NSE data

    return base


def _fetch_shareholding(symbol: str) -> dict:
    """
    NSE endpoint: /api/corporate-share-holdings-master?index=equities&symbol=X
    """
    try:
        rows = nse_get("/corporate-share-holdings-master", {"index": "equities", "symbol": symbol})
    except Exception as e:
        return {"history": [], "error": str(e)}

    if not isinstance(rows, list):
        rows = rows.get("data", []) if isinstance(rows, dict) else []

    history = []
    for rec in rows[:6]:
        date_val = rec.get("date") or rec.get("quarter") or ""

        def get_pct(*keys):
            for k in keys:
                v = rec.get(k)
                if v is not None: return fn(v)
            sh_list = rec.get("shareHolderInfo") or rec.get("shareHolding") or []
            for item in sh_list:
                cat = str(item.get("category", "") or item.get("name", "")).lower()
                if any(k.lower() in cat for k in keys):
                    return fn(item.get("percentage") or item.get("per"))
            return None

        history.append({
            "date":        str(date_val)[:10],
            "promoter":    get_pct("pr_and_prgrp", "promoter", "promoterAndPromoterGroup"),
            "fii":         get_pct("fii", "fpi", "foreIgnInst"),
            "dii":         get_pct("dii", "domInstit"),
            "mutual_fund": get_pct("mutualFunds", "mutual_funds", "mf"),
            "public":      get_pct("public_val", "public", "publicVal"),
        })

    return {"history": history}


def _fetch_financials(symbol: str) -> dict:
    """Use cached Screener scrape to return quarterly results."""
    scr_cache_key = f"scr:{symbol}"
    scr = cache_get(scr_cache_key)
    if scr is None:
        scr = _screener_full(symbol)
        cache_set(scr_cache_key, scr, ttl=7200)
    quarters = scr.get("quarters", [])
    return {"quarters": quarters}


def _fetch_history(symbol: str, period: str) -> list:
    """
    NSE NextApi historical trade data.
    URL: /api/NextApi/apiClient/GetQuoteApi
    Params: functionName=getHistoricalTradeData, symbol, series, fromDate, toDate (DD-MM-YYYY)
    """
    days_map = {"1d": 3, "1w": 8, "1m": 35, "3m": 95, "1y": 370, "5y": 1830}
    days = days_map.get(period, 35)

    to_dt = date.today()
    fr_dt = to_dt - timedelta(days=days)

    results = []
    chunk_start = fr_dt
    while chunk_start <= to_dt:
        chunk_end = min(chunk_start + timedelta(days=99), to_dt)
        try:
            data = nse_get(
                "/NextApi/apiClient/GetQuoteApi",
                {
                    "functionName": "getHistoricalTradeData",
                    "symbol":   symbol,
                    "series":   "EQ",
                    "fromDate": chunk_start.strftime("%d-%m-%Y"),
                    "toDate":   chunk_end.strftime("%d-%m-%Y"),
                }
            )
            rows = []
            if isinstance(data, dict):
                # Response can be {"data": [...]} or nested further
                rows = data.get("data", [])
                if isinstance(rows, dict):
                    rows = rows.get("tradesData", rows.get("data", []))
            elif isinstance(data, list):
                rows = data

            for row in rows:
                # Try multiple timestamp keys NSE uses
                ts = (row.get("mTIMESTAMP") or row.get("CH_TIMESTAMP")
                      or row.get("date") or row.get("toDate") or "")
                try:
                    dt = datetime.strptime(str(ts)[:10], "%Y-%m-%d")
                except:
                    try: dt = datetime.strptime(str(ts)[:11], "%d-%b-%Y")
                    except: continue

                close = fn(row.get("CH_CLOSING_PRICE") or row.get("CH_LAST_TRADED_PRICE")
                           or row.get("close") or row.get("ltp"))
                if close is None:
                    continue
                results.append({
                    "time":   dt.isoformat(),
                    "open":   fn(row.get("CH_OPENING_PRICE")    or row.get("open")),
                    "high":   fn(row.get("CH_TRADE_HIGH_PRICE") or row.get("high")),
                    "low":    fn(row.get("CH_TRADE_LOW_PRICE")  or row.get("low")),
                    "close":  close,
                    "volume": fn_int(row.get("CH_TOT_TRADED_QTY") or row.get("volume")),
                })
        except Exception:
            pass
        chunk_start = chunk_end + timedelta(days=1)
        if chunk_start <= to_dt:
            time.sleep(0.3)

    results.sort(key=lambda x: x["time"])
    return results


def _fetch_history_fallback(symbol: str, period: str) -> list:
    """
    Fallback: scrape historical data from Screener's JSON endpoint.
    https://www.screener.in/api/company/{id}/chart/?q=Price-Shares+Traded&days=365
    First we need the company ID from the HTML page.
    """
    try:
        html = _get_screener_html(symbol)
        if not html:
            return []
        # Screener embeds the company ID in the page
        m = re.search(r'"id"\s*:\s*(\d+)', html)
        if not m:
            m = re.search(r'/api/company/(\d+)/', html)
        if not m:
            return []
        company_id = m.group(1)

        days_map = {"1d": 7, "1w": 14, "1m": 35, "3m": 95, "1y": 370, "5y": 1830}
        days = days_map.get(period, 35)

        with httpx.Client(headers=SCREENER_HEADERS, follow_redirects=True, timeout=20) as c:
            r = c.get(
                f"https://www.screener.in/api/company/{company_id}/chart/",
                params={"q": "Price-Shares+Traded", "days": days},
                timeout=15,
            )
            if r.status_code != 200:
                return []
            chart = r.json()

        # Screener chart format: {"datasets": [{"metric": "Price", "values": [[date, price], ...]}, ...]}
        datasets = chart.get("datasets", [])
        price_data = []
        for ds in datasets:
            if "price" in str(ds.get("metric", "")).lower():
                price_data = ds.get("values", [])
                break

        results = []
        for point in price_data:
            if len(point) < 2: continue
            try:
                dt = datetime.strptime(str(point[0])[:10], "%Y-%m-%d")
                close = fn(point[1])
                if close:
                    results.append({
                        "time": dt.isoformat(),
                        "open": close, "high": close, "low": close, "close": close,
                        "volume": None,
                    })
            except:
                continue
        return results
    except Exception:
        return []


def _get_history_with_fallback(symbol: str, period: str) -> list:
    """Try NSE first, fall back to Screener chart data."""
    result = _fetch_history(symbol, period)
    if not result:
        result = _fetch_history_fallback(symbol, period)
    return result


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
        data = await loop.run_in_executor(executor, _fetch_quote, sym)
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
        if data.get("quarters"):
            cache_set(f"fin:{sym}", data, ttl=7200)
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
        if data.get("history"):
            cache_set(f"sh:{sym}", data, ttl=7200)
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
        result = await loop.run_in_executor(executor, _get_history_with_fallback, sym, period)
        if not result:
            raise HTTPException(404, f"No history data for {sym}")
        ttl = 300 if period in ("1m", "3m", "1y", "5y") else 120
        cache_set(f"hist:{sym}:{period}", result, ttl=ttl)
        return result
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, str(e))


# ── Phase 3: News & PESTEL routes ─────────────────────────────────────────────
from news import fetch_news_for_symbol, compute_pestel_scores, get_macro_pestel

def _get_groq_key() -> str:
    return os.environ.get("GROQ_API_KEY", "")


@app.get("/api/stock/{symbol}/news")
async def get_stock_news(symbol: str):
    sym = symbol.upper().strip()
    cached = cache_get(f"news:{sym}")
    if cached:
        return cached

    api_key      = _get_groq_key()
    stock_cached = cache_get(f"stock:{sym}")
    company_name = stock_cached.get("name", sym) if stock_cached else sym

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            executor,
            lambda: fetch_news_for_symbol(sym, company_name, api_key)
        )
        result["symbol"]      = sym
        result["llm_enabled"] = bool(api_key)
        if result.get("news") is not None:   # cache even if empty
            cache_set(f"news:{sym}", result, ttl=600)
        return result
    except Exception as e:
        # Never return 500 — return empty result with error info so UI shows something
        return {
            "symbol": sym, "llm_enabled": False,
            "news": [], "pestel": {},
            "error": str(e),
        }


@app.get("/api/stock/{symbol}/news/debug")
async def debug_news(symbol: str):
    """Debug endpoint — shows RSS fetch results and any errors without LLM."""
    sym = symbol.upper().strip()
    from news import RSS_FEEDS, _fetch_rss, _relevance_prefilter
    stock_cached = cache_get(f"stock:{sym}")
    company_name = stock_cached.get("name", sym) if stock_cached else sym

    feed_results = []
    for feed in RSS_FEEDS[:5]:   # test first 5 feeds
        try:
            items = _fetch_rss(feed, timeout=8)
            relevant = [i for i in items if _relevance_prefilter(i, sym, company_name) >= 1.0]
            feed_results.append({
                "feed": feed["name"], "fetched": len(items),
                "relevant": len(relevant), "status": "ok",
            })
        except Exception as ex:
            feed_results.append({"feed": feed["name"], "status": f"error: {ex}"})

    return {
        "symbol": sym, "company": company_name,
        "groq_key_set": bool(os.environ.get("GROQ_API_KEY")),
        "feeds": feed_results,
    }


@app.get("/api/macro/pestel")
async def get_macro():
    cached = cache_get("macro_pestel")
    if cached:
        return cached
    api_key = _get_groq_key()
    loop    = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            executor,
            lambda: get_macro_pestel(api_key)
        )
        cache_set("macro_pestel", result, ttl=1800)
        return result
    except Exception as e:
        return {"error": str(e)}
