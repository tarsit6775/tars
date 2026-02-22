"""
╔══════════════════════════════════════════════════════════════╗
║   TARS Research APIs — Reliable, API-First Data Sources      ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Phase 1:  Serper.dev Google Search API (primary)            ║
║  Phase 2:  Wikipedia REST API (knowledge base)               ║
║  Phase 3:  Search fallback chain (Serper → CDP → DDG)        ║
║  Phase 4:  HTTP page reader (no browser needed)              ║
║  Phase 5:  Yahoo Finance (stocks, crypto, market data)       ║
║  Phase 6:  Semantic Scholar + arXiv (academic papers)        ║
║  Phase 7:  Google News RSS (current events)                  ║
║  Phase 17: Research cache (1-hour TTL)                       ║
║                                                              ║
║  All functions return plain strings — no dict wrappers.      ║
║  The ResearchAgent calls these directly from _dispatch().    ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import re
import time
import hashlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════
#  Phase 17: Research Cache (1-hour TTL)
# ═══════════════════════════════════════════════════════

class ResearchCache:
    """In-memory cache with 1-hour TTL. Shared across agent invocations."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
            cls._instance._max_entries = 200
        return cls._instance

    def _key(self, prefix, query):
        h = hashlib.md5(f"{prefix}:{query}".encode()).hexdigest()[:16]
        return f"{prefix}:{h}"

    def get(self, prefix, query):
        key = self._key(prefix, query)
        entry = self._cache.get(key)
        if entry and time.time() - entry["ts"] < 3600:
            return entry["data"]
        return None

    def put(self, prefix, query, data):
        key = self._key(prefix, query)
        self._cache[key] = {"data": data, "ts": time.time()}
        # Prune if too large
        if len(self._cache) > self._max_entries:
            oldest = sorted(self._cache.items(), key=lambda x: x[1]["ts"])
            for k, _ in oldest[:50]:
                del self._cache[k]

    def stats(self):
        valid = sum(1 for v in self._cache.values() if time.time() - v["ts"] < 3600)
        return {"entries": len(self._cache), "valid": valid}


_cache = ResearchCache()


# ═══════════════════════════════════════════════════════
#  HTTP helpers
# ═══════════════════════════════════════════════════════

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _http_get(url, headers=None, timeout=15):
    """Simple HTTP GET → string. Returns None on failure."""
    h = dict(_HEADERS)
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _http_json(url, headers=None, timeout=15):
    """HTTP GET → parsed JSON dict. Returns None on failure."""
    raw = _http_get(url, headers, timeout)
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _http_post_json(url, payload, headers=None, timeout=15):
    """HTTP POST JSON → parsed JSON dict."""
    h = dict(_HEADERS)
    h["Content-Type"] = "application/json"
    if headers:
        h.update(headers)
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


# ═══════════════════════════════════════════════════════
#  Phase 1: Serper.dev Google Search API
# ═══════════════════════════════════════════════════════

