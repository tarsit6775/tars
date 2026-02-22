"""
╔══════════════════════════════════════════════════════════════╗
║   TARS Research Agent v3.0 — PhD-Level Research Intelligence ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Layer 1 (Phases 1-4):   Search Reliability                  ║
║    - Serper.dev Google Search API (primary)                   ║
║    - Wikipedia REST API (knowledge base)                      ║
║    - Search fallback chain (Serper → CDP → DDG)              ║
║    - HTTP page reader (no browser needed for articles)        ║
║                                                              ║
║  Layer 2 (Phases 5-8):   Domain-Specific Intelligence        ║
║    - Yahoo Finance (stocks, crypto, market data)              ║
║    - Semantic Scholar + arXiv (academic papers)               ║
║    - Google News RSS (current events)                         ║
║    - Domain router (auto-detect query type)                   ║
║                                                              ║
║  Layer 3 (Phases 9-12):  Fact-Checking & Verification        ║
║    - Cross-reference engine (verify across 2+ sources)        ║
║    - Contradiction detector (flag conflicting claims)         ║
║    - Claim tracker (evidence-weighted confidence)             ║
║    - Citation system ([1] footnotes in final report)          ║
║                                                              ║
║  Layer 4 (Phases 13-16): Synthesis & Output                   ║
║    - Smart research planner (adaptive step budgets)           ║
║    - Quality self-check before submitting                     ║
║    - Markdown-rich reports with comparison tables             ║
║    - Source credibility report in every output                ║
║                                                              ║
║  Layer 5 (Phases 17-20): Intelligence & Efficiency           ║
║    - Research cache (1-hour TTL, cross-invocation)            ║
║    - Adaptive step budget (simple=8, moderate=18, deep=35)    ║
║    - Smart tool dispatch (API-first, browser fallback)        ║
║    - Domain-routed queries (finance→YF, wiki→WP, etc.)       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

from agents.base_agent import BaseAgent
from agents.agent_tools import TOOL_DONE, TOOL_STUCK
from hands.browser import (
    _browser_lock, _ensure, _js, _activate_chrome,
)
from hands.research_apis import (
    serper_search, serper_news, serper_scholar,
    wikipedia_summary, wikipedia_search, wikipedia_full_article, wikipedia_infobox,
    yahoo_finance_quote, yahoo_finance_search,
    semantic_scholar_search, arxiv_search,
    google_news_rss,
    http_read_page, duckduckgo_search, search_chain,
    detect_domain, _score_url, ResearchCache,
)
import time as _time
import urllib.parse
import urllib.request
import json
import re
import math
from datetime import datetime, timedelta


def _navigate(url):
    """Navigate to URL with CDP fallback if JS navigation times out."""
    safe_url = url.replace("'", "\\'")
    result = _js(f"window.location.href='{safe_url}'")
    if result and "JS_ERROR" in result:
        try:
            import hands.browser as _bmod
            _bmod._cdp.send("Page.navigate", {"url": url}, timeout=15)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════
#  Calculation Engine (preserved from v2.0)
# ═══════════════════════════════════════════════════════

def _safe_calculate(expression):
    """Safe math evaluator with whitelisted functions only."""
    allowed_names = {
        "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
        "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "log2": math.log2,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "pi": math.pi, "e": math.e, "inf": float("inf"),
        "ceil": math.ceil, "floor": math.floor,
        "pow": pow, "len": len,
    }
    allowed_names["avg"] = lambda *args: sum(args) / len(args) if args else 0

    safe_expr = expression.strip()
    safe_expr = safe_expr.replace("^", "**")
    safe_expr = safe_expr.replace("\u00d7", "*")
    safe_expr = safe_expr.replace("\u00f7", "/")

    try:
        result = eval(safe_expr, {"__builtins__": {}}, allowed_names)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


_UNIT_CONVERSIONS = {
    ("km", "mi"): 0.621371, ("mi", "km"): 1.60934,
    ("m", "ft"): 3.28084, ("ft", "m"): 0.3048,
    ("cm", "in"): 0.393701, ("in", "cm"): 2.54,
    ("m", "cm"): 100, ("cm", "m"): 0.01,
    ("km", "m"): 1000, ("m", "km"): 0.001,
    ("mi", "ft"): 5280, ("ft", "mi"): 1 / 5280,
    ("yd", "m"): 0.9144, ("m", "yd"): 1.09361,
    ("kg", "lb"): 2.20462, ("lb", "kg"): 0.453592,
    ("g", "oz"): 0.035274, ("oz", "g"): 28.3495,
    ("kg", "g"): 1000, ("g", "kg"): 0.001,
    ("lb", "oz"): 16, ("oz", "lb"): 1 / 16,
    ("ton", "kg"): 907.185, ("kg", "ton"): 1 / 907.185,
    ("l", "gal"): 0.264172, ("gal", "l"): 3.78541,
    ("ml", "oz"): 0.033814, ("oz", "ml"): 29.5735,
    ("l", "ml"): 1000, ("ml", "l"): 0.001,
    ("mph", "kph"): 1.60934, ("kph", "mph"): 0.621371,
    ("m/s", "mph"): 2.23694, ("mph", "m/s"): 0.44704,
    ("sqft", "sqm"): 0.092903, ("sqm", "sqft"): 10.7639,
    ("acre", "sqft"): 43560, ("sqft", "acre"): 1 / 43560,
    ("sqmi", "sqkm"): 2.58999, ("sqkm", "sqmi"): 0.386102,
}


def _convert_units(value, from_unit, to_unit):
    """Convert between common units."""
    f = from_unit.lower().strip().replace(" ", "")
    t = to_unit.lower().strip().replace(" ", "")

    if f in ("c", "celsius") and t in ("f", "fahrenheit"):
        return str(round(value * 9 / 5 + 32, 2))
    if f in ("f", "fahrenheit") and t in ("c", "celsius"):
        return str(round((value - 32) * 5 / 9, 2))
    if f in ("c", "celsius") and t in ("k", "kelvin"):
        return str(round(value + 273.15, 2))
    if f in ("k", "kelvin") and t in ("c", "celsius"):
        return str(round(value - 273.15, 2))

    key = (f, t)
    if key in _UNIT_CONVERSIONS:
        return str(round(value * _UNIT_CONVERSIONS[key], 6))

    return f"Unknown conversion: {from_unit} -> {to_unit}"


def _date_math(expression):
    """Date arithmetic: today +/- N days/weeks/months/years, days between dates."""
    expr = expression.strip().lower()
    now = datetime.now()

    m = re.match(r"days?\s+between\s+(\S+)\s+and\s+(\S+)", expr)
    if m:
        try:
            d1 = datetime.strptime(m.group(1), "%Y-%m-%d")
            d2 = datetime.strptime(m.group(2), "%Y-%m-%d")
            delta = abs((d2 - d1).days)
            return f"{delta} days between {m.group(1)} and {m.group(2)}"
        except ValueError:
            return f"Could not parse dates: {m.group(1)}, {m.group(2)}"

    base = None
    remaining = expr
    if expr.startswith("today"):
        base = now
        remaining = expr[5:].strip()
    elif expr.startswith("tomorrow"):
        base = now + timedelta(days=1)
        remaining = expr[8:].strip()
    elif expr.startswith("yesterday"):
        base = now - timedelta(days=1)
        remaining = expr[9:].strip()
    else:
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y"]:
            for i in range(len(expr), 5, -1):
                try:
                    base = datetime.strptime(expr[:i].strip(), fmt)
                    remaining = expr[i:].strip()
                    break
                except ValueError:
                    continue
            if base:
                break

    if base is None:
        return f"Could not parse date expression: {expression}"

    if not remaining:
        return base.strftime("%A, %B %d, %Y")

    m = re.match(r"([+-])\s*(\d+)\s*(days?|weeks?|months?|years?)", remaining)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        amount = int(m.group(2))
        unit = m.group(3).rstrip("s")

        if unit == "day":
            result = base + timedelta(days=sign * amount)
        elif unit == "week":
            result = base + timedelta(weeks=sign * amount)
        elif unit == "month":
            month = base.month + sign * amount
            year = base.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            day = min(base.day, [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
            result = base.replace(year=year, month=month, day=day)
        elif unit == "year":
            try:
                result = base.replace(year=base.year + sign * amount)
            except ValueError:
                result = base.replace(year=base.year + sign * amount, day=28)
        else:
            return f"Unknown time unit: {unit}"

        return result.strftime("%A, %B %d, %Y")

    return base.strftime("%A, %B %d, %Y")


# ═══════════════════════════════════════════════════════
#  Tool Definitions — 25+ Research Tools
# ═══════════════════════════════════════════════════════

# ─── Search & Discover ───────────────────────

TOOL_WEB_SEARCH = {
    "name": "web_search",
    "description": "Google search via API (fast, reliable, no CAPTCHAs). Returns results with trust scores. Use specific, targeted queries. This is your PRIMARY search tool.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query — be specific and targeted"},
            "num_results": {"type": "integer", "description": "Number of results (default 10, max 20)", "default": 10},
        },
        "required": ["query"]
    }
}

TOOL_MULTI_SEARCH = {
    "name": "multi_search",
    "description": "Run 2-5 searches in sequence and combine results. Use when you need different angles on a topic. More efficient than multiple web_search calls.",
    "input_schema": {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of 2-5 different search queries"
            }
        },
        "required": ["queries"]
    }
}

TOOL_NEWS_SEARCH = {
    "name": "news_search",
    "description": "Search latest news articles on a topic. Returns recent headlines with sources and dates. Use for current events, breaking news, recent developments.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "News topic to search"},
            "num_results": {"type": "integer", "description": "Number of articles (default 10)", "default": 10},
        },
        "required": ["query"]
    }
}

# ─── Knowledge & Facts ───────────────────────

TOOL_WIKI_SEARCH = {
    "name": "wiki_search",
    "description": "Search Wikipedia for articles on a topic. Returns summaries with links. Use for factual lookups, historical facts, definitions, biographies.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Topic to look up on Wikipedia"},
        },
        "required": ["topic"]
    }
}

TOOL_WIKI_ARTICLE = {
    "name": "wiki_article",
    "description": "Read a full Wikipedia article in depth. Use when you need comprehensive, well-sourced information on a topic. Returns up to 20K chars of clean text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Exact Wikipedia article title"},
        },
        "required": ["title"]
    }
}

# ─── Financial Data ──────────────────────────

TOOL_STOCK_QUOTE = {
    "name": "stock_quote",
    "description": "Get current stock/crypto price, change, volume, 52-week range, market cap. Use for any financial market data. Supports NYSE, NASDAQ, crypto (BTC-USD, ETH-USD).",
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Ticker symbol (e.g., AAPL, GOOGL, TSLA, BTC-USD, ETH-USD)"},
        },
        "required": ["symbol"]
    }
}

TOOL_FINANCE_SEARCH = {
    "name": "finance_search",
    "description": "Search for a stock/crypto ticker symbol by company or asset name. Use when you don't know the exact ticker.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Company or asset name to search (e.g., 'Apple', 'Bitcoin')"},
        },
        "required": ["query"]
    }
}

# ─── Academic Research ───────────────────────

TOOL_ACADEMIC_SEARCH = {
    "name": "academic_search",
    "description": "Search academic papers on Semantic Scholar. Returns titles, authors, citation counts, abstracts. Free, no API key needed. Use for scientific research, medical studies, peer-reviewed evidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Academic search query"},
            "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
        },
        "required": ["query"]
    }
}

TOOL_ARXIV_SEARCH = {
    "name": "arxiv_search",
    "description": "Search arXiv preprints. Use for cutting-edge CS, physics, math, AI/ML research papers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "arXiv search query"},
            "max_results": {"type": "integer", "description": "Max results (default 5)", "default": 5},
        },
        "required": ["query"]
    }
}

# ─── Read & Understand ───────────────────────

TOOL_BROWSE = {
    "name": "browse",
    "description": "Read a web page via HTTP (fast, no browser needed) or Chrome CDP (for JS-rendered pages). Smart article extraction strips nav/ads. Returns up to 15K chars.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to visit and read"},
            "use_browser": {"type": "boolean", "description": "Force Chrome CDP (for JS-heavy sites). Default: false (HTTP first, faster)", "default": False},
        },
        "required": ["url"]
    }
}

TOOL_DEEP_READ = {
    "name": "deep_read",
    "description": "Read a long page by scrolling through it (requires Chrome). Captures up to 50K chars across multiple scroll positions. Use for long articles, documentation, reports.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to deeply read"},
            "max_scrolls": {"type": "integer", "description": "Scroll steps (default 5, max 10)", "default": 5}
        },
        "required": ["url"]
    }
}

TOOL_EXTRACT = {
    "name": "extract",
    "description": "Read a URL and extract SPECIFIC information by answering a targeted question. Better than browse when you know exactly what you need.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to visit"},
            "question": {"type": "string", "description": "Specific question to answer from the page"}
        },
        "required": ["url", "question"]
    }
}

TOOL_EXTRACT_TABLE = {
    "name": "extract_table",
    "description": "Extract structured tabular data from a page (pricing tables, comparison charts, specs, schedules). Returns formatted markdown tables.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL containing the table"},
            "table_description": {"type": "string", "description": "What table to look for"}
        },
        "required": ["url", "table_description"]
    }
}

TOOL_FOLLOW_LINKS = {
    "name": "follow_links",
    "description": "Read a page and find/follow links matching a keyword pattern. Use for exploring related content, subpages, or references.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Starting URL"},
            "link_pattern": {"type": "string", "description": "Keyword to match in link text/URL"},
            "max_links": {"type": "integer", "description": "Max links to follow (default 3, max 5)", "default": 3}
        },
        "required": ["url", "link_pattern"]
    }
}

# ─── Fact-Checking & Verification ────────────

TOOL_FACT_CHECK = {
    "name": "fact_check",
    "description": "Cross-reference a specific claim by searching multiple sources. Records evidence for and against. Use to verify important claims before including in your report.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claim": {"type": "string", "description": "The specific claim to verify (e.g., 'Tesla delivered 1.8M vehicles in 2023')"},
            "context": {"type": "string", "description": "Context about the claim (topic area, original source)"},
        },
        "required": ["claim"]
    }
}

TOOL_CROSS_REFERENCE = {
    "name": "cross_reference",
    "description": "Check if a finding is confirmed by multiple independent sources. Takes a key finding and searches for corroboration. Returns verification status with evidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "finding": {"type": "string", "description": "The finding to cross-reference"},
            "original_source": {"type": "string", "description": "Where you first found this information"},
        },
        "required": ["finding"]
    }
}

# ─── Organize & Track ────────────────────────

TOOL_NOTE = {
    "name": "note",
    "description": "Save a research finding with source tracking and citation. Always include source URL. Every note becomes a citable reference in your final report.",
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Short label for this finding"},
            "value": {"type": "string", "description": "The finding/fact to save"},
            "source": {"type": "string", "description": "URL or source name (REQUIRED for credibility)"},
            "confidence": {"type": "string", "enum": ["verified", "high", "medium", "low"], "description": "verified=cross-checked 2+ sources, high=authoritative single source, medium=single source, low=uncertain"},
        },
        "required": ["key", "value", "source"]
    }
}

TOOL_NOTES = {
    "name": "notes",
    "description": "Review all collected research notes organized by confidence level, with source attributions, citation numbers, and research stats.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_COMPARE = {
    "name": "compare",
    "description": "Build a side-by-side comparison table. Data is saved and included in your final report.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Comparison title"},
            "items": {"type": "array", "items": {"type": "string"}, "description": "Item names to compare"},
            "criteria": {"type": "array", "items": {"type": "string"}, "description": "Criteria to compare on"},
            "data": {"type": "object", "description": "Data: {item_name: {criterion: value}}"}
        },
        "required": ["title", "items", "criteria", "data"]
    }
}

# ─── Analyze & Calculate ─────────────────────

TOOL_CALCULATE = {
    "name": "calculate",
    "description": "Math: +, -, *, /, **, %, sqrt(), abs(), round(), log(), pi, e, min(), max(), sum(), avg().",
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Math expression"},
            "label": {"type": "string", "description": "What this calculates"}
        },
        "required": ["expression"]
    }
}

TOOL_CONVERT = {
    "name": "convert",
    "description": "Unit conversion: length, weight, volume, temperature, speed, area.",
    "input_schema": {
        "type": "object",
        "properties": {
            "value": {"type": "number", "description": "Numeric value"},
            "from_unit": {"type": "string", "description": "Source unit"},
            "to_unit": {"type": "string", "description": "Target unit"}
        },
        "required": ["value", "from_unit", "to_unit"]
    }
}

TOOL_DATE_CALC = {
    "name": "date_calc",
    "description": "Date arithmetic: today + 30 days, days between dates, etc.",
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Date expression to evaluate"}
        },
        "required": ["expression"]
    }
}

# ─── Planning ────────────────────────────────

TOOL_RESEARCH_PLAN = {
    "name": "research_plan",
    "description": "Create/update your research plan. Define sub-questions and track progress. ALWAYS start complex tasks with a plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {"type": "array", "items": {"type": "string"}, "description": "Research questions to answer"},
            "completed": {"type": "array", "items": {"type": "string"}, "description": "Questions answered so far"}
        },
        "required": ["questions"]
    }
}

TOOL_SCORE_SOURCES = {
    "name": "score_sources",
    "description": "Evaluate credibility of all sources visited. Returns trust scores with tier breakdown.",
    "input_schema": {"type": "object", "properties": {}}
}


# ═══════════════════════════════════════════════════════
#  System Prompt — PhD-Level Research Intelligence
# ═══════════════════════════════════════════════════════

RESEARCH_SYSTEM_PROMPT = (
    "You are TARS Research Agent v3.0 — a PhD-level research intelligence system. "
    "You combine the rigor of an investigative journalist, the depth of a McKinsey "
    "consultant, and the verification standards of a peer-reviewed academic.\n\n"

    "## YOUR IDENTITY\n"
    "You are the most capable research agent ever built. Your research is so thorough "
    "and well-verified that people trust it for life-critical decisions: medical research, "
    "investment analysis, legal research, property purchases, career changes.\n\n"

    "## YOUR 25+ SPECIALIZED TOOLS\n\n"

    "### Search & Discover (API-powered, zero CAPTCHAs)\n"
    "- **web_search**: Google search via API (PRIMARY — fast, reliable, structured results)\n"
    "- **multi_search**: 2-5 searches at once (different angles)\n"
    "- **news_search**: Latest news articles with sources and dates\n\n"

    "### Knowledge & Facts (instant, no browsing needed)\n"
    "- **wiki_search**: Wikipedia summaries (factual lookups, definitions, history)\n"
    "- **wiki_article**: Full Wikipedia articles (comprehensive deep knowledge)\n\n"

    "### Financial Data (real-time market data)\n"
    "- **stock_quote**: Stock/crypto prices, volume, market cap, 52-week range\n"
    "- **finance_search**: Find ticker symbols by company name\n\n"

    "### Academic Research (peer-reviewed sources)\n"
    "- **academic_search**: Semantic Scholar (papers, citations, abstracts)\n"
    "- **arxiv_search**: arXiv preprints (cutting-edge CS/AI/physics/math)\n\n"

    "### Read & Understand (web page reading)\n"
    "- **browse**: Read any web page (HTTP-first, fast; use_browser=true for JS pages)\n"
    "- **deep_read**: Scroll through long pages (up to 50K chars)\n"
    "- **extract**: Extract specific answers from a page\n"
    "- **extract_table**: Pull structured tabular data\n"
    "- **follow_links**: Follow links matching a pattern\n\n"

    "### Fact-Checking (CRITICAL — use on all important claims)\n"
    "- **fact_check**: Cross-reference a specific claim across multiple sources\n"
    "- **cross_reference**: Verify a finding via independent corroboration\n\n"

    "### Organize & Track\n"
    "- **note**: Save a finding WITH source URL (every note = citable reference)\n"
    "- **notes**: Review all findings with citation numbers\n"
    "- **compare**: Build side-by-side comparison tables\n"
    "- **research_plan**: Plan questions and track progress\n"
    "- **score_sources**: Evaluate all sources' credibility\n\n"

    "### Analyze & Calculate\n"
    "- **calculate**: Math, percentages, financial calculations\n"
    "- **convert**: Unit conversions\n"
    "- **date_calc**: Date arithmetic\n\n"

    "### Finish\n"
    "- **done**: Complete with full research report (include citations!)\n"
    "- **stuck**: Cannot proceed (explain what's blocking)\n\n"

    "## YOUR RESEARCH METHODOLOGY (6-Step Process)\n\n"

    "### Step 1: PLAN (Always start here)\n"
    "- Use **research_plan** to break the question into sub-questions\n"
    "- Identify which tools are best for each sub-question:\n"
    "  • Factual/historical → wiki_search + wiki_article first\n"
    "  • Financial/market → stock_quote + finance_search first\n"
    "  • Academic/scientific → academic_search + arxiv_search first\n"
    "  • Current events → news_search first\n"
    "  • General/product → web_search + browse\n"
    "- Estimate complexity: simple (3-5 steps), moderate (8-12), deep (15-25)\n\n"

    "### Step 2: GATHER (Use the right tool for the domain)\n"
    "- Start with API-powered tools (web_search, wiki_search, stock_quote) — they're instant and reliable\n"
    "- Use browse only when you need to read a specific URL\n"
    "- Use multi_search to explore different angles simultaneously\n"
    "- For academic questions, ALWAYS check academic_search\n\n"

    "### Step 3: READ (Go deep on best sources)\n"
    "- browse for regular pages (HTTP-first, no browser overhead)\n"
    "- deep_read for long articles/documentation\n"
    "- extract for specific data points (most efficient)\n"
    "- extract_table for pricing, specs, schedules\n\n"

    "### Step 4: VERIFY (Fact-check every important claim)\n"
    "- Use **fact_check** on every quantitative claim (numbers, dates, statistics)\n"
    "- Use **cross_reference** on every major finding\n"
    "- If sources disagree, report ALL viewpoints with source attribution\n"
    "- Distinguish: VERIFIED (2+ sources) vs REPORTED (single source) vs DISPUTED (conflicting sources)\n\n"

    "### Step 5: ANALYZE\n"
    "- Use compare for side-by-side analysis\n"
    "- Use calculate for derived metrics (ROI, price-per-unit, growth rates)\n"
    "- Identify patterns, contradictions, and consensus\n"
    "- score_sources to check overall source quality\n\n"

    "### Step 6: SYNTHESIZE (Final Report)\n"
    "- Review notes to compile everything\n"
    "- Structure with clear markdown headers\n"
    "- Include **[1] citation footnotes** for every claim\n"
    "- Add a Sources section at the bottom\n"
    "- Include confidence indicators: ✅ VERIFIED, ⚠️ SINGLE-SOURCE, ❌ DISPUTED\n"
    "- End with clear recommendation/conclusion when appropriate\n\n"

    "## ANTI-HALLUCINATION RULES (CRITICAL — NEVER VIOLATE)\n"
    "1. NEVER claim something you didn't find through your tools\n"
    "2. Every claim MUST be backed by a tool call\n"
    "3. If you didn't find it, say 'I could not find information on X'\n"
    "4. NEVER invent URLs, prices, dates, or statistics\n"
    "5. If sources contradict each other, present BOTH sides\n"
    "6. Use fact_check on numbers/statistics before including them\n"
    "7. Label confidence: VERIFIED (2+ sources confirm), REPORTED (single source), UNCERTAIN\n"
    "8. If task requires doing something (signup, booking), call stuck — you are READ-ONLY\n\n"

    "## EFFICIENCY RULES\n"
    "1. Simple factual questions: wiki_search → done (2-3 steps)\n"
    "2. Stock/crypto queries: stock_quote → done (1-2 steps)\n"
    "3. News queries: news_search → done (1-2 steps)\n"
    "4. Complex research: plan → gather → verify → synthesize (10-20 steps)\n"
    "5. Use API tools first — only browse when you need to read a specific URL\n"
    "6. Take notes AS you research — don't try to remember everything\n"
    "7. Review notes before writing your final report\n"
    "8. NEVER search the same query twice\n\n"

    "## DOMAIN EXPERTISE\n\n"

    "### Financial Research\n"
    "- Use stock_quote for real-time prices, not web search\n"
    "- Use finance_search to find ticker symbols\n"
    "- For deep financial analysis, browse SEC filings, Bloomberg, Investopedia\n"
    "- Include: price, change%, volume, market cap, 52-week range\n\n"

    "### Academic/Scientific Research\n"
    "- Use academic_search (Semantic Scholar) for peer-reviewed papers\n"
    "- Use arxiv_search for cutting-edge preprints (CS, AI, physics, math)\n"
    "- Always note citation counts — higher = more trusted\n"
    "- Check methodology, sample sizes, p-values when available\n\n"

    "### Medical/Health Research\n"
    "- ONLY use medical sources: NIH, Mayo Clinic, PubMed, CDC, WHO\n"
    "- Use academic_search for clinical studies\n"
    "- NEVER give medical advice — present information neutrally\n"
    "- Always recommend consulting a healthcare professional\n\n"

    "### Travel Research\n"
    "- ⚠️ Flight booking sites (Kayak, Skyscanner, Expedia) block bots — do NOT browse them\n"
    "- For flight info, baggage policies, airline reviews: web_search is fine\n"
    "- Use date_calc for date computations\n\n"

    "### Product Research\n"
    "- Check official product pages + 2-3 review sites\n"
    "- Use extract_table for pricing/specs comparison\n"
    "- Always note: price, ratings, pros/cons, where to buy\n\n"

    "### Real Estate Research\n"
    "- Use web_search + browse for Zillow/Redfin/Realtor.com data\n"
    "- Include: price, sqft, beds/baths, price history, neighborhood data\n"
    "- Use calculate for price-per-sqft, mortgage estimates\n\n"

    "### Historical/Factual Research\n"
    "- Start with wiki_search + wiki_article for foundational info\n"
    "- Cross-reference with web_search for different perspectives\n"
    "- Note primary vs secondary sources\n"
)


# ═══════════════════════════════════════════════════════
#  Research Agent v3.0 Class
# ═══════════════════════════════════════════════════════

class ResearchAgent(BaseAgent):
    """
    PhD-level research intelligence agent v3.0.
    
    API-first architecture: Serper, Wikipedia, Yahoo Finance,
    Semantic Scholar, arXiv, Google News — with Chrome CDP fallback.
    
    Fact-checking: cross-reference engine, contradiction detection,
    citation system with evidence-weighted confidence.
    """

    def __init__(self, *args, config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._notes = {}
        self._citations = []  # Ordered list of (url, title, trust_score) for [1] footnotes
        self._comparisons = []
        self._sources_visited = []
        self._claims = {}  # claim_text → {"evidence_for": [...], "evidence_against": [...], "status": "verified|disputed|unverified"}
        self._research_plan = {"questions": [], "completed": []}
        self._search_count = 0
        self._pages_read = 0
        self._cache_hits = 0
        self._browser_errors = 0
        self._browser_initialized = False

        # Config for API keys
        self._config = config or {}
        self._serper_key = self._config.get("research", {}).get("serper_api_key", "")
        if not self._serper_key:
            self._serper_key = self._config.get("serper_api_key", "")

    @property
    def agent_name(self):
        return "Research Agent"

    @property
    def agent_emoji(self):
        return "\U0001f50d"

    @property
    def system_prompt(self):
        today = datetime.now().strftime('%Y-%m-%d')
        year = datetime.now().year
        cache_stats = ResearchCache().stats()
        return (
            RESEARCH_SYSTEM_PROMPT +
            f"\n## CURRENT DATE\n"
            f"Today is {today}. The current year is {year}.\n"
            f"ALWAYS use {year} dates (never 2024 or 2025) when constructing URLs or date ranges.\n"
            f"When searching for flights, events, or time-sensitive data, use dates from {today} onwards.\n"
            f"\n## CACHE STATUS\n"
            f"Cache: {cache_stats['valid']} valid entries. Repeated queries are served from cache automatically.\n"
        )

    @property
    def tools(self):
        return [
            # Search & Discover
            TOOL_WEB_SEARCH, TOOL_MULTI_SEARCH, TOOL_NEWS_SEARCH,
            # Knowledge & Facts
            TOOL_WIKI_SEARCH, TOOL_WIKI_ARTICLE,
            # Financial Data
            TOOL_STOCK_QUOTE, TOOL_FINANCE_SEARCH,
            # Academic Research
            TOOL_ACADEMIC_SEARCH, TOOL_ARXIV_SEARCH,
            # Read & Understand
            TOOL_BROWSE, TOOL_DEEP_READ, TOOL_EXTRACT, TOOL_EXTRACT_TABLE, TOOL_FOLLOW_LINKS,
            # Fact-Checking
            TOOL_FACT_CHECK, TOOL_CROSS_REFERENCE,
            # Organize & Track
            TOOL_NOTE, TOOL_NOTES, TOOL_COMPARE,
            # Analyze & Calculate
            TOOL_CALCULATE, TOOL_CONVERT, TOOL_DATE_CALC,
            # Planning
            TOOL_RESEARCH_PLAN, TOOL_SCORE_SOURCES,
            # Terminal
            TOOL_DONE, TOOL_STUCK,
        ]

    def _on_start(self, task):
        """Clear state for new research task."""
        self._notes = {}
        self._citations = []
        self._comparisons = []
        self._sources_visited = []
        self._claims = {}
        self._research_plan = {"questions": [], "completed": []}
        self._search_count = 0
        self._pages_read = 0
        self._cache_hits = 0
        self._browser_errors = 0
        self._browser_initialized = False
        print(f"  Research Agent v3.0: {len(self.tools)} tools loaded (API-first, browser fallback)")
        print(f"  Serper API: {'✅ configured' if self._serper_key else '❌ not configured (using browser search)'}")

    def _ensure_browser(self):
        """Lazy-init Chrome only when browser-dependent tools are called."""
        if self._browser_initialized:
            return True
        try:
            with _browser_lock:
                _activate_chrome()
                _ensure()
            self._browser_initialized = True
            print(f"  Research Agent: Chrome initialized (lazy)")
            return True
        except Exception as e:
            print(f"  Research Agent: Chrome init failed: {e}")
            return False

    def _recover_browser(self):
        """Attempt to recover from a browser crash/disconnect."""
        import hands.browser as _browser_mod
        self._browser_errors += 1
        print(f"  🔄 Research Agent: Recovering browser (error #{self._browser_errors})...")
        try:
            if _browser_mod._cdp:
                try:
                    _browser_mod._cdp.connected = False
                except Exception:
                    pass
                _browser_mod._cdp = None
            _activate_chrome()
            _ensure()
            self._browser_initialized = True
            print(f"  ✅ Browser recovered")
            return True
        except Exception as e:
            print(f"  ❌ Browser recovery failed: {e}")
            self._browser_initialized = False
            return False

    def _add_citation(self, url, title="", trust_score=50):
        """Add a source to the citation list. Returns citation number [N]."""
        # Check if already cited
        for i, (u, t, s) in enumerate(self._citations, 1):
            if u == url:
                return i
        self._citations.append((url, title, trust_score))
        return len(self._citations)

    # ═══════════════════════════════════════════════════
    #  Main Dispatch — Route tool calls
    # ═══════════════════════════════════════════════════

    def _dispatch(self, name, inp):
        """Route research tool calls — API-first, browser fallback."""
        try:
            # ─── Search & Discover ───────────────
            if name == "web_search":
                return self._web_search(inp["query"], inp.get("num_results", 10))
            elif name == "multi_search":
                return self._multi_search(inp["queries"])
            elif name == "news_search":
                return self._news_search(inp["query"], inp.get("num_results", 10))

            # ─── Knowledge & Facts ───────────────
            elif name == "wiki_search":
                return self._wiki_search(inp["topic"])
            elif name == "wiki_article":
                return self._wiki_article(inp["title"])

            # ─── Financial Data ──────────────────
            elif name == "stock_quote":
                return self._stock_quote(inp["symbol"])
            elif name == "finance_search":
                return self._finance_search(inp["query"])

            # ─── Academic Research ───────────────
            elif name == "academic_search":
                return self._academic_search(inp["query"], inp.get("limit", 5))
            elif name == "arxiv_search":
                return self._arxiv_search(inp["query"], inp.get("max_results", 5))

            # ─── Read & Understand ───────────────
            elif name == "browse":
                return self._browse(inp["url"], inp.get("use_browser", False))
            elif name == "deep_read":
                return self._deep_read(inp["url"], inp.get("max_scrolls", 5))
            elif name == "extract":
                return self._extract(inp["url"], inp["question"])
            elif name == "extract_table":
                return self._extract_table(inp["url"], inp["table_description"])
            elif name == "follow_links":
                return self._follow_links(inp["url"], inp["link_pattern"], inp.get("max_links", 3))

            # ─── Fact-Checking ───────────────────
            elif name == "fact_check":
                return self._fact_check(inp["claim"], inp.get("context", ""))
            elif name == "cross_reference":
                return self._cross_reference(inp["finding"], inp.get("original_source", ""))

            # ─── Organize & Track ────────────────
            elif name == "note":
                return self._note(inp["key"], inp["value"], inp.get("source", ""), inp.get("confidence", "medium"))
            elif name == "notes":
                return self._get_notes()
            elif name == "compare":
                return self._compare(inp["title"], inp["items"], inp["criteria"], inp["data"])

            # ─── Analyze & Calculate ─────────────
            elif name == "calculate":
                return self._calculate(inp["expression"], inp.get("label", ""))
            elif name == "convert":
                return self._convert(inp["value"], inp["from_unit"], inp["to_unit"])
            elif name == "date_calc":
                return self._date_calc(inp["expression"])

            # ─── Planning ────────────────────────
            elif name == "research_plan":
                return self._research_plan_update(inp["questions"], inp.get("completed", []))
            elif name == "score_sources":
                return self._score_all_sources()

            return f"Unknown research tool: {name}"
        except Exception as e:
            return f"ERROR: {e}"

    # ═══════════════════════════════════════════════════
    #  Layer 1: Search — API-first with fallback chain
    # ═══════════════════════════════════════════════════

    def _web_search(self, query, num_results=10):
        """
        Primary search: Serper API → Google CDP → DuckDuckGo HTTP.
        API-first = no CAPTCHAs, structured data, knowledge graphs.
        """
        self._search_count += 1

        # Try Serper API first (most reliable)
        result = serper_search(query, self._serper_key, num_results)
        if result:
            result += f"\n\n_Search #{self._search_count} via Serper API_"
            return result

        # Fallback to DuckDuckGo HTTP
        result = duckduckgo_search(query, num_results)
        if result:
            result += f"\n\n_Search #{self._search_count} via DuckDuckGo_"
            return result

        # Last resort: CDP browser
        if self._ensure_browser():
            return self._cdp_google_search(query, num_results)

        return f"ERROR: All search methods failed for: {query}"

    def _cdp_google_search(self, query, num_results=10):
        """Google search via Chrome CDP — fallback when APIs are unavailable."""
        try:
            with _browser_lock:
                _ensure()
                encoded = urllib.parse.quote_plus(query)
                num = min(num_results, 20)
                search_url = f"https://www.google.com/search?q={encoded}&num={num}"
                _navigate(search_url)
                _time.sleep(3)

                results_js = r"""(function() {
                    var results = [];
                    var seen = {};
                    document.querySelectorAll('div.g').forEach(function(item) {
                        var link = item.querySelector('a[href^="http"]');
                        var title = item.querySelector('h3');
                        if (link && title && !seen[link.href]) {
                            seen[link.href] = true;
                            var snippet = item.querySelector('[data-sncf], .VwiC3b, [style*="-webkit-line-clamp"], .lEBKkf');
                            results.push({title: title.innerText, url: link.href, snippet: snippet ? snippet.innerText : ''});
                        }
                    });
                    if (results.length === 0) {
                        document.querySelectorAll('h3').forEach(function(h3) {
                            var parent = h3.closest('a') || h3.parentElement;
                            if (!parent) return;
                            var link = parent.tagName === 'A' ? parent : parent.querySelector('a[href^="http"]');
                            if (!link) { var p = parent.parentElement; if (p) link = p.querySelector('a[href^="http"]'); }
                            if (link && link.href && !seen[link.href] && !link.href.includes('google.com/search')) {
                                seen[link.href] = true;
                                results.push({title: h3.innerText, url: link.href, snippet: ''});
                            }
                        });
                    }
                    var featured = document.querySelector('.hgKElc, .IZ6rdc, .kno-rdesc span');
                    return JSON.stringify({
                        results: results.slice(0, """ + str(num) + r"""),
                        featured: featured ? featured.innerText.substring(0, 500) : ''
                    });
                })()"""
                raw = _js(results_js)

            try:
                data = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, TypeError):
                data = {}

            results = data.get("results", [])
            featured = data.get("featured", "")

            lines = [f"## Google Search (CDP): '{query}' ({len(results)} results)\n"]
            if featured:
                lines.append(f"### Featured Snippet\n{featured}\n")

            for i, r in enumerate(results, 1):
                score = _score_url(r.get("url", ""), r.get("title", ""), r.get("snippet", ""))
                trust_label = "HIGH" if score >= 70 else "MED" if score >= 45 else "LOW"
                self._sources_visited.append((r.get("url", ""), r.get("title", ""), score))
                lines.append(f"{i}. [{trust_label}:{score}] **{r.get('title', 'No title')}**")
                lines.append(f"   URL: {r.get('url', '')}")
                if r.get("snippet"):
                    lines.append(f"   {r['snippet']}")
                lines.append("")

            if not results:
                # Raw fallback
                with _browser_lock:
                    fallback = _js("(function(){var el=document.querySelector('#search,#rso,#main');return el?el.innerText.substring(0,8000):document.body?document.body.innerText.substring(0,8000):'';})()") or ""
                if fallback:
                    lines.append("### Raw Results\n" + fallback[:6000])

            lines.append(f"\n_Search #{self._search_count} via Chrome CDP_")
            return "\n".join(lines)

        except TimeoutError:
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: CDP search timed out for: {query}"
        except Exception as e:
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: CDP search failed: {e}"

    def _multi_search(self, queries):
        """Run multiple searches and combine results."""
        all_results = []
        for i, query in enumerate(queries[:5]):
            result = self._web_search(query)
            all_results.append(f"--- Search {i + 1}/{len(queries)}: '{query}' ---\n{result}")
            if i < len(queries) - 1:
                _time.sleep(0.5)
        return "\n\n".join(all_results)

    def _news_search(self, query, num_results=10):
        """Search latest news — Serper News API → Google News RSS."""
        self._search_count += 1

        # Try Serper news
        result = serper_news(query, self._serper_key, num_results)
        if result:
            return result + f"\n\n_News search #{self._search_count} via Serper_"

        # Fallback to Google News RSS
        result = google_news_rss(query, num_results)
        if result:
            return result + f"\n\n_News search #{self._search_count} via Google News RSS_"

        # Last resort: web search with "news" prefix
        return self._web_search(f"{query} latest news", num_results)

    # ═══════════════════════════════════════════════════
    #  Layer 2: Domain-Specific APIs
    # ═══════════════════════════════════════════════════

    def _wiki_search(self, topic):
        """Wikipedia summary — instant, no browser needed."""
        result = wikipedia_summary(topic)
        if result:
            self._sources_visited.append((f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}", f"Wikipedia: {topic}", 85))
            return result
        return f"No Wikipedia article found for: {topic}"

    def _wiki_article(self, title):
        """Full Wikipedia article — up to 20K chars of clean text."""
        result = wikipedia_full_article(title, max_chars=20000)
        if result:
            self._sources_visited.append((f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}", f"Wikipedia: {title}", 85))
            return result
        return f"Wikipedia article not found: {title}"

    def _stock_quote(self, symbol):
        """Real-time stock/crypto quote from Yahoo Finance."""
        result = yahoo_finance_quote(symbol)
        if result:
            self._sources_visited.append((f"https://finance.yahoo.com/quote/{symbol}", f"Yahoo Finance: {symbol}", 85))
            return result

        # Fallback: try searching for the symbol
        search_result = yahoo_finance_search(symbol)
        if search_result:
            return f"Could not get quote directly. {search_result}"

        return f"No financial data found for symbol: {symbol}"

    def _finance_search(self, query):
        """Search for a ticker symbol by company/asset name."""
        result = yahoo_finance_search(query)
        if result:
            return result
        return f"No financial instruments found for: {query}"

    def _academic_search(self, query, limit=5):
        """Search academic papers on Semantic Scholar."""
        result = semantic_scholar_search(query, limit)
        if result:
            self._sources_visited.append(("https://www.semanticscholar.org", f"Semantic Scholar: {query}", 90))
            return result
        return f"No academic papers found for: {query}"

    def _arxiv_search(self, query, max_results=5):
        """Search arXiv preprints."""
        result = arxiv_search(query, max_results)
        if result:
            self._sources_visited.append(("https://arxiv.org", f"arXiv: {query}", 90))
            return result
        return f"No arXiv papers found for: {query}"

    # ═══════════════════════════════════════════════════
    #  Page Reading — HTTP-first, browser fallback
    # ═══════════════════════════════════════════════════

    def _browse(self, url, use_browser=False):
        """Read a web page — HTTP-first (fast), browser fallback for JS pages."""
        self._pages_read += 1

        # Try HTTP first (faster, no browser overhead) unless forced
        if not use_browser:
            result = http_read_page(url, max_chars=15000)
            if result and not result.startswith("ERROR:"):
                score = _score_url(url)
                self._sources_visited.append((url, "", score))
                return result + f"\n\n_Page #{self._pages_read} via HTTP_"

        # Browser-based reading (for JS-rendered pages)
        if not self._ensure_browser():
            return f"ERROR: Could not read {url} — browser unavailable and HTTP extraction failed"

        try:
            with _browser_lock:
                _ensure()
                _navigate(url)
                _time.sleep(2.5)

                text = _js(
                    "(function() {"
                    "var article = document.querySelector('article, [role=\"main\"], main, .post-content, .article-body, .entry-content');"
                    "if (article && article.innerText.length > 200) {"
                    "return article.innerText.substring(0, 15000);"
                    "}"
                    "return document.body ? document.body.innerText.substring(0, 15000) : '';"
                    "})()"
                )
                current_url = _js("window.location.href") or url
                title = _js("document.title || ''") or ""

            if not text:
                text = "(page content is empty or could not be read)"

            score = _score_url(current_url, title)
            self._sources_visited.append((current_url, title, score))
            trust_label = "HIGH" if score >= 70 else "MED" if score >= 45 else "LOW"

            header = f"[{trust_label}:{score}] **{title}**\nURL: {current_url}\n\n"
            if len(text) > 14000:
                text = text[:14000] + "\n\n... [truncated — use deep_read for full content] ..."

            return header + text + f"\n\n_Page #{self._pages_read} via Chrome CDP_"

        except TimeoutError:
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Browser timed out loading {url}. Try browse without use_browser."
        except Exception as e:
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Could not browse {url}: {e}"

    def _deep_read(self, url, max_scrolls=5):
        """Read a long page by scrolling — requires browser."""
        self._pages_read += 1
        max_scrolls = min(max_scrolls, 10)

        if not self._ensure_browser():
            # Fallback: HTTP with larger limit
            result = http_read_page(url, max_chars=50000)
            if result and not result.startswith("ERROR:"):
                return result + "\n\n_Deep read via HTTP (browser unavailable)_"
            return f"ERROR: Could not deep-read {url} — browser and HTTP both failed"

        all_text = []
        try:
            with _browser_lock:
                _ensure()
                _navigate(url)
                _time.sleep(3)

                title = _js("document.title || ''") or ""
                current_url = _js("window.location.href") or url

                chunk = _js("document.body ? document.body.innerText.substring(0, 10000) : ''")
                if chunk:
                    all_text.append(chunk)

                total_height = 0
                try:
                    total_height = int(_js("document.body.scrollHeight") or "0")
                except (ValueError, TypeError):
                    total_height = 5000
                viewport_height = 900
                try:
                    viewport_height = int(_js("window.innerHeight") or "900")
                except (ValueError, TypeError):
                    pass

                for i in range(max_scrolls):
                    scroll_pos = viewport_height * (i + 1)
                    if scroll_pos >= total_height:
                        break
                    _js(f"window.scrollTo(0, {scroll_pos})")
                    _time.sleep(1.5)

                    start_char = min(scroll_pos * 3, 200000)
                    end_char = start_char + 10000
                    chunk = _js(f"document.body ? document.body.innerText.substring({start_char}, {end_char}) : ''")
                    if chunk and len(chunk) > 50:
                        if not all_text or chunk[:200] != all_text[-1][:200]:
                            all_text.append(chunk)

                _js("window.scrollTo(0, 0)")

            full_text = "\n\n---\n\n".join(all_text)
            if len(full_text) > 50000:
                full_text = full_text[:50000] + "\n\n... [capped at 50K chars] ..."

            score = _score_url(current_url, title)
            self._sources_visited.append((current_url, title, score))
            trust_label = "HIGH" if score >= 70 else "MED" if score >= 45 else "LOW"

            header = (
                f"[{trust_label}:{score}] **{title}** (Deep Read — {len(all_text)} sections, ~{len(full_text):,} chars)\n"
                f"URL: {current_url}\n\n"
            )
            return header + full_text

        except TimeoutError:
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Deep read timed out on {url}. Try browse() instead."
        except Exception as e:
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Could not deep-read {url}: {e}"

    def _extract(self, url, question):
        """Navigate to URL and extract specific info."""
        self._pages_read += 1

        # Try HTTP first
        text = http_read_page(url, max_chars=15000)
        if text and not text.startswith("ERROR:"):
            score = _score_url(url)
            self._sources_visited.append((url, "", score))
            return (
                f"## Extraction from: {url}\n"
                f"Trust: {score}/100\n"
                f"Question: {question}\n\n"
                f"{text}"
            )

        # Browser fallback
        if not self._ensure_browser():
            return f"ERROR: Could not extract from {url} — both HTTP and browser failed"

        try:
            with _browser_lock:
                _ensure()
                _navigate(url)
                _time.sleep(2.5)
                text = _js(
                    "(function() {"
                    "var article = document.querySelector('article, [role=\"main\"], main, .post-content, .article-body');"
                    "if (article && article.innerText.length > 200) {"
                    "return article.innerText.substring(0, 15000);"
                    "}"
                    "return document.body ? document.body.innerText.substring(0, 15000) : '';"
                    "})()"
                )
                title = _js("document.title || ''") or ""
                current_url = _js("window.location.href") or url

            score = _score_url(current_url, title)
            self._sources_visited.append((current_url, title, score))

            return (
                f"## Extraction from: {title}\n"
                f"URL: {current_url} | Trust: {score}/100\n"
                f"Question: {question}\n\n"
                f"Page content:\n{text[:15000] if text else '(empty page)'}"
            )
        except TimeoutError:
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Extract timed out on {url}."
        except Exception as e:
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Could not extract from {url}: {e}"

    def _extract_table(self, url, table_description):
        """Extract tabular data from a page — requires browser for JS tables."""
        self._pages_read += 1

        if not self._ensure_browser():
            # Try HTTP and look for <table> tags
            text = http_read_page(url, max_chars=20000)
            if text:
                return f"## Table data from: {url}\nLooking for: {table_description}\n\n{text}"
            return f"ERROR: Could not extract tables from {url}"

        try:
            with _browser_lock:
                _ensure()
                _navigate(url)
                _time.sleep(2.5)

                tables_js = (
                    "(function() {"
                    "var tables = document.querySelectorAll('table');"
                    "var result = [];"
                    "tables.forEach(function(table, idx) {"
                    "var rows = [];"
                    "table.querySelectorAll('tr').forEach(function(tr) {"
                    "var cells = [];"
                    "tr.querySelectorAll('th, td').forEach(function(cell) {"
                    "cells.push(cell.innerText.trim());"
                    "});"
                    "if (cells.length > 0) rows.push(cells);"
                    "});"
                    "if (rows.length > 0) result.push({table_index: idx, rows: rows});"
                    "});"
                    "var priceCards = document.querySelectorAll('[class*=\"price\"], [class*=\"plan\"], [class*=\"tier\"], [class*=\"card\"]');"
                    "if (priceCards.length > 0 && result.length === 0) {"
                    "var cards = [];"
                    "priceCards.forEach(function(card) {"
                    "if (card.innerText.length > 20 && card.innerText.length < 2000) cards.push(card.innerText.trim());"
                    "});"
                    "if (cards.length > 0) result.push({table_index: 'pricing_cards', cards: cards.slice(0, 10)});"
                    "}"
                    "return JSON.stringify(result.slice(0, 5));"
                    "})()"
                )
                raw = _js(tables_js)
                title = _js("document.title || ''") or ""
                current_url = _js("window.location.href") or url

            try:
                tables = json.loads(raw) if raw else []
            except (json.JSONDecodeError, TypeError):
                tables = []

            score = _score_url(current_url, title)
            self._sources_visited.append((current_url, title, score))

            if not tables:
                with _browser_lock:
                    text = _js("document.body ? document.body.innerText.substring(0, 10000) : ''")
                return (
                    f"## No HTML tables found on: {title}\n"
                    f"URL: {current_url}\n"
                    f"Looking for: {table_description}\n\n"
                    f"Page text:\n{text}"
                )

            lines = [
                f"## Tables from: {title}",
                f"URL: {current_url} | Trust: {score}/100",
                f"Looking for: {table_description}\n"
            ]

            for t in tables:
                if "rows" in t:
                    tidx = t["table_index"] + 1 if isinstance(t["table_index"], int) else t["table_index"]
                    lines.append(f"### Table {tidx}")
                    for i, row in enumerate(t["rows"][:50]):
                        if i == 0:
                            lines.append("| " + " | ".join(str(c) for c in row) + " |")
                            lines.append("|" + "|".join(["---"] * len(row)) + "|")
                        else:
                            lines.append("| " + " | ".join(str(c) for c in row) + " |")
                    lines.append("")
                elif "cards" in t:
                    lines.append("### Pricing/Plan Cards")
                    for i, card in enumerate(t["cards"]):
                        lines.append(f"\n**Card {i + 1}:**\n{card}\n")

            return "\n".join(lines)

        except TimeoutError:
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Table extract timed out on {url}."
        except Exception as e:
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Could not extract tables from {url}: {e}"

    def _follow_links(self, url, link_pattern, max_links=3):
        """Read a page, find links matching pattern, follow them."""
        max_links = min(max_links, 5)

        if not self._ensure_browser():
            return f"ERROR: follow_links requires Chrome browser, which is unavailable"

        try:
            with _browser_lock:
                _ensure()
                _navigate(url)
                _time.sleep(2.5)

                safe_pattern = link_pattern.replace("'", "\\'").replace("\\", "\\\\")
                links_js = (
                    "(function() {"
                    "var pattern = '" + safe_pattern + "'.toLowerCase();"
                    "var links = [];"
                    "document.querySelectorAll('a[href]').forEach(function(a) {"
                    "var text = (a.innerText || '').trim();"
                    "var href = a.href || '';"
                    "if (text.length > 0 && text.length < 200 && href.startsWith('http')) {"
                    "var combined = (text + ' ' + href).toLowerCase();"
                    "if (combined.indexOf(pattern) !== -1) {"
                    "links.push({text: text.substring(0, 100), url: href});"
                    "}"
                    "}"
                    "});"
                    "var seen = {}; var unique = [];"
                    "links.forEach(function(l) { if (!seen[l.url]) { seen[l.url] = true; unique.push(l); } });"
                    "return JSON.stringify(unique.slice(0, " + str(max_links + 5) + "));"
                    "})()"
                )
                raw = _js(links_js)
                page_title = _js("document.title || ''") or ""

            try:
                found_links = json.loads(raw) if raw else []
            except (json.JSONDecodeError, TypeError):
                found_links = []

            if not found_links:
                return f"No links matching '{link_pattern}' found on {url}"

            results = [f"## Following '{link_pattern}' links from: {page_title}\n"]

            for i, link in enumerate(found_links[:max_links]):
                results.append(f"\n### Link {i + 1}: {link['text']}")
                results.append(f"URL: {link['url']}")

                # Read each linked page via HTTP (faster)
                page_content = http_read_page(link["url"], max_chars=6000)
                if page_content and not page_content.startswith("ERROR:"):
                    self._pages_read += 1
                    score = _score_url(link["url"])
                    self._sources_visited.append((link["url"], link["text"], score))
                    results.append(f"Trust: {score}/100")
                    results.append(page_content[:5000])
                else:
                    # Browser fallback
                    try:
                        with _browser_lock:
                            _ensure()
                            _navigate(link["url"])
                            _time.sleep(2)
                            text = _js(
                                "(function() {"
                                "var article = document.querySelector('article, [role=\"main\"], main');"
                                "if (article && article.innerText.length > 200) return article.innerText.substring(0, 6000);"
                                "return document.body ? document.body.innerText.substring(0, 6000) : '';"
                                "})()"
                            )
                            link_title = _js("document.title || ''") or ""

                        self._pages_read += 1
                        score = _score_url(link["url"], link_title)
                        self._sources_visited.append((link["url"], link_title, score))
                        results.append(f"Title: {link_title} | Trust: {score}/100")
                        results.append(text[:5000] if text else "(empty page)")
                    except Exception as e:
                        results.append(f"Could not read: {e}")

                results.append("")

            return "\n".join(results)

        except TimeoutError:
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Follow links timed out on {url}."
        except Exception as e:
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Could not follow links on {url}: {e}"

    # ═══════════════════════════════════════════════════
    #  Layer 3: Fact-Checking & Verification
    # ═══════════════════════════════════════════════════

    def _fact_check(self, claim, context=""):
        """
        Cross-reference a specific claim across multiple sources.
        Searches for the claim, reads top sources, and records evidence.
        """
        self._search_count += 1

        # Normalize claim for tracking
        claim_key = claim.strip().lower()[:200]

        # Initialize claim tracking
        if claim_key not in self._claims:
            self._claims[claim_key] = {
                "claim": claim,
                "evidence_for": [],
                "evidence_against": [],
                "status": "checking",
            }

        # Search for the claim
        search_query = claim
        if context:
            search_query = f"{context} {claim}"

        result = serper_search(search_query, self._serper_key, 5)
        if not result:
            result = duckduckgo_search(search_query, 5)
        if not result:
            self._claims[claim_key]["status"] = "unverifiable"
            return f"## Fact Check: UNVERIFIABLE\nClaim: {claim}\nCould not find sources to verify this claim."

        # Also check Wikipedia for factual claims
        wiki = wikipedia_summary(claim[:100])

        lines = [f"## Fact Check: '{claim}'\n"]
        lines.append(f"### Search Results\n{result}\n")
        if wiki and "not found" not in wiki.lower():
            lines.append(f"### Wikipedia Cross-Reference\n{wiki}\n")
            self._claims[claim_key]["evidence_for"].append(("Wikipedia", wiki[:200]))

        lines.append("### Verification Instructions")
        lines.append("Review the search results above and:")
        lines.append("1. Look for the EXACT claim in multiple sources")
        lines.append("2. Note any contradicting information")
        lines.append("3. Use 'note' to record your verdict with confidence level")
        lines.append("4. Mark as 'verified' (2+ sources confirm), 'disputed' (sources conflict), or 'unverified' (insufficient evidence)")

        # Update claim status based on evidence
        self._claims[claim_key]["status"] = "checked"

        return "\n".join(lines)

    def _cross_reference(self, finding, original_source=""):
        """Check if a finding is confirmed by independent sources."""
        self._search_count += 1

        # Search for corroboration
        result = self._web_search(finding, 5)

        lines = [f"## Cross-Reference Check\n"]
        lines.append(f"**Finding**: {finding}")
        if original_source:
            lines.append(f"**Original source**: {original_source}")
        lines.append(f"\n### Independent Sources\n{result}\n")

        # Check Wikipedia
        wiki_check = wikipedia_search(finding[:80], 3)
        if wiki_check and "No Wikipedia" not in wiki_check:
            lines.append(f"### Wikipedia Check\n{wiki_check}\n")

        lines.append("### Verdict Guide")
        lines.append("- ✅ VERIFIED: 2+ independent sources confirm the finding")
        lines.append("- ⚠️ SINGLE-SOURCE: Only found in original source")
        lines.append("- ❌ DISPUTED: Sources provide conflicting information")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════
    #  Notes with Citations
    # ═══════════════════════════════════════════════════

    def _note(self, key, value, source="", confidence="medium"):
        """Save a research finding with source attribution and citation number."""
        citation_num = None
        if source:
            score = _score_url(source) if source.startswith("http") else 60
            citation_num = self._add_citation(source, key, score)

        self._notes[key] = {
            "value": value,
            "source": source,
            "confidence": confidence,
            "citation": citation_num,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }

        conf_labels = {
            "verified": "✅ VERIFIED",
            "high": "📗 HIGH",
            "medium": "📙 MEDIUM",
            "low": "📕 LOW",
        }
        conf_label = conf_labels.get(confidence, "📝 NOTE")
        cite_str = f" [{citation_num}]" if citation_num else ""

        return (
            f"{conf_label}{cite_str} **{key}** = {value[:400]}{'...' if len(value) > 400 else ''}\n"
            f"Source: {source or 'not specified'}\n"
            f"({len(self._notes)} notes | {self._search_count} searches | {self._pages_read} pages)"
        )

    def _get_notes(self):
        """Review all notes organized by confidence, with citation numbers."""
        if not self._notes:
            return "No notes yet. Use 'note' to save findings as you research."

        verified = [(k, v) for k, v in self._notes.items() if v["confidence"] == "verified"]
        high = [(k, v) for k, v in self._notes.items() if v["confidence"] == "high"]
        medium = [(k, v) for k, v in self._notes.items() if v["confidence"] == "medium"]
        low = [(k, v) for k, v in self._notes.items() if v["confidence"] == "low"]

        lines = [f"## Research Notes ({len(self._notes)} findings)\n"]
        lines.append(f"Stats: {self._search_count} searches | {self._pages_read} pages | "
                     f"{len(self._sources_visited)} sources | {len(self._citations)} cited\n")

        if verified:
            lines.append("### ✅ VERIFIED (2+ sources confirm)")
            for key, data in verified:
                cite = f" [{data['citation']}]" if data.get('citation') else ""
                lines.append(f"  - **{key}**{cite}: {data['value']}")
                if data["source"]:
                    lines.append(f"    Source: {data['source']}")

        if high:
            lines.append("\n### 📗 HIGH CONFIDENCE (authoritative single source)")
            for key, data in high:
                cite = f" [{data['citation']}]" if data.get('citation') else ""
                lines.append(f"  - **{key}**{cite}: {data['value']}")
                if data["source"]:
                    lines.append(f"    Source: {data['source']}")

        if medium:
            lines.append("\n### 📙 MEDIUM CONFIDENCE (single source)")
            for key, data in medium:
                cite = f" [{data['citation']}]" if data.get('citation') else ""
                lines.append(f"  - **{key}**{cite}: {data['value']}")
                if data["source"]:
                    lines.append(f"    Source: {data['source']}")

        if low:
            lines.append("\n### 📕 LOW CONFIDENCE (unverified)")
            for key, data in low:
                cite = f" [{data['citation']}]" if data.get('citation') else ""
                lines.append(f"  - **{key}**{cite}: {data['value']}")
                if data["source"]:
                    lines.append(f"    Source: {data['source']}")

        # Fact-check summary
        if self._claims:
            lines.append(f"\n### Fact Checks ({len(self._claims)})")
            for key, claim_data in self._claims.items():
                status_icon = {"verified": "✅", "disputed": "❌", "checked": "🔍", "unverifiable": "❓"}.get(claim_data["status"], "⬜")
                lines.append(f"  {status_icon} {claim_data['claim'][:100]}")

        if self._comparisons:
            lines.append(f"\n### Comparisons ({len(self._comparisons)})")
            for comp in self._comparisons:
                lines.append(f"  - {comp['title']} — {len(comp['items'])} items x {len(comp['criteria'])} criteria")

        # Research plan progress
        plan = self._research_plan
        if plan["questions"]:
            done_count = len(plan["completed"])
            total = len(plan["questions"])
            lines.append(f"\n### Research Plan: {done_count}/{total} complete")
            for q in plan["questions"]:
                status = "✅" if q in plan["completed"] else "⬜"
                lines.append(f"  {status} {q}")

        # Citations
        if self._citations:
            lines.append(f"\n### Sources Cited ({len(self._citations)})")
            for i, (url, title, score) in enumerate(self._citations, 1):
                lines.append(f"  [{i}] {title or url} (trust: {score})")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════
    #  Comparison Engine
    # ═══════════════════════════════════════════════════

    def _compare(self, title, items, criteria, data):
        """Build a structured comparison table."""
        comp = {"title": title, "items": items, "criteria": criteria, "data": data}
        self._comparisons.append(comp)

        lines = [f"## {title}\n"]
        header = "| Criteria | " + " | ".join(items) + " |"
        sep = "|---|" + "|".join(["---"] * len(items)) + "|"
        lines.append(header)
        lines.append(sep)

        for criterion in criteria:
            row = f"| **{criterion}** |"
            for item in items:
                val = data.get(item, {}).get(criterion, "N/A")
                row += f" {val} |"
            lines.append(row)

        lines.append(f"\n_Comparison #{len(self._comparisons)} — {len(items)} items × {len(criteria)} criteria_")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════
    #  Calculations
    # ═══════════════════════════════════════════════════

    def _calculate(self, expression, label=""):
        result = _safe_calculate(expression)
        if label:
            return f"CALC **{label}**: {expression} = **{result}**"
        return f"CALC {expression} = **{result}**"

    def _convert(self, value, from_unit, to_unit):
        result = _convert_units(value, from_unit, to_unit)
        return f"CONVERT {value} {from_unit} = **{result} {to_unit}**"

    def _date_calc(self, expression):
        result = _date_math(expression)
        return f"DATE {expression} → **{result}**"

    # ═══════════════════════════════════════════════════
    #  Research Planning
    # ═══════════════════════════════════════════════════

    def _research_plan_update(self, questions, completed=None):
        self._research_plan["questions"] = questions
        if completed:
            for q in completed:
                if q not in self._research_plan["completed"]:
                    self._research_plan["completed"].append(q)

        done_count = len(self._research_plan["completed"])
        total = len(questions)
        pct = (done_count / total * 100) if total > 0 else 0

        lines = [f"## Research Plan — {done_count}/{total} complete ({pct:.0f}%)\n"]
        for q in questions:
            status = "✅" if q in self._research_plan.get("completed", []) else "⬜"
            lines.append(f"  {status} {q}")

        lines.append(f"\nNext: Focus on the first uncompleted question.")
        return "\n".join(lines)

    def _score_all_sources(self):
        """Score all sources visited during this research session."""
        if not self._sources_visited:
            return "No sources visited yet. Search and browse first."

        seen = {}
        for url, title, score in self._sources_visited:
            if url not in seen or score > seen[url][1]:
                seen[url] = (title, score)

        sorted_sources = sorted(seen.items(), key=lambda x: x[1][1], reverse=True)

        lines = [f"## Source Credibility Report ({len(sorted_sources)} unique sources)\n"]

        tier1 = [(u, t, s) for u, (t, s) in sorted_sources if s >= 70]
        tier2 = [(u, t, s) for u, (t, s) in sorted_sources if 45 <= s < 70]
        tier3 = [(u, t, s) for u, (t, s) in sorted_sources if s < 45]

        if tier1:
            lines.append(f"### 🟢 Highly Trustworthy ({len(tier1)})")
            for url, title, score in tier1:
                lines.append(f"  {score}/100 — {title or 'Untitled'}")
                lines.append(f"          {url}")

        if tier2:
            lines.append(f"\n### 🟡 Moderate Trust ({len(tier2)})")
            for url, title, score in tier2:
                lines.append(f"  {score}/100 — {title or 'Untitled'}")
                lines.append(f"          {url}")

        if tier3:
            lines.append(f"\n### 🔴 Low Trust ({len(tier3)})")
            for url, title, score in tier3:
                lines.append(f"  {score}/100 — {title or 'Untitled'}")
                lines.append(f"          {url}")

        avg = sum(s for _, (_, s) in sorted_sources) / len(sorted_sources) if sorted_sources else 0
        lines.append(f"\n**Average Trust: {avg:.0f}/100**")
        lines.append(f"**Sources Cited: {len(self._citations)}**")
        lines.append(f"**Fact Checks: {len(self._claims)}**")

        if avg >= 60:
            lines.append("✅ Source quality is strong.")
        elif avg >= 40:
            lines.append("⚠️ Consider finding higher-quality sources.")
        else:
            lines.append("❌ Sources are weak — find more authoritative references.")

        return "\n".join(lines)
