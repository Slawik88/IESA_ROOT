#!/usr/bin/env python3
"""
Block 7: Deep UI/UX + Business Logic Refactoring
==================================================
1. CSS Architecture — 5 new Asian themes + CSS vars sync
2. Profile theme sync — showPubProfile applies visitor theme
3. Shop/Inventory — CSS Grid 2-col mobile / 3-4col desktop
4. Pet color bug fix
5. Profile frames overlay + premium effects
6. First top-up frame
7. Cross-chat sync + duplicate buy prevention
"""
import re, sys, os

INDEX = os.path.join(os.path.dirname(__file__), "web", "index.html")
SHOP_PY = os.path.join(os.path.dirname(__file__), "api", "shop.py")
STARS_PY = os.path.join(os.path.dirname(__file__), "handlers", "stars.py")
CONFIG_PY = os.path.join(os.path.dirname(__file__), "config.py")
SHARED_PRICES = os.path.join(os.path.dirname(__file__), "shared_prices.py")

ok = 0
fail = 0

def patch(filepath, old, new, label=""):
    global ok, fail
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print(f"  [SKIP] {label or 'patch'}: pattern not found in {os.path.basename(filepath)}")
        fail += 1
        return False
    count = content.count(old)
    if count > 1:
        print(f"  [WARN] {label}: found {count} times, replacing first in {os.path.basename(filepath)}")
    content = content.replace(old, new, 1)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [OK]   {label}")
    ok += 1
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  1. CSS — Add 5 new Asian themes after sakura
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 1. CSS: 5 New Asian Themes ===")

SAKURA_CSS = 'body[data-theme="sakura"]{--bg:#0b0710;--bg2:#140e22;--bg3:#1c1430;--accent:#f472b6;--accent2:#e879b0;--gold:#f9a8d4;--card:#0f081e;--border:#481240;--text:#ffe4f5;--text2:#b04888;background:linear-gradient(-45deg,#0b0710,#130c20,#0b0710,#150d1c);background-size:400% 400%;animation:themeGradShift 16s ease infinite}'

NEW_THEMES_CSS = """body[data-theme="sakura"]{--bg:#0b0710;--bg2:#140e22;--bg3:#1c1430;--accent:#f472b6;--accent2:#e879b0;--gold:#f9a8d4;--card:#0f081e;--border:#481240;--text:#ffe4f5;--text2:#b04888;background:linear-gradient(-45deg,#0b0710,#130c20,#0b0710,#150d1c);background-size:400% 400%;animation:themeGradShift 16s ease infinite}
body[data-theme="bamboo"]{--bg:#040d04;--bg2:#081808;--bg3:#0e240e;--accent:#4ade80;--accent2:#86efac;--gold:#a3e635;--card:#051005;--border:#1a4a1a;--text:#e8f5e8;--text2:#4a9a4a;background:linear-gradient(-45deg,#040d04,#081a06,#040d04,#0a1e08);background-size:400% 400%;animation:themeGradShift 18s ease infinite}
body[data-theme="torii"]{--bg:#100202;--bg2:#1a0404;--bg3:#280808;--accent:#dc2626;--accent2:#f87171;--gold:#fbbf24;--card:#120303;--border:#5c1010;--text:#fff0f0;--text2:#b03030;background:linear-gradient(-45deg,#100202,#180606,#100202,#1c0404);background-size:400% 400%;animation:themeGradShift 14s ease infinite}
body[data-theme="lotus"]{--bg:#0f0810;--bg2:#1a101c;--bg3:#241828;--accent:#f9a8d4;--accent2:#fbcfe8;--gold:#fda4af;--card:#12091a;--border:#4a1a4a;--text:#fff0f8;--text2:#c06090;background:linear-gradient(-45deg,#0f0810,#140c18,#0f0810,#180e1c);background-size:400% 400%;animation:themeGradShift 20s ease infinite}
body[data-theme="fuji"]{--bg:#030810;--bg2:#061020;--bg3:#0a1830;--accent:#60a5fa;--accent2:#93c5fd;--gold:#e0f2fe;--card:#040a18;--border:#1a3060;--text:#e8f0ff;--text2:#5080b0;background:linear-gradient(-45deg,#030810,#061428,#030810,#081830);background-size:400% 400%;animation:themeGradShift 22s ease infinite}
body[data-theme="crane"]{--bg:#0a0a0a;--bg2:#141414;--bg3:#1e1e1e;--accent:#ef4444;--accent2:#fca5a5;--gold:#f5f5f5;--card:#0e0e0e;--border:#333;--text:#fafafa;--text2:#888;background:#0a0a0a}"""

