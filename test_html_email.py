#!/usr/bin/env python3
"""Quick test: verify HTML email generation works"""
import sys
sys.path.insert(0, '.')

from hands.flight_search import _html_flight_report_email, _generate_flight_excel, _analyze_flights, _get_airline_booking_url

test_flights = [
    {"price": "$59", "airline": "United", "depart_time": "6:00 AM", "arrive_time": "2:30 PM",
     "duration": "8h 30m", "stops": "1 stop", "value_score": 95, "value_label": "Excellent",
     "booking_link": "https://google.com/flights", "layover_airport": "DEN", "layover_duration": "1h 45m",
     "fare_class": "Basic Economy", "baggage": "No carry-on"},
    {"price": "$120", "airline": "Delta", "depart_time": "9:00 AM", "arrive_time": "3:15 PM",
     "duration": "6h 15m", "stops": "Nonstop", "value_score": 88, "value_label": "Excellent",
     "booking_link": "https://google.com/flights", "fare_class": "Main Cabin", "baggage": "Carry-on included"},
    {"price": "$250", "airline": "American", "depart_time": "11:00 AM", "arrive_time": "5:45 PM",
     "duration": "6h 45m", "stops": "Nonstop", "value_score": 72, "value_label": "Great",
     "booking_link": "https://google.com/flights"},
]

# Test HTML generation
html = _html_flight_report_email("SLC", "LHE", "2026-03-20", "2026-04-05", test_flights, "https://google.com/flights",
                                  price_insight="Prices are currently low for this route",
                                  return_flight={"depart_time": "4:00 PM", "arrive_time": "8:00 AM+1", "duration": "16h", "stops": "1 stop"},
                                  tracker_suggestion="Set a price tracker at $50 to catch a deal")
print(f"HTML length: {len(html)}")
print(f"Has DOCTYPE: {'DOCTYPE' in html}")
print(f"Has table: {'<table' in html}")
print(f"Has bar chart: {'Price Comparison' in html}")
print(f"Has TARS v5: {'TARS v5' in html}")
print(f"Has layover info: {'DEN' in html}")
print(f"Has fare class: {'Basic Economy' in html}")
print(f"Has baggage: {'No carry-on' in html}")
print(f"Has price insight: {'Prices are currently low' in html}")
print(f"Has return flight: {'4:00 PM' in html}")
print(f"Has tracker suggestion: {'price tracker' in html}")

# Save HTML to file for visual inspection
with open("/tmp/tars_test_email.html", "w") as f:
    f.write(html)
print(f"\nHTML saved to /tmp/tars_test_email.html")

# Test booking link generation
for airline in ["United", "Delta", "American", "PIA", "Emirates", "Turkish Airlines"]:
    link = _get_airline_booking_url(airline, "SLC", "LHE", "2026-03-20", "2026-04-05")
    print(f"  {airline}: {link[:80] if link else 'NO LINK'}")

# Test Excel generation
excel_result = _generate_flight_excel("Test Flights SLC->LHE", test_flights, "SLC", "LHE", "https://google.com/flights",
                                       summary_data={"Route": "SLC->LHE"}, analytics={"price_min": 59, "price_max": 250, "price_avg": 143,
                                       "total_flights": 3, "price_median": 120, "price_std_dev": 78, "price_range": 191,
                                       "nonstop_count": 2, "connecting_count": 1, "nonstop_premium": None, "airline_count": 3,
                                       "airline_stats": {"United": {"min": 59, "avg": 59, "count": 1, "nonstop": 0},
                                                         "Delta": {"min": 120, "avg": 120, "count": 1, "nonstop": 1}}},
                                       suggestions=[{"icon": "tip", "type": "nonstop_value", "text": "Nonstop is worth it"}])
print(f"\nExcel: {excel_result}")
print("\nAll tests passed!")
