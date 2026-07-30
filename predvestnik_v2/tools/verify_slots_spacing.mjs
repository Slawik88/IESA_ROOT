// Регресс-проверка: заголовок секции слота (Задача 2, мини-измеритель) обернулся
// в .sec-head с margin-bottom:0 на .looks-sec-t — эта проверка убеждается, что
// секции БЕЗ измерителя (Темы/Приветствие), у которых нет .sec-head, не потеряли
// свой margin-bottom:8px по ошибке.
// Запуск: node tools/verify_slots_spacing.mjs (нужен запущенный preview_server.mjs на :8402)
import puppeteer from 'puppeteer';
const browser=await puppeteer.launch({headless:'new'});
const page=await browser.newPage();
await page.setViewport({width:390,height:844,deviceScaleFactor:2});
await page.goto('http://localhost:8402/',{waitUntil:'load'});
await new Promise(r=>setTimeout(r,1500));
await page.mouse.click(195,700);
await new Promise(r=>setTimeout(r,500));
await page.evaluate(()=>openLooksModal());
await new Promise(r=>setTimeout(r,1000));
const spacing=await page.evaluate(()=>{
  const themeTitle=document.querySelector('#looks-sec-themes .looks-sec-t');
  const welcomeTitle=document.querySelector('#looks-sec-welcome .looks-sec-t');
  const themesMargin=themeTitle?getComputedStyle(themeTitle).marginBottom:null;
  const welcomeMargin=welcomeTitle?getComputedStyle(welcomeTitle).marginBottom:null;
  return {themesMargin,welcomeMargin};
});
console.log('Theme section title margin-bottom:', spacing.themesMargin);
console.log('Welcome section title margin-bottom:', spacing.welcomeMargin);
if(spacing.themesMargin==='8px' && spacing.welcomeMargin==='8px'){
  console.log('✓ Spacing restored correctly');
} else {
  console.error('✗ Spacing issue detected');
  process.exit(1);
}
await browser.close();
