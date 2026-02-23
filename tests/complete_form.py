"""Complete the GitHub repo creation form."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hands.browser import act_click, act_inspect_page, act_read_page, _js, act_read_url

# Step 1: Click Private in the visibility dropdown
print("=== Step 1: Select Private Visibility ===")
# First check if dropdown is open
page = act_read_page()
has_public_option = "Public\n" in page[:1000]
if has_public_option:
    print("Dropdown is open. Clicking Private option...")
    # Click the Private radio option 
    r = _js("""(function() {
        var els = document.querySelectorAll('[role=option], [role=radio], [role=menuitemradio], label, div, span');
        for (var i = 0; i < els.length; i++) {
            var t = (els[i].innerText||'').trim();
            var r = els[i].getBoundingClientRect();
            if (t === 'Private' && r.width > 0 && r.height > 0 && r.y < 600) {
                els[i].click();
                return 'Clicked Private at y=' + r.y;
            }
        }
        return 'Not found';
    })()""")
    print(f"  Result: {r}")
    time.sleep(0.5)
else:
    print("Dropdown not open. Clicking Private button...")
    print(act_click("Private"))
    time.sleep(1)
    # Try clicking Private option
    page2 = act_read_page()
    if "Public\n" in page2[:1000]:
        r = act_click("Private")
        print(f"  Clicked Private option: {r}")
        time.sleep(0.5)

# Step 2: Toggle README on
print("\n=== Step 2: Toggle README On ===")
readme_state = _js("""(function() {
    var btn = document.querySelector('button[aria-label="add-readme"]');
    if (!btn) return 'not found';
    return 'pressed=' + btn.getAttribute('aria-pressed');
})()""")
print(f"  README state: {readme_state}")
if "false" in str(readme_state):
    r = _js("""(function() {
        var btn = document.querySelector('button[aria-label="add-readme"]');
        if (btn) { btn.click(); return 'clicked'; }
        return 'not found';
    })()""")
    print(f"  Click result: {r}")
    time.sleep(0.5)
    new_state = _js("""(function() {
        var btn = document.querySelector('button[aria-label="add-readme"]');
        if (!btn) return 'not found';
        return 'pressed=' + btn.getAttribute('aria-pressed');
    })()""")
    print(f"  New README state: {new_state}")

# Step 3: Click Create repository
print("\n=== Step 3: Create Repository ===")
r = act_click("Create repository")
print(f"  Click result: {r}")
time.sleep(3)

# Step 4: Check result
print("\n=== Result ===")
print(act_read_url())
page = act_read_page()
print(page[:500])
