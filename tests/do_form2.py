"""Complete GitHub form using high-level browser tools."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import act_click, act_scroll, _js, _ensure, act_read_url, act_read_page, act_inspect_page

# Re-connect to Chrome
_ensure()

# Scroll to top, then down to see form
_js("window.scrollTo(0, 0)")
time.sleep(0.3)
act_scroll("down")
time.sleep(0.3)

# Step 1: Check current visibility state  
vis_text = _js("document.getElementById('visibility-anchor-button').innerText.trim()")
print(f"Current visibility: '{vis_text}'")

if vis_text != "Private":
    print("Need to select Private...")
    # Click the visibility button
    r1 = act_click("[Private]")
    print(f"  {r1}")
    time.sleep(1)
    
    # Check if dropdown opened
    page = act_read_page()
    lines = page.split('\n')
    for i, l in enumerate(lines):
        if l.strip() in ('Public', 'Private') and i < 30:
            print(f"  Option visible: '{l.strip()}'")
    
    # Use JS to click the right Private element in the dropdown
    result = _js("""(function() {
        // GitHub uses a listbox pattern - look for it
        var options = document.querySelectorAll('[role=option], [role=radio], [role=menuitemradio]');
        for (var i = 0; i < options.length; i++) {
            var t = (options[i].innerText||'').trim();
            var r = options[i].getBoundingClientRect();
            if (t.indexOf('Private') !== -1 && r.height > 0) {
                options[i].click();
                return 'Clicked option: ' + t;
            }
        }
        // Fallback: find a clickable Private element that's NOT the anchor button
        var all = document.querySelectorAll('div, span, label, li, button');
        var anchorBtn = document.getElementById('visibility-anchor-button');
        for (var j = 0; j < all.length; j++) {
            if (all[j] === anchorBtn) continue;
            var t2 = (all[j].innerText||'').trim();
            var r2 = all[j].getBoundingClientRect();
            if (t2 === 'Private' && r2.width > 0 && r2.height > 0 && r2.width < 300) {
                all[j].click();
                return 'Clicked fallback: ' + all[j].tagName + ' at y=' + Math.round(r2.y);
            }
        }
        return 'No Private option found in dropdown';
    })()""")
    print(f"  {result}")
    time.sleep(0.5)
    
    # Verify
    vis_text2 = _js("document.getElementById('visibility-anchor-button').innerText.trim()")
    print(f"  Visibility now: '{vis_text2}'")
else:
    print("Already Private!")

# Step 2: Toggle README  
print("\n--- README Toggle ---")
readme_btns = _js("""(function() {
    var btns = document.querySelectorAll('button[aria-pressed]');
    var out = [];
    btns.forEach(function(b) {
        var r = b.getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && r.y > 0) {
            // Get nearby text to identify what this toggle controls
            var prev = b.previousElementSibling;
            var parent = b.parentElement;
            var context = '';
            if (prev) context = (prev.innerText||'').trim().substring(0,30);
            if (!context && parent) context = (parent.innerText||'').trim().substring(0,30);
            out.push('pressed=' + b.getAttribute('aria-pressed') + ' context="' + context + '" pos=(' + Math.round(r.x+r.width/2) + ',' + Math.round(r.y+r.height/2) + ')');
        }
    });
    return out.join('\\n');
})()""")
print(f"  Toggle buttons: {readme_btns}")

# Click the README toggle via JS
toggle_result = _js("""(function() {
    var btns = document.querySelectorAll('button[aria-pressed]');
    for (var i = 0; i < btns.length; i++) {
        var r = btns[i].getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && r.y > 0) {
            var pressed = btns[i].getAttribute('aria-pressed');
            if (pressed === 'false') {
                btns[i].click();
                return 'Toggled on (was pressed=false)';
            }
        }
    }
    return 'No toggle found or already on';
})()""")
print(f"  Toggle result: {toggle_result}")
time.sleep(0.5)

# Verify README state  
readme_state = _js("""(function() {
    var btns = document.querySelectorAll('button[aria-pressed]');
    for (var i = 0; i < btns.length; i++) {
        var r = btns[i].getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && r.y > 0) {
            return 'pressed=' + btns[i].getAttribute('aria-pressed');
        }
    }
    return 'not found';
})()""")
print(f"  README now: {readme_state}")

# Step 3: Click Create repository
print("\n--- Create Repository ---")
r3 = act_click("Create repository")
print(f"  {r3}")
time.sleep(4)

# Step 4: Check result
print("\n--- Result ---")
print(act_read_url())
page = act_read_page()
print(page[:600])
