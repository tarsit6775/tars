"""Verify repo created and get page content."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import _js, _ensure, act_read_url, act_read_page

_ensure()

url = act_read_url()
print(url)
print()
page = act_read_page()
print(page[:1500])