patch(INDEX, SAKURA_CSS, NEW_THEMES_CSS, "Add 5 Asian CSS themes after sakura")


# ══════════════════════════════════════════════════════════════════════════════
#  1b. Add premium animation keyframes after themeGradShift
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 1b. CSS: Premium keyframes ===")

patch(INDEX,
    '@keyframes themeGradShift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}',
    '@keyframes themeGradShift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}\n@keyframes premiumBorder{0%{border-color:rgba(168,85,247,.6)}25%{border-color:rgba(236,72,153,.6)}50%{border-color:rgba(59,130,246,.6)}75%{border-color:rgba(250,204,21,.6)}100%{border-color:rgba(168,85,247,.6)}}\n@keyframes premiumGlow{0%,100%{box-shadow:0 0 8px rgba(168,85,247,.3)}50%{box-shadow:0 0 20px rgba(168,85,247,.5),0 0 40px rgba(168,85,247,.2)}}',
    "Add premium border/glow keyframes"
)


# ══════════════════════════════════════════════════════════════════════════════
#  1c. CSS: Grid layouts, frame overlays, premium effects
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 1c. CSS: Grid + frame overlay + premium ===")

GRID_CSS = """
/* Shop grid layouts */
.shop-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.shop-grid .scard{margin-bottom:0;flex-direction:column;align-items:stretch;min-height:120px}
.shop-grid .scard .scard-accent{position:absolute;top:0;left:0;right:0;height:3px;border-radius:12px 12px 0 0}
.shop-grid .scard .scard-icon{font-size:22px;text-align:center;margin:4px 0 2px}
.shop-grid .scard .scard-body{text-align:center}
.shop-grid .scard .scard-name{font-size:11px}
.shop-grid .scard .scard-desc{display:none}
.shop-grid .scard .scard-footer{justify-content:center}
@media(min-width:600px){.shop-grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}}
/* Inventory grid */
.inv-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.inv-grid .inv-item{flex-direction:column;align-items:stretch;padding:10px;gap:6px}
.inv-grid .inv-item .ii-emoji{font-size:20px;text-align:center}
.inv-grid .inv-item .ii-info{text-align:center}
.inv-grid .inv-item .ii-name{font-size:11px}
.inv-grid .inv-item button{width:100%;margin-top:4px}
@media(min-width:600px){.inv-grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}}
/* Scrollable subtabs */
.subtabs{overflow-x:auto;white-space:nowrap;-webkit-overflow-scrolling:touch;scrollbar-width:none;-ms-overflow-style:none}
.subtabs::-webkit-scrollbar{display:none}
/* Frame overlay on avatars */
.avatar-frame-wrap{position:relative;display:inline-block}
.avatar-frame-wrap img{border-radius:50%;display:block}
.avatar-frame-ring{position:absolute;inset:-3px;border-radius:50%;border:3px solid var(--accent);pointer-events:none}
.avatar-frame-ring.premium{animation:premiumBorder 3s linear infinite,premiumGlow 2s ease-in-out infinite}
/* Premium item effects */
.scard.premium-item{border:1.5px solid rgba(168,85,247,.5);animation:premiumGlow 3s ease-in-out infinite}
.inv-item.premium-item{border:1.5px solid rgba(168,85,247,.4);animation:premiumGlow 4s ease-in-out infinite}
/* First top-up frame badge */
.first-topup-badge{background:linear-gradient(135deg,#f59e0b,#ef4444);color:#fff;font-size:9px;padding:2px 6px;border-radius:4px;font-weight:700;display:inline-block}"""

patch(INDEX,
    '.dev-event-btn .dev-event-label{font-size:11px;color:var(--text2);margin-top:4px}',
    '.dev-event-btn .dev-event-label{font-size:11px;color:var(--text2);margin-top:4px}' + GRID_CSS,
    "Add grid layout, frame overlay, premium CSS"
)


# ══════════════════════════════════════════════════════════════════════════════
#  2. SHARED_PRICES: Add first_topup frame
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 2. shared_prices.py: first_topup frame ===")

