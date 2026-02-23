"""Check GitHub form state: errors, submit button, visibility."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import _js, _ensure

_ensure()

# 1. Form errors
errors = _js("""(function() {
    var out = [];
    var errs = document.querySelectorAll('[role=alert], .flash-error, .color-fg-danger, .FormControl-inlineValidation--error');
    errs.forEach(function(e) {
        var r = e.getBoundingClientRect();
        if (r.height > 0) out.push('ERR: ' + (e.innerText||'').trim().substring(0,120));
    });
    return out.length ? out.join('\\n') : 'No errors found';
})()""")
print("=== ERRORS ===")
print(errors)

# 2. Submit button
submit = _js("""(function() {
    var btn = document.querySelector('button[type=submit]');
    if (!btn) return 'No submit button found';
    return 'disabled=' + btn.disabled + ' text="' + btn.innerText.trim() + '" classes=' + btn.className;
})()""")
print("\n=== SUBMIT BUTTON ===")
print(submit)

# 3. Visibility state
vis = _js("""(function() {
    var anchor = document.getElementById('visibility-anchor-button');
    if (!anchor) return 'No visibility anchor found';
    var out = 'text="' + anchor.innerText.trim() + '" expanded=' + anchor.getAttribute('aria-expanded');
    // Check hidden inputs
    var hiddens = document.querySelectorAll('input[name*=visib], input[name*=private]');
    hiddens.forEach(function(h) {
        out += '\\nHIDDEN: name=' + h.name + ' value=' + h.value;
    });
    return out;
})()""")
print("\n=== VISIBILITY ===")
print(vis)

# 4. All form data
formdata = _js("""(function() {
    var form = document.querySelector('form');
    if (!form) return 'No form found';
    var out = 'action=' + form.action + '\\nmethod=' + form.method + '\\n';
    var inputs = form.querySelectorAll('input, select, textarea');
    inputs.forEach(function(inp) {
        if (inp.type === 'hidden' || inp.value) {
            out += inp.type + ' name="' + inp.name + '" value="' + (inp.value||'').substring(0,60) + '"\\n';
        }
    });
    return out;
})()""")
print("\n=== FORM DATA ===")
print(formdata)

# 5. README toggle
readme = _js("""(function() {
    var btns = document.querySelectorAll('button[aria-pressed]');
    var out = [];
    btns.forEach(function(b) {
        var r = b.getBoundingClientRect();
        out.push('pressed=' + b.getAttribute('aria-pressed') + ' label="' + (b.getAttribute('aria-label')||'') + '" visible=' + (r.height>0));
    });
    return out.join('\\n');
})()""")
print("\n=== TOGGLES ===")
print(readme)
