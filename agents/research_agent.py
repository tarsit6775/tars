"""
TARS Research Agent v2.0 — World-Class Deep Researcher
10-Phase Upgrade: The best research agent on the planet.

Phase 1:  Multi-query search with query expansion
Phase 2:  Deep page reading (scroll + paginate)
Phase 3:  Source credibility & trust scoring
Phase 4:  Structured data extraction (tables, lists, prices)
Phase 5:  Compare & analyze across sources
Phase 6:  Follow links & deep-dive chain reading
Phase 7:  Calculations, unit conversion, date math
Phase 8:  Research plan with progress tracking
Phase 9:  Elite researcher system prompt
Phase 10: Rich output (markdown tables, citations, scores)
"""

from agents.base_agent import BaseAgent
from agents.agent_tools import TOOL_DONE, TOOL_STUCK
from hands.browser import (
    _browser_lock, _ensure, _js, _activate_chrome,
)
import time as _time
import urllib.parse
import json
import re
import math
from datetime import datetime, timedelta


def _navigate(url):
    """Navigate to URL with CDP fallback if JS navigation times out.
    
    First tries JS navigation (window.location.href). If that hits a CDP 
    timeout (e.g., browser stuck on heavy JS page), falls back to CDP 
    Page.navigate which works even when the JS runtime is unresponsive.
    """
    safe_url = url.replace("'", "\\'")
    result = _js(f"window.location.href='{safe_url}'")
    if result and "JS_ERROR" in result:
        try:
            import hands.browser as _bmod
            _bmod._cdp.send("Page.navigate", {"url": url}, timeout=15)
        except Exception:
            pass


# =============================================
#  Phase 3: Source credibility scoring
# =============================================

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
}

_TIER2_DOMAINS = {
    "wikipedia.org", "britannica.com", "cnn.com", "nbcnews.com",
    "theguardian.com", "forbes.com", "businessinsider.com", "cnbc.com",
    "techcrunch.com", "arstechnica.com", "wired.com", "theverge.com",
    "engadget.com", "zdnet.com", "cnet.com", "tomsguide.com",
    "pcmag.com", "tomshardware.com", "anandtech.com",
    "healthline.com", "medicalnewstoday.com",
    "tripadvisor.com", "yelp.com", "glassdoor.com",
    "github.com", "stackoverflow.com", "docs.python.org",
    "developer.mozilla.org", "w3schools.com",
    "consumer.ftc.gov", "usa.gov",
    "amazon.com", "bestbuy.com", "walmart.com",
    "zillow.com", "realtor.com", "redfin.com",
    "google.com",
}

_TIER3_DOMAINS = {
    "reddit.com", "quora.com", "medium.com", "substack.com",
    "blogspot.com", "wordpress.com", "tumblr.com",
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "tiktok.com", "youtube.com",
}


def _score_source(url, title="", snippet=""):
    """Score a source 0-100 based on domain authority, recency clues, content type."""
    from urllib.parse import urlparse
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
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

    current_year = str(datetime.now().year)
    last_year = str(datetime.now().year - 1)
    text = f"{title} {snippet}".lower()
    if current_year in text:
        score += 10
    elif last_year in text:
        score += 5
    if "updated" in text or "revised" in text:
        score += 5

    if any(w in text for w in ["study", "research", "data", "statistics", "report", "analysis"]):
        score += 10
    if any(w in text for w in ["opinion", "editorial", "blog post", "my experience"]):
        score -= 5
    if "sponsored" in text or "advertisement" in text:
        score -= 20

    return max(0, min(100, score))


# =============================================
#  Phase 7: Calculation engine
# =============================================

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


# =============================================
#  Tool Definitions (15+ Research Tools)
# =============================================

TOOL_WEB_SEARCH = {
    "name": "web_search",
    "description": "Google search with smart query. Returns top results with titles, URLs, snippets, and trust scores. Use specific, targeted queries.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query - be specific and targeted"},
            "num_results": {"type": "integer", "description": "Number of results (default 10, max 30)", "default": 10},
        },
        "required": ["query"]
    }
}

TOOL_MULTI_SEARCH = {
    "name": "multi_search",
    "description": "Run 2-5 Google searches in sequence and combine results. Use when you need to approach a topic from different angles. More efficient than multiple web_search calls.",
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

TOOL_BROWSE = {
    "name": "browse",
    "description": "Navigate to a URL and read the page content. Smart article extraction strips nav/ads. Returns up to 15K chars. For longer pages use deep_read.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to visit and read"}
        },
        "required": ["url"]
    }
}

TOOL_DEEP_READ = {
    "name": "deep_read",
    "description": "Read a long page by scrolling through it. Captures up to 50K chars across multiple scroll positions. Use for long articles, documentation, reports.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to deeply read"},
            "max_scrolls": {"type": "integer", "description": "How many scroll steps (default 5, max 10)", "default": 5}
        },
        "required": ["url"]
    }
}