patch(SHARED_PRICES,
    '    # Crystal-exclusive frames (price = 99999, not obtainable via mora shop)\n    ("dark_matter_frame","🌑",  "Рамка «Тёмная материя»", 99999),\n    ("herald_frame",     "📯",  "Рамка «Вестник»",        99999),\n]',
    '    # Crystal-exclusive frames (price = 99999, not obtainable via mora shop)\n    ("dark_matter_frame","🌑",  "Рамка «Тёмная материя»", 99999),\n    ("herald_frame",     "📯",  "Рамка «Вестник»",        99999),\n    # First top-up exclusive (auto-granted on first crystal purchase)\n    ("first_topup",      "🌟",  "Первое пополнение",      99999),\n]',
    "Add first_topup frame"
)


# ══════════════════════════════════════════════════════════════════════════════
#  3. CONFIG: 5 new Asian themes in PROFILE_THEMES
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 3. config.py: 5 new PROFILE_THEMES ===")

patch(CONFIG_PY,
    '''    "sakura": {
        "name": "🌸 Сакура",
        "source": "gacha",
        "price": 0,
        "tier": "legendary",
        "header": "🌸🍃 <b>ПРОФИЛЬ</b> 🍃🌸",
        "separator": "─🌸─🍃─🌸─🍃─🌸─🍃─🌸─🍃─",
        "footer": "🌸 <i>Лепестки сакуры кружатся…</i>",
    },
}''',
    '''    "sakura": {
        "name": "🌸 Сакура",
        "source": "gacha",
        "price": 0,
        "tier": "legendary",
        "header": "🌸🍃 <b>ПРОФИЛЬ</b> 🍃🌸",
        "separator": "─🌸─🍃─🌸─🍃─🌸─🍃─🌸─🍃─",
        "footer": "🌸 <i>Лепестки сакуры кружатся…</i>",
    },
    "bamboo": {
        "name": "🎋 Бамбук",
        "source": "shop",
        "price": 3500,
        "tier": "epic",
        "header": "🎋🌿 <b>ПРОФИЛЬ</b> 🌿🎋",
        "separator": "─🎋─🌿─🎋─🌿─🎋─🌿─🎋─🌿─",
        "footer": "🎋 <i>Тишина бамбуковой рощи</i>",
    },
    "torii": {
        "name": "⛩ Тории",
        "source": "shop",
        "price": 4000,
        "tier": "epic",
        "header": "⛩️🖤 <b>ПРОФИЛЬ</b> 🖤⛩️",
        "separator": "━⛩━━━━━━━━━━━━━━━━⛩━",
        "footer": "⛩️ <i>Врата в мир духов</i>",
    },
    "lotus": {
        "name": "🪷 Лотос",
        "source": "shop",
        "price": 3500,
        "tier": "epic",
        "header": "🪷✨ <b>ПРОФИЛЬ</b> ✨🪷",
        "separator": "─🪷─✨─🪷─✨─🪷─✨─🪷─✨─",
        "footer": "🪷 <i>Цветок, рождённый из тьмы</i>",
    },
    "fuji": {
        "name": "🗻 Гора Фудзи",
        "source": "shop",
        "price": 4500,
        "tier": "legendary",
        "header": "🗻❄ <b>ПРОФИЛЬ</b> ❄🗻",
        "separator": "═🗻═══════════════🗻═",
        "footer": "🗻 <i>Вершина, скрытая в облаках</i>",
    },
    "crane": {
        "name": "🏯 Журавль",
        "source": "shop",
        "price": 5000,
        "tier": "legendary",
        "header": "🏯🔴 <b>ПРОФИЛЬ</b> 🔴🏯",
        "separator": "──🏯──────────────🏯──",
        "footer": "🏯 <i>Грация и сила журавля</i>",
    },
}''',
    "Add 5 Asian themes"
)


# ══════════════════════════════════════════════════════════════════════════════
#  4. FRONTEND: Update THEME_CONF (inventory) with 5 new themes
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 4. Frontend: THEME_CONF + THEME_SHOP_CONF ===")

NEW_THEME_ENTRIES = """    bamboo:  {accent:'#4ade80',bg:'#040d04',name:'Бамбук',emoji:'🎋'},
    torii:   {accent:'#dc2626',bg:'#100202',name:'Тории',emoji:'⛩️'},
    lotus:   {accent:'#f9a8d4',bg:'#0f0810',name:'Лотос',emoji:'🪷'},
    fuji:    {accent:'#60a5fa',bg:'#030810',name:'Фудзи',emoji:'🗻'},
    crane:   {accent:'#ef4444',bg:'#0a0a0a',name:'Журавль',emoji:'🏯'},"""

