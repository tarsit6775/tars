"""Quick script to complete the GitHub repo creation form."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hands.browser import act_click, act_inspect_page, act_read_page, _js

# Step 1: Check current state
print("=== Current Page State ===")
page = act_inspect_page()
print(page[:1500])

# Step 2: Click Private visibility button
print("\n=== Clicking Private ===")
r = act_click("Private")
print(r)
time.sleep(1)

# Step 3: Check if dropdown opened, click Private option if needed
page2 = act_read_page()
if "Public" in page2[:500] and "Private" in page2[:500]:
    print("Dropdown opened - clicking Private option...")
    # Find the radio/option elements
    options = _js("""(function() {
        var els = document.querySelectorAll('[role=option], [role=radio], [role=menuitemradio], label');
        var out = [];
        els.forEach(function(el) {
            var r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                var t = (el.innerText||'').trim().substring(0,50);
                if (t.indexOf('Private') !== -1 || t.indexOf('private') !== -1) {
                    out.push(el.tagName + '|' + t + '|' + (el.id||'noid'));
                }
            }
        });
        return out.join('\\n');
    })()""")
    print(f"Private elements: {options}")
    
    # Click "Private" text again (should hit the option in the dropdown)
    r2 = act_click("Private")
    print(f"Click result: {r2}")
    time.sleep(0.5)

# Step 4: Check state again  
print("\n=== After Private Click ===")
page3 = act_inspect_page()
for line in page3.split('\n'):
    if any(w in line.lower() for w in ['rivate', 'isib', 'readme', 'button', 'check']):
        print(f"  {line.strip()}")
