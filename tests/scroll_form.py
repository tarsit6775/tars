"""Scroll and inspect GitHub form."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import act_click, _js, act_scroll, act_inspect_page

# Scroll to top first
_js("window.scrollTo(0, 0)")
time.sleep(0.5)

# Now scroll down to see the full form
print("=== Scrolling down ===")
act_scroll("down")
time.sleep(0.5)

# Check visibility
print("\n=== After scroll - visible elements ===")
raw = _js("""(function() {
    var out = [];
    // Find visibility-related elements in viewport
    var all = document.querySelectorAll('button, [role=radio], [role=switch], [aria-pressed]');
    all.forEach(function(el) {
        var r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && r.y > 0 && r.y < 900) {
            var t = (el.innerText||'').trim().substring(0,40);
            var label = el.getAttribute('aria-label') || '';
            var pressed = el.getAttribute('aria-pressed') || '';
            if (t || label || pressed) {
                out.push(el.tagName + ' text="' + t + '" label="' + label + '" pressed="' + pressed + '" pos=(' + Math.round(r.x) + ',' + Math.round(r.y) + ') id=' + (el.id||'none'));
            }
        }
    });
    return out.join('\\n');
})()""")
print(raw)

# Now try the full inspect
print("\n=== Full Inspect ===")
page = act_inspect_page()
for line in page.split('\n'):
    lower = line.lower()
    if any(w in lower for w in ['private', 'public', 'visibility', 'readme', 'gitignore', 'license', 'create', 'off', 'on', 'check']):
        print(f"  {line.strip()[:120]}")