# Need to find specific context for each THEME_CONF to replace the right one
# Inventory THEME_CONF is followed by "const ownedSet=new Set"
patch(INDEX,
    "    sakura:  {accent:'#f472b6',bg:'#0b0710',name:'Сакура',emoji:'🌸'},\n  };\n  const ownedSet=new Set",
    "    sakura:  {accent:'#f472b6',bg:'#0b0710',name:'Сакура',emoji:'🌸'},\n" + NEW_THEME_ENTRIES + "\n  };\n  const ownedSet=new Set",
    "Update inventory THEME_CONF"
)

# Shop THEME_SHOP_CONF — the second occurrence of sakura line + }; 
# followed by "document.getElementById('themesShopGrid')"
patch(INDEX,
    "    sakura:  {accent:'#f472b6',bg:'#0b0710',name:'Сакура',emoji:'🌸'},\n  };\n  document.getElementById('themesShopGrid')",
    "    sakura:  {accent:'#f472b6',bg:'#0b0710',name:'Сакура',emoji:'🌸'},\n" + NEW_THEME_ENTRIES + "\n  };\n  document.getElementById('themesShopGrid')",
    "Update shop THEME_SHOP_CONF"
)


# ══════════════════════════════════════════════════════════════════════════════
#  5. FRONTEND: Shop frames → grid layout + premium effects
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 5. Frontend: Frames grid layout ===")

OLD_FRAMES = """  document.getElementById('framesGrid').innerHTML=(d.frames||[]).map(f=>{
    const accent=frameAccents[f.key]||'var(--accent)';
    return `<div class="scard${f.owned?' owned':''}${f.active?' scard-active':''}" onclick="buyShopItem('frame','${f.key}')">
      <div class="scard-accent" style="background:${accent}"></div>
      <div class="scard-icon">${f.emoji}</div>
      <div class="scard-body">
        <div class="scard-name">${esc(f.name)}</div>
        <div class="cosmetic-preview">${f.emoji} <strong>${myName}</strong> <span style="color:var(--text2);font-size:11px">— рядом с именем в профиле</span></div>
        <div class="scard-footer">
          ${f.price===0?'<span class="sbadge sbadge-free">Бесплатно</span>':
            f.owned?(f.active?'<span class="sbadge sbadge-active">✓ Активна</span>':
              '<span class="sbadge sbadge-owned">✓ Надеть</span>'):
            '<span class="sbadge sbadge-price">'+f.price+' 🪙</span>'}
        </div>
      </div></div>`;
  }).join('');"""

NEW_FRAMES = """  const isPremiumFrame=k=>['dark_matter_frame','herald_frame','first_topup'].includes(k);
  document.getElementById('framesGrid').innerHTML='<div class="shop-grid">'+(d.frames||[]).filter(f=>f.price!==99999||f.owned).map(f=>{
    const accent=frameAccents[f.key]||'var(--accent)';
    const prem=isPremiumFrame(f.key);
    return `<div class="scard${f.owned?' owned':''}${f.active?' scard-active':''}${prem?' premium-item':''}" onclick="buyShopItem('frame','${f.key}')" style="position:relative">
      <div class="scard-accent" style="background:${accent}"></div>
      <div class="scard-icon">${f.emoji}</div>
      <div class="scard-body">
        <div class="scard-name">${esc(f.name)}</div>
        ${f.key==='first_topup'?'<div class="first-topup-badge">Первое пополнение</div>':''}
        <div class="scard-footer">
          ${f.price===0?'<span class="sbadge sbadge-free">Бесплатно</span>':
            f.owned?(f.active?'<span class="sbadge sbadge-active">✓ Активна</span>':
              '<span class="sbadge sbadge-owned">✓ Надеть</span>'):
            (f.price===99999?'<span class="sbadge" style="background:#7c3aed22;color:#a78bfa">💎</span>':
            '<span class="sbadge sbadge-price">'+f.price+' 🪙</span>')}
        </div>
      </div></div>`;
  }).join('')+'</div>';"""

patch(INDEX, OLD_FRAMES, NEW_FRAMES, "Frames: grid + premium + first_topup badge")


