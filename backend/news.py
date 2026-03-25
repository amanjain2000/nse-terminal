"""
News ingestion + PESTEL scoring engine.
Sources: free RSS feeds — no API keys needed.
"""
import httpx
import time
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dataclasses import dataclass, field

# ── RSS Sources ───────────────────────────────────────────────────────────────
RSS_FEEDS = [
    # Economic Times
    {"name": "Economic Times — Markets",  "url": "https://economictimes.indiatimes.com/markets/rss.cms"},
    {"name": "Economic Times — Stocks",   "url": "https://economictimes.indiatimes.com/markets/stocks/rss.cms"},
    {"name": "Economic Times — Economy",  "url": "https://economictimes.indiatimes.com/news/economy/rss.cms"},
    {"name": "Economic Times — Finance",  "url": "https://economictimes.indiatimes.com/news/company/corporate-news/rss.cms"},
    # Business Standard
    {"name": "Business Standard — Markets", "url": "https://www.business-standard.com/rss/markets-106.rss"},
    {"name": "Business Standard — Economy", "url": "https://www.business-standard.com/rss/economy-102.rss"},
    {"name": "Business Standard — Companies","url": "https://www.business-standard.com/rss/companies-101.rss"},
    # Moneycontrol
    {"name": "Moneycontrol — News",       "url": "https://www.moneycontrol.com/rss/latestnews.xml"},
    {"name": "Moneycontrol — Markets",    "url": "https://www.moneycontrol.com/rss/marketreports.xml"},
    # Hindu Business Line
    {"name": "BusinessLine — Markets",    "url": "https://www.thehindubusinessline.com/markets/?service=rss"},
    {"name": "BusinessLine — Economy",    "url": "https://www.thehindubusinessline.com/economy/?service=rss"},
    # Mint
    {"name": "Mint — Markets",            "url": "https://www.livemint.com/rss/markets"},
    {"name": "Mint — Companies",          "url": "https://www.livemint.com/rss/companies"},
]

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NSETerminal/1.0; RSS Reader)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# ── PESTEL keyword maps ───────────────────────────────────────────────────────
# Each category has weighted keywords. Higher weight = stronger signal.
PESTEL_KEYWORDS = {
    "Political": {
        "high": [
            "government policy", "rbi policy", "sebi", "ministry", "cabinet", "parliament",
            "budget", "union budget", "election", "regulation", "regulatory", "government ban",
            "fdi policy", "import duty", "export ban", "geopolitical", "sanctions",
            "tax policy", "gst", "disinvestment", "privatisation", "nationalization",
        ],
        "medium": [
            "government", "policy", "minister", "political", "regulatory",
            "compliance", "nda", "opposition", "legislation", "bill passed",
        ],
        "low": ["pm modi", "finance minister", "bjp", "congress", "state government"],
    },
    "Economic": {
        "high": [
            "gdp", "inflation", "cpi", "wpi", "repo rate", "interest rate", "rbi rate",
            "monetary policy", "mpc", "credit policy", "economic growth", "recession",
            "trade deficit", "current account", "forex reserves", "rupee", "usd inr",
            "iip", "pmi", "employment", "unemployment", "fiscal deficit", "tax revenue",
        ],
        "medium": [
            "economy", "economic", "growth", "market cap", "revenue", "profit", "earnings",
            "quarterly results", "fy25", "fy26", "annual results", "ebitda", "margin",
            "capex", "debt", "credit rating", "downgrade", "upgrade",
        ],
        "low": ["sales", "order book", "contract", "deal", "acquisition", "merger"],
    },
    "Social": {
        "high": [
            "consumer demand", "consumer sentiment", "rural demand", "urban demand",
            "demographic", "labour law", "employment generation", "wage", "social media",
            "brand reputation", "boycott", "consumer protection", "public health",
            "pandemic", "epidemic", "health crisis",
        ],
        "medium": [
            "consumer", "customer", "workforce", "employee", "hiring", "layoff",
            "social", "community", "csr", "esg", "gender", "diversity",
        ],
        "low": ["brand", "reputation", "marketing", "advertisement", "campaign"],
    },
    "Technological": {
        "high": [
            "artificial intelligence", "ai", "machine learning", "automation",
            "digital transformation", "technology", "innovation", "patent", "r&d",
            "semiconductor", "chip", "ev", "electric vehicle", "renewable energy",
            "blockchain", "cloud computing", "cybersecurity", "data breach",
            "5g", "iot", "robotics", "biotech", "pharma r&d",
        ],
        "medium": [
            "tech", "software", "platform", "digital", "online", "app", "startup",
            "investment in tech", "it spending", "digital india",
        ],
        "low": ["upgrade", "new product", "launch", "update"],
    },
    "Environmental": {
        "high": [
            "climate change", "carbon emission", "net zero", "carbon neutral",
            "esg", "sustainability", "renewable", "solar", "wind energy",
            "pollution", "environmental compliance", "green", "paris agreement",
            "deforestation", "water scarcity", "drought", "flood",
            "carbon credit", "emission trading",
        ],
        "medium": [
            "environment", "environmental", "green energy", "clean energy",
            "waste management", "recycling", "sustainable", "eco-friendly",
        ],
        "low": ["natural disaster", "monsoon", "weather", "climate"],
    },
    "Legal": {
        "high": [
            "court order", "supreme court", "high court", "tribunal", "nclt",
            "litigation", "lawsuit", "legal challenge", "sebi order", "rbi action",
            "penalty", "fine", "enforcement", "investigation", "cbi", "ed",
            "insolvency", "bankruptcy", "ibc", "arbitration", "fraud",
        ],
        "medium": [
            "legal", "regulatory action", "compliance", "violation", "notice",
            "show cause", "inquiry", "audit", "governance", "board meeting",
        ],
        "low": ["contract dispute", "ip", "patent dispute", "trademark"],
    },
}

