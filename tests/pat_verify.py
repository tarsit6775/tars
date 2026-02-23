"""Handle GitHub sudo verification and create PAT."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import _js, _ensure, act_goto, act_read_url, act_read_page, act_click, act_fill, act_scroll

_ensure()

# Step 1: Click "Verify via email"
print("=== Step 1: Click Verify via email ===")
r = act_click("Verify via email")
print(r)
time.sleep(3)

url = act_read_url()
print(f"\nURL: {url}")
page = act_read_page()
print(page[:1000])