# ══════════════════════════════════════════════════════════════════════════════
#  6. FRONTEND: Themes shop — auto-fill columns for 12 themes
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 6. Frontend: Themes shop auto-fill grid ===")

patch(INDEX,
    "document.getElementById('themesShopGrid').innerHTML='<div class=\"theme-palette-grid\" style=\"grid-template-columns:repeat(4,1fr)\">'+",
    "document.getElementById('themesShopGrid').innerHTML='<div class=\"theme-palette-grid\" style=\"grid-template-columns:repeat(auto-fill,minmax(64px,1fr))\">'+",
    "Themes shop: auto-fill columns"
)


# ══════════════════════════════════════════════════════════════════════════════
#  7. FRONTEND: Potions shop → grid
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 7. Frontend: Potions grid ===")

OLD_POTIONS = """  document.getElementById('potionsSection').innerHTML=(d.potions||[]).map(p=>`
    <div class="scard" onclick="buyPotion('${p.key}','${p.price}','${p.emoji} ${p.name}')">
      <div class="scard-accent" style="background:${potAccent[p.buff_type]||'var(--accent)'}"></div>
      <div class="scard-icon">${p.emoji}</div>
      <div class="scard-body">
        <div class="scard-name">${esc(p.name)}</div>
        <div class="scard-desc">${esc(p.desc)}</div>
        <div class="scard-footer"><span class="sbadge sbadge-price">${p.price} 🪙</span></div>
      </div></div>`).join('');"""

NEW_POTIONS = """  document.getElementById('potionsSection').innerHTML='<div class="shop-grid">'+(d.potions||[]).map(p=>`
    <div class="scard" onclick="buyPotion('${p.key}','${p.price}','${p.emoji} ${p.name}')">
      <div class="scard-accent" style="background:${potAccent[p.buff_type]||'var(--accent)'}"></div>
      <div class="scard-icon">${p.emoji}</div>
      <div class="scard-body">
        <div class="scard-name">${esc(p.name)}</div>
        <div class="scard-desc">${esc(p.desc)}</div>
        <div class="scard-footer"><span class="sbadge sbadge-price">${p.price} 🪙</span></div>
      </div></div>`).join('')+'</div>';"""

patch(INDEX, OLD_POTIONS, NEW_POTIONS, "Potions: grid layout")


# ══════════════════════════════════════════════════════════════════════════════
#  8. FRONTEND: Inventory → grid for weapons/armor/junk
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 8. Frontend: Inventory grid ===")

# Weapons: wrap in grid
patch(INDEX,
    "function renderWeaponsInventory(weapons) {\n  document.getElementById('invWeaponsList').innerHTML = weapons.length ? weapons.map(i =>",
    "function renderWeaponsInventory(weapons) {\n  document.getElementById('invWeaponsList').innerHTML = weapons.length ? '<div class=\"inv-grid\">'+weapons.map(i =>",
    "Weapons inventory: open grid"
)

patch(INDEX,
    "  ).join('') : '<div style=\"color:var(--text2);text-align:center;padding:20px\">Нет оружия</div>';\n  \n  updateBatchSellUI();\n}\n\nfunction renderArmorInventory",
    "  ).join('')+'</div>' : '<div style=\"color:var(--text2);text-align:center;padding:20px\">Нет оружия</div>';\n  \n  updateBatchSellUI();\n}\n\nfunction renderArmorInventory",
    "Weapons inventory: close grid"
)

# Armor: wrap in grid
patch(INDEX,
    "function renderArmorInventory(armor) {\n  document.getElementById('invArmorList').innerHTML = armor.length ? armor.map(i =>",
    "function renderArmorInventory(armor) {\n  document.getElementById('invArmorList').innerHTML = armor.length ? '<div class=\"inv-grid\">'+armor.map(i =>",
    "Armor inventory: open grid"
)

patch(INDEX,
    "  ).join('') : '<div style=\"color:var(--text2);text-align:center;padding:20px\">Нет брони</div>';\n  \n  updateBatchSellUI();\n}\n\nfunction renderPotionsInventory",
    "  ).join('')+'</div>' : '<div style=\"color:var(--text2);text-align:center;padding:20px\">Нет брони</div>';\n  \n  updateBatchSellUI();\n}\n\nfunction renderPotionsInventory",
    "Armor inventory: close grid"
)