# Sentiment keywords
POSITIVE_WORDS = {
    "surge", "rally", "gain", "rise", "jump", "soar", "hit high", "record high",
    "strong", "beat", "outperform", "upgrade", "positive", "growth", "profit",
    "win", "approval", "breakthrough", "expansion", "order win", "new contract",
    "acquisition", "good", "bullish", "buy", "upside", "robust", "milestone",
}
NEGATIVE_WORDS = {
    "fall", "drop", "decline", "crash", "plunge", "sink", "hit low", "record low",
    "weak", "miss", "underperform", "downgrade", "negative", "loss", "penalty",
    "reject", "ban", "delay", "risk", "concern", "sell", "downside", "bearish",
    "fraud", "probe", "investigation", "fine", "crisis", "warning", "cut",
}


@dataclass
class NewsItem:
    title: str
    summary: str
    url: str
    source: str
    published: str
    pestel_categories: list = field(default_factory=list)
    sentiment: str = "neutral"   # positive / negative / neutral
    sentiment_score: float = 0.0  # -1 to +1
    relevance_score: float = 0.0


def _fetch_rss(feed: dict, timeout: int = 8) -> list[dict]:
    """Fetch and parse one RSS feed. Returns list of raw items."""
    try:
        r = httpx.get(feed["url"], headers=RSS_HEADERS, timeout=timeout, follow_redirects=True)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = []

        # RSS 2.0
        for item in root.findall(".//item"):
            title   = (item.findtext("title") or "").strip()
            desc    = (item.findtext("description") or "").strip()
            link    = (item.findtext("link") or "").strip()
            pub     = (item.findtext("pubDate") or "").strip()
            # Clean HTML from description
            desc = re.sub(r"<[^>]+>", " ", desc).strip()
            desc = re.sub(r"\s+", " ", desc)[:400]
            items.append({"title": title, "summary": desc, "url": link,
                          "source": feed["name"], "published": pub})

        # Atom feed fallback
        if not items:
            for entry in root.findall("atom:entry", ns):
                title   = (entry.findtext("atom:title", namespaces=ns) or "").strip()
                summary = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
                link_el  = entry.find("atom:link", ns)
                link    = link_el.get("href", "") if link_el is not None else ""
                pub     = (entry.findtext("atom:published", namespaces=ns) or "").strip()
                summary = re.sub(r"<[^>]+>", " ", summary).strip()[:400]
                items.append({"title": title, "summary": summary, "url": link,
                              "source": feed["name"], "published": pub})

        return items
    except Exception:
        return []


def _score_pestel(text: str) -> list[str]:
    """Return list of PESTEL categories triggered by the text."""
    text_lower = text.lower()
    triggered = []
    for category, weights in PESTEL_KEYWORDS.items():
        score = 0
        for kw in weights.get("high", []):
            if kw in text_lower:
                score += 3
        for kw in weights.get("medium", []):
            if kw in text_lower:
                score += 1.5
        for kw in weights.get("low", []):
            if kw in text_lower:
                score += 0.5
        if score >= 1.5:
            triggered.append(category)
    return triggered


