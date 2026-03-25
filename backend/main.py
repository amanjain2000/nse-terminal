from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import time
import json
import gzip
import re
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
SESSION_TTL = 200  # refresh every ~3 min

def _build_client() -> httpx.Client:
    c = httpx.Client(headers=NSE_HEADERS, follow_redirects=True, timeout=20)
    for url in ["/", "/market-data/live-equity-market", "/get-quotes/equity?symbol=RELIANCE"]:
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

def nse_get(path: str, params: dict | None = None, base: str = NSE_API) -> dict | list:
    client = get_client()
    url = base + path
    try:
        r = client.get(url, params=params, timeout=15)
        r.raise_for_status()
        return _decode(r)
    except Exception:
        # Rebuild session once and retry
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
        return round(float(str(v).replace(",", "")), 2)
    except: return None

def fn_int(v):
    try:
        if v in (None, "", "–", "-", "--", "NA", "N/A"): return None
        return int(float(str(v).replace(",", "")))
    except: return None

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

# ── Fetchers ──────────────────────────────────────────────────────────────────

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
    data       = nse_get("/quote-equity", {"symbol": symbol})
    trade_data = {}
    try:
        trade_data = nse_get("/quote-equity", {"symbol": symbol, "section": "trade_info"})
    except: pass

    pi = data.get("priceInfo", {})
    md = data.get("metadata", {})
    ind = data.get("industryInfo", {})
    sec = data.get("securityInfo", {})
    td = trade_data.get("securityWiseDP", {})
    w52 = pi.get("weekHighLow", {})

    return {
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
        "market_cap":    fn_int(md.get("totalMarketCap") or md.get("ffmc")),
        "pe_ratio":      fn(md.get("pdSymbolPe")),
        "week_52_high":  fn(w52.get("max")),
        "week_52_low":   fn(w52.get("min")),
        "sector":        ind.get("macro", ""),
        "industry":      ind.get("sector", ""),
        "isin":          sec.get("isin", ""),
        "face_value":    fn(sec.get("faceVal")),
        "series":        md.get("series", "EQ"),
        "exchange": "NSE", "currency": "INR",
        "pb_ratio": None, "dividend_yield": None, "eps": None,
        "book_value": None, "debt_to_equity": None,
        "roe": None, "roa": None, "employees": None,
        "avg_volume": None, "description": "", "website": "",
    }


def _fetch_shareholding(symbol: str) -> dict:
    """
    Correct endpoint discovered from nse library source:
    /api/corporate-share-holdings-master?index=equities&symbol=SYMBOL
    Returns a list of quarterly records with keys like pr_and_prgrp, public_val etc.
    """
    try:
        rows = nse_get(
            "/corporate-share-holdings-master",
            {"index": "equities", "symbol": symbol}
        )
    except Exception as e:
        return {"history": [], "error": str(e)}

    if not isinstance(rows, list):
        rows = rows.get("data", []) if isinstance(rows, dict) else []

    history = []
    for rec in rows[:6]:
        # Key field names from the nse library sample response
        date_val = rec.get("date") or rec.get("quarter") or ""

        def get_pct(keys):
            for k in keys:
                v = rec.get(k)
                if v is not None:
                    return fn(v)
            return None

        # NSE field names confirmed from library docs
        promoter = get_pct(["pr_and_prgrp", "promoter", "promoterAndPromoterGroup"])
        public   = get_pct(["public_val", "public", "publicVal"])
        # FII/DII are usually inside a sub-list; try flat keys too
        fii      = get_pct(["fii", "fpi", "foreIgnInst"])
        dii      = get_pct(["dii", "domInstit"])
        mf       = get_pct(["mutualFunds", "mutual_funds", "mf"])

        # If sub-categories not in flat keys, try the nested shareHolderInfo list
        sh_list = rec.get("shareHolderInfo") or rec.get("shareHolding") or []
        for item in sh_list:
            cat = str(item.get("category", "") or item.get("name", "")).lower()
            pct = fn(item.get("percentage") or item.get("per") or item.get("pct"))
            if "promoter" in cat and promoter is None:
                promoter = pct
            elif ("fii" in cat or "fpi" in cat or "foreign" in cat) and fii is None:
                fii = pct
            elif "dii" in cat and dii is None:
                dii = pct
            elif "mutual" in cat and mf is None:
                mf = pct
            elif "public" in cat and public is None:
                public = pct

        history.append({
            "date":        str(date_val)[:10],
            "promoter":    promoter,
            "fii":         fii,
            "dii":         dii,
            "mutual_fund": mf,
            "public":      public,
        })

    return {"history": history}


