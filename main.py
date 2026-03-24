from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import asyncio
from concurrent.futures import ThreadPoolExecutor
from stocks_list import NSE_STOCKS

app = FastAPI(title="NSE Stock Terminal API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=20)

INDICES = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
    "NIFTY PHARMA": "^CNXPHARMA",
}

SECTOR_INDICES = {
    "IT": "^CNXIT",
    "Bank": "^NSEBANK",
    "Pharma": "^CNXPHARMA",
    "Auto": "^CNXAUTO",
    "FMCG": "^CNXFMCG",
    "Metal": "^CNXMETAL",
    "Realty": "^CNXREALTY",
    "Energy": "^CNXENERGY",
    "PSU Bank": "^CNXPSUBANK",
    "Media": "^CNXMEDIA",
}


def _fetch_ticker(symbol: str):
    t = yf.Ticker(symbol)
    info = t.info
    hist = t.history(period="2d", interval="1d")
    return info, hist


def _fetch_history(symbol: str, period: str, interval: str):
    t = yf.Ticker(symbol)
    return t.history(period=period, interval=interval)


@app.get("/health")
def health():
    return {"status": "ok", "message": "NSE Terminal API is running"}


@app.get("/api/indices")
async def get_indices():
    loop = asyncio.get_event_loop()

    async def fetch_one(name, sym):
        try:
            info, hist = await loop.run_in_executor(executor, _fetch_ticker, sym)
            if hist.empty:
                return None
            cur = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cur
            chg = cur - prev
            chg_pct = (chg / prev * 100) if prev else 0
            return {
                "name": name,
                "symbol": sym,
                "price": round(cur, 2),
                "change": round(chg, 2),
                "change_pct": round(chg_pct, 2),
            }
        except Exception:
            return None

    tasks = [fetch_one(n, s) for n, s in INDICES.items()]
    raw = await asyncio.gather(*tasks)
    return [r for r in raw if r]


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
    sym = symbol.upper().strip()
    yf_sym = f"{sym}.NS"
    loop = asyncio.get_event_loop()

    try:
        info, hist = await loop.run_in_executor(executor, _fetch_ticker, yf_sym)

        cur = (
            info.get("regularMarketPrice")
            or info.get("currentPrice")
        )
        if not cur and not hist.empty:
            cur = float(hist["Close"].iloc[-1])

        prev = (
            info.get("regularMarketPreviousClose")
            or info.get("previousClose")
        )
        if not prev and len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
        elif not prev and not hist.empty:
            prev = float(hist["Close"].iloc[-1])

        if not cur:
            raise HTTPException(404, f"No price data found for {sym}")

        chg = (cur - prev) if prev else 0
        chg_pct = (chg / prev * 100) if prev else 0

        def fmt(v):
            try:
                return round(float(v), 2) if v is not None else None
            except Exception:
                return None

        def fmt_int(v):
            try:
                return int(v) if v is not None else None
            except Exception:
                return None

        return {
            "symbol": sym,
            "name": info.get("longName") or info.get("shortName") or sym,
            "price": fmt(cur),
            "change": fmt(chg),
            "change_pct": fmt(chg_pct),
            "open": fmt(info.get("open") or info.get("regularMarketOpen")),
            "high": fmt(info.get("dayHigh") or info.get("regularMarketDayHigh")),
            "low": fmt(info.get("dayLow") or info.get("regularMarketDayLow")),
            "prev_close": fmt(prev),
            "volume": fmt_int(info.get("volume") or info.get("regularMarketVolume")),
            "avg_volume": fmt_int(info.get("averageVolume")),
            "market_cap": fmt_int(info.get("marketCap")),
            "pe_ratio": fmt(info.get("trailingPE")),
            "pb_ratio": fmt(info.get("priceToBook")),
            "dividend_yield": fmt(info.get("dividendYield")),
            "week_52_high": fmt(info.get("fiftyTwoWeekHigh")),
            "week_52_low": fmt(info.get("fiftyTwoWeekLow")),
            "sector": info.get("sector") or "",
            "industry": info.get("industry") or "",
            "description": (info.get("longBusinessSummary") or "")[:600],
            "eps": fmt(info.get("trailingEps")),
            "book_value": fmt(info.get("bookValue")),
            "debt_to_equity": fmt(info.get("debtToEquity")),
            "roe": fmt(info.get("returnOnEquity")),
            "roa": fmt(info.get("returnOnAssets")),
            "employees": fmt_int(info.get("fullTimeEmployees")),
            "website": info.get("website") or "",
            "exchange": "NSE",
            "currency": "INR",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error fetching {sym}: {str(e)}")


@app.get("/api/stock/{symbol}/history")
async def get_history(symbol: str, period: str = "1m"):
    sym = symbol.upper().strip()
    yf_sym = f"{sym}.NS"

    period_map = {
        "1d": ("1d", "5m"),
        "1w": ("5d", "30m"),
        "1m": ("1mo", "1d"),
        "3m": ("3mo", "1d"),
        "1y": ("1y", "1wk"),
        "5y": ("5y", "1mo"),
    }
    yf_period, yf_interval = period_map.get(period, ("1mo", "1d"))

    loop = asyncio.get_event_loop()
    try:
        hist = await loop.run_in_executor(
            executor, _fetch_history, yf_sym, yf_period, yf_interval
        )
        if hist.empty:
            raise HTTPException(404, "No history data found")

        return [
            {
                "time": idx.isoformat(),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
            for idx, row in hist.iterrows()
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/sectors")
async def get_sectors():
    loop = asyncio.get_event_loop()

    async def fetch_sector(name, sym):
        try:
            info, hist = await loop.run_in_executor(executor, _fetch_ticker, sym)
            if hist.empty or len(hist) < 2:
                return None
            cur = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            chg_pct = ((cur - prev) / prev * 100) if prev else 0
            return {
                "name": name,
                "change_pct": round(chg_pct, 2),
                "price": round(cur, 2),
            }
        except Exception:
            return None

    tasks = [fetch_sector(n, s) for n, s in SECTOR_INDICES.items()]
    raw = await asyncio.gather(*tasks)
    return [r for r in raw if r]