# Junk: wrap in grid
patch(INDEX,
    "function renderJunkInventory(junkItems) {\n  document.getElementById('invJunkList').innerHTML = junkItems.length ? junkItems.map(i =>",
    "function renderJunkInventory(junkItems) {\n  document.getElementById('invJunkList').innerHTML = junkItems.length ? '<div class=\"inv-grid\">'+junkItems.map(i =>",
    "Junk inventory: open grid"
)

patch(INDEX,
    """  ).join('') : '<div style="color:var(--text2);text-align:center;padding:20px">\U0001faa8 Нет хлама — вам везёт!</div>';
  
  updateBatchSellUI();
}

function canSelectItem""",
    """  ).join('')+'</div>' : '<div style="color:var(--text2);text-align:center;padding:20px">\U0001faa8 Нет хлама — вам везёт!</div>';
  
  updateBatchSellUI();
}

function canSelectItem""",
    "Junk inventory: close grid"
)


# ══════════════════════════════════════════════════════════════════════════════
#  9. FRONTEND: Profile theme sync — apply viewed user's theme
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 9. Frontend: Profile theme sync ===")

# Add _savedTheme variable and save theme before opening profile
patch(INDEX,
    """async function showPubProfile(userId){
  if(!userId) return;
  const overlay = document.getElementById('pubProfileOverlay');
  document.getElementById('pubProfileContent').style.display='none';
  document.getElementById('pubProfileLoading').style.display='block';
  document.getElementById('pubProfileLoading').textContent='⏳ Загрузка…';
  overlay.classList.add('open');""",

    """let _savedTheme = null;
async function showPubProfile(userId){
  if(!userId) return;
  _savedTheme = document.body.dataset.theme || '';
  const overlay = document.getElementById('pubProfileOverlay');
  document.getElementById('pubProfileContent').style.display='none';
  document.getElementById('pubProfileLoading').style.display='block';
  document.getElementById('pubProfileLoading').textContent='⏳ Загрузка…';
  overlay.classList.add('open');""",
    "Profile sync: save theme"
)

# Restore theme on close
patch(INDEX,
    """function closePubProfile(){
  document.getElementById('pubProfileOverlay').classList.remove('open');
}""",

    """function closePubProfile(){
  document.getElementById('pubProfileOverlay').classList.remove('open');
  if(_savedTheme!==null){applyTheme(_savedTheme);_savedTheme=null;}
}""",
    "Profile sync: restore theme on close"
)

# Apply the viewed user's theme after profile content is displayed
patch(INDEX,
    "    document.getElementById('pubProfileLoading').style.display='none';\n    document.getElementById('pubProfileContent').style.display='block';\n    document.getElementById('pubAvatar')",
    "    document.getElementById('pubProfileLoading').style.display='none';\n    document.getElementById('pubProfileContent').style.display='block';\n    // Apply the viewed user's theme\n    if(p.active_theme) applyTheme(p.active_theme);\n    document.getElementById('pubAvatar')",
    "Profile sync: apply viewed user's theme"
)


# ══════════════════════════════════════════════════════════════════════════════
#  10. FRONTEND: _FRAME_NAMES — add new frames
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 10. Frontend: _FRAME_NAMES ===")

patch(INDEX,
    "    const _FRAME_NAMES={'default':'🔰 Стандарт','warrior':'⚔️ Воин','king':'👑 Король','moon':'🌙 Ночной','fire':'🔥 Огненный','diamond':'💎 Алмазный','star':'⭐ Звёздный','sakura':'🌸 Сакура','abyss':'🌀 Бездна','fatui':'⚡ Предвестник','angel':'🕊️ Крылья ветра','champion':'🏆 Чемпион','celestia':'🏰 Целестия'};",
    "    const _FRAME_NAMES={'default':'🔰 Стандарт','warrior':'⚔️ Воин','king':'👑 Король','moon':'🌙 Ночной','fire':'🔥 Огненный','diamond':'💎 Алмазный','star':'⭐ Звёздный','sakura':'🌸 Сакура','abyss':'🌀 Бездна','fatui':'⚡ Предвестник','angel':'🕊️ Крылья ветра','champion':'🏆 Чемпион','celestia':'🏰 Целестия','dark_matter_frame':'🌑 Тёмная материя','herald_frame':'📯 Вестник','first_topup':'🌟 Первое пополнение'};",
    "Update _FRAME_NAMES with new frames"
)


