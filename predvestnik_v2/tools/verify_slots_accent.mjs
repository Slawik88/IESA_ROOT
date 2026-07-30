// Карточка предмета в сетке «По слотам» должна иметь класс lc-lineup-accent
// и инлайн-переменную --lc, совпадающую с цветом её линейки, БЕЗ удаления
// r-{rarity} класса (нужен модалке сундуков/крафта).
import puppeteer from 'puppeteer';
const FAIL=[];
function check(name,cond){ if(!cond) FAIL.push(name); else console.log('OK:',name); }
const browser=await puppeteer.launch({headless:'new'});
const page=await browser.newPage();
await page.setViewport({width:390,height:844,deviceScaleFactor:2});
await page.goto('http://localhost:8402/',{waitUntil:'load'});
await new Promise(r=>setTimeout(r,1500));
await page.mouse.click(195,700);
await new Promise(r=>setTimeout(r,500));
await page.evaluate(()=>openLooksModal());
await new Promise(r=>setTimeout(r,500));
await page.click('[data-mode="slots"]');
await new Promise(r=>setTimeout(r,300));
const info=await page.evaluate(()=>{
  const card=document.querySelector('#looks-grid-name_glow .looks-card[data-cos]:not([data-cos="__none__"])');
  if(!card) return null;
  const cosId=card.getAttribute('data-cos');
  const it=_looksData.slots.name_glow.find(x=>x.id===cosId);
  return {
    hasAccentClass: card.classList.contains('lc-lineup-accent'),
    hasRarityClass: [...card.classList].some(c=>c.startsWith('r-')),
    styleAttr: card.getAttribute('style')||'',
    expectedColor: lineupColor(it.lineup),
  };
});
check('карточка нашлась', !!info);
if(info){
  check('есть класс lc-lineup-accent', info.hasAccentClass);
  check('класс r-{rarity} НЕ удалён (нужен сундукам/крафту)', info.hasRarityClass);
  check('инлайн-стиль содержит цвет линейки', info.styleAttr.includes(info.expectedColor));
}
await browser.close();
if(FAIL.length){console.error('FAIL:',FAIL);process.exit(1);}
console.log('ALL OK');