TOOL_EXTRACT = {
    "name": "extract",
    "description": "Open a URL and extract SPECIFIC information by answering a targeted question about the page. Better than browse when you know exactly what you need.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to visit"},
            "question": {"type": "string", "description": "Specific question to answer from the page content"}
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
            "table_description": {"type": "string", "description": "What table to look for (e.g. pricing plans, flight schedule, spec comparison)"}
        },
        "required": ["url", "table_description"]
    }
}

TOOL_FOLLOW_LINKS = {
    "name": "follow_links",
    "description": "Read a page and find/follow links matching a keyword pattern. Reads each linked page. Use for exploring related content, subpages, or references.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Starting URL"},
            "link_pattern": {"type": "string", "description": "Keyword to match in link text/URL (e.g. pricing, about, reviews)"},
            "max_links": {"type": "integer", "description": "Max links to follow (default 3, max 5)", "default": 3}
        },
        "required": ["url", "link_pattern"]
    }
}

TOOL_NOTE = {
    "name": "note",
    "description": "Save a research finding with source tracking. Always include where you found the information and your confidence level.",
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Short label for this finding"},
            "value": {"type": "string", "description": "The finding/fact to save"},
            "source": {"type": "string", "description": "URL or source name (important for credibility)"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"], "description": "high=verified 2+ sources, medium=single source, low=uncertain"}
        },
        "required": ["key", "value"]
    }
}

TOOL_NOTES = {
    "name": "notes",
    "description": "Review all collected research notes organized by confidence level, with source attributions and research stats.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_COMPARE = {
    "name": "compare",
    "description": "Build a side-by-side comparison table. Great for products, services, flights, plans. Data is saved and included in your final report.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Comparison title"},
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Item names to compare"
            },
            "criteria": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Criteria to compare on"
            },
            "data": {
                "type": "object",
                "description": "Data: {item_name: {criterion: value}}"
            }
        },
        "required": ["title", "items", "criteria", "data"]
    }
}

TOOL_CALCULATE = {
    "name": "calculate",
    "description": "Math calculations: +, -, *, /, **, %, sqrt(), abs(), round(), log(), pi, e, min(), max(), sum(), avg(). Use for price comparisons, percentages, unit economics.",
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Math expression (e.g. 1999 * 0.85, sqrt(144))"},
            "label": {"type": "string", "description": "What this calculates"}
        },
        "required": ["expression"]
    }
}

TOOL_CONVERT = {
    "name": "convert",
    "description": "Unit conversion: length (km/mi/m/ft/cm/in), weight (kg/lb/g/oz), volume (l/gal/ml), temperature (C/F/K), speed (mph/kph), area (sqft/sqm/acre).",
    "input_schema": {
        "type": "object",
        "properties": {
            "value": {"type": "number", "description": "Numeric value to convert"},
            "from_unit": {"type": "string", "description": "Source unit"},
            "to_unit": {"type": "string", "description": "Target unit"}
        },
        "required": ["value", "from_unit", "to_unit"]
    }
}

TOOL_DATE_CALC = {
    "name": "date_calc",
    "description": "Date arithmetic: today + 30 days, today - 2 weeks, 2026-03-15 + 90 days, days between 2026-01-01 and 2026-12-31.",
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Date expression to evaluate"}
        },
        "required": ["expression"]
    }
}

TOOL_RESEARCH_PLAN = {
    "name": "research_plan",
    "description": "Create/update your research plan. Define sub-questions to answer and track which are complete. Keeps you organized on complex tasks.",
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of research questions to answer"
            },
            "completed": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Questions that have been answered"
            }
        },
        "required": ["questions"]
    }
}

TOOL_SCORE_SOURCES = {
    "name": "score_sources",
    "description": "Evaluate credibility of all sources visited. Returns trust scores (0-100) with tier breakdown. Use to weigh conflicting info.",
    "input_schema": {"type": "object", "properties": {}}
}


# =============================================
#  Phase 9: Elite System Prompt
# =============================================