def _score_sentiment(text: str) -> tuple[str, float]:
    """Return (label, score) where score is -1 to +1."""
    text_lower = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text_lower)
    total = pos + neg
    if total == 0:
        return "neutral", 0.0
    score = (pos - neg) / total
    if score > 0.2:
        return "positive", round(score, 2)
    elif score < -0.2:
        return "negative", round(score, 2)
    return "neutral", round(score, 2)


def _relevance(item: dict, symbol: str, company_name: str) -> float:
    """Score 0–10 how relevant a news item is to the given stock."""
    text = (item["title"] + " " + item["summary"]).lower()
    sym_lower  = symbol.lower()
    name_lower = company_name.lower()

    score = 0.0
    # Exact symbol match in title = very strong
    if sym_lower in item["title"].lower():
        score += 6
    elif sym_lower in text:
        score += 3

    # Company name words in title/text
    name_words = [w for w in name_lower.split() if len(w) > 3
                  and w not in ("limited", "india", "ltd", "company", "corp")]
    for w in name_words:
        if w in item["title"].lower():
            score += 2
        elif w in text:
            score += 0.5

    return min(score, 10.0)


def fetch_news_for_symbol(
    symbol: str,
    company_name: str,
    max_items: int = 30,
    min_relevance: float = 1.0,
) -> list[dict]:
    """
    Fetch news from all RSS feeds, filter/rank by relevance to symbol,
    annotate with PESTEL categories and sentiment.
    Returns top `max_items` results sorted by relevance then recency.
    """
    all_raw = []
    for feed in RSS_FEEDS:
        items = _fetch_rss(feed, timeout=6)
        all_raw.extend(items)
        time.sleep(0.05)

    # Deduplicate by URL
    seen_urls = set()
    unique = []
    for item in all_raw:
        if item["url"] and item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique.append(item)

    # Score each item
    annotated = []
    for item in unique:
        rel = _relevance(item, symbol, company_name)
        if rel < min_relevance:
            continue
        text = item["title"] + " " + item["summary"]
        pestel = _score_pestel(text)
        sentiment, score = _score_sentiment(text)
        annotated.append({
            "title":             item["title"],
            "summary":           item["summary"][:300],
            "url":               item["url"],
            "source":            item["source"],
            "published":         item["published"],
            "pestel_categories": pestel,
            "sentiment":         sentiment,
            "sentiment_score":   score,
            "relevance_score":   rel,
        })

    # Sort: relevance desc, then recency (we don't parse dates to keep it simple)
    annotated.sort(key=lambda x: x["relevance_score"], reverse=True)
    return annotated[:max_items]


def compute_pestel_scores(news_items: list[dict]) -> dict:
    """
    Aggregate PESTEL signal scores from news items.
    Returns dict with each category's score (0–100) and sentiment breakdown.
    """
    categories = list(PESTEL_KEYWORDS.keys())
    scores = {c: {"count": 0, "positive": 0, "negative": 0, "neutral": 0, "score": 0} for c in categories}

    for item in news_items:
        weight = max(item.get("relevance_score", 1), 1)
        for cat in item.get("pestel_categories", []):
            if cat in scores:
                scores[cat]["count"] += 1
                s = item.get("sentiment", "neutral")
                scores[cat][s] += weight
                # Score: positive sentiment → green, negative → red
                sent_score = item.get("sentiment_score", 0)
                scores[cat]["score"] += sent_score * weight

    # Normalize scores to 0–100 (50 = neutral)
    for cat in categories:
        d = scores[cat]
        total_weight = d["positive"] + d["negative"] + d["neutral"]
        if total_weight > 0:
            raw = d["score"] / total_weight
            d["normalized"] = round(50 + raw * 50, 1)
        else:
            d["normalized"] = 50.0
        d["signal"] = (
            "bullish" if d["normalized"] > 60
            else "bearish" if d["normalized"] < 40
            else "neutral"
        )

    return scores


def get_macro_pestel() -> dict:
    """
    Macro-level PESTEL — fetch market-wide news and score.
    Used for the overall market overview.
    """
    all_raw = []
    for feed in RSS_FEEDS[:6]:  # use first 6 feeds for macro
        items = _fetch_rss(feed, timeout=5)
        all_raw.extend(items[:10])
        time.sleep(0.05)

    macro_items = []
    for item in all_raw[:60]:
        text = item["title"] + " " + item["summary"]
        pestel = _score_pestel(text)
        sentiment, score = _score_sentiment(text)
        if pestel:
            macro_items.append({
                **item,
                "pestel_categories": pestel,
                "sentiment": sentiment,
                "sentiment_score": score,
                "relevance_score": 3.0,
            })

    return compute_pestel_scores(macro_items)