def serper_search(query, api_key, num_results=10, search_type="search"):
    """
    Google search via Serper.dev API. $5/2500 searches. Zero CAPTCHAs.
    
    search_type: "search" (web), "news", "images", "scholar"
    Returns formatted string with results + trust scores.
    """
    if not api_key:
        return None  # Fall through to next search method

    cached = _cache.get("serper", f"{search_type}:{query}")
    if cached:
        return cached

    payload = {"q": query, "num": min(num_results, 20)}
    data = _http_post_json(
        f"https://google.serper.dev/{search_type}",
        payload,
        headers={"X-API-KEY": api_key},
        timeout=10,
    )

    if not data:
        return None

    lines = [f"## Google Search: '{query}'\n"]

    # Knowledge graph
    kg = data.get("knowledgeGraph", {})
    if kg:
        lines.append(f"### Knowledge Panel: {kg.get('title', '')}")
        if kg.get("type"):
            lines.append(f"Type: {kg['type']}")
        if kg.get("description"):
            lines.append(f"{kg['description']}")
        for attr_key, attr_val in kg.get("attributes", {}).items():
            lines.append(f"  {attr_key}: {attr_val}")
        lines.append("")

    # Answer box
    answer = data.get("answerBox", {})
    if answer:
        lines.append(f"### Direct Answer")
        if answer.get("answer"):
            lines.append(f"**{answer['answer']}**")
        if answer.get("snippet"):
            lines.append(answer["snippet"])
        if answer.get("title"):
            lines.append(f"Source: {answer['title']}")
        lines.append("")

    # Organic results
    organic = data.get("organic", [])
    for i, r in enumerate(organic[:num_results], 1):
        url = r.get("link", "")
        score = _score_url(url)
        trust_label = "HIGH" if score >= 70 else "MED" if score >= 45 else "LOW"
        lines.append(f"{i}. [{trust_label}:{score}] **{r.get('title', 'No title')}**")
        lines.append(f"   URL: {url}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("date"):
            lines.append(f"   Date: {r['date']}")
        lines.append("")

    # People also ask
    paa = data.get("peopleAlsoAsk", [])
    if paa:
        lines.append("### People Also Ask")
        for q in paa[:5]:
            lines.append(f"  - {q.get('question', '')}")
            if q.get("snippet"):
                lines.append(f"    → {q['snippet'][:200]}")
        lines.append("")

    # Related searches
    related = data.get("relatedSearches", [])
    if related:
        lines.append("### Related Searches")
        for r in related[:5]:
            lines.append(f"  - {r.get('query', '')}")

    result = "\n".join(lines)
    _cache.put("serper", f"{search_type}:{query}", result)
    return result


def serper_news(query, api_key, num_results=10):
    """Search Google News via Serper."""
    if not api_key:
        return None

    cached = _cache.get("serper_news", query)
    if cached:
        return cached

    data = _http_post_json(
        "https://google.serper.dev/news",
        {"q": query, "num": min(num_results, 20)},
        headers={"X-API-KEY": api_key},
        timeout=10,
    )

    if not data:
        return None

    news = data.get("news", [])
    lines = [f"## News: '{query}' ({len(news)} results)\n"]
    for i, n in enumerate(news[:num_results], 1):
        lines.append(f"{i}. **{n.get('title', '')}**")
        lines.append(f"   Source: {n.get('source', '')} | {n.get('date', '')}")
        lines.append(f"   URL: {n.get('link', '')}")
        if n.get("snippet"):
            lines.append(f"   {n['snippet']}")
        lines.append("")

    result = "\n".join(lines)
    _cache.put("serper_news", query, result)
    return result


def serper_scholar(query, api_key, num_results=10):
    """Search Google Scholar via Serper."""
    if not api_key:
        return None

    cached = _cache.get("serper_scholar", query)
    if cached:
        return cached

    data = _http_post_json(
        "https://google.serper.dev/scholar",
        {"q": query, "num": min(num_results, 10)},
        headers={"X-API-KEY": api_key},
        timeout=10,
    )

    if not data:
        return None

    papers = data.get("organic", [])
    lines = [f"## Scholar: '{query}' ({len(papers)} results)\n"]
    for i, p in enumerate(papers[:num_results], 1):
        lines.append(f"{i}. **{p.get('title', '')}**")
        if p.get("publication_info", {}).get("summary"):
            lines.append(f"   {p['publication_info']['summary']}")
        if p.get("inline_links", {}).get("cited_by", {}).get("total"):
            lines.append(f"   Cited by: {p['inline_links']['cited_by']['total']}")
        lines.append(f"   URL: {p.get('link', '')}")
        if p.get("snippet"):
            lines.append(f"   {p['snippet']}")
        lines.append("")

    result = "\n".join(lines)
    _cache.put("serper_scholar", query, result)
    return result


# ═══════════════════════════════════════════════════════
#  Phase 2: Wikipedia REST API
# ═══════════════════════════════════════════════════════

def wikipedia_summary(topic):
    """Get Wikipedia summary for a topic. Free, no API key needed."""
    cached = _cache.get("wiki_summary", topic)
    if cached:
        return cached

    encoded = urllib.parse.quote(topic.replace(" ", "_"))
    data = _http_json(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}",
        timeout=10,
    )

    if not data or data.get("type") == "https://mediawiki.org/wiki/HyperSwitch/errors/not_found":
        # Try search instead
        return wikipedia_search(topic)

    lines = [f"## Wikipedia: {data.get('title', topic)}\n"]

    if data.get("description"):
        lines.append(f"*{data['description']}*\n")

    extract = data.get("extract", "")
    if extract:
        lines.append(extract)

    if data.get("content_urls", {}).get("desktop", {}).get("page"):
        lines.append(f"\nFull article: {data['content_urls']['desktop']['page']}")

    # Get key facts from Wikidata if available
    wikidata_id = data.get("wikibase_item")
    if wikidata_id:
        lines.append(f"Wikidata: {wikidata_id}")

    result = "\n".join(lines)
    _cache.put("wiki_summary", topic, result)
    return result


