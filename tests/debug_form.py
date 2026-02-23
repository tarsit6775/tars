"""Debug GitHub form elements."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import _js

# 1. Find ALL buttons with aria-label or aria-pressed
print("=== Buttons with aria-label/aria-pressed ===")
raw = _js("""(function() {
    var out = [];
    document.querySelectorAll('button[aria-label], button[aria-pressed], [role=switch]').forEach(function(el) {
        var r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) {
            out.push('BUTTON | label=' + (el.getAttribute('aria-label')||'') + 
                ' | pressed=' + (el.getAttribute('aria-pressed')||'n/a') + 
                ' | text=' + (el.innerText||'').trim().substring(0,40) +
                ' | pos=(' + Math.round(r.x) + ',' + Math.round(r.y) + ')' +
                ' | id=' + (el.id||'none'));
        }
    });
    return out.join('\\n');
})()""")
print(raw)

print("\n=== Visibility Section DOM ===")
raw2 = _js("""(function() {
    // Find elements near "visibility" text
    var all = document.querySelectorAll('*');
    var vis_els = [];
    for (var i = 0; i < all.length; i++) {
        var t = (all[i].innerText||'').trim();
        if (t === 'Private' || t === 'Public') {
            var r = all[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.y > 300 && r.y < 700) {
                vis_els.push(all[i].tagName + '.' + (all[i].className||'').substring(0,30) + 
                    ' | text=' + t + 
                    ' | pos=(' + Math.round(r.x) + ',' + Math.round(r.y) + ')' +
                    ' | role=' + (all[i].getAttribute('role')||'') +
                    ' | id=' + (all[i].id||''));
            }
        }
    }
    return vis_els.join('\\n');
})()""")
print(raw2)

print("\n=== README area DOM ===")
raw3 = _js("""(function() {
    var all = document.querySelectorAll('*');
    var readme_els = [];
    for (var i = 0; i < all.length; i++) {
        var t = (all[i].innerText||'').trim();
        if (t === 'Add README' || t === 'Off' || t === 'On') {
            var r = all[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.y > 400) {
                readme_els.push(all[i].tagName + ' | text=' + t + 
                    ' | class=' + (all[i].className||'').substring(0,40) +
                    ' | pos=(' + Math.round(r.x) + ',' + Math.round(r.y) + ')' +
                    ' | role=' + (all[i].getAttribute('role')||'') +
                    ' | pressed=' + (all[i].getAttribute('aria-pressed')||'n/a') +
                    ' | label=' + (all[i].getAttribute('aria-label')||''));
            }
        }
    }
    return readme_els.join('\\n');
})()""")
print(raw3)

print("\n=== Submit button ===")
raw4 = _js("""(function() {
    var btn = document.querySelector('button[type=submit]');
    if (!btn) return 'not found';
    var r = btn.getBoundingClientRect();
    return 'text=' + (btn.innerText||'').trim() + 
        ' | disabled=' + btn.disabled + 
        ' | pos=(' + Math.round(r.x) + ',' + Math.round(r.y) + ')' +
        ' | visible=' + (r.width > 0);
})()""")
print(raw4)
