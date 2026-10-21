#!/usr/bin/env node
/* Рендер промо-роликов: scenarios/*.json → out/*.mp4 (1080×1920, 30 к/с, H.264 + AAC).
 *
 *   node render.cjs                         # все сценарии
 *   node render.cjs scenarios/01-dead-chat.json --workers 6
 *   node render.cjs scenarios/01-dead-chat.json --stills 0,1.2,5   # только кадры PNG для проверки
 *
 * Нужны: Node 18+, playwright (npm i -g playwright или локально) с Chromium, ffmpeg в PATH.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { spawn, execSync } = require("child_process");

function loadPlaywright() {
  try { return require("playwright"); } catch { /* ищем глобальный */ }
  const root = execSync("npm root -g").toString().trim();
  return require(path.join(root, "playwright"));
}

const HERE = __dirname;
const args = process.argv.slice(2);
const opt = (name, def) => { const i = args.indexOf(name); if (i < 0) return def; const v = args[i + 1]; args.splice(i, 2); return v; };
const OUT = path.resolve(opt("--out", path.join(HERE, "out")));
const WORKERS = Number(opt("--workers", Math.max(2, Math.min(6, require("os").cpus().length))));
const STILLS = opt("--stills", null);
const AUDIO_ONLY = args.includes("--audio-only") && args.splice(args.indexOf("--audio-only"), 1);
const CRF = opt("--crf", "16");
const files = args.length ? args.map(a => path.resolve(a))
  : fs.readdirSync(path.join(HERE, "scenarios")).filter(f => f.endsWith(".json")).sort().map(f => path.join(HERE, "scenarios", f));

// ---------- звуки интерфейса (синтез, без чужих сэмплов) ----------
// Звук — фон под музыку TikTok: мягкие низкие тона, плавная атака (без щелчка в начале), без резких верхов.
// Итог нормируется: пик не выше −10 dBFS, средняя громкость около −28 dB.
const RATE = 44100;
const PEAK = Math.pow(10, -10 / 20);
function synth(kind) {
  const n = s => Math.floor(s * RATE);
  const out = (dur, fn) => { const a = new Float32Array(n(dur)); for (let i = 0; i < a.length; i++) a[i] = fn(i / RATE); return a; };
  const env = (t, atk, dec) => Math.min(1, t / atk) * Math.exp(-t * dec);   // плавная атака, затухание
  const sweep = (f0, f1, len) => { let ph = 0; return t => { const f = f0 + (f1 - f0) * Math.min(1, t / len); ph += 2 * Math.PI * f / RATE; return Math.sin(ph); }; };
  const sine = f => t => Math.sin(2 * Math.PI * f * t);
  switch (kind) {
    case "pop": { const s = sweep(760, 420, .05); return out(.16, t => .5 * s(t) * env(t, .004, 30)); }
    case "send": { const s = sweep(380, 720, .07); return out(.18, t => .4 * s(t) * env(t, .006, 24)); }
    case "ding": { const a = sine(784), b = sine(1175); return out(.7, t => .32 * (a(t) * env(t, .006, 7) + .35 * b(t) * env(t, .006, 11))); }
    case "tick": { const a = sine(1050); return out(.06, t => .16 * a(t) * env(t, .003, 70)); }
    case "click": { const a = sine(640); return out(.08, t => .3 * a(t) * env(t, .003, 60)); }
    case "whoosh": {
      let lp = 0, seed = 7; const r = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
      return out(.42, t => { const c = .02 + .1 * Math.sin(Math.PI * t / .42); lp += c * ((r() * 2 - 1) - lp); return 1.3 * lp * Math.sin(Math.PI * t / .42) ** 2; });
    }
    case "boom": { const s = sweep(95, 45, .3); return out(.9, t => .9 * s(t) * env(t, .01, 4.5)); }
    case "hit": { const s = sweep(120, 60, .2); return out(.45, t => .65 * s(t) * env(t, .008, 9)); }
    case "sparkle": {
      const notes = [1047, 1319, 1568, 2093];
      return out(.9, t => notes.reduce((acc, f, i) => { const lt = t - i * .08; return lt < 0 ? acc : acc + .12 * Math.sin(2 * Math.PI * f * lt) * env(lt, .005, 8); }, 0));
    }
    default: return new Float32Array(0);
  }
}

function writeWav(file, cues, duration) {
  const len = Math.ceil(duration * RATE) + RATE;
  const mix = new Float32Array(len);
  const bank = {};
  for (const c of cues) {
    const snd = bank[c.s] || (bank[c.s] = synth(c.s));
    const off = Math.floor(c.t * RATE), v = c.v ?? 1;
    for (let i = 0; i < snd.length && off + i < len; i++) mix[off + i] += snd[i] * v;
  }
  // мягкий срез верхов (~5 кГц) и нормировка пика
  let lp = 0, peak = 1e-9; const k = 1 - Math.exp(-2 * Math.PI * 5000 / RATE);
  for (let i = 0; i < len; i++) { lp += k * (mix[i] - lp); mix[i] = Math.tanh(lp); peak = Math.max(peak, Math.abs(mix[i])); }
  const gain = Math.min(1, PEAK / peak);
  const n = Math.ceil(duration * RATE);
  const buf = Buffer.alloc(44 + n * 4);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 4, 4); buf.write("WAVE", 8); buf.write("fmt ", 12);
  buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22); buf.writeUInt32LE(RATE, 24);
  buf.writeUInt32LE(RATE * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34); buf.write("data", 36); buf.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) {
    const s = Math.round(mix[i] * gain * 32767);
    buf.writeInt16LE(s, 44 + i * 4); buf.writeInt16LE(s, 46 + i * 4);
  }
  fs.writeFileSync(file, buf);
}