RESEARCH_SYSTEM_PROMPT = (
    "You are TARS Research Agent v2.0 -- an elite, world-class research analyst "
    "and personal research assistant. You combine the rigor of an investigative "
    "journalist, the analytical depth of a McKinsey consultant, and the "
    "thoroughness of a PhD researcher.\n\n"
    "## YOUR IDENTITY\n"
    "You are the most capable research agent ever built. Your research is so "
    "thorough that people trust it for making important decisions -- booking "
    "flights, buying homes, choosing careers, evaluating investments, comparing "
    "products, and understanding complex topics.\n\n"
    "## YOUR POWERS (15+ specialized tools)\n\n"
    "### Search & Discover\n"
    "- web_search: Google search (targeted, specific queries)\n"
    "- multi_search: Multiple searches at once (different angles on same topic)\n"
    "- follow_links: Follow links on a page to discover deeper content\n\n"
    "### Read & Understand\n"
    "- browse: Read a web page (up to 15K chars)\n"
    "- deep_read: Scroll through long pages (up to 50K chars)\n"
    "- extract: Extract specific answers from a page\n"
    "- extract_table: Pull structured tabular data (prices, specs, schedules)\n\n"
    "### Organize & Track\n"
    "- note: Save a finding with source URL and confidence level\n"
    "- notes: Review all collected findings\n"
    "- research_plan: Plan research questions and track progress\n"
    "- compare: Build side-by-side comparison tables\n\n"
    "### Analyze & Calculate\n"
    "- calculate: Math, percentages, financial calculations\n"
    "- convert: Unit conversions (length, weight, temp, speed, area)\n"
    "- date_calc: Date arithmetic (deadlines, durations, scheduling)\n"
    "- score_sources: Evaluate source credibility scores\n\n"
    "### Finish\n"
    "- done: Complete with full research report\n"
    "- stuck: Cannot proceed (explain what is blocking)\n\n"
    "## YOUR RESEARCH METHODOLOGY\n\n"
    "### Step 1: PLAN (Always start here for complex questions)\n"
    "- Use research_plan to break the question into sub-questions\n"
    "- Identify what types of sources you will need\n"
    "- Estimate how many sources are sufficient\n\n"
    "### Step 2: SEARCH BROADLY\n"
    "- Use multi_search with 2-4 query variations to find sources\n"
    "- Look at results to identify the best sources to read\n"
    "- Prioritize: official sources > expert reviews > news > forums\n\n"
    "### Step 3: READ DEEPLY\n"
    "- browse for medium pages, deep_read for long articles/docs\n"
    "- extract when you need just one specific data point\n"
    "- extract_table for pricing, specs, schedules\n"
    "- follow_links to explore related pages and references\n\n"
    "### Step 4: COLLECT & VERIFY\n"
    "- Use note for EVERY important finding (with source URL!)\n"
    "- Cross-reference claims across 2-3 independent sources\n"
    "- Use calculate to verify numbers and percentages\n"
    "- Use score_sources to check your source quality\n\n"
    "### Step 5: ANALYZE\n"
    "- Use compare to build structured comparison tables\n"
    "- Use calculate for derived metrics (price per unit, ROI, etc.)\n"
    "- Identify patterns, contradictions, and consensus across sources\n\n"
    "### Step 6: SYNTHESIZE\n"
    "- Review notes to see everything you have collected\n"
    "- Structure findings logically with clear headers\n"
    "- Include source URLs for verifiability\n"
    "- Call done with a comprehensive, well-structured report\n\n"
    "## RESEARCH STANDARDS\n\n"
    "### Accuracy\n"
    "- Never make claims without sourcing them\n"
    "- If sources disagree, report ALL viewpoints with source attribution\n"
    "- Distinguish: FACT (verified) vs. CLAIM (single source) vs. OPINION (subjective)\n"
    "- Include specific numbers, dates, names -- not vague generalizations\n\n"
    "### Completeness\n"
    "- Answer ALL aspects of the question\n"
    "- If something cannot be found, say so explicitly\n"
    "- For comparison tasks: cover at least 3 options unless user specified fewer\n"
    "- For fact-finding: verify across at least 2 independent sources\n\n"
    "### Recency\n"
    "- Always note when information was published/updated\n"
    "- Prefer sources from the current year\n"
    "- Flag if information might be outdated\n\n"
    "### Output Quality\n"
    "- Use markdown formatting in your final report\n"
    "- Include comparison tables when comparing items\n"
    "- Structure with clear headers and sections\n"
    "- End with a clear recommendation/conclusion when appropriate\n"
    "- Include source URLs so findings can be verified\n"
    "- Confidence indicators: high=verified 2+ sources, medium=single source, low=unverified\n\n"
    "## DOMAIN EXPERTISE\n\n"
    "### Travel Research\n"
    "- ⚠️ For FLIGHT SEARCHES: DO NOT search Kayak, Skyscanner, or Expedia — they detect bots and serve CAPTCHAs\n"
    "- Flight searches should use the search_flights tool (handled by TARS brain, not research agent)\n"
    "- If asked to research flight-related info (baggage policies, airline reviews, airport info), use web_search normally\n"
    "- ALWAYS use the date_calc tool to compute correct future dates before building any date-specific URLs\n"
    "- CRITICAL: Flight booking sites use aggressive bot detection — never navigate directly to Kayak/Skyscanner/Expedia\n\n"
    "### Product Research\n"
    "- Check official product pages + 2-3 review sites\n"
    "- Compare: price, specs, user ratings, pros/cons\n"
    "- Note where to buy, best deals, warranty\n\n"
    "### Financial Research\n"
    "- Use authoritative sources (SEC, Bloomberg, official filings)\n"
    "- Include metrics, time periods, market conditions\n"
    "- Calculate returns, ratios, comparisons\n\n"
    "### Medical/Health Research\n"
    "- ONLY use medical sources (NIH, Mayo Clinic, PubMed, CDC)\n"
    "- Never give medical advice -- present neutrally\n"
    "- Always recommend consulting a professional\n\n"
    "### Technical Research\n"
    "- Check official documentation first\n"
    "- Note version compatibility\n"
    "- Compare alternatives with decision criteria\n\n"
    "## ANTI-HALLUCINATION RULES (CRITICAL)\n"
    "1. MUST search and read sources before making claims\n"
    "2. Every claim MUST be backed by a tool call (web_search, browse, extract)\n"
    "3. If you did not find it through tools, do not claim it exists\n"
    "4. NEVER claim you performed actions -- you are READ-ONLY\n"
    "5. If task requires doing something (signup, booking), call stuck\n"
    "6. Report BOTH sides when you find contradictory information\n\n"
    "## EFFICIENCY RULES\n"
    "1. Simple factual questions: 2-3 searches may suffice\n"
    "2. Complex comparisons: budget 5-8 searches, 3-5 page reads\n"
    "3. Use extract instead of browse for single data points\n"
    "4. Use multi_search instead of multiple web_search calls\n"
    "5. Take notes AS you research -- do not try to remember everything\n"
    "6. Review notes and research_plan before writing final report\n"
)


