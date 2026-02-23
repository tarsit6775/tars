"""Check GitHub form elements."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import _js

# Check what the README toggle looks like
raw = _js("""(function() {
    var out = [];
    // Look for all toggle/switch/checkbox-like elements
    var els = document.querySelectorAll('input[type=checkbox], [role=switch], [role=checkbox], button[aria-pressed], [class*=toggle], [class*=Toggle]');
    els.forEach(function(el) {
        var r = el.getBoundingClientRect();
        var vis = r.width > 0 && r.height > 0;
        var label = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.name || el.id || '';
        var checked = el.checked || el.getAttribute('aria-checked') || el.getAttribute('aria-pressed') || 'n/a';
        var txt = (el.innerText||'').trim().substring(0,30);
        out.push(el.tagName + ' | id=' + (el.id||'none') + ' | label=' + label + ' | checked=' + checked + ' | visible=' + vis + ' | text=' + txt);
    });
    // Also look for the README-related area
    var body = document.body.innerHTML;
    var readmeIdx = body.indexOf('README');
    if (readmeIdx > -1) {
        var snippet = body.substring(Math.max(0, readmeIdx-200), readmeIdx+300);
        // Extract relevant tags
        var m = snippet.match(/<(input|button|label|div|span)[^>]*>/g);
        if (m) out.push('\\nREADME context tags: ' + m.slice(0,10).join(' '));
    }
    return out.join('\\n');
})()""")
print("Toggle elements:")
print(raw)

print("\n---")
# Check all visible checkboxes/switches
raw2 = _js("""(function() {
    var checkboxes = document.querySelectorAll('input[type=checkbox]');
    var out = [];
    checkboxes.forEach(function(el) {
        var r = el.getBoundingClientRect();
        out.push('checkbox id=' + (el.id||'none') + ' name=' + (el.name||'none') + ' checked=' + el.checked + ' vis=' + (r.width>0));
    });
    return out.join('\\n');
})()""")
print("All checkboxes:")
print(raw2)
