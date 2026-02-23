"""Navigate to GitHub fine-grained PAT creation page."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import _js, _ensure, act_goto, act_read_url, act_read_page, act_click, act_fill, act_scroll

_ensure()

# Navigate to fine-grained token creation
act_goto("https://github.com/settings/personal-access-tokens/new")
time.sleep(3)

url = act_read_url()
print(f"URL: {url}")
print()
page = act_read_page()
print(page[:2000])