def wikipedia_search(query, limit=5):
    """Search Wikipedia for articles matching a query."""
    cached = _cache.get("wiki_search", query)
    if cached:
        return cached

    encoded = urllib.parse.quote_plus(query)
    data = _http_json(
        f"https://en.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={encoded}&srlimit={limit}&format=json",
        timeout=10,
    )

    if not data:
        return f"Wikipedia search failed for '{query}'"

    results = data.get("query", {}).get("search", [])
    if not results:
        return f"No Wikipedia articles found for '{query}'"

    lines = [f"## Wikipedia Search: '{query}' ({len(results)} results)\n"]
    for i, r in enumerate(results, 1):
        snippet = re.sub(r'<[^>]+>', '', r.get("snippet", ""))
        lines.append(f"{i}. **{r['title']}**")
        lines.append(f"   {snippet}")
        lines.append(f"   URL: https://en.wikipedia.org/wiki/{urllib.parse.quote(r['title'].replace(' ', '_'))}")
        lines.append("")

    result = "\n".join(lines)
    _cache.put("wiki_search", query, result)
    return result


def wikipedia_full_article(title, max_chars=20000):
    """Get full Wikipedia article text. Use for deep reading."""
    cached = _cache.get("wiki_full", title)
    if cached:
        return cached

    encoded = urllib.parse.quote(title.replace(" ", "_"))
    # Use the TextExtracts API for clean plaintext
    data = _http_json(
        f"https://en.wikipedia.org/w/api.php?action=query&titles={encoded}"
        f"&prop=extracts&explaintext=1&format=json",
        timeout=15,
    )

    if not data:
        return f"Could not fetch Wikipedia article: {title}"

    pages = data.get("query", {}).get("pages", {})
    for page_id, page in pages.items():
        if page_id == "-1":
            return f"Wikipedia article not found: {title}"
        extract = page.get("extract", "")
        if extract:
            lines = [f"## Wikipedia: {page.get('title', title)}\n"]
            lines.append(f"URL: https://en.wikipedia.org/wiki/{encoded}\n")
            lines.append(extract[:max_chars])
            if len(extract) > max_chars:
                lines.append(f"\n... [truncated at {max_chars} chars, full article is {len(extract)} chars]")
            result = "\n".join(lines)
            _cache.put("wiki_full", title, result)
            return result

    return f"No content found for Wikipedia article: {title}"


