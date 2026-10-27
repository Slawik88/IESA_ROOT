// Собирает build/{bundle.js,all.css,nickname-v3.js,page.html} из статики Mini App. Запуск: node build.js
// Каталог образов: сначала python3 -I dump_skins.py. Пути относительны к этой папке.
const fs = require('fs'), path = require('path');
const S = path.resolve(__dirname, '../../../../FastAPI/static') + path.sep;
const OUT = path.join(__dirname, 'build') + path.sep;
fs.mkdirSync(OUT, { recursive: true });
// Порядок важен: app.20 (разметка образа) → 22 (токены, подпись) → 32–38, 48, 53 (сцены и вектор).
const parts = ['app.20.js', 'app.22.js', 'app.32.js', 'app.33.js', 'app.34.js', 'app.35.js', 'app.36.js', 'app.37.js', 'app.38.js', 'app.48.js', 'app.53.js'];
let js = "const esc=s=>String(s).replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));const _profileEsc=esc;\n"
  + "function _v3Ring(percent){const offset=Math.round(220*(1-Math.min(100,Math.max(0,percent))/100));return `<svg viewBox=\"0 0 76 76\" aria-hidden=\"true\"><circle cx=\"38\" cy=\"38\" r=\"35\" stroke=\"var(--v3-faint)\"/><circle cx=\"38\" cy=\"38\" r=\"35\" stroke=\"var(--v3-acc)\" stroke-dasharray=\"220\" stroke-dashoffset=\"${offset}\"/></svg>`;}\n";
for (const p of parts) js += fs.readFileSync(S + p, 'utf8') + '\n';
fs.writeFileSync(OUT + 'bundle.js', js);
const css = ['app.css', 'shell-v3.css', 'shell-v3-home.css', 'fx-tiers-v3.css', 'appearance-v3.css', 'appearance-ring-v3.css', 'appearance-stage-v3.css', 'looks-v3.css',
  'skin-signatures-v3.css', 'skin-signatures-2-v3.css', 'skins-exclusive-v3.css', 'skin-sig-a-v3.css', 'skin-sig-b-v3.css', 'skin-sig-c-v3.css', 'skin-sig-d-v3.css',
  'skin-scene-v3.css', 'skin-scene-a-v3.css', 'skin-scene-b-v3.css', 'skin-scene-c-v3.css', 'skin-scene-d-v3.css', 'skin-scene-e-v3.css', 'skin-scene-f-v3.css', 'skin-scene-g-v3.css',
  'skin-holidays-v3.css', 'nickname-v3.css', 'marks-v3.css'];
fs.writeFileSync(OUT + 'all.css', css.map(f => fs.readFileSync(S + f, 'utf8')).join('\n'));
fs.copyFileSync(S + 'nickname-v3.js', OUT + 'nickname-v3.js');
fs.copyFileSync(path.join(__dirname, 'page.html'), OUT + 'page.html');
console.log('build ok:', OUT, 'js', js.length);
