import {mkdirSync} from 'fs';
import {resolve} from 'path';
import puppeteer from 'puppeteer';

const outputDir = resolve(process.env.OUTPUT_DIR || '/tmp/predvestnik-avatar-pair-audit');
mkdirSync(outputDir, {recursive: true});

const label = process.env.CAPTURE_LABEL || 'current';
const frameId = process.env.FRAME_ID || 'cos_avatar_frame_inferno';
const haloId = process.env.HALO_ID || 'cos_avatar_halo_ice';
const viewportWidth = Number(process.env.VIEWPORT_WIDTH) || 390;
const viewportHeight = Number(process.env.VIEWPORT_HEIGHT) || 844;

const browser = await puppeteer.launch({headless: 'new'});
const page = await browser.newPage();
await page.setViewport({width: viewportWidth, height: viewportHeight, deviceScaleFactor: 2});
await page.goto('http://localhost:8402/', {waitUntil: 'load'});
await page.waitForFunction(() => typeof openLooksModal === 'function');
await page.evaluate(() => openLooksModal());
await page.waitForFunction(() => _activePage === 'looks' && !!_looksData);
await page.evaluate(({frameIdValue, haloIdValue}) => {
  const look = {
    name_glow: 'cos_name_glow_frost',
    avatar_frame: frameIdValue,
    avatar_halo: haloIdValue,
    title: 'cos_title_frostchild',
    profile_bg: 'cos_profile_bg_snowpeak',
    card_fx: 'cos_card_fx_snow',
  };
  Object.entries(look).forEach(([slot, id]) => _looksTapUnowned(slot, id));
  _looksOpenFittingSheet();
}, {frameIdValue: frameId, haloIdValue: haloId});
await page.waitForFunction(() => document.getElementById('modal')?.open
  && document.querySelector('#mb .fit-player-card .ava'));
await new Promise(resolveWait => setTimeout(resolveWait, 450));

const card = await page.$('#mb .fit-player-card');
const avatar = await page.$('#mb .fit-player-card .ava');
const cardBox = await card.boundingBox();
const avatarBox = await avatar.boundingBox();
const pad = 24;
const crop = {
  x: Math.max(0, avatarBox.x - pad),
  y: Math.max(0, avatarBox.y - pad),
  width: Math.min(viewportWidth, cardBox.x + cardBox.width) - Math.max(0, avatarBox.x - pad),
  height: Math.min(150, avatarBox.height + pad * 2),
};
const screenshot = resolve(outputDir, `${label}-${viewportWidth}-${frameId}-${haloId}.png`);
await page.screenshot({path: screenshot, clip: crop});

const state = await page.evaluate(() => {
  const avatarNode = document.querySelector('#mb .fit-player-card .ava');
  const style = getComputedStyle(avatarNode);
  const halo = getComputedStyle(avatarNode, '::after');
  return {
    classes: avatarNode.className,
    avatarBoxShadow: style.boxShadow,
    avatarFilter: style.filter,
    haloContent: halo.content,
    haloBorder: halo.border,
    haloBorderRadius: halo.borderRadius,
    haloBackground: halo.backgroundImage,
    haloBoxShadow: halo.boxShadow,
  };
});

console.log(JSON.stringify({screenshot, crop, state}, null, 2));
await browser.close();