def wikipedia_infobox(title):
    """Extract structured infobox data from Wikipedia article."""
    cached = _cache.get("wiki_infobox", title)
    if cached:
        return cached

    encoded = urllib.parse.quote(title.replace(" ", "_"))
    # Get parsed wikitext with infobox properties
    data = _http_json(
        f"https://en.wikipedia.org/w/api.php?action=query&titles={encoded}"
        f"&prop=revisions&rvprop=content&rvsection=0&format=json",
        timeout=15,
    )

    if not data:
        return None

    pages = data.get("query", {}).get("pages", {})
    for page_id, page in pages.items():
        revisions = page.get("revisions", [])
        if not revisions:
            return None
        wikitext = revisions[0].get("*", "")

        # Parse infobox fields
        infobox_match = re.search(r'\{\{Infobox(.*?)(?:\n\}\}|\n\|)', wikitext, re.S | re.I)
        if not infobox_match:
            return None

        # Extract | key = value pairs
        fields = re.findall(r'\|\s*(\w[\w\s]*?)\s*=\s*(.*?)(?=\n\||\n\}\})', wikitext, re.S)
        if not fields:
            return None

        lines = [f"## Infobox: {title}\n"]
        for key, value in fields[:30]:
            # Clean wikitext markup
            clean_val = re.sub(r'\[\[([^|\]]*\|)?([^\]]*)\]\]', r'\2', value)
            clean_val = re.sub(r'\{\{[^}]*\}\}', '', clean_val)
            clean_val = re.sub(r'<[^>]+>', '', clean_val).strip()
            if clean_val and len(clean_val) < 500:
                lines.append(f"  {key.strip()}: {clean_val}")

        result = "\n".join(lines)
        _cache.put("wiki_infobox", title, result)
        return result

    return None


# ═══════════════════════════════════════════════════════
#  Phase 5: Yahoo Finance (stocks, crypto, market data)
# ═══════════════════════════════════════════════════════

def yahoo_finance_quote(symbol):
    """Get current stock/crypto quote from Yahoo Finance API."""
    cached = _cache.get("yf_quote", symbol)
    if cached:
        return cached

    symbol = symbol.upper().strip()
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
        f"?interval=1d&range=5d"
    )
    # Yahoo Finance requires specific headers to avoid 401/403
    yf_headers = dict(_HEADERS)
    yf_headers["Accept"] = "application/json"
    data = _http_json(url, headers=yf_headers, timeout=10)

    if not data or "chart" not in data:
        return None

    result_data = data.get("chart", {}).get("result", [])
    if not result_data:
        return f"No data found for symbol: {symbol}"

    meta = result_data[0].get("meta", {})
    price = meta.get("regularMarketPrice", 0)
    prev_close = meta.get("previousClose", meta.get("chartPreviousClose", 0))
    currency = meta.get("currency", "USD")
    exchange = meta.get("exchangeName", "")
    name = meta.get("shortName", meta.get("symbol", symbol))

    change = price - prev_close if prev_close else 0
    pct = (change / prev_close * 100) if prev_close else 0

    # Get historical data for the chart
    timestamps = result_data[0].get("timestamp", [])
    closes = result_data[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])

    arrow = "📈" if change >= 0 else "📉"
    sign = "+" if change >= 0 else ""

    lines = [f"## {arrow} {name} ({symbol})\n"]
    lines.append(f"**Price: {currency} {price:,.2f}** ({sign}{change:,.2f}, {sign}{pct:.2f}%)")
    lines.append(f"Exchange: {exchange}")
    lines.append(f"Previous Close: {currency} {prev_close:,.2f}")

    if meta.get("regularMarketVolume"):
        vol = meta["regularMarketVolume"]
        lines.append(f"Volume: {vol:,.0f}")
    if meta.get("fiftyTwoWeekHigh"):
        lines.append(f"52-Week High: {currency} {meta['fiftyTwoWeekHigh']:,.2f}")
    if meta.get("fiftyTwoWeekLow"):
        lines.append(f"52-Week Low: {currency} {meta['fiftyTwoWeekLow']:,.2f}")
    if meta.get("marketCap"):
        mc = meta["marketCap"]
        if mc > 1e12:
            lines.append(f"Market Cap: {currency} {mc/1e12:.2f}T")
        elif mc > 1e9:
            lines.append(f"Market Cap: {currency} {mc/1e9:.2f}B")
        elif mc > 1e6:
            lines.append(f"Market Cap: {currency} {mc/1e6:.2f}M")

    # Recent price history
    if timestamps and closes:
        lines.append("\n### Recent Prices")
        for ts, close in zip(timestamps[-5:], closes[-5:]):
            if close is not None:
                date = datetime.fromtimestamp(ts).strftime("%b %d")
                lines.append(f"  {date}: {currency} {close:,.2f}")

    result = "\n".join(lines)
    _cache.put("yf_quote", symbol, result)
    return result


