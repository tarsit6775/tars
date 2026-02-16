#!/usr/bin/env python3
"""TARS v6.2 — Full Verification Test"""
import re, sys

print("=" * 60)
print("  TARS v6.2 — Full Verification Test")
print("=" * 60)

# ── 1. Import tests ────────────────────────────────────────
print("\n[1/3] Testing imports...")
errors = []

try:
    from hands.flight_search import (
        search_flights, search_flights_report,
        find_cheapest_dates, track_flight_price,
        book_flight, _resolve_airport, _parse_date
    )
    print("  ✅ flight_search — all functions importable")
except Exception as e:
    errors.append(f"flight_search import: {e}")
    print(f"  ❌ flight_search: {e}")

try:
    from hands.cdp import CDP
    print("  ✅ cdp — imports OK (no signal)")
except Exception as e:
    errors.append(f"cdp import: {e}")
    print(f"  ❌ cdp: {e}")

try:
    from brain.tools import TARS_TOOLS
    tool_names = [t["name"] for t in TARS_TOOLS]
    has_book = "book_flight" in tool_names
    print(f"  ✅ brain/tools — {len(TARS_TOOLS)} tools, book_flight={has_book}")
    if not has_book:
        errors.append("book_flight not in TARS_TOOLS")
except Exception as e:
    errors.append(f"brain/tools import: {e}")
    print(f"  ❌ brain/tools: {e}")

try:
    from executor import ToolExecutor
    print("  ✅ executor — imports OK")
except Exception as e:
    errors.append(f"executor import: {e}")
    print(f"  ❌ executor: {e}")

try:
    from brain.prompts import TARS_SYSTEM_PROMPT
    prompt = TARS_SYSTEM_PROMPT
    has_rule = "NEVER" in prompt and "research_agent" in prompt and "flight" in prompt
    print(f"  ✅ brain/prompts — anti-research-agent rule={has_rule}")
    if not has_rule:
        errors.append("Missing anti-research-agent rule in prompts")
except Exception as e:
    errors.append(f"brain/prompts import: {e}")
    print(f"  ❌ brain/prompts: {e}")

# ── 2. Airport resolution tests ────────────────────────────
print("\n[2/3] Testing _resolve_airport()...")
airport_tests = {
    "Lahore Pakistan": "LHE",
    "lahore pakistan": "LHE",
    "Lahore": "LHE",
    "Islamabad Pakistan": "ISB",
    "Karachi Pakistan": "KHI",
    "Salt Lake City": "SLC",
    "Tampa": "TPA",
    "Tokyo": "NRT",
    "Hawaii": "HNL",
    "London UK": "LHR",
    "Dubai UAE": "DXB",
    "New York": "JFK",
    "Los Angeles": "LAX",
    "SLC": "SLC",
    "LAX": "LAX",
    "LHE": "LHE",
}
airport_pass = 0
for inp, expected in airport_tests.items():
    try:
        got = _resolve_airport(inp)
        if got == expected:
            airport_pass += 1
        else:
            errors.append(f'_resolve_airport("{inp}") = {got}, expected {expected}')
            print(f"  ❌ \"{inp}\" → {got}  (expected {expected})")
    except Exception as e:
        errors.append(f'_resolve_airport("{inp}") raised: {e}')
        print(f"  ❌ \"{inp}\" → ERROR: {e}")

if airport_pass == len(airport_tests):
    print(f"  ✅ All {airport_pass}/{len(airport_tests)} airport tests passed")
else:
    print(f"  ⚠️  {airport_pass}/{len(airport_tests)} passed")

# ── 3. Date parsing tests ──────────────────────────────────
print("\n[3/3] Testing _parse_date()...")
date_tests = {
    "in 6 months": r"2026-0[78]",
    "in one month": r"2026-03",
    "in 2 weeks": r"2026-0[23]",
    "in 10 days": r"2026-02-2",
    "6 months from now": r"2026-0[78]",
    "next 6 months": r"2026-0[78]",
    "three months from now": r"2026-05",
    "today": r"2026-02-1[6-9]",
    "tomorrow": r"2026-02-1[7-9]",
    "March 15": r"202[56]-03-15",
}
date_pass = 0
for inp, pattern in date_tests.items():
    try:
        got = _parse_date(inp)
        if re.match(pattern, got):
            date_pass += 1
        else:
            errors.append(f'_parse_date("{inp}") = {got}, expected ~{pattern}')
            print(f"  ❌ \"{inp}\" → {got}  (expected ~{pattern})")
    except Exception as e:
        errors.append(f'_parse_date("{inp}") raised: {e}')
        print(f"  ❌ \"{inp}\" → ERROR: {e}")

if date_pass == len(date_tests):
    print(f"  ✅ All {date_pass}/{len(date_tests)} date tests passed")
else:
    print(f"  ⚠️  {date_pass}/{len(date_tests)} passed")

# ── Summary ─────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"  ❌ FAILED — {len(errors)} error(s):")
    for e in errors:
        print(f"     • {e}")
    sys.exit(1)
else:
    total = len(airport_tests) + len(date_tests) + 5  # 5 import checks
    print(f"  ✅ ALL {total} TESTS PASSED — v6.2 is ready")
    sys.exit(0)
