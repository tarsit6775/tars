"""
╔══════════════════════════════════════════════════════════╗
║      TARS — Headless Browser (Playwright)                ║
╠══════════════════════════════════════════════════════════╣
║  Alternative to CDP browser — runs headlessly without    ║
║  needing Chrome open. Uses Playwright for:               ║
║    • Scraping content from pages                         ║
║    • Taking screenshots                                  ║
║    • Filling forms                                       ║
║    • Running in server/background mode                   ║
║                                                          ║
║  Falls back to CDP browser for tasks needing the         ║
║  user's actual Chrome session (cookies, logins).         ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import logging
import tempfile
from datetime import datetime

logger = logging.getLogger("tars.headless")

REPORT_DIR = os.path.expanduser("~/Documents/TARS_Reports")
os.makedirs(REPORT_DIR, exist_ok=True)

_browser = None
_context = None
_page = None
_pw = None  # Playwright instance — must be stopped on cleanup


def _ensure_browser():
    """Ensure Playwright browser is running."""
    global _browser, _context, _page, _pw

    if _page and not _page.is_closed():
        return _page

    try:
        from playwright.sync_api import sync_playwright

        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        _context = _browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        _page = _context.new_page()
        logger.info("  🌐 Headless browser started (Playwright/Chromium)")
        return _page
    except ImportError:
        raise ImportError("Playwright not installed. Run: pip install playwright && playwright install chromium")
    except Exception as e:
        raise RuntimeError(f"Failed to start headless browser: {e}")


def scrape_page(url, wait_for=None, timeout=30):
    """Navigate to URL and extract page content.
    
    Args:
        url: URL to scrape
        wait_for: Optional CSS selector to wait for before extracting
        timeout: Page load timeout in seconds
    
    Returns:
        Standard tool result dict
    """
    try:
        page = _ensure_browser()
        page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")

        if wait_for:
            try:
                page.wait_for_selector(wait_for, timeout=10000)
            except Exception:
                pass

        # Wait for dynamic content
        time.sleep(1)

        # Extract text
        text = page.evaluate("""() => {
            // Remove script, style, nav, footer
            document.querySelectorAll('script, style, nav, footer, iframe, noscript').forEach(el => el.remove());
            return document.body.innerText;
        }""")

        title = page.title()

        return {
            "success": True,
            "content": f"## {title}\nURL: {url}\n\n{text[:10000]}"
        }

    except ImportError as e:
        return {"success": False, "error": True, "content": str(e)}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Scrape error: {e}"}


def take_screenshot(url=None, full_page=False, filename=None):
    """Take a screenshot of the current page or a URL.
    
    Args:
        url: Optional URL to navigate to first
        full_page: Whether to capture the full scrollable page
        filename: Custom filename
    
    Returns:
        Standard tool result dict with path
    """
    try:
        page = _ensure_browser()

        if url:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(2)

        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        filepath = os.path.join(REPORT_DIR, filename)
        page.screenshot(path=filepath, full_page=full_page)

        return {
            "success": True,
            "path": filepath,
            "content": f"Screenshot saved to {filepath}"
        }

    except ImportError as e:
        return {"success": False, "error": True, "content": str(e)}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Screenshot error: {e}"}


def extract_links(url):
    """Extract all links from a page.
    
    Returns:
        Standard tool result dict with list of links
    """
    try:
        page = _ensure_browser()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")

        links = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.innerText.trim().substring(0, 100),
                href: a.href,
            })).filter(l => l.href.startsWith('http'));
        }""")

        formatted = "\n".join(f"  {l['text'][:60]} → {l['href']}" for l in links[:50])
        return {
            "success": True,
            "content": f"Found {len(links)} links on {url}:\n{formatted}"
        }

    except ImportError as e:
        return {"success": False, "error": True, "content": str(e)}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Link extraction error: {e}"}


def extract_tables(url):
    """Extract tables from a webpage as structured data.
    
    Returns:
        Standard tool result dict with table data
    """
    try:
        page = _ensure_browser()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")

        tables = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('table')).map(table => {
                const headers = Array.from(table.querySelectorAll('th')).map(th => th.innerText.trim());
                const rows = Array.from(table.querySelectorAll('tbody tr')).map(tr =>
                    Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim())
                );
                return { headers, rows: rows.slice(0, 50) };
            });
        }""")

        if not tables:
            return {"success": True, "content": f"No tables found on {url}"}

        parts = []
        for i, table in enumerate(tables[:5]):
            parts.append(f"### Table {i + 1}")
            if table["headers"]:
                parts.append(" | ".join(table["headers"]))
                parts.append("-" * 40)
            for row in table["rows"][:20]:
                parts.append(" | ".join(row))
            parts.append("")

        return {"success": True, "content": "\n".join(parts)}

    except ImportError as e:
        return {"success": False, "error": True, "content": str(e)}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Table extraction error: {e}"}


def close_browser():
    """Close the headless browser and stop Playwright."""
    global _browser, _context, _page, _pw
    try:
        if _page:
            _page.close()
        if _context:
            _context.close()
        if _browser:
            _browser.close()
        if _pw:
            _pw.stop()
    except Exception:
        pass
    _page = _context = _browser = _pw = None