def yahoo_finance_search(query):
    """Search Yahoo Finance for a ticker symbol."""
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote_plus(query)}&quotesCount=5"
    data = _http_json(url, timeout=10)

    if not data:
        return None

    quotes = data.get("quotes", [])
    if not quotes:
        return f"No financial instruments found for: {query}"

    lines = [f"## Finance Search: '{query}'\n"]
    for q in quotes[:5]:
        symbol = q.get("symbol", "")
        name = q.get("shortname", q.get("longname", ""))
        exchange = q.get("exchange", "")
        qtype = q.get("quoteType", "")
        lines.append(f"  **{symbol}** — {name} ({exchange}, {qtype})")

    lines.append(f"\nUse stock_quote with the symbol (e.g., '{quotes[0].get('symbol', '')}') for full data.")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
#  Phase 6: Academic Search (Semantic Scholar + arXiv)
# ═══════════════════════════════════════════════════════

def semantic_scholar_search(query, limit=5):
    """Search academic papers via Semantic Scholar API. Free, no key needed."""
    cached = _cache.get("s2", query)
    if cached:
        return cached

    encoded = urllib.parse.quote_plus(query)
    url = (
        f"https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={encoded}&limit={limit}"
        f"&fields=title,authors,year,citationCount,abstract,url,venue,openAccessPdf"
    )
    data = _http_json(url, timeout=15)

    if not data or not data.get("data"):
        return f"No academic papers found for: {query}"

    papers = data["data"]
    lines = [f"## Academic Papers: '{query}' ({data.get('total', '?')} total, showing {len(papers)})\n"]

    for i, p in enumerate(papers, 1):
        title = p.get("title", "Untitled")
        year = p.get("year", "?")
        citations = p.get("citationCount", 0)
        venue = p.get("venue", "")
        authors = ", ".join(a.get("name", "") for a in (p.get("authors", [])[:3]))
        if len(p.get("authors", [])) > 3:
            authors += " et al."

        lines.append(f"{i}. **{title}** ({year})")
        lines.append(f"   Authors: {authors}")
        if venue:
            lines.append(f"   Venue: {venue}")
        lines.append(f"   Citations: {citations}")
        if p.get("abstract"):
            abstract = p["abstract"][:300]
            lines.append(f"   Abstract: {abstract}{'...' if len(p['abstract']) > 300 else ''}")
        if p.get("url"):
            lines.append(f"   URL: {p['url']}")
        if p.get("openAccessPdf", {}).get("url"):
            lines.append(f"   PDF: {p['openAccessPdf']['url']}")
        lines.append("")

    result = "\n".join(lines)
    _cache.put("s2", query, result)
    return result


def arxiv_search(query, max_results=5):
    """Search arXiv preprints. Free, no key needed."""
    cached = _cache.get("arxiv", query)
    if cached:
        return cached

    encoded = urllib.parse.quote_plus(query)
    url = f"https://export.arxiv.org/api/query?search_query=all:{encoded}&max_results={max_results}&sortBy=relevance"
    raw = _http_get(url, timeout=15)

    if not raw:
        return f"arXiv search failed for: {query}"

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return f"arXiv response parse error for: {query}"

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)

    if not entries:
        return f"No arXiv papers found for: {query}"

    lines = [f"## arXiv Papers: '{query}' ({len(entries)} results)\n"]

    for i, entry in enumerate(entries, 1):
        title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
        summary = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
        published = entry.findtext("atom:published", "", ns)[:10] if entry.findtext("atom:published", "", ns) else ""
        link = ""
        for lnk in entry.findall("atom:link", ns):
            if lnk.get("type") == "text/html" or lnk.get("rel") == "alternate":
                link = lnk.get("href", "")
                break

        authors = []
        for author in entry.findall("atom:author", ns):
            name = author.findtext("atom:name", "", ns)
            if name:
                authors.append(name)

        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " et al."

        lines.append(f"{i}. **{title}**")
        lines.append(f"   Authors: {author_str}")
        lines.append(f"   Published: {published}")
        if summary:
            lines.append(f"   Abstract: {summary[:300]}{'...' if len(summary) > 300 else ''}")
        if link:
            lines.append(f"   URL: {link}")
        lines.append("")

    result = "\n".join(lines)
    _cache.put("arxiv", query, result)
    return result