# =============================================
#  Research Agent Class
# =============================================

class ResearchAgent(BaseAgent):
    """Autonomous research agent v2.0 -- world-class deep research and synthesis."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._notes = {}
        self._comparisons = []
        self._sources_visited = []
        self._research_plan = {"questions": [], "completed": []}
        self._search_count = 0
        self._pages_read = 0

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
        return (
            RESEARCH_SYSTEM_PROMPT +
            f"\n## CURRENT DATE\n"
            f"Today is {today}. The current year is {year}.\n"
            f"ALWAYS use {year} dates (never 2024 or 2025) when constructing URLs or date ranges.\n"
            f"When searching for flights, events, or time-sensitive data, use dates starting from {today}.\n"
        )

    @property
    def tools(self):
        return [
            TOOL_WEB_SEARCH, TOOL_MULTI_SEARCH, TOOL_BROWSE, TOOL_DEEP_READ,
            TOOL_EXTRACT, TOOL_EXTRACT_TABLE, TOOL_FOLLOW_LINKS,
            TOOL_NOTE, TOOL_NOTES, TOOL_COMPARE,
            TOOL_CALCULATE, TOOL_CONVERT, TOOL_DATE_CALC,
            TOOL_RESEARCH_PLAN, TOOL_SCORE_SOURCES,
            TOOL_DONE, TOOL_STUCK,
        ]

    def _on_start(self, task):
        """Clear state and activate Chrome for new research task."""
        self._notes = {}
        self._comparisons = []
        self._sources_visited = []
        self._research_plan = {"questions": [], "completed": []}
        self._search_count = 0
        self._pages_read = 0
        self._browser_errors = 0
        try:
            with _browser_lock:
                _activate_chrome()
                _ensure()
            print(f"  Research Agent v2.0: Chrome ready -- {len(self.tools)} tools loaded")
        except Exception as e:
            print(f"  Research Agent: Chrome init failed: {e}")

    def _recover_browser(self):
        """Attempt to recover from a browser crash/disconnect.
        
        Called when a browser operation hits a TimeoutError or connection issue.
        Kills the dead CDP connection and creates a fresh one.
        """
        import hands.browser as _browser_mod
        self._browser_errors += 1
        print(f"  🔄 Research Agent: Recovering browser (error #{self._browser_errors})...")
        try:
            # Force-kill the old CDP connection
            if _browser_mod._cdp:
                try:
                    _browser_mod._cdp.connected = False
                except Exception:
                    pass
                _browser_mod._cdp = None
            # Re-init
            _activate_chrome()
            _ensure()
            print(f"  ✅ Browser recovered")
            return True
        except Exception as e:
            print(f"  ❌ Browser recovery failed: {e}")
            return False

    def _dispatch(self, name, inp):
        """Route research tool calls."""
        try:
            if name == "web_search":
                return self._web_search(inp["query"], inp.get("num_results", 10))
            elif name == "multi_search":
                return self._multi_search(inp["queries"])
            elif name == "browse":
                return self._browse(inp["url"])
            elif name == "deep_read":
                return self._deep_read(inp["url"], inp.get("max_scrolls", 5))
            elif name == "extract":
                return self._extract(inp["url"], inp["question"])
            elif name == "extract_table":
                return self._extract_table(inp["url"], inp["table_description"])
            elif name == "follow_links":
                return self._follow_links(inp["url"], inp["link_pattern"], inp.get("max_links", 3))
            elif name == "note":
                return self._note(inp["key"], inp["value"], inp.get("source", ""), inp.get("confidence", "medium"))
            elif name == "notes":
                return self._get_notes()
            elif name == "compare":
                return self._compare(inp["title"], inp["items"], inp["criteria"], inp["data"])
            elif name == "calculate":
                return self._calculate(inp["expression"], inp.get("label", ""))
            elif name == "convert":
                return self._convert(inp["value"], inp["from_unit"], inp["to_unit"])
            elif name == "date_calc":
                return self._date_calc(inp["expression"])
            elif name == "research_plan":
                return self._research_plan_update(inp["questions"], inp.get("completed", []))
            elif name == "score_sources":
                return self._score_all_sources()
            return f"Unknown research tool: {name}"
        except Exception as e:
            return f"ERROR: {e}"

    # -----------------------------------------
    #  Phase 1: Multi-query search
    # -----------------------------------------

    def _web_search(self, query, num_results=10):
        """Google search -- atomic. Multi-strategy extraction with fallback."""
        self._search_count += 1
        try:
            with _browser_lock:
                _ensure()
                encoded = urllib.parse.quote_plus(query)
                num = min(num_results, 30)
                search_url = f"https://www.google.com/search?q={encoded}&num={num}"
                _navigate(search_url)
                _time.sleep(3)

                # Strategy 1: Multiple CSS selectors (Google changes these frequently)
                results_js = r"""(function() {
                    var results = [];
                    var seen = {};

                    // Strategy 1: div.g (classic)
                    document.querySelectorAll('div.g').forEach(function(item) {
                        var link = item.querySelector('a[href^="http"]');
                        var title = item.querySelector('h3');
                        if (link && title && !seen[link.href]) {
                            seen[link.href] = true;
                            var snippet = item.querySelector('[data-sncf], .VwiC3b, [style*="-webkit-line-clamp"], .lEBKkf, span.aCOpRe, .IsZvec');
                            results.push({title: title.innerText, url: link.href, snippet: snippet ? snippet.innerText : ''});
                        }
                    });

                    // Strategy 2: h3 > ancestor with link (catches new layouts)
                    if (results.length === 0) {
                        document.querySelectorAll('h3').forEach(function(h3) {
                            var parent = h3.closest('a') || h3.parentElement;
                            if (!parent) return;
                            var link = parent.tagName === 'A' ? parent : parent.querySelector('a[href^="http"]');
                            if (!link) { var p = parent.parentElement; if (p) link = p.querySelector('a[href^="http"]'); }
                            if (link && link.href && !seen[link.href] && !link.href.includes('google.com/search')) {
                                seen[link.href] = true;
                                var container = h3.closest('[data-sokoban], [data-hveid], [data-ved]') || h3.parentElement.parentElement;
                                var snippetEl = container ? container.querySelector('[data-sncf], .VwiC3b, [style*="-webkit-line-clamp"], .lEBKkf, span, div:not(:first-child)') : null;
                                var snipText = '';
                                if (snippetEl && snippetEl !== h3 && snippetEl.innerText !== h3.innerText) snipText = snippetEl.innerText;
                                results.push({title: h3.innerText, url: link.href, snippet: snipText.substring(0, 300)});
                            }
                        });
                    }

                    // Strategy 3: Any link with h3 descendant
                    if (results.length === 0) {
                        document.querySelectorAll('a[href^="http"]').forEach(function(a) {
                            var h3 = a.querySelector('h3');
                            if (h3 && !seen[a.href] && !a.href.includes('google.com')) {
                                seen[a.href] = true;
                                results.push({title: h3.innerText, url: a.href, snippet: ''});
                            }
                        });
                    }

                    // Featured snippet
                    var featured = document.querySelector('.hgKElc, .IZ6rdc, .kno-rdesc span, [data-attrid="description"] span, .xpdopen .LGOjhe');
                    var featuredText = featured ? featured.innerText.substring(0, 500) : '';

                    // People Also Ask
                    var paa = [];
                    document.querySelectorAll('[data-sgrd] .dnXCYb, .related-question-pair, [jsname="Cpkphb"]').forEach(function(q) {
                        paa.push(q.innerText || '');
                    });

                    return JSON.stringify({
                        results: results.slice(0, """ + str(num) + r"""),
                        featured_snippet: featuredText,
                        people_also_ask: paa.slice(0, 5),
                        strategy_used: results.length > 0 ? 'structured' : 'none'
                    });
                })()"""
                raw = _js(results_js)

                # Strategy 4 (fallback): If structured parsing failed, grab raw text
                structured_failed = False
                try:
                    data = json.loads(raw) if raw else {}
                except (json.JSONDecodeError, TypeError):
                    data = {}
                    structured_failed = True

                results = data.get("results", [])

                if not results and not structured_failed:
                    structured_failed = True

                # If no structured results, extract raw page text as fallback
                fallback_text = ""
                if structured_failed or len(results) == 0:
                    fallback_text = _js(
                        "(function() {"
                        "  var el = document.querySelector('#search, #rso, #main');"
                        "  if (el) return el.innerText.substring(0, 10000);"
                        "  return document.body ? document.body.innerText.substring(0, 10000) : '';"
                        "})()"
                    ) or ""

            # Build response
            featured = data.get("featured_snippet", "")
            paa = data.get("people_also_ask", [])

            # Score results
            for i, r in enumerate(results):
                r["rank"] = i + 1
                score = _score_source(r.get("url", ""), r.get("title", ""), r.get("snippet", ""))
                r["trust_score"] = score
                self._sources_visited.append((r.get("url", ""), r.get("title", ""), score))

            lines = [f"## Google Search: '{query}' ({len(results)} results)\n"]

            if featured:
                lines.append(f"### Featured Snippet\n{featured}\n")

            for r in results:
                trust_icon = "HIGH" if r["trust_score"] >= 70 else "MED" if r["trust_score"] >= 45 else "LOW"
                lines.append(f"{r['rank']}. [{trust_icon}] **{r.get('title', 'No title')}**")
                lines.append(f"   URL: {r.get('url', '')}")
                lines.append(f"   {r.get('snippet', '')}")
                lines.append(f"   Trust: {r['trust_score']}/100")
                lines.append("")

            if paa:
                lines.append("### People Also Ask")
                for q in paa[:5]:
                    lines.append(f"  - {q}")

            # If structured parsing failed, append raw text so agent still gets info
            if len(results) == 0 and fallback_text:
                lines.append("### Raw Search Results (structured parsing unavailable)")
                lines.append(fallback_text[:8000])

            lines.append(f"\nSearch #{self._search_count} | {len(results)} results scored")
            return "\n".join(lines)

        except TimeoutError as e:
            print(f"  Research web_search timeout: {e}")
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Search timed out (browser recovered). Try again: {e}"
        except Exception as e:
            print(f"  Research web_search error: {e}")
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Search failed: {e}"

    def _multi_search(self, queries):
        """Run multiple searches and combine results."""
        all_results = []
        for i, query in enumerate(queries[:5]):
            result = self._web_search(query)
            all_results.append(f"--- Search {i + 1}/{len(queries)}: '{query}' ---\n{result}")
            if i < len(queries) - 1:
                _time.sleep(1)
        return "\n\n".join(all_results)

    # -----------------------------------------
    #  Phase 2: Deep page reading
    # -----------------------------------------

    def _browse(self, url):
        """Navigate to URL and read -- atomic. Smart article extraction."""
        self._pages_read += 1
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

            score = _score_source(current_url, title)
            self._sources_visited.append((current_url, title, score))
            trust_label = "HIGH" if score >= 70 else "MED" if score >= 45 else "LOW"

            header = f"[{trust_label}] **{title}**\nURL: {current_url}\nTrust: {score}/100 | Page #{self._pages_read}\n\n"

            if len(text) > 14000:
                text = text[:14000] + "\n\n... [truncated -- use deep_read for full content, or extract for specific info] ..."

            return header + text

        except TimeoutError as e:
            print(f"  Research browse timeout: {e}")
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Browser timed out loading {url} (recovered). Try a different URL."
        except Exception as e:
            print(f"  Research browse error: {e}")
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Could not browse {url}: {e}"

    def _deep_read(self, url, max_scrolls=5):
        """Read a long page by scrolling through it. Captures up to 50K chars."""
        self._pages_read += 1
        max_scrolls = min(max_scrolls, 10)
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

            score = _score_source(current_url, title)
            self._sources_visited.append((current_url, title, score))
            trust_label = "HIGH" if score >= 70 else "MED" if score >= 45 else "LOW"

            header = (
                f"[{trust_label}] **{title}** (Deep Read -- {len(all_text)} sections, ~{len(full_text):,} chars)\n"
                f"URL: {current_url}\n"
                f"Trust: {score}/100\n\n"
            )
            return header + full_text

        except TimeoutError as e:
            print(f"  Research deep_read timeout: {e}")
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Deep read timed out on {url} (recovered). Try browse() instead."
        except Exception as e:
            print(f"  Research deep_read error: {e}")
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Could not deep-read {url}: {e}"

    # -----------------------------------------
    #  Phase 4: Structured extraction
    # -----------------------------------------

    def _extract(self, url, question):
        """Navigate to URL and extract specific info -- atomic."""
        self._pages_read += 1
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

            if not text:
                text = "(page content is empty)"

            score = _score_source(current_url, title)
            self._sources_visited.append((current_url, title, score))

            return (
                f"## Extraction from: {title}\n"
                f"URL: {current_url} | Trust: {score}/100\n"
                f"Question: {question}\n\n"
                f"Page content:\n{text[:15000]}"
            )

        except TimeoutError as e:
            print(f"  Research extract timeout: {e}")
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Extract timed out on {url} (recovered). Try again."
        except Exception as e:
            print(f"  Research extract error: {e}")
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Could not extract from {url}: {e}"

    def _extract_table(self, url, table_description):
        """Extract tabular data from a page."""
        self._pages_read += 1
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
                    "if (rows.length > 0) {"
                    "result.push({table_index: idx, rows: rows});"
                    "}"
                    "});"
                    "var priceCards = document.querySelectorAll('[class*=\"price\"], [class*=\"plan\"], [class*=\"tier\"], [class*=\"card\"]');"
                    "if (priceCards.length > 0 && result.length === 0) {"
                    "var cards = [];"
                    "priceCards.forEach(function(card) {"
                    "if (card.innerText.length > 20 && card.innerText.length < 2000) {"
                    "cards.push(card.innerText.trim());"
                    "}"
                    "});"
                    "if (cards.length > 0) {"
                    "result.push({table_index: 'pricing_cards', cards: cards.slice(0, 10)});"
                    "}"
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

            score = _score_source(current_url, title)
            self._sources_visited.append((current_url, title, score))

            if not tables:
                with _browser_lock:
                    text = _js("document.body ? document.body.innerText.substring(0, 10000) : ''")
                return (
                    f"## No HTML tables found on: {title}\n"
                    f"URL: {current_url}\n"
                    f"Looking for: {table_description}\n\n"
                    f"Page text (may contain data in text format):\n{text}"
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

        except TimeoutError as e:
            print(f"  Research extract_table timeout: {e}")
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Table extract timed out on {url} (recovered). Try again."
        except Exception as e:
            print(f"  Research extract_table error: {e}")
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Could not extract tables from {url}: {e}"

    # -----------------------------------------
    #  Phase 6: Follow links
    # -----------------------------------------

    def _follow_links(self, url, link_pattern, max_links=3):
        """Read a page, find links matching a pattern, and follow them."""
        max_links = min(max_links, 5)
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
                    "var seen = {};"
                    "var unique = [];"
                    "links.forEach(function(l) {"
                    "if (!seen[l.url]) {"
                    "seen[l.url] = true;"
                    "unique.push(l);"
                    "}"
                    "});"
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

            results = [f"## Following links matching '{link_pattern}' from: {page_title}\n"]
            results.append(f"Found {len(found_links)} matching links, reading top {min(max_links, len(found_links))}:\n")

            for i, link in enumerate(found_links[:max_links]):
                results.append(f"\n### Link {i + 1}: {link['text']}")
                results.append(f"URL: {link['url']}")

                try:
                    with _browser_lock:
                        _ensure()
                        _navigate(link["url"])
                        _time.sleep(2)
                        text = _js(
                            "(function() {"
                            "var article = document.querySelector('article, [role=\"main\"], main');"
                            "if (article && article.innerText.length > 200) {"
                            "return article.innerText.substring(0, 6000);"
                            "}"
                            "return document.body ? document.body.innerText.substring(0, 6000) : '';"
                            "})()"
                        )
                        link_title = _js("document.title || ''") or ""

                    score = _score_source(link["url"], link_title)
                    self._sources_visited.append((link["url"], link_title, score))
                    self._pages_read += 1

                    results.append(f"Title: {link_title} | Trust: {score}/100")
                    results.append(f"Content:\n{text[:5000] if text else '(empty page)'}\n")
                except Exception as e:
                    results.append(f"Could not read: {e}\n")

                if i < max_links - 1:
                    _time.sleep(0.5)

            return "\n".join(results)

        except TimeoutError as e:
            print(f"  Research follow_links timeout: {e}")
            with _browser_lock:
                self._recover_browser()
            return f"ERROR: Follow links timed out on {url} (recovered). Try again."
        except Exception as e:
            print(f"  Research follow_links error: {e}")
            if "Not connected" in str(e) or "timeout" in str(e).lower():
                with _browser_lock:
                    self._recover_browser()
            return f"ERROR: Could not follow links on {url}: {e}"

    # -----------------------------------------
    #  Notes with source tracking
    # -----------------------------------------

    def _note(self, key, value, source="", confidence="medium"):
        """Save a research finding with source attribution."""
        self._notes[key] = {
            "value": value,
            "source": source,
            "confidence": confidence,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        conf_label = {"high": "[VERIFIED]", "medium": "[SINGLE-SRC]", "low": "[UNCERTAIN]"}.get(confidence, "[NOTE]")
        return (
            f"{conf_label} Noted: **{key}** = {value[:300]}{'...' if len(value) > 300 else ''}\n"
            f"Source: {source or 'not specified'}\n"
            f"({len(self._notes)} notes | {self._search_count} searches | {self._pages_read} pages)"
        )

    def _get_notes(self):
        """Review all collected notes, organized by confidence."""
        if not self._notes:
            return "No notes yet. Use 'note' to save findings as you research."

        high = [(k, v) for k, v in self._notes.items() if v["confidence"] == "high"]
        medium = [(k, v) for k, v in self._notes.items() if v["confidence"] == "medium"]
        low = [(k, v) for k, v in self._notes.items() if v["confidence"] == "low"]

        lines = [f"## Research Notes ({len(self._notes)} findings)\n"]
        lines.append(f"Stats: {self._search_count} searches | {self._pages_read} pages | {len(self._sources_visited)} sources\n")

        if high:
            lines.append("### [VERIFIED] High Confidence")
            for key, data in high:
                lines.append(f"  - **{key}**: {data['value']}")
                if data["source"]:
                    lines.append(f"    Source: {data['source']}")

        if medium:
            lines.append("\n### [SINGLE-SRC] Medium Confidence")
            for key, data in medium:
                lines.append(f"  - **{key}**: {data['value']}")
                if data["source"]:
                    lines.append(f"    Source: {data['source']}")

        if low:
            lines.append("\n### [UNCERTAIN] Low Confidence")
            for key, data in low:
                lines.append(f"  - **{key}**: {data['value']}")
                if data["source"]:
                    lines.append(f"    Source: {data['source']}")

        if self._comparisons:
            lines.append(f"\n### Comparisons ({len(self._comparisons)})")
            for comp in self._comparisons:
                lines.append(f"  - {comp['title']} -- {len(comp['items'])} items x {len(comp['criteria'])} criteria")

        plan = self._research_plan
        if plan["questions"]:
            done_count = len(plan["completed"])
            total = len(plan["questions"])
            lines.append(f"\n### Research Plan: {done_count}/{total} complete")
            for q in plan["questions"]:
                status = "DONE" if q in plan["completed"] else "TODO"
                lines.append(f"  [{status}] {q}")

        return "\n".join(lines)

    # -----------------------------------------
    #  Phase 5: Comparison engine
    # -----------------------------------------

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

        lines.append(f"\n_Comparison #{len(self._comparisons)} -- {len(items)} items x {len(criteria)} criteria_")
        return "\n".join(lines)

    # -----------------------------------------
    #  Phase 7: Calculations
    # -----------------------------------------

    def _calculate(self, expression, label=""):
        """Safe math calculation."""
        result = _safe_calculate(expression)
        if label:
            return f"CALC **{label}**: {expression} = **{result}**"
        return f"CALC {expression} = **{result}**"

    def _convert(self, value, from_unit, to_unit):
        """Unit conversion."""
        result = _convert_units(value, from_unit, to_unit)
        return f"CONVERT {value} {from_unit} = **{result} {to_unit}**"

    def _date_calc(self, expression):
        """Date arithmetic."""
        result = _date_math(expression)
        return f"DATE {expression} -> **{result}**"

    # -----------------------------------------
    #  Phase 8: Research planning
    # -----------------------------------------

    def _research_plan_update(self, questions, completed=None):
        """Create or update the research plan."""
        self._research_plan["questions"] = questions
        if completed:
            for q in completed:
                if q not in self._research_plan["completed"]:
                    self._research_plan["completed"].append(q)

        done_count = len(self._research_plan["completed"])
        total = len(questions)
        pct = (done_count / total * 100) if total > 0 else 0

        lines = [f"## Research Plan -- {done_count}/{total} complete ({pct:.0f}%)\n"]
        for q in questions:
            status = "DONE" if q in self._research_plan.get("completed", []) else "TODO"
            lines.append(f"  [{status}] {q}")

        lines.append(f"\nNext: Focus on the first uncompleted question.")
        return "\n".join(lines)

    # -----------------------------------------
    #  Phase 3: Source scoring
    # -----------------------------------------

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
            lines.append(f"### Highly Trustworthy ({len(tier1)})")
            for url, title, score in tier1:
                lines.append(f"  {score}/100 -- {title or 'Untitled'}")
                lines.append(f"          {url}")

        if tier2:
            lines.append(f"\n### Moderately Trustworthy ({len(tier2)})")
            for url, title, score in tier2:
                lines.append(f"  {score}/100 -- {title or 'Untitled'}")
                lines.append(f"          {url}")

        if tier3:
            lines.append(f"\n### Low Trust ({len(tier3)})")
            for url, title, score in tier3:
                lines.append(f"  {score}/100 -- {title or 'Untitled'}")
                lines.append(f"          {url}")

        avg = sum(s for _, (_, s) in sorted_sources) / len(sorted_sources) if sorted_sources else 0
        lines.append(f"\n**Average Trust: {avg:.0f}/100**")
        if avg >= 60:
            lines.append("Sources are reliable.")
        elif avg >= 40:
            lines.append("Consider finding higher-quality sources.")
        else:
            lines.append("Sources are weak -- find more authoritative references.")

        return "\n".join(lines)