# ══════════════════════════════════════════════════════════════════════════════
#  11. FRONTEND: Update frameAccents map
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 11. Frontend: frameAccents map ===")

patch(INDEX,
    """  const frameAccents={
    'default':'#6b7280','warrior':'#dc2626','king':'#d97706','moon':'#4338ca',
    'fire':'#ea580c','diamond':'#06b6d4','star':'#fbbf24','sakura':'#fb7185',
    'abyss':'#1e1b4b','fatui':'#f59e0b','angel':'#7dd3fc','champion':'#f97316',
    'celestia':'#8b5cf6',
  };""",

    """  const frameAccents={
    'default':'#6b7280','warrior':'#dc2626','king':'#d97706','moon':'#4338ca',
    'fire':'#ea580c','diamond':'#06b6d4','star':'#fbbf24','sakura':'#fb7185',
    'abyss':'#1e1b4b','fatui':'#f59e0b','angel':'#7dd3fc','champion':'#f97316',
    'celestia':'#8b5cf6','dark_matter_frame':'#7c3aed','herald_frame':'#f59e0b',
    'first_topup':'#f59e0b',
  };""",
    "frameAccents: add new frame colors"
)


# ══════════════════════════════════════════════════════════════════════════════
#  12. FRONTEND: buyShopItem — prevent duplicate purchases
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 12. Frontend: buyShopItem duplicate guard ===")

OLD_BUY = """async function buyShopItem(type, key){
  let price=0, label=key;
  if(shopData){
    if(type==='frame'){const f=(shopData.frames||[]).find(x=>x.key===key);if(f){price=f.price;label=f.emoji+' '+f.name;}}
    else if(type==='cosmetic'){const c=(shopData.cosmetics||[]).find(x=>x.key===key);if(c){price=c.price;label=c.emoji+' '+c.name;}}
    else if(type==='vip'){price=2000;label='👑 VIP статус';}
  }"""

NEW_BUY = """async function buyShopItem(type, key){
  let price=0, label=key;
  if(shopData){
    if(type==='frame'){
      const f=(shopData.frames||[]).find(x=>x.key===key);
      if(f){
        if(f.owned){
          // Already owned — just equip
          try{
            const r=await api('/api/shop/buy','POST',{chat_id:chatId,item_type:'frame',item_key:key,equip:true});
            toast(r.equipped?'✅ Рамка активирована':'✅ Уже куплено','success');
            shopData=null; await loadShop(); renderInvFramesCosmetics();
          }catch(e){toast('❌ '+e.message,'error');}
          return;
        }
        if(f.price===99999){toast('💎 Эта рамка недоступна для покупки','info');return;}
        price=f.price;label=f.emoji+' '+f.name;
      }
    }
    else if(type==='cosmetic'){
      const c=(shopData.cosmetics||[]).find(x=>x.key===key);
      if(c){
        if(c.owned){toast('✅ Эта косметика уже куплена','info');return;}
        price=c.price;label=c.emoji+' '+c.name;
      }
    }
    else if(type==='vip'){price=2000;label='👑 VIP статус';}
  }"""

patch(INDEX, OLD_BUY, NEW_BUY, "buyShopItem: duplicate purchase guard")


# ══════════════════════════════════════════════════════════════════════════════
#  13. BACKEND: Fix duplicate purchase — cross-chat ownership check
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 13. Backend: Cross-chat ownership check ===")

patch(SHOP_PY,
    """    # Check ownership (frame/cosmetic only) — equip if already owned
    if item_type in ("frame", "cosmetic"):
        already_owned = await has_shop_item(uid, chat_id, item_type, item_key)""",

    """    # Check ownership (frame/cosmetic only) — equip if already owned
    # Check both per-chat and global (chat_id=0) ownership
    if item_type in ("frame", "cosmetic"):
        already_owned = await has_shop_item(uid, chat_id, item_type, item_key)
        if not already_owned:
            already_owned = await has_shop_item(uid, 0, item_type, item_key)""",
    "Fix: check global ownership for frames/cosmetics"
)


# ══════════════════════════════════════════════════════════════════════════════
#  14. BACKEND: Store frames/cosmetics globally (chat_id=0)
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 14. Backend: Store frames/cosmetics globally ===")

