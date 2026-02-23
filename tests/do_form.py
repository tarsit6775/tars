"""Complete GitHub form step by step."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import _js, _cdp_click_at, _human_pre_click, act_read_url, act_read_page

# Step 1: Click the Private button to open dropdown
print("=== Step 1: Open visibility dropdown ===")
_human_pre_click(1183, 148)
_cdp_click_at(1183, 148)
time.sleep(1)

# Check what appeared
dropdown = _js("""(function() {
    var items = document.querySelectorAll('[role=listbox] [role=option], [role=radio], [role=radiogroup] label, [role=radiogroup] div');
    var out = [];
    items.forEach(function(el) {
        var r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) {
            out.push(el.tagName + '|' + (el.innerText||'').trim().substring(0,30) + '|y=' + Math.round(r.y));
        }
    });
    return out.join('\\n');
})()""")
print(f"Dropdown items: {dropdown}")

# Find and click Private option
print("\n=== Step 2: Select Private ===")
r = _js("""(function() {
    // Try to find Private text element to click
    var all = document.querySelectorAll('*');
    var privateEls = [];
    for (var i = 0; i < all.length; i++) {
        var t = (all[i].innerText||'').trim();
        var r = all[i].getBoundingClientRect();
        if (t === 'Private' && r.width > 0 && r.height > 0 && r.width < 300) {
            privateEls.push({el: all[i], y: r.y, x: r.x + r.width/2, cy: r.y + r.height/2, tag: all[i].tagName});
        }
    }
    // Sort by y — the dropdown option should be below the button
    privateEls.sort(function(a,b) { return a.y - b.y; });
    if (privateEls.length >= 2) {
        // Second one is likely the dropdown option
        privateEls[1].el.click();
        return 'Clicked Private option at y=' + privateEls[1].y;
    } else if (privateEls.length === 1) {
        privateEls[0].el.click();
        return 'Clicked only Private at y=' + privateEls[0].y;
    }
    return 'No Private found';
})()""")
print(f"  Result: {r}")
time.sleep(0.5)

# Check visibility state
vis = _js("""(function() {
    var btn = document.getElementById('visibility-anchor-button');
    if (!btn) return 'button not found';
    return 'text=' + (btn.innerText||'').trim() + ' y=' + Math.round(btn.getBoundingClientRect().y);
})()""")
print(f"  Visibility button now: {vis}")

# Step 3: Click README toggle
print("\n=== Step 3: Toggle README ===")
toggle = _js("""(function() {
    var btns = document.querySelectorAll('button[aria-pressed]');
    var out = [];
    btns.forEach(function(b) {
        var r = b.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) {
            out.push('pressed=' + b.getAttribute('aria-pressed') + ' pos=(' + Math.round(r.x + r.width/2) + ',' + Math.round(r.y + r.height/2) + ') label=' + (b.getAttribute('aria-label')||'none'));
        }
    });
    return out.join('\\n');
})()""")
print(f"  Toggle buttons: {toggle}")

# Click the first aria-pressed=false toggle (should be README)
_human_pre_click(1251, 229)
_cdp_click_at(1251, 229)
time.sleep(0.5)

toggle2 = _js("""(function() {
    var btns = document.querySelectorAll('button[aria-pressed]');
    var out = [];
    btns.forEach(function(b) {
        var r = b.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) {
            out.push('pressed=' + b.getAttribute('aria-pressed'));
        }
    });
    return out.join(', ');
})()""")
print(f"  After click: {toggle2}")

# Step 4: Click Create repository
print("\n=== Step 4: Create Repository ===")
_human_pre_click(1171, 793)
_cdp_click_at(1171, 793)
time.sleep(3)

# Step 5: Check result
print("\n=== Result ===")
url = act_read_url()
print(url)
page = act_read_page()
print(page[:800])