// ---------- кадры ----------
async function openPage(browser, scenario, base) {
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  page.on("pageerror", e => console.error("  ошибка на странице:", e.message));
  await page.goto("file://" + path.join(HERE, "engine", "index.html"));
  const info = await page.evaluate(([sc, b]) => window.__load(sc, b), [scenario, base]);
  return { page, info };
}

async function shot(page, t) {
  await page.evaluate(x => window.__seek(x), t);
  return page.screenshot({ type: "png", animations: "disabled", caret: "initial" });
}

async function renderOne(browser, file) {
  const scenario = JSON.parse(fs.readFileSync(file, "utf8"));
  // настоящие тексты бота (capture/real_texts.py): путь от файла сценария
  if (scenario.texts) scenario.textsData = JSON.parse(fs.readFileSync(path.resolve(path.dirname(file), scenario.texts), "utf8"));
  const name = path.basename(file, ".json");
  const base = "file://" + path.dirname(file) + "/";
  fs.mkdirSync(OUT, { recursive: true });

  if (STILLS) {
    const { page } = await openPage(browser, scenario, base);
    for (const t of STILLS.split(",").map(Number)) {
      const png = await shot(page, t);
      const f = path.join(OUT, `${name}@${t.toFixed(2)}s.png`);
      fs.writeFileSync(f, png); console.log("  кадр:", f);
    }
    await page.close();
    return;
  }

  if (AUDIO_ONLY) {   // только звук: новая дорожка в уже готовый out/<имя>.mp4, картинка не пересчитывается
    const { page, info } = await openPage(browser, scenario, base);
    await page.close();
    const mp4 = path.join(OUT, `${name}.mp4`), wav = path.join(OUT, `${name}.wav`), tmp = path.join(OUT, `${name}.tmp.mp4`);
    if (!fs.existsSync(mp4)) { console.log(`  нет ${mp4}, пропуск`); return; }
    writeWav(wav, info.cues, info.duration);
    await new Promise((res, rej) => spawn("ffmpeg", ["-y", "-loglevel", "error", "-i", mp4, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
      "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", tmp], { stdio: "inherit" }).on("close", c => (c ? rej(new Error("ffmpeg " + c)) : res())));
    fs.renameSync(tmp, mp4); fs.unlinkSync(wav);
    console.log(`  звук обновлён: ${mp4}`);
    return;
  }

  const pages = await Promise.all(Array.from({ length: WORKERS }, () => openPage(browser, scenario, base)));
  const { info } = pages[0];
  const fps = info.fps, frames = Math.round(info.duration * fps);
  const wav = path.join(OUT, `${name}.wav`);
  writeWav(wav, info.cues, info.duration);
  const mp4 = path.join(OUT, `${name}.mp4`);
  console.log(`▶ ${name}: ${info.duration.toFixed(1)} с, ${frames} кадров, ${WORKERS} потоков`);

  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "png", "-i", "-",
    "-i", wav, "-c:v", "libx264", "-preset", "slow", "-crf", CRF, "-pix_fmt", "yuv420p", "-profile:v", "high",
    "-r", String(fps), "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", mp4], { stdio: ["pipe", "inherit", "inherit"] });
  const ffDone = new Promise((res, rej) => ff.on("close", c => (c === 0 ? res() : rej(new Error("ffmpeg код " + c)))));

  // Кадры снимают несколько вкладок кусками по 12 подряд (меньше перестроек сцены), в ffmpeg уходят по порядку.
  const CHUNK = 12, ready = new Map();
  let next = 0, nextChunk = 0, wake = null;
  const started = Date.now();
  const write = async () => {
    while (ready.has(next)) {
      const buf = ready.get(next); ready.delete(next);
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
      next++;
      if (next % (fps * 2) === 0) process.stdout.write(`\r  ${Math.round(next / frames * 100)}% (${((Date.now() - started) / 1000).toFixed(0)} с)`);
    }
  };
  let writing = Promise.resolve();
  await Promise.all(pages.map(async ({ page }) => {
    for (;;) {
      const c = nextChunk++;
      if (c * CHUNK >= frames) return;
      while (c * CHUNK - next > CHUNK * WORKERS * 3) await new Promise(r => { wake = r; setTimeout(r, 50); });
      for (let f = c * CHUNK; f < Math.min(frames, (c + 1) * CHUNK); f++) {
        ready.set(f, await shot(page, f / fps));
      }
      writing = writing.then(write); if (wake) wake();
    }
  }));
  await writing; await write();
  ff.stdin.end();
  await ffDone;
  fs.unlinkSync(wav);
  await Promise.all(pages.map(p => p.page.close()));
  console.log(`\r  готово: ${mp4} (${((Date.now() - started) / 1000).toFixed(0)} с)`);
}

(async () => {
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  try {
    for (const f of files) await renderOne(browser, f);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