# ═══════════════════════════════════════════════════════
#  Phase 7: Google News RSS
# ═══════════════════════════════════════════════════════

def google_news_rss(query, max_results=10):
    """Fetch Google News RSS feed for a topic."""
    cached = _cache.get("gnews", query)
    if cached:
        return cached

    encoded = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    raw = _http_get(url, timeout=10)

    if not raw:
        return None

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None

    items = root.findall(".//item")
    if not items:
        return f"No news found for: {query}"

    lines = [f"## News: '{query}' ({min(len(items), max_results)} articles)\n"]

    for i, item in enumerate(items[:max_results], 1):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        pub_date = item.findtext("pubDate", "")
        source = item.findtext("source", "")

        # Clean up date
        if pub_date:
            try:
                dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %Z")
                pub_date = dt.strftime("%b %d, %Y")
            except ValueError:
                pub_date = pub_date[:20]

        lines.append(f"{i}. **{title}**")
        lines.append(f"   Source: {source} | {pub_date}")
        lines.append(f"   URL: {link}")
        lines.append("")

    result = "\n".join(lines)
    _cache.put("gnews", query, result)
    return result


# ═══════════════════════════════════════════════════════
#  Phase 4: HTTP Page Reader (no browser needed)
# ═══════════════════════════════════════════════════════

def http_read_page(url, max_chars=15000):
    """
    Read a web page via HTTP — no browser needed.
    Uses readability-like extraction to get article content.
    Falls back to full body text if no article found.
    """
    cached = _cache.get("page", url)
    if cached:
        return cached

    raw = _http_get(url, timeout=15)
    if not raw:
        return f"ERROR: Could not fetch {url}"

    # Extract title
    title_match = re.search(r'<title[^>]*>(.*?)</title>', raw, re.S | re.I)
    title = title_match.group(1).strip() if title_match else ""
    title = re.sub(r'<[^>]+>', '', title)  # Remove any tags in title

    # Try to find article content
    text = ""

    # Strategy 1: <article> tag
    article_match = re.search(r'<article[^>]*>(.*?)</article>', raw, re.S | re.I)
    if article_match:
        text = article_match.group(1)

    # Strategy 2: role=main
    if not text or len(text) < 200:
        main_match = re.search(r'<main[^>]*>(.*?)</main>', raw, re.S | re.I)
        if main_match:
            text = main_match.group(1)

    # Strategy 3: Common content divs
    if not text or len(text) < 200:
        for cls in ["article-body", "post-content", "entry-content", "content", "article-content"]:
            content_match = re.search(
                rf'<div[^>]*class="[^"]*{cls}[^"]*"[^>]*>(.*?)</div>',
                raw, re.S | re.I,
            )
            if content_match and len(content_match.group(1)) > 200:
                text = content_match.group(1)
                break

    # Strategy 4: Full body
    if not text or len(text) < 200:
        body_match = re.search(r'<body[^>]*>(.*?)</body>', raw, re.S | re.I)
        if body_match:
            text = body_match.group(1)

    if not text:
        text = raw

    # Clean HTML
    # Remove scripts, styles, navs
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.S)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.S)
    text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.S)
    text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.S)
    text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.S)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)

    # Convert block elements to newlines
    text = re.sub(r'<(?:p|div|h[1-6]|li|br|tr)[^>]*>', '\n', text, flags=re.I)
    text = re.sub(r'</(?:p|div|h[1-6]|li|tr)>', '\n', text, flags=re.I)

    # Remove remaining tags
    text = re.sub(r'<[^>]+>', ' ', text)

    # Clean whitespace
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    text = text.strip()

    if not text:
        return f"ERROR: Page at {url} appears empty after extraction"

    score = _score_url(url)
    trust_label = "HIGH" if score >= 70 else "MED" if score >= 45 else "LOW"

    header = f"[{trust_label}:{score}] **{title}**\nURL: {url}\n\n"
    content = text[:max_chars]
    if len(text) > max_chars:
        content += f"\n\n... [truncated at {max_chars} chars, full page is {len(text)} chars]"

    result = header + content
    _cache.put("page", url, result)
    return result