def _scrape_screener(symbol: str) -> dict:
    """
    Scrape Screener.in for quarterly financials.
    URL: https://www.screener.in/company/RELIANCE/consolidated/
    Returns structured quarterly P&L data.
    """
    client = httpx.Client(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
        follow_redirects=True,
        timeout=20,
    )

    quarters = []
    try:
        # Try consolidated first, fall back to standalone
        for suffix in ["consolidated", ""]:
            url = f"https://www.screener.in/company/{symbol}/" + (f"{suffix}/" if suffix else "")
            r = client.get(url, timeout=15)
            if r.status_code == 200 and "quarterly" in r.text.lower():
                break
        else:
            return {"quarters": [], "error": "Screener page not found"}

        html = r.text

        # Find the Quarterly Results section
        # Screener uses a table with id containing "quarters"
        qr_match = re.search(
            r'<section[^>]*id=["\']quarters["\'][^>]*>(.*?)</section>',
            html, re.DOTALL | re.IGNORECASE
        )
        if not qr_match:
            return {"quarters": [], "error": "Quarterly section not found on Screener"}

        section = qr_match.group(1)

        # Extract column headers (quarter dates)
        header_matches = re.findall(r'<th[^>]*>(.*?)</th>', section, re.DOTALL)
        headers = [re.sub(r'<[^>]+>', '', h).strip() for h in header_matches]
        # First header is usually "Quarter" label, rest are dates
        period_headers = [h for h in headers if re.search(r'\d{4}', h)]

        # Extract each data row
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

        # Map rows to standard keys
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

        n = len(period_headers)
        for i in range(min(n, 8)):
            quarters.append({
                "period": period_headers[i] if i < len(period_headers) else f"Q{i+1}",
                "income": sales[i]   if i < len(sales)   else None,
                "profit": profit[i]  if i < len(profit)  else None,
                "ebitda": ebitda[i]  if i < len(ebitda)  else None,
                "eps":    eps_row[i] if i < len(eps_row) else None,
            })

    except Exception as e:
        return {"quarters": quarters, "error": str(e)}
    finally:
        client.close()

    return {"quarters": quarters}


def _fetch_history(symbol: str, period: str) -> list:
    """
    Use NSE's NextApi endpoint (confirmed from nse library source):
    /api/NextApi/apiClient/GetQuoteApi?functionName=getHistoricalTradeData
    &symbol=X&series=EQ&fromDate=DD-MM-YYYY&toDate=DD-MM-YYYY
    """
    days_map = {"1d": 3, "1w": 8, "1m": 35, "3m": 95, "1y": 370, "5y": 1830}
    days = days_map.get(period, 35)

    to_dt   = date.today()
    fr_dt   = to_dt - timedelta(days=days)

    # For long ranges, split into max 100-day chunks
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
            # Response: {"data": [...]} — each row has mTIMESTAMP, CH_OPENING_PRICE etc.
            rows = data.get("data", []) if isinstance(data, dict) else []
            for row in rows:
                ts = row.get("mTIMESTAMP") or row.get("CH_TIMESTAMP", "")
                try:
                    dt = datetime.strptime(str(ts)[:10], "%Y-%m-%d")
                except:
                    try:
                        dt = datetime.strptime(str(ts)[:10], "%d-%b-%Y")
                    except:
                        continue
                results.append({
                    "time":   dt.isoformat(),
                    "open":   fn(row.get("CH_OPENING_PRICE")  or row.get("open")),
                    "high":   fn(row.get("CH_TRADE_HIGH_PRICE") or row.get("high")),
                    "low":    fn(row.get("CH_TRADE_LOW_PRICE")  or row.get("low")),
                    "close":  fn(row.get("CH_CLOSING_PRICE") or row.get("CH_LAST_TRADED_PRICE") or row.get("close")),
                    "volume": fn_int(row.get("CH_TOT_TRADED_QTY") or row.get("volume")),
                })
        except Exception:
            pass
        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(0.2)

    results.sort(key=lambda x: x["time"])
    return results


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
        data = await loop.run_in_executor(executor, _scrape_screener, sym)
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
        result = await loop.run_in_executor(executor, _fetch_history, sym, period)
        if not result:
            raise HTTPException(404, f"No history data for {sym}")
        ttl = 300 if period in ("1m", "3m", "1y", "5y") else 120
        cache_set(f"hist:{sym}:{period}", result, ttl=ttl)
        return result
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, str(e))
