"""Find and click the actual Create repository button."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import _js, _ensure, act_read_url, _cdp_click_at

_ensure()

# Find ALL buttons with "Create" in text
buttons = _js("""(function() {
    var out = [];
    var btns = document.querySelectorAll('button, [role=button], a.btn, input[type=submit]');
    btns.forEach(function(b) {
        var t = (b.innerText||b.value||'').trim();
        if (t.toLowerCase().indexOf('create') !== -1) {
            var r = b.getBoundingClientRect();
            out.push('tag=' + b.tagName + ' type=' + b.type + ' text="' + t.substring(0,50) + '" disabled=' + b.disabled + ' pos=(' + Math.round(r.x+r.width/2) + ',' + Math.round(r.y+r.height/2) + ') visible=' + (r.height>0) + ' classes=' + b.className.substring(0,80));
        }
    });
    return out.join('\\n') || 'No create buttons found';
})()""")
print("=== CREATE BUTTONS ===")
print(buttons)

# Scroll down to make sure button is visible
_js("window.scrollTo(0, document.body.scrollHeight)")
time.sleep(0.5)

buttons2 = _js("""(function() {
    var out = [];
    var btns = document.querySelectorAll('button, [role=button], a.btn');
    btns.forEach(function(b) {
        var t = (b.innerText||'').trim();
        if (t.toLowerCase().indexOf('create') !== -1) {
            var r = b.getBoundingClientRect();
            out.push('text="' + t.substring(0,50) + '" pos=(' + Math.round(r.x+r.width/2) + ',' + Math.round(r.y+r.height/2) + ') visible=' + (r.height>0 && r.y>0));
        }
    });
    return out.join('\\n') || 'No create buttons found';
})()""")
print("\n=== AFTER SCROLL ===")
print(buttons2)

# Try direct JS click on create repo button
click_result = _js("""(function() {
    var btns = document.querySelectorAll('button, [role=button]');
    for (var i = 0; i < btns.length; i++) {
        var t = (btns[i].innerText||'').trim();
        if (t === 'Create repository') {
            btns[i].click();
            return 'JS clicked "Create repository" button';
        }
    }
    return 'Button not found';
})()""")
print("\n=== JS CLICK ===")
print(click_result)
time.sleep(5)

print("\n=== URL AFTER CLICK ===")
print(act_read_url())