# ═══════════════════════════════════════════════════════
#  Phase 3: Search Fallback Chain
# ═══════════════════════════════════════════════════════

def duckduckgo_search(query, num_results=10):
    """DuckDuckGo HTML search — last resort fallback."""
    cached = _cache.get("ddg", query)
    if cached:
        return cached

    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    html = _http_get(url, timeout=10)

    if not html:
        return None

    # Check for CAPTCHA
    if "Please complete the" in html or "bot" in html.lower()[:500]:
        return None

    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.S)
    snippets = re.findall(r'class="result__snippet">(.*?)</a>', html, re.S)
    urls = re.findall(r'class="result__url"[^>]*>(.*?)</a>', html, re.S)

    if not titles:
        return None

    lines = [f"## DuckDuckGo: '{query}' ({len(titles)} results)\n"]
    for i, (t, s) in enumerate(zip(titles, snippets), 1):
        if i > num_results:
            break
        t_clean = re.sub(r'<[^>]+>', '', t).strip()
        s_clean = re.sub(r'<[^>]+>', '', s).strip()
        u_clean = re.sub(r'<[^>]+>', '', urls[i - 1]).strip() if i - 1 < len(urls) else ""
        lines.append(f"{i}. **{t_clean}**")
        lines.append(f"   URL: {u_clean}")
        lines.append(f"   {s_clean}")
        lines.append("")

    result = "\n".join(lines)
    _cache.put("ddg", query, result)
    return result


def search_chain(query, serper_key=None, num_results=10):
    """
    Phase 3: Reliable search with automatic fallback.
    Serper API → DuckDuckGo HTTP → None (caller can try CDP).
    """
    # Try Serper first (most reliable)
    if serper_key:
        result = serper_search(query, serper_key, num_results)
        if result:
            return result

    # Fallback to DuckDuckGo HTTP
    result = duckduckgo_search(query, num_results)
    if result:
        return result

    # All HTTP methods failed — return None so caller can try CDP browser
    return None


# ═══════════════════════════════════════════════════════
#  Phase 8: Domain Router
# ═══════════════════════════════════════════════════════

_FINANCE_KEYWORDS = {
    "stock", "share", "price", "market", "nasdaq", "nyse", "sp500", "s&p",
    "dow", "crypto", "bitcoin", "btc", "eth", "ethereum", "ticker",
    "earnings", "dividend", "ipo", "market cap", "pe ratio", "revenue",
    "profit", "quarterly", "annual report", "sec filing",
}

_ACADEMIC_KEYWORDS = {
    "paper", "research", "study", "journal", "citation", "peer-reviewed",
    "arxiv", "preprint", "thesis", "dissertation", "methodology",
    "hypothesis", "experiment", "findings", "literature review",
    "meta-analysis", "systematic review", "clinical trial",
}

_NEWS_KEYWORDS = {
    "news", "breaking", "today", "latest", "just announced", "reported",
    "controversy", "scandal", "election", "update", "developing",
    "headline", "press conference", "statement",
}

_WIKI_KEYWORDS = {
    "who is", "what is", "history of", "define", "definition",
    "when was", "where is", "capital of", "population of",
    "born", "died", "founded", "invented", "discovered",
}