patch(SHOP_PY,
    """    if item_type in ("frame", "cosmetic"):
        await buy_shop_item(uid, chat_id, item_type, item_key)
        if item_type == "frame" and equip:
            await set_top_frame(uid, chat_id, item_key)""",

    """    if item_type in ("frame", "cosmetic"):
        await buy_shop_item(uid, chat_id, item_type, item_key)
        # Also track globally so ownership works cross-chat
        if chat_id != 0:
            try:
                await buy_shop_item(uid, 0, item_type, item_key)
            except Exception:
                pass  # ignore duplicate key on global row
        if item_type == "frame" and equip:
            await set_top_frame(uid, chat_id, item_key)""",
    "Store frames/cosmetics globally (chat_id=0)"
)


# ══════════════════════════════════════════════════════════════════════════════
#  15. BACKEND: Pet color — store globally
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 15. Backend: Pet color cross-chat sync ===")

patch(SHOP_PY,
    """        # Track ownership in shop_items so the color persists even after switching
        await buy_shop_item(uid, chat_id, "pet_color", item_key)""",

    """        # Track ownership globally (chat_id=0) so color persists cross-chat
        await buy_shop_item(uid, 0, "pet_color", item_key)
        if chat_id != 0:
            try:
                await buy_shop_item(uid, chat_id, "pet_color", item_key)
            except Exception:
                pass""",
    "Pet color: store ownership globally"
)


# ══════════════════════════════════════════════════════════════════════════════
#  16. BACKEND: Theme — store globally for cross-chat
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 16. Backend: Theme cross-chat sync ===")

patch(SHOP_PY,
    """    elif item_type == "profile_theme":
        from database.db import add_user_theme, set_active_theme
        await add_user_theme(uid, chat_id, item_key, source="shop")
        if equip:
            await set_active_theme(uid, chat_id, item_key)""",

    """    elif item_type == "profile_theme":
        from database.db import add_user_theme, set_active_theme
        await add_user_theme(uid, chat_id, item_key, source="shop")
        # Store globally for cross-chat ownership
        if chat_id != 0:
            try:
                await add_user_theme(uid, 0, item_key, source="shop")
            except Exception:
                pass
        if equip:
            await set_active_theme(uid, chat_id, item_key)""",
    "Theme purchase: store globally"
)

# Fix theme ownership query to check ANY chat_id
patch(SHOP_PY,
    '''            _theme_row = await _dbt.fetchone(
                "SELECT 1 FROM user_themes WHERE user_id=? AND theme_key=?",
                (uid, item_key),
            )''',
    '''            _theme_row = await _dbt.fetchone(
                "SELECT 1 FROM user_themes WHERE user_id=? AND theme_key=? LIMIT 1",
                (uid, item_key),
            )''',
    "Theme ownership: add LIMIT 1 for any-chat check"
)


# ══════════════════════════════════════════════════════════════════════════════
#  17. BACKEND: First top-up frame on Telegram Stars payment
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 17. Backend: First top-up frame ===")

patch(STARS_PY,
    """    new_balance = await add_crystals(user_id, crystals)
    await log_stars_purchase(user_id, stars, crystals, pack_key, charge_id)

    await msg.answer(""",

    """    new_balance = await add_crystals(user_id, crystals)
    await log_stars_purchase(user_id, stars, crystals, pack_key, charge_id)

    # First top-up: auto-grant exclusive frame
    first_topup_msg = ""
    try:
        from database.db import has_shop_item, buy_shop_item
        has_first = await has_shop_item(user_id, 0, "frame", "first_topup")
        if not has_first:
            await buy_shop_item(user_id, 0, "frame", "first_topup")
            first_topup_msg = "\\n🌟 <b>Бонус первого пополнения!</b> Получена эксклюзивная рамка «Первое пополнение»!"
    except Exception:
        pass

    await msg.answer(""",
    "First top-up: auto-grant frame"
)

patch(STARS_PY,
    '        f"💎 Баланс: <b>{new_balance}</b>\\n\\n"\n        f"Тратьте кристаллы в Mini App → Магазин → Кристаллы."',
    '        f"💎 Баланс: <b>{new_balance}</b>"\n        f"{first_topup_msg}\\n\\n"\n        f"Тратьте кристаллы в Mini App → Магазин → Кристаллы."',
    "First top-up: include in payment success message"
)


# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"Block 7 refactoring complete: {ok} OK, {fail} SKIP")
print(f"{'='*60}")
