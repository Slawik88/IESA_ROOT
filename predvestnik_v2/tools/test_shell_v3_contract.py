#!/usr/bin/env python3
"""Static contract for the shell-v3 interface: flag wiring, tap targets, safe animation, honest copy."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI/static"
css = (STATIC / "shell-v3.css").read_text(encoding="utf-8")
home = (STATIC / "app.15.js").read_text(encoding="utf-8")
hub = (STATIC / "app.04.js").read_text(encoding="utf-8")
index = (STATIC / "index.html").read_text(encoding="utf-8")
app = (STATIC / "app.01.js").read_text(encoding="utf-8")
flags = (ROOT / "infrastructure/repositories/system_flags.py").read_text(encoding="utf-8")

# Every game shown in the hub is controlled by a real server flag.
hub_flags = re.findall(r"flag:'([a-z0-9_]+)'", hub.split("const _V3_GAMES = [",1)[1].split("];",1)[0])
assert {"game_mafia_v1","game_rhythm_v2","game_minesweeper_v2"} <= set(hub_flags), hub_flags
for key in hub_flags:
    assert f'("{key}"' in flags, f"unknown flag {key}"

# Primary controls keep a 44px tap target.
for selector in (".v3-pill", ".v3-link", ".v3-row", ".nb"):
    block = re.search(re.escape(selector) + r" \{[^}]*\}", css)
    assert block and re.search(r"(min-)?(height|width): 4[4-9]px|min-height: (5\d|7\d)px", block.group(0)), selector

# Motion budget: only transform/opacity are animated or transitioned in the new layer.
for line in css.splitlines():
    if "transition:" in line:
        assert not re.search(r"transition:[^;]*\b(width|height|margin|padding|top|left)\b", line), line
assert "@keyframes v3rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }" in css
assert "animation: v3rise .28s var(--v3-ease) backwards" in css
assert "backdrop-filter" not in css.split(".nav {", 1)[1].split("}", 1)[0]

# Quest reward claim: optimistic, but a failed balance refresh must not roll the reward back.
claim = home[home.index("function v3ClaimQuestReward"):home.index("// Баланс на профиле")]
assert "_v3RefreshBalance();" in claim and ".catch(e => { _v3Quests = before" in claim
assert "data-kind" in (STATIC / "app.16.js").read_text(encoding="utf-8") and "onclick=\"v3ClaimQuestReward('${" not in home

# TMA shell: version-gated chrome colours, haptics throttled, text selection restored for inputs.
assert "isVersionAtLeast(since)" in home and "'7.10'" in home and "_hapticAt" in home
assert "disableVerticalSwipes" in home
assert "overscroll-behavior: none" in css and "touch-action: manipulation" in css
assert "input, textarea" in css and "user-select: text" in css

# Navigation and honest copy.
assert index.count('type="button" class="nb') == 11
assert index.index('id="cc-exchange-v1"') < index.index('class="nb" data-page="pets"'), "exchange stays in the first visible dock destinations"
assert ':not([hidden])' in app, "a dock tab hidden by its feature flag must not keep the active highlight"
for page in ('looks', 'chests', 'top'):
    assert f'data-wn-page="{page}"' in index
assert 'role="status"' in index and 'id="dev-notice"' not in index, "the player shell has no «in development» notice"
assert 'id="app-update-banner"' in index and "applyAppUpdate()" in index
assert "event?.type === 'app_version'" in app and "event?.type === 'data_changed'" in app
assert "event?.type === 'notification_pending'" in app and "queueDynamicRefresh" in app
assert "setInterval(refreshCurrBar" not in app, "dynamic player data must stay push-driven"
assert "bottom: calc(var(--v3-dock-clear) - 22px + var(--v3-safe-b))" in css and "@keyframes appUpdateRise" in css
assert "/vip/" not in home and "Магазине" not in (STATIC / "app.02.js").read_text(encoding="utf-8").split("function showCurrModal", 1)[1][:2500]
# Skin tiers: server contract, cumulative fx classes, motion budget in the tier stylesheet.
skins_src = (ROOT / "core/skins_v3.py").read_text(encoding="utf-8")
assert 'TIERS: Final = ("D", "C", "B", "A", "S", "SS", "SSS")' in skins_src or 'TIERS = ("D", "C", "B", "A", "S", "SS", "SSS")' in skins_src
fx = (STATIC / "fx-tiers-v3.css").read_text(encoding="utf-8")
for level in range(1, 8):
    assert f"fx-{level}" in fx or level == 1, level
controller = (STATIC / "app.18.js").read_text(encoding="utf-8")
assert "fx-${i}" in controller and "v3_fx_cap" in controller and "visibilitychange" in controller
assert not re.search(r"classList\.add\([`'\"]skin-", controller), "tier classes must not use the skin- prefix"
def keyframe_props(css: str) -> dict[str, set[str]]:
    result, pos = {}, 0
    while (start := css.find("@keyframes", pos)) != -1:
        name = css[start:].split("{", 1)[0].split()[1]
        depth, i = 0, css.index("{", start)
        for j in range(i, len(css)):
            depth += css[j] == "{"
            depth -= css[j] == "}"
            if depth == 0:
                break
        result[name] = set(re.findall(r"([a-z-]+)\s*:", css[i + 1:j]))
        pos = j
    return result


appearance_files = ("appearance-v3.css", "appearance-ring-v3.css", "appearance-stage-v3.css", "skin-signatures-v3.css", "skin-signatures-2-v3.css", "skins-exclusive-v3.css", "skin-sig-a-v3.css", "skin-sig-b-v3.css", "skin-sig-c-v3.css", "skin-sig-d-v3.css", "looks-v3.css", "collect-v3.css", "toast-v3.css", "toast-gift-v3.css")
appearance = "".join((STATIC / name).read_text(encoding="utf-8") for name in appearance_files)
home_css = (STATIC / "shell-v3-home.css").read_text(encoding="utf-8")
for sheet in (fx, appearance, home_css, css):
    for name, props in keyframe_props(sheet).items():
        assert props <= {"transform", "opacity"}, (name, props)   # без исключений: блик по буквам тоже едет через transform (окно .ap-gl), фон текста не анимируется
assert len(keyframe_props(fx)) >= 1 and len(keyframe_props(appearance)) >= 12   # свет страницы рисует app.18.js на canvas: в fx-tiers-v3.css остался боковой переход
# Glint: the window (.ap-gl) carries a white copy of the text and moves by transform only, so the main thread never repaints it (it used to move the text's background:
# up to 55 main-thread frames a second, which on a phone lagged the whole interface). Names get the markup from apName(), the big S+ titles from v3GlintMark().
assert {"apgl-w", "apgl-t"} <= set(keyframe_props(appearance)) and not ({"apglint", "v3glint"} & set(keyframe_props(appearance) | keyframe_props(fx)))
assert not re.search(r"apglint|v3glint|animationend", appearance + fx + home_css + controller), "the old background glint and its restart-by-script are gone"
for rule in re.findall(r"([^{}]*\.ap-gl[^{}]*)\{[^{}]*animation: (?!none)", appearance):
    assert ".ap-anim" in rule, rule   # the window moves only under .ap-anim
glint_rule = re.search(r"\.ap-anim \.ap-name:is\(([^)]*)\):is\(\.ap-t4[^{]*> \.ap-gl \{ display: block", appearance)
ident = (STATIC / "app.20.js").read_text(encoding="utf-8")
assert glint_rule and sorted(re.findall(r"\.ap-nm-([a-z]+)", glint_rule.group(1))) == sorted(re.findall(r"'([a-z]+)'", re.search(r"_AP_GLINT_KINDS = \[([^\]]*)\]", ident).group(1))), "apName and the CSS must light the same name kinds"
assert 'ap.ti >= 4 && _AP_GLINT_KINDS.includes(ap.k.name)' in ident and 'class="ap-gl" aria-hidden="true"><span data-t=' in ident
assert ".v3-who .ap-gl { display: none !important; }" in appearance, "list rows never get a glint window"
assert ".fx-5 .v3-title > .ap-gl" in fx and ".fx-5 .v3-gname > .ap-gl" in fx and "will-change" not in fx.split("/* S · fx-5", 1)[1].split("/* SS · fx-6", 1)[0]
for name in ("app.04.js", "app.12.js", "app.19.js", "app.26.js"):
    src = (STATIC / name).read_text(encoding="utf-8")
    assert "v3GlintMark(" in src or "v3Head(" in src, name   # every big title is built with its glint window (v3Head adds it itself)
assert "${esc(title)}${v3GlintMark(title)}" in (STATIC / "app.20.js").read_text(encoding="utf-8"), "v3Head carries the glint window"
assert 'class="v3-title">Ещё<span class="ap-gl" aria-hidden="true"><span data-t="Ещё">' in index
# An element with its own transform animation and an animated pseudo-element of its own is moved to the main thread by Blink (both fall back): the rays halo turns its child, not itself.
assert not re.search(r"\.ap-ha-rays(?:[^{},]*)::(?:before|after)[^{]*\{[^{}]*animation:", appearance), "rays animate a child, never their own ::before/::after"
for level in range(1, 8):
    assert f".ap-t{level}" in appearance, level
assert 'skins-v3.css' in index and 'fx-tiers-v3.css' in index
# Public card: skins scoped to the card, new card replaces the legacy opener, rows are clickable.
skins_css = (STATIC / "skins-v3.css").read_text(encoding="utf-8")
assert ".v3-scope.pp-neutral" in skins_css and "skin-deep-water" not in skins_css, "palettes now come from the server catalog"
card = (STATIC / "app.21.js").read_text(encoding="utf-8")
assert "window.openPublicProfile = openPublicCardV3" in card and "/public-profile-v3/" in card
assert "a.visible" in card and "pp-neutral" in card, "hidden look must fall back to the neutral palette"
top = (STATIC / "app.17.js").read_text(encoding="utf-8")
assert "_v3RowButton" in top and "openPublicProfile(" in top and "appearance-v3.css" in index
# Toasts: one implementation (app.28.js), shaped by the worn look; the old green blob and its CSS are gone.
assert sum(path.read_text(encoding="utf-8").count("function toast(") for path in STATIC.glob("app.*.js")) == 1
toast_js = (STATIC / "app.28.js").read_text(encoding="utf-8")
assert "apFromLook(_profileData?.look)" in toast_js and "tv-fr-" in toast_js and "role" in toast_js and "textContent" not in toast_js
assert "rgb(86,196,106)" not in (STATIC / "app.01.js").read_text(encoding="utf-8") and "@keyframes toastIn" not in (STATIC / "app.css").read_text(encoding="utf-8")
assert "toast-v3.css" in index
# The dashed toast frame is a child element: an `outline` on a toast was repainted on the main thread on every frame and halved the frame rate while any toast was shown (dash looks only).
for _css_name in ("toast-v3.css", "toast-gift-v3.css"):
    assert "outline" not in re.sub(r"/\*.*?\*/", "", (STATIC / _css_name).read_text(encoding="utf-8"), flags=re.S), f"{_css_name}: no outline on a toast, the dashed frame is .tv-dash"
assert toast_js.count('<i class="tv-dash" aria-hidden="true"></i>') == 2, "toast and gift card both carry the dashed frame element"
# Looks: native Telegram main button only inside Telegram, a first-visit tour, and the two display options live in settings.
looks_extra = (STATIC / "app.27.js").read_text(encoding="utf-8")
assert "tg && tg.initData && tg.MainButton" in looks_extra and "setParams(params)" in looks_extra and "hideProgress" in looks_extra and "is-native" in looks_extra
assert "lkTourOnce" in looks_extra and "pv_looks_tour" in looks_extra and "lkTourOnce(st)" in (STATIC / "app.23.js").read_text(encoding="utf-8")
settings_js, settings_css = (STATIC / "app.26.js").read_text(encoding="utf-8"), (STATIC / "settings-v3.css").read_text(encoding="utf-8")
assert "_toggleOled" in settings_js and "_toggleBig" in settings_js and "body.pv-oled" in settings_css and "!important" in settings_css.split("body.pv-oled", 1)[1].split("}", 1)[0]
assert "body.pv-big .page" in settings_css
# Balance chips are separate buttons: each reacts alone, Zarniki lead to the top-up sheet, Mora and Diamonds to the wallet.
chips = index[index.index('<div class="v3-chips"'):index.index("</div>", index.index('<div class="v3-chips"'))]
assert 'class="v3-chips" onclick' not in index, "the chips group itself is not a button"
chips = index[index.index('<div class="v3-chips"'):index.index("</header>")]
order = [chips.index(f'id="vb-{k}"') for k in ("mora", "dia", "ess", "zar")]
assert chips.count('<button type="button" class="v3-chip') == 4 and order == sorted(order), "order: Mora, Diamonds, the other currencies, Zarniki last"
assert 'class="v3-chip v3-chip--zar" onclick="openZarnikiTopup()"' in chips and chips.count('onclick="showCurrModal()"') == 2 and 'onclick="openLooksModal()"' in chips
assert ".v3-chips:active" not in home_css and ".v3-chip:active" in home_css and ".v3-bar .v3-chip:active" in home_css and ".v3-bar .v3-chip { background: none; }" in home_css
# The header never loses a digit: chips do not shrink, the row tightens in steps (fit-1..3) and only then scrolls with a fade.
bar_js = (STATIC / "app.16.js").read_text(encoding="utf-8")
assert ".v3-chip { flex: none;" in home_css and "flex: 0 1 auto" not in home_css.split(".v3-chip { flex: none;")[1][:40], "chips must not shrink their numbers away"
assert all(f".v3-bar.fit-{n}" in home_css for n in (1, 2, 3)) and "classList.add('fit-1')" in bar_js and "classList.add('fit-3')" in bar_js and "_v3BarNumbers(true)" in bar_js
assert re.search(r"fit-3 \.v3-chip-plus \{ display: none", home_css) and not re.search(r"@media[^{]*\{[^}]*v3-chip-plus \{ display: none", home_css), "the plus survives until the last step"
# Marks: shown in both heroes and next to names in lists; everything from the server is validated and escaped before it reaches markup.
marks_js = (STATIC / "app.29.js").read_text(encoding="utf-8")
assert "v3MarksHtml(d.marks, { own: true })" in (STATIC / "app.15.js").read_text(encoding="utf-8") and "v3MarksHtml(d.marks)" in card
assert "v3MarkDot(row.mark)" in (STATIC / "app.20.js").read_text(encoding="utf-8") and "mark: r.mark" in top
assert "_mkSafe" in marks_js and "_MK_TONES.has(m.tone)" in marks_js and "_profileEsc(m.glyph)" in marks_js and "_profileEsc(m.title)" in marks_js and "textContent" not in marks_js
assert "marks-v3.css" in index and ".v3-mark " in (STATIC / "marks-v3.css").read_text(encoding="utf-8")
marks_css = (STATIC / "marks-v3.css").read_text(encoding="utf-8")
# Players see «Регалии», never «метки», and the hero shows every regalia: two chips, the rest as icons, with a cap far above the catalog.
visible = re.sub(r"//[^\n]*", "", marks_js)
assert "Регалии" in marks_js and not re.search(r"Метк|метк", visible), "players never see the word «метки»"
assert "_MK_FULL = 2" in marks_js and "v3-mark--ico" in marks_css and "_MK_ICONS = 18" in marks_js
assert "mk-head" in marks_css and "position: sticky" in marks_css and "mk-tile" in marks_js and "m.desc" in marks_js, "the sheet keeps its header and spells out every description"
assert "_profileData" in marks_js and "/marks-v1/me" in marks_js and marks_js.index("_mkShow(known") < marks_js.index("api('/marks-v1/me')"), "the own sheet opens before the request returns"
assert "v3MarksNotice(d.marks)" in (STATIC / "app.25.js").read_text(encoding="utf-8")
# The hero greeting leads into the nickname below it; the streak is not glued to it («Добрый день · 12 дней подряд» read as a formality).
greet_js = (STATIC / "app.25.js").read_text(encoding="utf-8")
assert "function _v3GreetLead(" in greet_js and "подряд" not in greet_js.split("function v3GreetHtml")[0].split("function _v3GreetLead")[1] and "${_profileEsc(_v3GreetLead(d))}," in greet_js
# One kind of pill in the hero: regalia. The skin title stays in the preview and in lists, not in the hero next to them.
assert "apTitle(ap)" not in (STATIC / "app.15.js").read_text(encoding="utf-8") and "apTitle(ap)" not in card
# Zarniki and VIP are one page that sells itself; the old top-up sheet and VIP modal are gone and every entry point leads to the page.
store_js = (STATIC / "app.30.js").read_text(encoding="utf-8")
assert 'id="pg-store"' in index and "store-v3.css" in index and not (STATIC / "app.24.js").exists()
assert "function openStoreV3(" in store_js and "window.openZarnikiTopup" in store_js and "window.openVipModal" in store_js and "/payments/zarniki/invoice" in store_js and "/vip-v2/purchase" in store_js
assert "_svReach" in store_js and "_svRecommended" in store_js and "_svSee" in store_js and "apStage(" in store_js, "the page shows what a pack buys and how others see a VIP"
assert "function openVipModal" not in (STATIC / "app.02.js").read_text(encoding="utf-8") and "_ztPay" not in store_js
assert "openStoreV3('vip')" in (STATIC / "app.16.js").read_text(encoding="utf-8") and "openStoreV3('zarniki'" in (STATIC / "app.23.js").read_text(encoding="utf-8")
assert "openStoreV3('zarniki')" in index and "openStoreV3('vip')" in index
# Motion with a purpose: events get one-shot feedback (money in or out, a reward flying to its chip, a sheet leaving, a page arriving from its side, a new
# star), repeated things are static where there are many of them, and the device class decides how much runs.
motion_css = (STATIC / "motion-v3.css").read_text(encoding="utf-8")
motion_js = (STATIC / "app.31.js").read_text(encoding="utf-8")
for sheet_name, sheet in (("motion-v3.css", motion_css), ("marks-v3.css", (STATIC / "marks-v3.css").read_text(encoding="utf-8")), ("shell-v3.css", css)):
    for name, props in keyframe_props(sheet).items():
        assert props <= {"transform", "opacity"}, (sheet_name, name, props)
assert "infinite" not in motion_css, "motion-v3.css is one-shot only"
assert all(f"function {name}(" in motion_js for name in ("v3Dismiss", "v3BalanceFx", "v3Fly", "_v3Moves")) and "_v3Class() !== 'low'" in motion_js
assert "v3BalanceFx(" in bar_js and "Date.now() - since < 2500" in motion_js, "no fireworks at app start"
assert "document.body.dataset.dir" in (STATIC / "app.01.js").read_text(encoding="utf-8") and 'body[data-dir="f"]' in motion_css and 'body[data-dev="low"]' in motion_css
assert "v3Dismiss(" in marks_js and "v3ApplyLook(look);" in (STATIC / "app.23.js").read_text(encoding="utf-8") and "v3Fly(" in (STATIC / "app.30.js").read_text(encoding="utf-8") and "v3Fly(" in (STATIC / "app.12.js").read_text(encoding="utf-8")
assert "v3GrowStar(" in greet_js and "function v3GrowStar(" in (STATIC / "app.20.js").read_text(encoding="utf-8")
assert "prefers-reduced-motion" in motion_css and ".no-fx" in motion_css, "calm mode leaves no motion behind"
assert "function v3QuestsDone(" in motion_js and "v3QuestsDone(root)" in (STATIC / "app.12.js").read_text(encoding="utf-8") and 'data-q="${period}-${quest.slot}"' in (STATIC / "app.12.js").read_text(encoding="utf-8")
assert "function v3RingIn(" in motion_js and "v3RingIn(root, prevAll, seen)" in greet_js, "the level ring draws from what the player saw last time"
# Performance: the skins strip (thirty look previews) and list rows never animate; a mid phone gets the lite mode; the watchdog tries lite before lowering the cap.
assert re.search(r"\.lk-mini \*, \.lk-mini \*::before, \.lk-mini \*::after \{ animation: none !important; \}", css_all := (STATIC / "looks-v3.css").read_text(encoding="utf-8"))
assert re.search(r"\.v3-who \.ap-name, \.v3-who \.ap-title, \.v3-who \.ap-title::after \{ animation: none !important; \}", (STATIC / "appearance-v3.css").read_text(encoding="utf-8"))
# Three modes: full; .ap-lite (a mid phone: half the particles, no .w2 scene layers, the motion stays); .ap-low (the weakest: the look stands still). What is off screen is paused (.ap-off).
assert ".ap-low .ap-bg b" in fx and ".ap-lite .ap-fx i:nth-child(even)" in fx and ".ap-off" in fx and "animation-play-state: paused" in fx
assert "function _v3Class()" in controller and "_V3_LITE_KEY" in controller and "_V3_LOW_KEY" in controller and "ap-lite" in controller and "ap-low" in controller and "measure(step)" in controller and "lower(median)" in controller
assert "IntersectionObserver" in controller and "'ap-off'" in controller, "effects outside the screen are paused, not rendered"
# Every spend goes through one confirmation sheet (what, price, balance, what remains); cancelling does nothing. Chests keep their own confirm (OM) and the exchange
# of the player market its own pending-confirm flow.
confirm_js = (STATIC / "app.28.js").read_text(encoding="utf-8")
assert "function v3Confirm(" in confirm_js and "role=\"alertdialog\"" in confirm_js and "Escape" in confirm_js and "Promise" in confirm_js and (STATIC / "confirm-v3.css").exists()
assert "await v3Confirm(spec)" in (STATIC / "app.23.js").read_text(encoding="utf-8") and "_lkConfirmSpec('" not in "" and "function _lkConfirmSpec(" in (STATIC / "app.23.js").read_text(encoding="utf-8")
assert store_js.count("await v3Confirm(") == 2, "Zarniki packs and VIP are confirmed before any request"
assert "await v3Confirm(" in (STATIC / "app.02.js").read_text(encoding="utf-8"), "Zarniki exchange"
assert "await v3Confirm(" in (STATIC / "app.06.js").read_text(encoding="utf-8"), "partner gifts"
# Loading placeholders appear after a delay and softly; the top screen keeps the previous list instead of flashing a grey block.
assert re.search(r"\.sk \{[^}]*animation: v3skel \.3s ease \.22s backwards", css) and "@keyframes v3skel" in css
top_js = (STATIC / "app.19.js").read_text(encoding="utf-8")
assert "f.data = null; f.failed = false; renderTopV3();" not in top_js and "is-loading" in top_js and ".v3-top-body.is-loading" in home_css
# A cascade plays once per visit: a re-render right after the first one continues it instead of restarting it (the profile used to flicker on open).
assert "function v3EnterSync(" in motion_js and "--enter-skip" in fx and "v3EnterSync(" in (STATIC / "app.02.js").read_text(encoding="utf-8") and "v3EnterReset(" in (STATIC / "app.01.js").read_text(encoding="utf-8")
assert "pg-enter" not in (STATIC / "app.css").read_text(encoding="utf-8"), "the old second cascade is gone"
# VIP page: facts come from the server list, the reminder switch names what it really does, the comparison shows the whole look.
assert "Напоминать о поручении дня" in store_js and "о конце срока" not in store_js and "apStage(ap" in store_js and "sv-prev" in store_js
# Monolith (docs/DESIGN_IMPLEMENTATION_GATES: «Monolithic composition»): the store page is rows with hairlines and one selected row, not cards; the old screens lose their card shells in monolith-v3.css.
store_css = (STATIC / "store-v3.css").read_text(encoding="utf-8")
assert not re.search(r"\.sv-(hero|pack|tile|mission|term|badge|status)\b[^{]*\{[^}]*(box-shadow: inset 0 0 0 1px|background: color-mix\(in srgb, var\(--v3-ink\))", store_css), "no card shells on the store page"
assert "lk-seg" not in store_js and "lk-wallet" not in store_js and "sv-opt" in store_js and ".sv-opt.is-on" in store_css
assert "monolith-v3.css" in (ROOT / "FastAPI/main.py").read_text(encoding="utf-8") and "monolith-v3.css" in (STATIC / "index.html").read_text(encoding="utf-8")
mono = (STATIC / "monolith-v3.css").read_text(encoding="utf-8")
for page in ("#pg-pets", "#pg-help", "#pg-looks"):   # Достижения и Сундуки собраны на v3-компонентах (achievements-v3.css, chests-v3.css), уплощать нечего
    assert page in mono, f"{page} must be flattened in monolith-v3.css"
# 100% new design on the player side: the old control/card classes are gone with admin-legacy.css (the old admin screens no longer exist); the only rules left are the .btn family
# at the end of app.css for one old dialog footer (app.14.js passes c: 'btn-gold'). A player screen (every JS part except app.07/08/09, and index.html outside the admin pages)
# may not use them in markup: use v3-pill, v3-field, v3-err, v3-dim, v3-line, v3-empty, v3-row.
assert "admin-legacy.css" not in (ROOT / "FastAPI/main.py").read_text(encoding="utf-8") and "admin-legacy.css" not in (STATIC / "index.html").read_text(encoding="utf-8")
assert not (STATIC / "admin-legacy.css").exists(), "admin-legacy.css is deleted: every player loaded 20 KB of rules for screens that no longer exist"
LEGACY_CONTROLS = {"btn", "btn-sm", "btn-gold", "btn-ghost", "btn-red", "btn-full", "btn-teal", "num-input", "err", "card", "card-title", "irow", "ik", "iv", "empty-state", "es-icon", "es-title", "es-sub", "cx-dim", "set-hint", "pcard"}
_html = (STATIC / "index.html").read_text(encoding="utf-8")
_player_html = re.sub(r'<div id="pg-(?:admin|global|console)".*?(?=<div id="pg-(?!admin|global|console))', "", _html, flags=re.S)
_player_sources = {"index.html": _player_html}
for _js in sorted(STATIC.glob("app.[0-9][0-9].js")):
    if _js.name not in ("app.07.js", "app.08.js", "app.09.js"):
        _player_sources[_js.name] = _js.read_text(encoding="utf-8")
for _name, _src in _player_sources.items():
    for _m in re.finditer(r"class(?:Name)?\s*=\s*['\"`]([^'\"`]*)", _src):
        _bad = LEGACY_CONTROLS.intersection(_m.group(1).split())
        assert not _bad, f"{_name} uses the legacy class {sorted(_bad)} (admin-only): {_m.group(0)[:80]}"
# SSS made phones flash and lag (elements and the dock vanishing and returning): the light ribbons were 160vmax conic gradients with blur(60px), spinning, a layer far beyond graphics memory.
# The effect layer may not hold a viewport-max sized layer or a big blur, and the tilt may not write into body (it re-styles the whole page).
_fx_css = (STATIC / "fx-tiers-v3.css").read_text(encoding="utf-8")
assert "vmax" not in re.sub(r"/\*.*?\*/", "", _fx_css, flags=re.S), "no screen-multiple layers in the effect layer"
assert not re.search(r"blur\((4\d|[5-9]\d|\d{3,})px\)", re.sub(r"/\*.*?\*/", "", _fx_css, flags=re.S)), "no big blur in the effect layer"
assert "document.body.style.setProperty('--tilt" not in (STATIC / "app.18.js").read_text(encoding="utf-8"), "tilt must not write into body"
# Phones lagged on heavy looks because of how the page was drawn, not because of how much: (1) five full-screen CSS layers of page light (about six screens of textures, a repaint of the whole
# screen every frame) became three (wash, light, grain) and are now ONE canvas drawn by app.18.js every 200 ms: every full-screen layer is a screen of texture in memory and a screen of fill per frame;
# (2) a polygon clip-path makes the browser draw each such layer in a separate pass (34 passes a frame from sparks alone): shapes are masks; (3) reading innerWidth/innerHeight in the effect loop
# forces the browser to recalculate every running animation, so the screen size is cached.
_fx_js = (STATIC / "app.18.js").read_text(encoding="utf-8")
assert "createRadialGradient" in _fx_js and "_V3_FX_SCALE" in _fx_js and "v3-fx-glow" in _fx_js and "_v3FxPaintGrain" in _fx_js and "_v3FxPaintWash" in _fx_js, "page light, wash and grain are drawn on canvas"
assert "v3-fx-grain" not in _fx_js and "v3-fx-grain" not in _fx_css, "the grain is not a layer of its own: it is drawn into the one canvas"
assert _fx_js.split("function _v3BuildFx", 1)[1].split("\n}", 1)[0].count("layer.appendChild(") == 1, "one canvas in the effect layer, the rest are off-screen"
assert int(re.search(r"_V3_FX_STEP = (\d+)", _fx_js).group(1)) >= 150, "the slow light is redrawn rarely, not every frame"
assert re.search(r"\.v3-fx > canvas \{[^}]*position: absolute", _fx_css), "the canvas lies in the effect layer"
assert re.search(r"body\.v3-fx-wash::before \{ display: none; \}", _fx_css), "while the canvas holds the wash, the CSS layer of it is off"
assert not re.search(r"\.v3-fx-(breath|tilt|ribbon)", _fx_css), "no full-screen CSS layers of light"
_frame_body = _fx_js.split("function _v3FxFrame", 1)[1].split("\nfunction _v3FxRun", 1)[0]
assert "innerWidth" in _frame_body and "_V3_FX.w ||" in _frame_body and "_V3_FX.h ||" in _frame_body, "the frame uses the cached screen size first"
assert "_V3_FX.w = innerWidth" in _fx_js.split("function _v3FxResize", 1)[1].split("}", 1)[0], "the cache is filled on resize"
for _css_path in sorted(STATIC.glob("*.css")):
    _plain = re.sub(r"/\*.*?\*/", "", _css_path.read_text(encoding="utf-8"), flags=re.S)
    assert not re.search(r"clip-path\s*:\s*(polygon|circle|ellipse|path)\(", _plain), f"{_css_path.name}: a shaped clip-path costs a render pass per element, use a mask"
# Every mix-blend-mode element gets a render surface of its own and the browser copies the backdrop for it: in the artifact look the three of them (the tear and two copies of the glitch nick)
# cost about six render passes of seven a frame and 8-13 frames a second. The looks use none (card effects cfx-* in app.css are an old shop category and stay as they are); where light has to add up,
# use a lighter colour in normal blending. A filter may not wrap running animation either: a drop-shadow on the root of the artifact's hexagon HUD (it turns inside) and on the glitch nick (two
# copies run inside) was re-drawn every frame, so the glow sits on the shapes themselves and on the text itself.
for _css_path in sorted(STATIC.glob("*.css")):
    if _css_path.name == "app.css":
        continue
    _plain = re.sub(r"/\*.*?\*/", "", _css_path.read_text(encoding="utf-8"), flags=re.S)
    assert not re.search(r"mix-blend-mode\s*:\s*(?!normal)", _plain), f"{_css_path.name}: mix-blend-mode costs about two render passes per element"
_sig2 = re.sub(r"/\*.*?\*/", "", (STATIC / "skin-signatures-2-v3.css").read_text(encoding="utf-8"), flags=re.S)
assert not re.search(r"\.sg-hex \{[^}]*filter\s*:", _sig2) and re.search(r"\.sg-hex polygon \{[^}]*filter: drop-shadow", _sig2), "the hexagon glow sits on its polygons, not on the rotating svg"
_look_css = re.sub(r"/\*.*?\*/", "", (STATIC / "appearance-v3.css").read_text(encoding="utf-8"), flags=re.S)
assert re.search(r"\.ap-nm-glitch:is\([^)]*\) \{[^}]*filter: none;[^}]*text-shadow: 0 0 8px", _look_css), "the glitch nick glows with text-shadow, not with a filter around its running copies"
# The aurora veils sway all the time, so their soft edge is a mask baked into the layer (the same Gaussian profile as the old blur(26px), checked by pixels: mean difference 1 level out of 255),
# not a filter that has to be re-run. The vortex disc keeps blur(22px) on purpose: besides the rim, the blur smooths the narrow wedges that meet in the centre, and a mask turns them into a hard bow-tie.
_stage = re.sub(r"/\*.*?\*/", "", (STATIC / "appearance-stage-v3.css").read_text(encoding="utf-8"), flags=re.S)
assert not re.search(r"\.ap-bg-aurora[^{]*\{[^}]*filter\s*:", _stage), "aurora veils have no filter"
assert re.search(r"\.ap-bg-aurora b, \.ap-bg-aurora::after \{[^}]*mask-image: radial-gradient\(closest-side", _stage), "aurora veils are softened by a mask"
assert re.search(r"\.ap-bg-vortex b:nth-child\(1\) \{[^}]*filter: blur\(22px\)", _stage), "the vortex keeps its blur, a mask cannot soften the centre"
# A page must never be wider than the phone: effects of a look that reach past the edge widen the document, the mobile browser then widens the viewport
# and the fixed dock lands below the visible screen (reported on production). The document clips sideways and may not be zoomed out.
shell_css_text = (STATIC / "shell-v3.css").read_text(encoding="utf-8")
assert re.search(r"html, body \{ overflow-x: clip; \}", shell_css_text), "html and body must clip sideways"
assert re.search(r'<meta name="viewport" content="[^"]*minimum-scale=1(\.0)?[^"]*"', (STATIC / "index.html").read_text(encoding="utf-8")), "the page may not be zoomed out"
# The app is one classic script made of numbered parts (FastAPI/main.py, _APP_JS_PARTS): one syntax error in any part kills every function, so the whole is parsed here.
import re as _re, shutil, subprocess, tempfile  # noqa: E401
if shutil.which("node"):
    parts = _re.findall(r"app\.(\d\d)\.js", _re.search(r"_APP_JS_PARTS = \[([^\]]*)\]", (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")).group(1)) or \
        [f"{int(n):02d}" for n in _re.search(r"for i in \(([^)]*)\)", (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")).group(1).split(",")]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
        tmp.write("\n".join((STATIC / f"app.{n}.js").read_text(encoding="utf-8") for n in parts))
    done = subprocess.run(["node", "--check", tmp.name], capture_output=True, text=True)
    Path(tmp.name).unlink()
    assert done.returncode == 0, done.stderr[:600]
print("OK: shell-v3 flags, tap targets, motion budget, claim safety and TMA shell are wired")
