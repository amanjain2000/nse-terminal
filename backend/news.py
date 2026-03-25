"""
News ingestion + LLM-powered PESTEL & sentiment analysis.
RSS fetching is free. Analysis uses Claude via Anthropic API.
"""
import httpx
import time
import re
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime

# ── RSS Sources ───────────────────────────────────────────────────────────────
RSS_FEEDS = [
    {"name": "Economic Times — Markets",   "url": "https://economictimes.indiatimes.com/markets/rss.cms"},
    {"name": "Economic Times — Stocks",    "url": "https://economictimes.indiatimes.com/markets/stocks/rss.cms"},
    {"name": "Economic Times — Economy",   "url": "https://economictimes.indiatimes.com/news/economy/rss.cms"},
    {"name": "Economic Times — Corporate", "url": "https://economictimes.indiatimes.com/news/company/corporate-news/rss.cms"},
    {"name": "Business Standard — Markets","url": "https://www.business-standard.com/rss/markets-106.rss"},
    {"name": "Business Standard — Economy","url": "https://www.business-standard.com/rss/economy-102.rss"},
    {"name": "Business Standard — Companies","url": "https://www.business-standard.com/rss/companies-101.rss"},
    {"name": "Moneycontrol — News",        "url": "https://www.moneycontrol.com/rss/latestnews.xml"},
    {"name": "Moneycontrol — Markets",     "url": "https://www.moneycontrol.com/rss/marketreports.xml"},
    {"name": "BusinessLine — Markets",     "url": "https://www.thehindubusinessline.com/markets/?service=rss"},
    {"name": "BusinessLine — Economy",     "url": "https://www.thehindubusinessline.com/economy/?service=rss"},
    {"name": "Mint — Markets",             "url": "https://www.livemint.com/rss/markets"},
    {"name": "Mint — Companies",           "url": "https://www.livemint.com/rss/companies"},
]

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NSETerminal/1.0; RSS Reader)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


# ── RSS Fetching ──────────────────────────────────────────────────────────────

def _fetch_rss(feed: dict, timeout: int = 8) -> list[dict]:
    try:
        r = httpx.get(feed["url"], headers=RSS_HEADERS, timeout=timeout, follow_redirects=True)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = []

        for item in root.findall(".//item"):
            title   = (item.findtext("title") or "").strip()
            desc    = re.sub(r"<[^>]+>", " ", item.findtext("description") or "").strip()
            desc    = re.sub(r"\s+", " ", desc)[:350]
            link    = (item.findtext("link") or "").strip()
            pub     = (item.findtext("pubDate") or "").strip()
            if title:
                items.append({"title": title, "summary": desc, "url": link,
                              "source": feed["name"], "published": pub})

        if not items:
            for entry in root.findall("atom:entry", ns):
                title   = (entry.findtext("atom:title", namespaces=ns) or "").strip()
                summary = re.sub(r"<[^>]+>", " ",
                                 entry.findtext("atom:summary", namespaces=ns) or "").strip()[:350]
                link_el = entry.find("atom:link", ns)
                link    = link_el.get("href", "") if link_el is not None else ""
                pub     = (entry.findtext("atom:published", namespaces=ns) or "").strip()
                if title:
                    items.append({"title": title, "summary": summary, "url": link,
                                  "source": feed["name"], "published": pub})
        return items
    except Exception:
        return []


def _relevance_prefilter(item: dict, symbol: str, company_name: str) -> float:
    """
    Fast pre-filter before sending to LLM — avoids wasting API calls on
    clearly irrelevant news. Returns 0.0 (skip) or a rough relevance 1–10.
    """
    text      = (item["title"] + " " + item["summary"]).lower()
    sym_lower = symbol.lower()
    # Extract meaningful name words (skip generic words)
    stop = {"limited", "india", "ltd", "company", "corp", "private", "pvt",
            "industries", "enterprises", "group", "holdings", "services"}
    name_words = [w for w in company_name.lower().split()
                  if len(w) > 3 and w not in stop]

    score = 0.0
    if sym_lower in item["title"].lower():
        score += 7
    elif sym_lower in text:
        score += 3
    for w in name_words:
        if w in item["title"].lower():
            score += 3
        elif w in text:
            score += 1
    return min(score, 10.0)


