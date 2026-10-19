"""All actual skin/tier payloads through both public nickname renderers.

Run --browser for Edge/Chromium layout, contrast visibility and SVG CSS parsing.
The browser uses only local sources; no Telegram or live player operations.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.skins_v3 import TIERS
from core.skins_v3_catalog import SKINS
from services.skins_v3 import look_payload

STATIC = ROOT / 'FastAPI/static'
looks = [look_payload(sid, tier) for sid in SKINS for tier in TIERS]
shared = (STATIC / 'nickname-v3.js').read_text(encoding='utf-8')
app = (STATIC / 'app.20.js').read_text(encoding='utf-8')
game = (STATIC / 'game-board-v3.js').read_text(encoding='utf-8')
fixtures = json.dumps(looks, ensure_ascii=False)
source = "global.window={};const _profileEsc=v=>String(v).replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));\n"
source += shared + '\n' + app + '\n' + game
source += '\nconst looks=' + fixtures + r''';
for (const look of looks) {
  const raw='<img src=x onerror="alert(1)"> & «Игрок»', safe=_profileEsc(raw);
  const mini=apName(apFromLook(look),safe,raw);
  const board=window.gameWhoV3({look,display_name:raw});
  if (!mini.includes('ap-designed') || !board.includes('ap-designed')) throw Error(look.id);
  if (mini.includes('<img') || board.includes('<img')) throw Error('unescaped player name');
  const n=look.tier, ti=look.tier && ['D','C','B','A','S','SS','SSS'].indexOf(n)+1;
  if (mini.includes('ap-nick-emblem') !== (ti>=3)) throw Error('emblem tier '+n);
  if (mini.includes('ap-nick-rail') !== (ti>=4)) throw Error('rail tier '+n);
  if (mini.includes('ap-nick-rank') !== (ti>=6)) throw Error('rank tier '+n);
}
if(window.skinNicknameV3({id:'__proto__'},'plain','plain')!=='plain')throw Error('prototype skin');
const fn=window.skinNicknameV3;delete window.skinNicknameV3;
if(apName(apFromLook(looks[0]),'plain')!=='plain')throw Error('network fallback');
if(!window.gameWhoV3({look:looks[0],display_name:'plain'}).includes('plain'))throw Error('game fallback');
window.skinNicknameV3=fn;
console.log('OK: '+looks.length+' actual skin/tier payloads, shared game renderer, escaping and missing-script fallback');
'''
done = subprocess.run(['node'], input=source, text=True, encoding='utf-8', capture_output=True)
assert done.returncode == 0, done.stderr
print(done.stdout.strip())

if '--browser' in sys.argv:
    from playwright.sync_api import sync_playwright
    css_names = ('appearance-v3.css', 'skin-signatures-v3.css', 'skin-signatures-2-v3.css',
                 'skins-exclusive-v3.css', 'nickname-v3.css', 'skin-scene-v3.css', 'skin-scene-e-v3.css')
    css = '\n'.join((STATIC / f).read_text(encoding='utf-8') for f in css_names)
    edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    out = ROOT / '.local/nickname-qa'
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**({'executable_path':str(edge)} if edge.exists() else {}))
        page = browser.new_page()
        page.set_content('<style>body{margin:16px;background:#100d18;color:#fff;font:15px system-ui}.row{display:flex;align-items:center;gap:8px;padding:12px 0;border-bottom:1px solid #333;min-width:0}.tier{width:26px;flex:none;color:#999}.v3-who{flex:1;min-width:0}'+css+'</style><main id="rows"></main>')
        page.add_script_tag(content=shared + '\n' + game)
        page.evaluate('looks=>{document.querySelector("#rows").innerHTML=looks.map(look=>`<div class="row"><span class="tier">${look.tier}</span>${window.gameWhoV3({look,display_name:look.name+" · "+"ОченьДлинныйНик".repeat(5)})}</div>`).join("")}', looks)
        for width in (320, 390, 430, 1280):
            page.set_viewport_size({'width':width,'height':900})
            result = page.evaluate('''() => ({overflow:document.documentElement.scrollWidth>innerWidth, names:[...document.querySelectorAll('.ap-nick-text')].every(e=>e.offsetWidth>5&&getComputedStyle(e).visibility!=='hidden')})''')
            assert not result['overflow'] and result['names'], (width,result)
        # Parse every new CSS data URL; a newline in url("...") previously
        # made the illustration disappear while the CSS request still returned200.
        page.evaluate('''() => {document.body.insertAdjacentHTML('beforeend','<div class="ap-scene" style="--bleed:0px;position:relative;height:200px">'+['ravenMask','ravenKey','ghostCoach','ghostGate','sugarBakery','sugarTools','northEngine','northBridge','roseEnvelope','roseQuill','crystalHeart','crystalArc'].map(id=>`<i class="sc sil i-${id}" style="width:100px;height:180px"></i>`).join('')+'</div>')}''')
        assert page.evaluate("() => [...document.querySelectorAll('.sil')].every(e=>getComputedStyle(e).backgroundImage.startsWith('url('))")
        page.set_viewport_size({'width':430,'height':900})
        page.screenshot(path=str(out/'mobile.png'))
        # Every motif must be distinct, including same-family lotus/sakura skins.
        page.evaluate('looks=>{document.querySelector("#rows").innerHTML=looks.filter(l=>l.tier==="SSS").map(look=>`<div class="row">${window.gameWhoV3({look,display_name:look.name})}</div>`).join("")}', looks)
        paths = page.locator('.ap-nick-emblem path').evaluate_all('(es)=>es.map(e=>e.getAttribute("d"))')
        assert len(paths) == len(SKINS) and len(set(paths)) == len(SKINS)
        page.screenshot(path=str(out/'all-skin-names.png'),full_page=True)
        browser.close()
    print('OK: Edge all273 names at320/390/430/1280, 39 unique motifs, all12 holiday CSS illustrations parse')
