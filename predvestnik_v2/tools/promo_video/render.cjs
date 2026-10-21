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
const CRF = opt("--crf", "16");
const files = args.length ? args.map(a => path.resolve(a))
  : fs.readdirSync(path.join(HERE, "scenarios")).filter(f => f.endsWith(".json")).sort().map(f => path.join(HERE, "scenarios", f));

// ---------- звуки интерфейса (синтез, без чужих сэмплов) ----------
const RATE = 44100;
function synth(kind, r) {
  const n = s => Math.floor(s * RATE);
  const out = (dur, fn) => { const a = new Float32Array(n(dur)); for (let i = 0; i < a.length; i++) a[i] = fn(i / RATE); return a; };
  const sweep = (f0, f1, len) => { let ph = 0; return t => { const f = f0 + (f1 - f0) * Math.min(1, t / len); ph += 2 * Math.PI * f / RATE; return Math.sin(ph); }; };
  switch (kind) {
    case "pop": { const s = sweep(1500, 520, .06); return out(.13, t => .38 * s(t) * Math.exp(-t * 38)); }
    case "send": { const s = sweep(480, 1500, .08); return out(.14, t => .26 * s(t) * Math.exp(-t * 26)); }
    case "ding": return out(.75, t => .2 * (Math.sin(2 * Math.PI * 1318.5 * t) * Math.exp(-t * 6) + .6 * Math.sin(2 * Math.PI * 1975.5 * t) * Math.exp(-t * 9)) * Math.min(1, t * 400));
    case "tick": return out(.05, t => .16 * Math.sin(2 * Math.PI * 2600 * t) * Math.exp(-t * 90));
    case "key": return out(.03, t => .1 * (r() * 2 - 1) * Math.exp(-t * 200));
    case "click": return out(.06, t => .22 * (Math.sin(2 * Math.PI * 1800 * t) + .5 * Math.sin(2 * Math.PI * 700 * t)) * Math.exp(-t * 110));
    case "whoosh": { let lp = 0; return out(.38, t => { const c = .04 + .5 * Math.sin(Math.PI * t / .38); lp += c * ((r() * 2 - 1) - lp); return .55 * lp * Math.sin(Math.PI * t / .38); }); }
    case "boom": { const s = sweep(120, 42, .25); return out(.9, t => .85 * s(t) * Math.exp(-t * 4.5) + .25 * (r() * 2 - 1) * Math.exp(-t * 60)); }
    case "hit": { const s = sweep(160, 60, .15); return out(.4, t => .6 * s(t) * Math.exp(-t * 9) + .18 * (r() * 2 - 1) * Math.exp(-t * 80)); }
    case "sparkle": {
      const notes = [2093, 2637, 3136, 3951, 3520];
      return out(.8, t => notes.reduce((acc, f, i) => { const lt = t - i * .07; return lt < 0 ? acc : acc + .07 * Math.sin(2 * Math.PI * f * lt) * Math.exp(-lt * 9); }, 0));
    }
    default: return new Float32Array(0);
  }
}

function writeWav(file, cues, duration) {
  let seed = 12345; const r = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const len = Math.ceil(duration * RATE) + RATE;
  const mix = new Float32Array(len);
  const bank = {};
  for (const c of cues) {
    const snd = bank[c.s] || (bank[c.s] = synth(c.s, r));
    const off = Math.floor(c.t * RATE), v = c.v ?? 1;
    for (let i = 0; i < snd.length && off + i < len; i++) mix[off + i] += snd[i] * v;
  }
  const n = Math.ceil(duration * RATE);
  const buf = Buffer.alloc(44 + n * 4);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 4, 4); buf.write("WAVE", 8); buf.write("fmt ", 12);
  buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22); buf.writeUInt32LE(RATE, 24);
  buf.writeUInt32LE(RATE * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34); buf.write("data", 36); buf.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) {
    const s = Math.round(Math.tanh(mix[i] * 1.1) * 30000);
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