# ── LLM Analysis ─────────────────────────────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = """You are a financial news analyst specializing in Indian equity markets.
You will receive a batch of news articles related to a specific NSE-listed stock.
For each article, you must analyze and return structured JSON.

PESTEL categories (choose ALL that apply, can be empty list):
- Political: government policy, regulation, SEBI/RBI directives, elections, trade policy, FDI rules
- Economic: GDP, inflation, interest rates, earnings, revenue, profit, macroeconomic indicators, RBI rates, forex
- Social: consumer behavior, workforce, demographics, ESG, brand reputation, public opinion, health trends
- Technological: AI, automation, R&D, patents, digital transformation, new products, IT, semiconductor
- Environmental: climate, sustainability, pollution, carbon emissions, green energy, natural disasters, ESG
- Legal: court orders, NCLT, SEBI/ED actions, penalties, litigation, compliance violations, fraud

Sentiment:
- positive: clearly good for the stock/company (profit growth, order wins, upgrades, strong results)
- negative: clearly bad (losses, penalties, downgrades, fraud, weak results, regulatory action)
- neutral: factual/balanced or unclear market impact

sentiment_score: float from -1.0 (very negative) to +1.0 (very positive), 0.0 = neutral

reasoning: 1 sentence explaining why you chose these categories and sentiment.

