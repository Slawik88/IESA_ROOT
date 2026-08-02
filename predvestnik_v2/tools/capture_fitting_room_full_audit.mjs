import {mkdirSync} from 'fs';
import {resolve} from 'path';
import puppeteer from 'puppeteer';

const outputDir = resolve(process.env.OUTPUT_DIR || '/tmp/predvestnik-fitting-room-full-audit');
mkdirSync(outputDir, {recursive: true});

const browser = await puppeteer.launch({headless: 'new'});
const page = await browser.newPage();
await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
await page.goto('http://localhost:8402/', {waitUntil: 'load'});
await page.waitForFunction(() => typeof openLooksModal === 'function');
await page.mouse.click(195, 700);
await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');
await page.evaluate(() => openLooksModal());
await page.waitForFunction(() => _activePage === 'looks' && !!_looksData);
await page.evaluate(() => {
  const frostLook = {
    name_glow: 'cos_name_glow_frost',
    avatar_frame: 'cos_avatar_frame_crystal',
    avatar_halo: 'cos_avatar_halo_ice',
    title: 'cos_title_frostchild',
    profile_bg: 'cos_profile_bg_snowpeak',
    card_fx: 'cos_card_fx_snow',
  };
  Object.entries(frostLook).forEach(([slot, id]) => _looksTapUnowned(slot, id));
  _looksOpenFittingSheet();
});
await page.waitForFunction(() => document.getElementById('modal')?.open
  && document.querySelectorAll('#mb .fit-outfit-row.trial').length === 6);
await new Promise(resolveWait => setTimeout(resolveWait, 450));

const label = process.env.CAPTURE_LABEL || 'current';
const screenshot = resolve(outputDir, `${label}-390.png`);
await page.screenshot({path: screenshot});
const state = await page.evaluate(() => {
  const sheet = document.querySelector('#modal .sheet');
  const body = document.getElementById('mb');
  const profile = document.querySelector('#mb .fit-player-card');
  const rows = [...document.querySelectorAll('#mb .fit-outfit-row')];
  const footer = document.getElementById('mf');
  const rect = node => {
    if (!node) return null;
    const value = node.getBoundingClientRect();
    return {top: value.top, bottom: value.bottom, left: value.left, right: value.right,
      width: value.width, height: value.height};
  };
  return {
    sheet: rect(sheet),
    body: rect(body),
    profile: rect(profile),
    rowHeights: rows.map(row => Math.round(rect(row)?.height || 0)),
    footer: rect(footer),
    bodyScrollHeight: body?.scrollHeight || 0,
    bodyClientHeight: body?.clientHeight || 0,
    horizontalOverflow: !!body && body.scrollWidth > body.clientWidth,
  };
});

console.log(JSON.stringify({screenshot, state}, null, 2));
await browser.close();
