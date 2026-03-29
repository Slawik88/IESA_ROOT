import re

with open(r'g:\IESA_ROOT\PredvestnikBot\web\index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Fix guide nav buttons: remove inline styles, add btn-ghost class
html = re.sub(
    r'class="btn btn-sm" style="background:var\(--bg3\);color:var\(--text2\);font-size:11px" (onclick="showGuideSection[^"]+?")',
    r'class="btn btn-ghost btn-sm" \1',
    html
)
# First guide button active state
html = html.replace(
    'class="btn btn-sm" style="background:var(--accent);color:#fff;font-size:11px" onclick="showGuideSection',
    'class="btn btn-primary btn-sm" onclick="showGuideSection'
)
# Remove inline style from guide-nav div
html = html.replace(
    'class="guide-nav" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px"',
    'class="guide-nav"'
)

# Replace gacha show-rates button inline style
html = html.replace(
    'class="btn" style="width:100%;background:var(--bg3);color:var(--text2);font-size:11px;border:1px solid var(--border)" onclick="showGachaRates()"',
    'class="btn btn-ghost" onclick="showGachaRates()"'
)

# Replace batch sell select-all inline style buttons
html = html.replace(
    'class="btn btn-sm" style="background:var(--bg3);color:var(--text2)" onclick="selectAllItems()"',
    'class="btn btn-ghost btn-sm" onclick="selectAllItems()"'
)
html = html.replace(
    'class="btn btn-sm" style="background:var(--bg3);color:var(--text2)" onclick="clearSelection()"',
    'class="btn btn-ghost btn-sm" onclick="clearSelection()"'
)

with open(r'g:\IESA_ROOT\PredvestnikBot\web\index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('Done')