Return ONLY a JSON array, no markdown, no explanation outside the array:
[
  {
    "index": 0,
    "pestel_categories": ["Economic", "Political"],
    "sentiment": "positive",
    "sentiment_score": 0.6,
    "reasoning": "RBI rate cut reduces borrowing costs, boosting profitability outlook."
  },
  ...
]"""


def _analyze_batch_llm(articles: list[dict], symbol: str, api_key: str) -> list[dict]:
    """
    Send a batch of articles to Groq (free tier) for PESTEL + sentiment analysis.
    Uses Llama 3.1 8B — fast, free, 14,400 req/day limit.
    Returns list of analysis results matching the input indices.
    """
    if not articles:
        return []

    articles_text = ""
    for i, art in enumerate(articles):
        articles_text += f"\n[{i}] SOURCE: {art['source']}\nTITLE: {art['title']}\nSUMMARY: {art['summary']}\n"

    user_msg = (
        f"Analyze these {len(articles)} news articles about {symbol} (NSE-listed Indian stock).\n"
        f"Return a JSON array with one object per article.\n\n"
        f"{articles_text}"
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    # Groq uses OpenAI-compatible chat completions format
    body = {
        "model":       "llama-3.1-8b-instant",   # free, fast, very capable
        "max_tokens":  2000,
        "temperature": 0.1,   # low temp = more consistent JSON output
        "messages": [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    }

    try:
        r = httpx.post(GROQ_API_URL, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        resp = r.json()
        text = resp["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        results = json.loads(text)
        if isinstance(results, list):
            return results
    except Exception:
        pass

    # Fallback: neutral for all if Groq call fails
    return [{"index": i, "pestel_categories": [], "sentiment": "neutral",
             "sentiment_score": 0.0, "reasoning": "Analysis unavailable."}
            for i in range(len(articles))]


def _analyze_all_articles(articles: list[dict], symbol: str, api_key: str,
                          batch_size: int = 10) -> list[dict]:
    """
    Process all articles through LLM in batches of `batch_size`.
    Merges LLM results back into the article dicts.
    """
    annotated = []
    for start in range(0, len(articles), batch_size):
        batch = articles[start: start + batch_size]
        llm_results = _analyze_batch_llm(batch, symbol, api_key)

        # Build a lookup by index
        llm_by_idx = {r.get("index", i): r for i, r in enumerate(llm_results)}

        for j, art in enumerate(batch):
            llm = llm_by_idx.get(j, {})
            annotated.append({
                **art,
                "pestel_categories": llm.get("pestel_categories", []),
                "sentiment":         llm.get("sentiment", "neutral"),
                "sentiment_score":   float(llm.get("sentiment_score", 0.0)),
                "reasoning":         llm.get("reasoning", ""),
            })

        # Small delay between batches to be kind to the API
        if start + batch_size < len(articles):
            time.sleep(0.3)

    return annotated


# ── Main entry points ─────────────────────────────────────────────────────────

def fetch_news_for_symbol(
    symbol: str,
    company_name: str,
    api_key: str,
    max_items: int = 30,
    min_relevance: float = 1.0,
) -> dict:
    """
    1. Fetch all RSS feeds in parallel (no API key needed)
    2. Pre-filter by relevance to the symbol
    3. Send relevant articles to Claude for PESTEL + sentiment
    4. Compute aggregate PESTEL scores
    Returns: {"news": [...], "pestel": {...}}
    """
    # Step 1: Fetch all feeds
    all_raw = []
    for feed in RSS_FEEDS:
        items = _fetch_rss(feed, timeout=6)
        all_raw.extend(items)
        time.sleep(0.03)

    # Deduplicate by URL
    seen_urls: set = set()
    unique = []
    for item in all_raw:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(item)
        elif not url:
            unique.append(item)

    # Step 2: Pre-filter by relevance
    with_relevance = []
    for item in unique:
        rel = _relevance_prefilter(item, symbol, company_name)
        if rel >= min_relevance:
            with_relevance.append({**item, "relevance_score": rel})

    # Sort by relevance, take top candidates for LLM
    with_relevance.sort(key=lambda x: x["relevance_score"], reverse=True)
    candidates = with_relevance[:max_items]

    # Step 3: LLM analysis
    if api_key and candidates:
        annotated = _analyze_all_articles(candidates, symbol, api_key)
    else:
        # No API key — return articles without PESTEL analysis
        annotated = [{**art, "pestel_categories": [], "sentiment": "neutral",
                      "sentiment_score": 0.0, "reasoning": ""}
                     for art in candidates]

    # Step 4: Compute aggregate PESTEL scores
    pestel_scores = compute_pestel_scores(annotated)

    return {"news": annotated, "pestel": pestel_scores}


def compute_pestel_scores(news_items: list[dict]) -> dict:
    """
    Aggregate PESTEL signals from LLM-annotated news items.
    Returns a dict with per-category scores, counts, and bullish/bearish signal.
    """
    categories = ["Political", "Economic", "Social", "Technological", "Environmental", "Legal"]
    scores = {c: {"count": 0, "positive": 0, "negative": 0, "neutral": 0,
                  "score_sum": 0.0, "articles": []} for c in categories}

    for item in news_items:
        rel_weight = max(item.get("relevance_score", 1.0), 1.0)
        for cat in item.get("pestel_categories", []):
            if cat not in scores:
                continue
            scores[cat]["count"] += 1
            sent = item.get("sentiment", "neutral")
            scores[cat][sent] = scores[cat].get(sent, 0) + 1
            scores[cat]["score_sum"] += item.get("sentiment_score", 0.0) * rel_weight
            # Keep top 3 article titles per category for display
            if len(scores[cat]["articles"]) < 3:
                scores[cat]["articles"].append({
                    "title":     item.get("title", ""),
                    "sentiment": sent,
                    "reasoning": item.get("reasoning", ""),
                })

    for cat in categories:
        d = scores[cat]
        total_weight = max(d["count"], 1)
        raw_score    = d["score_sum"] / total_weight
        # Normalize to 0–100 (50 = neutral baseline)
        d["normalized"] = round(50 + raw_score * 50, 1)
        d["signal"] = (
            "bullish" if d["normalized"] > 60
            else "bearish" if d["normalized"] < 40
            else "neutral"
        )
        del d["score_sum"]  # Don't expose raw intermediate

    return scores


def get_macro_pestel(api_key: str) -> dict:
    """
    Market-wide PESTEL from general market news (no stock filter).
    """
    all_raw = []
    for feed in RSS_FEEDS[:8]:
        items = _fetch_rss(feed, timeout=5)
        all_raw.extend(items[:8])
        time.sleep(0.03)

    # Take top 30 macro items
    candidates = [
        {**item, "relevance_score": 3.0}
        for item in all_raw[:30]
        if item.get("title")
    ]

    if api_key and candidates:
        annotated = _analyze_all_articles(candidates, "MACRO", api_key, batch_size=15)
    else:
        annotated = [{**art, "pestel_categories": [], "sentiment": "neutral",
                      "sentiment_score": 0.0, "reasoning": ""}
                     for art in candidates]

    return compute_pestel_scores(annotated)
