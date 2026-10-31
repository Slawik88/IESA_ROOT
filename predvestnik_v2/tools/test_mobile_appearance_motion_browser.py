"""Exercise the ordinary motion controller, without the skin lab's force/watchdog bypass.

The clean baseline supplies unchanged CSS/templates. Only actual app.18.js is replaced
in the candidate fixture. --out retains the real before/after pages for owner review.
Cadence cases scale rAF timestamps; they are controller simulations, not phone benchmarks.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright
from PIL import Image
from skin_compare import make_preview

ROOT = Path(__file__).resolve().parents[1]
ORDINARY = """
document.documentElement.dataset.live='yes';
const look=LAB_DATA.looks.void.SSS, t=document.createElement('template');
t.innerHTML=renderProfileHome({...labFixture,look});
labRoot.innerHTML='<div id="pg-profile" class="page active"><div id="pro-main"></div></div>';
document.getElementById('pro-main').append(t.content.querySelector('.ap-stage'));
v3ApplyLook(look);
await labAssetsReady();
"""
STATE = """()=>({forced:_v3Forced,calm:_v3Calm(),classes:document.body.className,fx:v3FxLevelNow(),
  low:document.body.classList.contains('ap-low'),lite:document.body.classList.contains('ap-lite'),
  sceneRunning:document.querySelector('.ap-scene').getAnimations({subtree:true}).filter(a=>a.playState==='running').length,
  saved:{low:localStorage.getItem('v3_low'),lite:localStorage.getItem('v3_lite'),cap:localStorage.getItem('v3_fx_cap')}})"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('Output must be empty')
    out.mkdir(parents=True, exist_ok=True)
    info = make_preview(args.baseline_root.resolve(), out/'before', out/'raw', cards=False)
    shutil.copytree(out/'before', out/'after')
    before_source = (args.baseline_root/'predvestnik_v2/FastAPI/static/app.18.js').read_text(encoding='utf-8')
    after_source = (ROOT/'FastAPI/static/app.18.js').read_text(encoding='utf-8')
    bundle = (out/'after/bundle.js').read_text(encoding='utf-8')
    if bundle.count(before_source) != 1:
        raise RuntimeError('Baseline controller must occur exactly once')
    (out/'after/bundle.js').write_text(bundle.replace(before_source,after_source,1), encoding='utf-8')
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None,
                                     args=['--disable-gpu','--force-color-profile=srgb'])
        for case, side, fps, saved, reduced in [
            ('before-saved','before',60,True,False), ('after-saved','after',60,True,False),
            ('before-30','before',30,False,False), ('after-30','after',30,False,False),
            ('after-20','after',20,False,False), ('after-reduced','after',60,False,True),
        ]:
            context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,
                                        reduced_motion='reduce' if reduced else 'no-preference',
                                        record_video_dir=str(out/'recordings'),record_video_size={'width':390,'height':844})
            context.add_init_script("""Object.defineProperty(navigator,'deviceMemory',{get:()=>8});
                Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>8});
                localStorage.clear();localStorage.setItem('v3_perf_rev','2026-10-12b');localStorage.setItem('pv_no_fx','0');
                """ + ("localStorage.setItem('v3_low','7');localStorage.setItem('v3_lite','7');localStorage.setItem('v3_fx_cap','5');" if saved else '') +
                f"""const nativeNow=performance.now.bind(performance),nativeRaf=requestAnimationFrame.bind(window);
                performance.now=()=>nativeNow()*{60/fps};window.requestAnimationFrame=fn=>nativeRaf(time=>fn(time*{60/fps}));""")
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto((out/side/'preview.html').as_uri())
            page.evaluate('async()=>{'+ORDINARY+'}')
            if case in ('before-30','after-20'):
                page.wait_for_function("document.body.classList.contains('ap-low')",timeout=25000)
            elif case=='after-30':
                page.wait_for_function("!_v3Watchdog",timeout=20000)
            page.wait_for_timeout(250)
            state=page.evaluate(STATE)
            assert not state['forced'], 'ordinary launch was forced'
            assert not errors,errors
            if case in ('before-saved','before-30','after-20'):
                assert state['low'] and state['sceneRunning']==0,(case,state)
            elif case in ('after-saved','after-30'):
                assert not state['low'] and state['sceneRunning']>0,(case,state)
            elif reduced:
                assert state['calm'] and state['sceneRunning']==0,(case,state)
            state['case']=case
            results.append(state)
            Image.open(io.BytesIO(page.screenshot())).save(out/f'{case}.webp',quality=80,method=6)
            page.wait_for_timeout(2500)
            video=page.video
            context.close()
            recording=Path(video.path())
            recording.relative_to(out)
            video.save_as(out/f'{case}.webm')
            recording.unlink()
        browser.close()
    metadata={'baseline':info['revision'],'candidate_controller_sha256':hashlib.sha256(after_source.encode()).hexdigest(),
              'cadence':'scaled rAF timestamps, not real phone FPS','results':results}
    (out/'results.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'index.html').write_text('''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Предвестник · Проверка движения</title>
<style>body{margin:0;background:#090a0e;color:#f2f3f7;font:16px/1.5 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:24px}h1{font-size:32px;line-height:1.2}h2{font-size:22px}p{max-width:760px}small{color:#b6bac7}section{border-top:1px solid #343740;padding:24px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}video{width:100%;max-height:600px;background:#101117;border-radius:12px}button{font:inherit;min-height:44px;border-radius:24px;padding:8px 18px;background:#e4defa;color:#171323;border:0;cursor:pointer}button:focus-visible{outline:2px solid white;outline-offset:4px}@media(max-width:600px){main{padding:18px}.pair{grid-template-columns:1fr}}</style>
<main><small>Предвестник · исправление S16b · ещё не в проде</small>
<h1>Проверка движения на телефоне</h1>
<p>Здесь обычный запуск приложения без принудительного полного режима стенда. Персонаж тестовый, твоих данных нет.</p>
<p>Воспроизведены ошибки автоматического ограничения движения. На настоящих Nothing и Redmi исправление ещё не проверено.</p>
<section><h2>Раньше сохранилось снижение качества</h2><p>До — прежняя отметка продолжает останавливать сцену. После — новый запуск оценивает скорость заново.</p>
<button type="button" onclick="playPair(this)">Сравнить движение</button><div class="pair"><div><h3>До</h3><video controls muted playsinline loop poster="before-saved.webp" src="before-saved.webm"></video></div><div><h3>После</h3><video controls muted playsinline loop poster="after-saved.webp" src="after-saved.webm"></video></div></div></section>
<section><h2>Стабильные 30 кадров в секунду</h2><p>Имитация частоты для проверки контроллера, не замер телефона. До — спустя несколько секунд сцена замирает. После — продолжает двигаться.</p>
<button type="button" onclick="playPair(this)">Сравнить движение</button><div class="pair"><div><h3>До</h3><video controls muted playsinline loop poster="before-30.webp" src="before-30.webm"></video></div><div><h3>После</h3><video controls muted playsinline loop poster="after-30.webp" src="after-30.webm"></video></div></div></section>
<section><h2>Защита от тормозов сохранена</h2><div class="pair"><div><h3>Устойчивая низкая скорость</h3><p>При имитации 20 кадров сцена по-прежнему останавливается.</p><video controls muted playsinline loop poster="after-20.webp" src="after-20.webm"></video></div><div><h3>Запрет движения</h3><p>Настройка системы «Без движения» по-прежнему учитывается.</p><video controls muted playsinline loop poster="after-reduced.webp" src="after-reduced.webm"></video></div></div></section>
<p>Это проверка поведения, перерисовки образов здесь нет. «Спокойный режим», ограничения слабых устройств, цены и уровни сохранены.</p></main>
<script>function playPair(button){for(const video of button.parentElement.querySelectorAll('video')){video.currentTime=0;video.play().catch(()=>{video.controls=true;});}}</script></html>''',encoding='utf-8')
    print(f'PASS {len(results)} ordinary browser launches: cached limits, 30/20 cadence and reduced motion; no force')


if __name__=='__main__':
    main()