def detect_domain(query):
    """
    Detect query domain to route to the best API.
    Returns: "finance", "academic", "news", "wiki", or "general"
    """
    q_lower = query.lower()
    words = set(q_lower.split())

    # Check for stock ticker pattern (1-5 uppercase letters)
    if re.match(r'^[A-Z]{1,5}$', query.strip()):
        return "finance"

    # Score each domain
    scores = {
        "finance": sum(1 for k in _FINANCE_KEYWORDS if k in q_lower),
        "academic": sum(1 for k in _ACADEMIC_KEYWORDS if k in q_lower),
        "news": sum(1 for k in _NEWS_KEYWORDS if k in q_lower),
        "wiki": sum(1 for k in _WIKI_KEYWORDS if k in q_lower),
    }

    best = max(scores, key=scores.get)
    if scores[best] >= 1:
        return best
    return "general"


# ═══════════════════════════════════════════════════════
#  Source Credibility Scoring (shared)
# ═══════════════════════════════════════════════════════

_TIER1_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com",
    "washingtonpost.com", "wsj.com", "economist.com", "nature.com",
    "science.org", "pubmed.ncbi.nlm.nih.gov", "scholar.google.com",
    "who.int", "cdc.gov", "nih.gov", "fda.gov", "sec.gov", "congress.gov",
    "gov.uk", "europa.eu", "un.org", "worldbank.org", "imf.org",
    "arxiv.org", "ieee.org", "acm.org", "jstor.org",
    "harvard.edu", "mit.edu", "stanford.edu", "oxford.ac.uk", "cambridge.org",
    "mayoclinic.org", "webmd.com", "clevelandclinic.org",
    "investopedia.com", "bloomberg.com", "ft.com",
    "statista.com", "pewresearch.org", "gallup.com",
    "finance.yahoo.com", "semanticscholar.org", "en.wikipedia.org",
}

_TIER2_DOMAINS = {
    "wikipedia.org", "britannica.com", "cnn.com", "nbcnews.com",
    "theguardian.com", "forbes.com", "businessinsider.com", "cnbc.com",
    "techcrunch.com", "arstechnica.com", "wired.com", "theverge.com",
    "zdnet.com", "cnet.com", "pcmag.com", "tomshardware.com",
    "healthline.com", "medicalnewstoday.com",
    "github.com", "stackoverflow.com", "docs.python.org",
    "developer.mozilla.org",
    "zillow.com", "realtor.com", "redfin.com",
    "google.com",
}

_TIER3_DOMAINS = {
    "reddit.com", "quora.com", "medium.com", "substack.com",
    "blogspot.com", "wordpress.com", "tumblr.com",
    "twitter.com", "x.com", "facebook.com",
    "tiktok.com", "youtube.com",
}


def _score_url(url, title="", snippet=""):
    """Score a URL 0-100 based on domain authority and content clues."""
    try:
        domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return 30

    score = 50

    if any(domain.endswith(d) or domain == d for d in _TIER1_DOMAINS):
        score += 35
    elif any(domain.endswith(d) or domain == d for d in _TIER2_DOMAINS):
        score += 20
    elif any(domain.endswith(d) or domain == d for d in _TIER3_DOMAINS):
        score -= 10
    elif domain.endswith(".gov") or domain.endswith(".edu"):
        score += 30
    elif domain.endswith(".org"):
        score += 10

    if url.startswith("https://"):
        score += 5

    text = f"{title} {snippet}".lower()
    current_year = str(datetime.now().year)
    if current_year in text:
        score += 10
    elif str(datetime.now().year - 1) in text:
        score += 5

    if any(w in text for w in ["study", "research", "data", "statistics", "report", "analysis"]):
        score += 10
    if any(w in text for w in ["opinion", "editorial", "blog post", "my experience"]):
        score -= 5
    if "sponsored" in text or "advertisement" in text:
        score -= 20

    return max(0, min(100, score))
