// tools/preview_server.mjs — локальный предпросмотр мини-аппа БЕЗ бэка и БД.
// Запуск: node tools/preview_server.mjs  →  http://localhost:8402/
// Отдаёт index.html (BASE=''), склеенный app.js (порядок как в main.py), app.css;
// все /api/* — реалистичные мок-JSON (формы сняты с реальных роутеров 2026-07-13).
// Сессия пре-сидится в localStorage → логин-оверлей не мешает.
// Изменения static/* рассылаются всем открытым вкладкам через SSE → ручной F5 не нужен.
// Незамоканные эндпоинты логируются в unknown-api.log рядом со скриптом.
import http from 'http';
import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';

const STATIC = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'FastAPI', 'static');
const HERE = path.dirname(fileURLToPath(import.meta.url));
const UNKNOWN_LOG = path.join(HERE, 'unknown-api.log');
const PORT = Number(process.env.PORT) || 8402;
const RECON_PREVIEW_PORT = Number(process.env.RECON_PREVIEW_PORT) || 8403;
const liveReloadClients = new Set();
let liveReloadTimer = null;
let reconstructionApi = null;
let reconstructionRestartTimer = null;
let reconstructionRestartRequested = false;
let shuttingDown = false;

// Dev-only bridge: the browser lab talks to the real Python combat engine.
// It is deliberately not part of the production FastAPI process.
const RECONSTRUCTION_WATCH_FILES = [
  path.join(HERE, 'reconstruction_preview_api.py'),
  path.join(HERE, '..', 'core', 'reconstruction.py'),
  path.join(HERE, '..', 'core', 'companions_v3.py'),
  path.join(HERE, '..', 'core', 'reconstruction_progression.py'),
  path.join(HERE, '..', 'services', 'reconstruction.py'),
  path.join(HERE, '..', 'services', 'companions_v3.py'),
  path.join(HERE, '..', 'services', 'reconstruction_combat.py'),
  path.join(HERE, '..', 'services', 'reconstruction_integrity.py'),
  path.join(HERE, '..', 'services', 'reconstruction_timing.py'),
];

function startReconstructionApi() {
  if (shuttingDown || reconstructionApi) return;
  const child = spawn('python3', [path.join(HERE, 'reconstruction_preview_api.py')], {
    cwd: path.join(HERE, '..'),
    env: { ...process.env, RECON_PREVIEW_PORT: String(RECON_PREVIEW_PORT) },
    stdio: ['ignore', 'inherit', 'inherit'],
  });
  reconstructionApi = child;
  child.on('exit', (code, signal) => {
    if (reconstructionApi === child) reconstructionApi = null;
    if (shuttingDown) return;
    if (code && code !== 0) {
      console.error(`reconstruction preview api exited with code ${code}${signal ? ` (${signal})` : ''}`);
    }
    const requested = reconstructionRestartRequested;
    reconstructionRestartRequested = false;
    setTimeout(() => {
      startReconstructionApi();
      if (requested) scheduleLiveReload('reconstruction-engine');
    }, requested ? 80 : 500).unref();
  });
}

function scheduleReconstructionRestart(changedPath = 'reconstruction-engine') {
  clearTimeout(reconstructionRestartTimer);
  reconstructionRestartTimer = setTimeout(() => {
    if (shuttingDown) return;
    reconstructionRestartRequested = true;
    if (reconstructionApi && reconstructionApi.exitCode === null) {
      reconstructionApi.kill('SIGTERM');
      return;
    }
    reconstructionRestartRequested = false;
    startReconstructionApi();
    scheduleLiveReload(changedPath);
  }, 180);
}

startReconstructionApi();

const read = (n) => fs.readFileSync(path.join(STATIC, n), 'utf8');
const PARTS = Array.from({ length: 11 }, (_, i) => `app.${String(i + 1).padStart(2, '0')}.js`);

function indexHtml() {
  let h = read('index.html')
    .replaceAll('{{BASE}}', '')
    .replaceAll('{{ASSET_VER}}', String(Date.now()))
    .replaceAll('{{BOT_USERNAME}}', 'devbot');
  // Сессия до загрузки app.js → логин-оверлей не появляется; сборщик ошибок для скриншот-прогона.
  h = h.replace('<body>', `<body>\n<script>
try{if(!localStorage.getItem('pv_sess'))localStorage.setItem('pv_sess','dev-session');}catch(e){}
window.__errs=[];
window.addEventListener('error',e=>window.__errs.push(String(e.message)));
window.addEventListener('unhandledrejection',e=>window.__errs.push('rej: '+String(e.reason)));
// Локальный live reload: обновляет все открытые вкладки после правки static/* и
// после автоматического перезапуска preview-сервера.
(()=>{
  const source=new EventSource('/__preview/live');
  let connected=false;
  source.addEventListener('open',()=>{
    if(connected) location.reload();
    connected=true;
  });
  source.addEventListener('reload',()=>location.reload());
})();
</script>`);
  return h;
}

function reconstructionGameHtml() {
  const assetVersion = String(Date.now());
  return read('reconstruction-lab.html')
    .replace('data-runtime="preview"', 'data-runtime="production"')
    .replace('data-api-base="/__reconstruction"', 'data-api-base=""')
    .replace('href="/static/reconstruction-lab.css"', `href="/static/reconstruction-lab.css?v=${assetVersion}"`)
    .replace('src="/static/reconstruction-lab.js"', `src="/static/reconstruction-lab.js?v=${assetVersion}"`)
    // Production uses the authenticated Mini App session.  This local-only
    // bootstrap creates an equivalent opaque dev session before the deferred
    // production script runs; the browser still calls only /reconstruction.
    .replace(
      '<body data-runtime="production" data-api-base="" data-app-base="">',
      '<body data-runtime="production" data-api-base="" data-app-base=""><script>try{const saved=localStorage.getItem(\'pv_sess\');if(!saved||saved===\'dev-session\'){const id=globalThis.crypto?.randomUUID?.()||`${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;localStorage.setItem(\'pv_sess\',\'preview-reconstruction-\'+id);}}catch(_){}</script>',
    );
}

// ── Мок-данные ────────────────────────────────────────────────────────────────
const PROFILE = {
  user_id: 1460945748,
  username: 'star_seeker',
  rank: '🌟 Легенда',
  mora: 125430, diamonds: 42.5, dark_mora: 340, zarniki: 1250,
  streak: 17, achievements: 23,
  account_level: 27, account_xp: 48210, xp_into: 1210, xp_to_next: 3400, xp_per_level: 3400,
  combat_power: null,
  cp_breakdown: null,
  chats: [
    { chat_tg_id: -100111, chat_title: 'Предвестники Ночи', user_level: 31, user_xp: 15400, user_messages_count_all_time: 15873, local_rank: 2 },
    { chat_tg_id: -100222, chat_title: 'Тайный Орден', user_level: 12, user_xp: 2100, user_messages_count_all_time: 3421, local_rank: 7 },
  ],
  pets: [
    { id: 1, name: 'Азраил', species_id: 'dragon', rarity: 'legendary', placement: 'active', fatigue: 12, pet_level: 8 },
    { id: 2, name: 'Луна', species_id: 'owl', rarity: 'epic', placement: 'passive', fatigue: 40, pet_level: 7 },
    { id: 3, name: 'Пух', species_id: 'hamster', rarity: 'common', placement: 'storage', fatigue: 0, pet_level: 3 },
  ],
  is_vip: true, tos_accepted: true, global_rank: 3, partner: 'moon_witch',
  cosmetics: {
    name_glow: { css: 'glow-moon', name: 'Лунный свет', lineup: 'forest' },
    avatar_frame: { css: 'frame-oak', name: 'Дубовая оправа', lineup: 'forest' },
    title: 'Предвестник Рассвета',
    lineage: { id: 'forest', source_slot: 'avatar_frame' },
  },
  system_flags: [
    { key: 'tab_zoo', enabled: true }, { key: 'tab_market', enabled: true },
    { key: 'tab_bp', enabled: true }, { key: 'tab_auction', enabled: true },
  ],
};


// Ключ: "METHOD /path". Значение: объект | функция(url)→объект | [status, объект].
const MOCKS = {
  'GET /profile/me': PROFILE,
  'GET /api/health': { status: 'ok' },
  'POST /profile/whatsnew-seen': { ok: true },
  'POST /analytics/tab': { ok: true },
  'POST /analytics/tab-duration': { ok: true },
  'GET /admin/dev-overlay/check': [404, { detail: 'нет' }],
  'GET /favicon.ico': [404, {}],
  'GET /profile/avatar': { avatar: null, vip: true },
  'GET /profile/nickname': { nickname: 'Звездочёт' },
  'GET /notifications/pending': { notifications: [] },
  'POST /notifications/seen': { ok: true },
  'GET /inventory/buffs': { buffs: [
    { icon: '🍀', label: 'Зелье удачи', mode: 'time', expires_at: '2026-07-13 21:00:00', value: 0.15 },
    { icon: '⚡', label: 'Свиток энергии', mode: 'uses', uses_left: 3 },
  ] },
  'GET /wallet/history': [
    { label: '🛒 Покупка на рынке', created_at: '2026-07-12 14:30:00', delta_mora: -1200, mora_after: 125430, note: 'Зелье удачи ×2' },
    { label: '⚔️ Награда за поход', created_at: '2026-07-12 09:12:00', delta_mora: 3400, mora_after: 126630 },
    { label: '🎡 Колесо фортуны', created_at: '2026-07-11 20:05:00', delta_zarniki: -50, zarniki_after: 1250 },
    { label: '🏛 Продажа на аукционе', created_at: '2026-07-11 16:40:00', delta_mora: 8800, mora_after: 123230, note: 'Лунный амулет' },
    { label: '💎 Обмен валют', created_at: '2026-07-10 11:00:00', delta_diamonds: 2.5, diamonds_after: 42.5 },
  ],
  'GET /marriage/': {
    married: true, marriage_id: 7, partner_name: 'moon_witch', partner_is_vip: true, days: 212,
    family_balance: 15400, family_balance_diamonds: 5, family_balance_dark_mora: 0, family_balance_zarniki: 120,
    received_gifts: [{ name: '🌹 Букет роз', sent_at: '2026-07-10 12:00:00' }],
    family_pets: [{ name: 'Звёздочка', species_id: 'unicorn', rarity: 'mythic', placement: 'active', pet_level: 10 }],
  },
  'GET /marriage/proposals': { proposals: [] },
  'GET /clans/': {
    my_clan: null,
    top: [
      { clan_id: 11, name: 'Тёмный Орден', tag: 'DARK', emblem: '🛡', total_xp: 48200, level: 8, member_count: 18, effective_max: 24 },
      { clan_id: 12, name: 'Стражи Рассвета', tag: 'DAWN', emblem: '☀️', total_xp: 36100, level: 7, member_count: 16, effective_max: 22 },
      { clan_id: 13, name: 'Лунный Круг', tag: 'MOON', emblem: '🌙', total_xp: 24900, level: 6, member_count: 14, effective_max: 20 },
    ],
    create_cost: 50000,
    max_members: 20,
    emblems: ['🛡', '⚔️', '🌙', '☀️', '🐉'],
    name_max: 24,
    tag_max: 5,
    request_items: [],
  },
  'GET /admin/my-chats': { chats: [
    { chat_tg_id: -100111, chat_title: 'Предвестники Ночи', role: 'main', local_rank: 5 },
    { chat_tg_id: -100222, chat_title: 'Тайный Орден', role: 'admin', local_rank: 4 },
  ] },

  // ── Зоопарк ──
  'GET /zoo/': {
    pets: [
      { id: 1, name: 'Азраил', species_id: 'dragon', rarity: 'legendary', placement: 'active', fatigue: 12, pet_level: 8, duplicates_collected: 4 },
      { id: 2, name: 'Луна', species_id: 'owl', rarity: 'epic', placement: 'passive', fatigue: 40, pet_level: 7, duplicates_collected: 2 },
      { id: 3, name: 'Пух', species_id: 'hamster', rarity: 'common', placement: 'passive', fatigue: 74, pet_level: 3, duplicates_collected: 0 },
      { id: 4, name: 'Гром', species_id: 'wolf', rarity: 'rare', placement: 'storage', fatigue: 0, pet_level: 6, duplicates_collected: 1 },
    ],
    available_food: {
      food_apple: { name: '🍎 Яблоко', qty: 5, restore: 20 },
      food_meat: { name: '🍖 Мясо', qty: 2, restore: 50 },
    },
    max_slots: 4, base_slots: 3, bought_slots: 1, max_purchasable: 3,
    slot_next_price: 5000, at_slot_cap: false, vip_extra_slot: 1,
    pending_hamster_mora: 120, wolf_restore: null, unicorn_ability: null,
  },
  'GET /zoo/expeditions': { expeditions: [], boosters: {} },
  'GET /zoo/expedition-options': {
    options: [
      { hours: 1, cost: 100, min_m: 150, max_m: 260, min_xp: 8, max_xp: 15, fatigue: 12 },
      { hours: 4, cost: 320, min_m: 700, max_m: 1150, min_xp: 30, max_xp: 55, fatigue: 30 },
      { hours: 8, cost: 550, min_m: 1600, max_m: 2500, min_xp: 70, max_xp: 120, fatigue: 55 },
    ],
    active_pet: { id: 1, name: 'Азраил', species_id: 'dragon', rarity: 'legendary', fatigue: 12, pet_level: 8 },
    busy: false, busy_until: null, busy_remaining_sec: null, busy_pet: null, mora: 125430,
  },

  // ── Казарма (Боёвка 3.0) ──
  'GET /barracks': {
    units: [
      { unit_id: 'ash_knight', name: 'Рыцарь Пепла', emoji: '🔥', element: 'fire', element_emoji: '🔥', element_name: 'Огонь', role: 'dd', role_emoji: '⚔️', role_name: 'Урон', rarity: 'epic', level: 6, shards: 12, owned: true, cp: 3400, atk: 420, def: 180, hp: 2400, skill: { name: 'Пламенный росчерк', desc: 'Удар по цели с поджогом на 2 хода' }, ult: { name: 'Пепельный шторм', desc: 'Урон всем врагам + поджог' }, squad_slot: 0, next_level_shards: 20, next_level_mora: 6000, unlock_shards: null },
      { unit_id: 'tide_maiden', name: 'Дева Прилива', emoji: '🌊', element: 'water', element_emoji: '💧', element_name: 'Вода', role: 'support', role_emoji: '💚', role_name: 'Поддержка', rarity: 'rare', level: 4, shards: 5, owned: true, cp: 1900, atk: 160, def: 210, hp: 2800, skill: { name: 'Волна жизни', desc: 'Лечит самого раненого союзника' }, ult: { name: 'Прилив', desc: 'Лечит весь отряд' }, squad_slot: 1, next_level_shards: 12, next_level_mora: 4000, unlock_shards: null },
      { unit_id: 'stone_guard', name: 'Страж Скалы', emoji: '⛰️', element: 'earth', element_emoji: '🪨', element_name: 'Земля', role: 'tank', role_emoji: '🛡️', role_name: 'Защита', rarity: 'rare', level: 3, shards: 2, owned: true, cp: 1500, atk: 120, def: 380, hp: 3600, skill: { name: 'Каменная кожа', desc: 'Щит на себя на 2 хода' }, ult: { name: 'Обвал', desc: 'Оглушает врага на ход' }, squad_slot: 2, next_level_shards: 12, next_level_mora: 3000, unlock_shards: null },
      { unit_id: 'void_seer', name: 'Провидица Пустоты', emoji: '🌑', element: 'void', element_emoji: '🌑', element_name: 'Пустота', role: 'dd', role_emoji: '⚔️', role_name: 'Урон', rarity: 'legendary', level: 0, shards: 14, owned: false, cp: 0, atk: 0, def: 0, hp: 0, skill: { name: 'Взгляд Бездны', desc: 'Игнорирует 40% защиты цели' }, ult: { name: 'Схлопывание', desc: 'Огромный урон одной цели' }, squad_slot: null, next_level_shards: null, next_level_mora: null, unlock_shards: 40 },
    ],
    squad: { '0': 'ash_knight', '1': 'tide_maiden', '2': 'stone_guard' },
    squad_cp: 6800, shards: 23, summon_cost: 1500, owned_count: 3,
    starter_available: false, starter_choices: [],
  },

  // ── Гача ──
  'GET /gacha/': {
    retired: true, archive_pending: true, mora: 125430, diamonds: 42.5,
    spin_types: [], saved_tokens: 7,
    saved_pity: [{type:'mora',count:23},{type:'diamond',count:4}],
    message: 'Крутки больше не продают силу и валюту. Жетоны и накопленный гарант сохранены для прозрачного разбора в Архиве.',
  },

  // ── Аукцион ──
  'GET /auction/lots': {
    lots: [
      { id: 11, seller_id: 2, item_name: 'Лунный амулет||amulet_moon', quantity: 1, min_bid: 500, buyout: 5000, ends_at: '2026-07-14 12:00:00', status: 'active', remaining_sec: 9500, current_bid: 1200, bid_count: 3, seller_name: 'moon_witch', seller_is_vip: true, item_rarity: 'epic', has_bids: true, min_next_bid: 1261, item_name_display: 'Лунный амулет', item_id_ref: 'amulet_moon', item_description: 'Слабое сияние отгоняет усталость питомцев.', item_category: 'артефакт' },
      { id: 12, seller_id: 3, item_name: '🍖 Мясо||food_meat', quantity: 5, min_bid: 200, buyout: 900, ends_at: '2026-07-13 21:30:00', status: 'active', remaining_sec: 2400, current_bid: 200, bid_count: 0, seller_name: 'grimm', seller_is_vip: false, has_bids: false, min_next_bid: 200, item_name_display: '🍖 Мясо', item_id_ref: 'food_meat', item_description: 'Восстанавливает 50 усталости.', item_category: 'еда' },
      { id: 13, seller_id: 4, item_name: 'Осколки юнита||unit_shards', quantity: 10, min_bid: 3000, buyout: 12000, ends_at: '2026-07-15 09:00:00', status: 'active', remaining_sec: 86000, current_bid: 4500, bid_count: 7, seller_name: 'night_raven', seller_is_vip: false, item_rarity: 'rare', has_bids: true, min_next_bid: 4726, item_name_display: 'Осколки юнита', item_id_ref: 'unit_shards', item_description: 'Для призыва и прокачки юнитов Казармы.', item_category: 'боёвка' },
    ],
    total: 3, page: 0, per_page: 20, has_more: false, min_bid_floor: 100,
    market_open: false,
    market_message: 'Новые лоты и ставки закрыты до проверки происхождения товаров. Активные обязательства можно просмотреть или снять.',
  },

  // ── Боевой пропуск ──
  'GET /battle_pass/status': {
    active: true, retired: true, retired_message: 'Прогресс и покупка уровней закрыты. Уже заработанные награды можно забрать.', season_label: 'Сезон 4 «Кровавая Луна»', frozen: true,
    level: 12, max_level: 30, xp: 6100, xp_in_level: 340, xp_per_level: 500, xp_to_next: 160,
    season_starts: '2026-07-01', season_ends: '2026-07-31',
    weekend_boost: { active: false, pct: 0 }, paid_track_open: true, buy_next: null,
    rewards: [
      { level: 11, free: { mora: 800, status: 'claimed' }, paid: { diamonds: 1, status: 'claimed' } },
      { level: 12, free: { mora: 1000, status: 'available' }, paid: { items: [{ item_id: 'cos_glow_ruby', name: 'Рубиновое сияние', qty: 1, is_cosmetic: true, slot: 'name_glow', rarity: 'epic' }], status: 'available' } },
      { level: 13, free: { mora: 1200, status: 'locked_level' }, paid: { diamonds: 2, status: 'locked_level' } },
      { level: 14, free: { items: [{ item_id: 'food_meat', name: '🍖 Мясо', qty: 3, is_cosmetic: false }], status: 'locked_level' }, paid: { mora: 5000, status: 'locked_level' } },
    ],
  },

  // ── Квесты / Ачивки / Топ ──
  'GET /quests/-100111': {
    retired: true, message: 'Старые задания закрыты. Сохранённый прогресс показан только для истории.',
    quests: [], bonus: {retired:true}, weekly: [], weekly_bonus: {retired:true},
  },
  'GET /achievements/': [
    { id: 'messages', icon: '💬', name: 'Голос чата', level: 3, max_level: 10, progress: 15873, next_threshold: 25000, pct: 63, completed: false, next_reward: { mora: 2000 } },
    { id: 'gacha_spins', icon: '🎰', name: 'Испытатель удачи', level: 2, max_level: 10, progress: 214, next_threshold: 500, pct: 43, completed: false, next_reward: { mora: 1500, diamonds: 1 } },
    { id: 'streak', icon: '🔥', name: 'Верность', level: 5, max_level: 5, progress: 30, next_threshold: null, pct: 100, completed: true, next_reward: null },
  ],
  // Глобальный топ — формат как реальный _fmt: user_id/username/count/is_vip.
  // Сессионный игрок (1460945748) на 5-м месте — проверка строки «до топ-3».
  'GET /craft/': [
    { recipe_id: 'spin_token_craft', name: '🎟 Жетон Призыва', can_craft: true, can_craft_times: 1,
      what_is: 'Собери из осколков души — даёт бесплатную крутку Гачи.',
      ingredients_status: [ { item_id: 'soul_shard', item_name: '💠 Осколок Души', have: 7, needed: 5 } ] },
  ],
  'GET /top/global': [
    { user_id: 2, username: 'moon_witch', count: 48200, is_vip: true },
    { user_id: 7, username: 'abyss_lord', count: 39100, is_vip: true },
    { user_id: 3, username: 'grimm', count: 31050, is_vip: false },
    { user_id: 9, username: 'nightcaller', count: 22400, is_vip: false },
    { user_id: 1460945748, username: 'star_seeker', count: 15873, is_vip: true },
    { user_id: 4, username: 'night_raven', count: 8033, is_vip: false },
  ],
  'GET /top/local/-100111': [
    { user_tg_id: 2, username: 'moon_witch', nickname: 'Лунная Ведьма', count: 21450, is_vip: true },
    { user_tg_id: 1460945748, username: 'star_seeker', nickname: 'Звездочёт', count: 15873, is_vip: true },
    { user_tg_id: 3, username: 'grimm', nickname: null, count: 12200, is_vip: false },
    { user_tg_id: 4, username: 'night_raven', nickname: 'Ворон', count: 8033, is_vip: false },
    { user_tg_id: 5, username: 'sunny', nickname: null, count: 5410, is_vip: false },
  ],

  // ── Глобальная модерация (объёмы «наплыва» — для аудита UI под нагрузкой) ──
  // БЛОК 21.2: my-permissions (фронт строит вкладки по правам), матрица прав, штат.
  'GET /admin/global/my-permissions': { rank: 3, rank_name: '🌌 Главный разработчик', perms: [
    'sanction_warn_user', 'sanction_restrict_user', 'sanction_ban_user',
    'sanction_warn_chat', 'sanction_restrict_chat', 'sanction_ban_chat',
    'appeals_view', 'appeals_reply', 'appeals_resolve', 'appeals_close',
    'members_view', 'sanctions_view', 'log_view', 'chats_view_all',
    'dossier_view', 'user_search', 'local_actions_any_chat',
    'economy_balance', 'economy_items', 'economy_vip', 'promo_manage', 'log_admin_view',
    'bp_manage', 'themes_manage', 'console_overview', 'metrics_view',
    'flags_manage', 'modules_manage', 'broadcast_send', 'sql_run', 'staff_manage',
  ] },
  'GET /admin/global/permissions': {
    groups: ['🚨 Санкции', '📨 Апелляции', '🌐 Сеть чатов', '👤 Игроки и досье', '💰 Экономика', '🎫 Контент', '🖥 Система'],
    items: [
      { key: 'sanction_warn_user', label: '⚠️ Варн игроку', group: '🚨 Санкции', default: 1, locked: false, rank1: true, rank2: true, rank1_override: false, rank2_override: false },
      { key: 'sanction_restrict_user', label: '🔇 Ограничение игроку', group: '🚨 Санкции', default: 2, locked: false, rank1: false, rank2: true, rank1_override: false, rank2_override: false },
      { key: 'sanction_ban_user', label: '🚫 Бан игроку', group: '🚨 Санкции', default: 3, locked: false, rank1: false, rank2: true, rank1_override: false, rank2_override: true },
      { key: 'appeals_view', label: '📨 Видеть апелляции и диалоги', group: '📨 Апелляции', default: 1, locked: false, rank1: true, rank2: true, rank1_override: false, rank2_override: false },
      { key: 'appeals_resolve', label: '⚖️ Принимать/отклонять апелляции', group: '📨 Апелляции', default: 1, locked: false, rank1: false, rank2: true, rank1_override: true, rank2_override: false },
      { key: 'members_view', label: '👥 Списки чатов и участников', group: '🌐 Сеть чатов', default: 1, locked: false, rank1: true, rank2: true, rank1_override: false, rank2_override: false },
      { key: 'chats_view_all', label: '🌐 Видеть ВСЕ чаты бота', group: '🌐 Сеть чатов', default: 3, locked: false, rank1: false, rank2: false, rank1_override: false, rank2_override: false },
      { key: 'dossier_view', label: '🔎 Центр игрока (досье)', group: '👤 Игроки и досье', default: 3, locked: false, rank1: false, rank2: true, rank1_override: false, rank2_override: true },
      { key: 'user_search', label: '🔍 Глобальный поиск игроков', group: '👤 Игроки и досье', default: 3, locked: false, rank1: false, rank2: false, rank1_override: false, rank2_override: false },
      { key: 'economy_balance', label: '💰 Править балансы игроков', group: '💰 Экономика', default: 3, locked: false, rank1: false, rank2: false, rank1_override: false, rank2_override: false },
      { key: 'bp_manage', label: '🎫 Боевой пропуск', group: '🎫 Контент', default: 3, locked: false, rank1: false, rank2: false, rank1_override: false, rank2_override: false },
      { key: 'sql_run', label: '🖥 SQL-консоль', group: '🖥 Система', default: 3, locked: true, rank1: false, rank2: false, rank1_override: false, rank2_override: false },
      { key: 'staff_manage', label: '👮 Штат и настройка прав', group: '🖥 Система', default: 3, locked: true, rank1: false, rank2: false, rank1_override: false, rank2_override: false },
    ],
  },
  'POST /admin/global/permissions': { ok: true, groups: [], items: [] },
  'GET /admin/global/ranks': { staff: [
    { user_tg_id: 1460945748, user_tg_username: 'star_seeker', global_rank: 3, rank_name: '🌌 Главный разработчик', sanctions_30d: 18, appeals_30d: 9, last_sanction_at: '2026-07-13 21:14:00' },
    { user_tg_id: 2, user_tg_username: 'moon_witch', global_rank: 2, rank_name: '⚔️ Старший хелпер', sanctions_30d: 7, appeals_30d: 3, last_sanction_at: '2026-07-12 10:00:00' },
    { user_tg_id: 77, user_tg_username: 'helper_one', global_rank: 1, rank_name: '🛡 Хелпер', sanctions_30d: 2, appeals_30d: 0, last_sanction_at: null },
  ] },
  'GET /admin/dev/user-search': (u) => {
    const q = (u.searchParams.get('q') || '').toLowerCase();
    const all = [
      { user_tg_id: 2005, user_tg_username: 'crystal_5', nickname: 'Кристалл', global_rank: 0, global_rank_name: '👤 Пользователь', mora: 342100, zarniki: 20, is_vip: false, has_sanction: true },
      { user_tg_id: 2, user_tg_username: 'moon_witch', nickname: 'Лунная Ведьма', global_rank: 2, global_rank_name: '⚔️ Старший хелпер', mora: 88000, zarniki: 310, is_vip: true, has_sanction: false },
      { user_tg_id: 3, user_tg_username: 'grimm', nickname: null, global_rank: 0, global_rank_name: '👤 Пользователь', mora: 15200, zarniki: 0, is_vip: false, has_sanction: false },
      { user_tg_id: 2001, user_tg_username: 'spam_lord_1', nickname: null, global_rank: 0, global_rank_name: '👤 Пользователь', mora: 900, zarniki: 0, is_vip: false, has_sanction: true },
    ];
    return { results: all.filter(r => !q || (r.user_tg_username || '').includes(q) || (r.nickname || '').toLowerCase().includes(q) || String(r.user_tg_id).startsWith(q)) };
  },
  'GET /admin/dev/dm-check': { dm_ok: true, hint: null },
  'GET /admin/global/chats': { view_all: true, chats: [
    { chat_id: -100111, chat_title: 'Предвестники Ночи', role: 'main', member_count: 214, linked_title: 'Тайный Орден', is_member: true, warned_count: 3, chat_sanctioned: false },
    { chat_id: -100222, chat_title: 'Тайный Орден', role: 'admin', member_count: 37, linked_title: 'Предвестники Ночи', is_member: true, warned_count: 0, chat_sanctioned: false },
    { chat_id: -100333, chat_title: 'Логово Дракона', role: 'main', member_count: 158, is_member: false, warned_count: 12, chat_sanctioned: false },
    { chat_id: -100444, chat_title: 'Культ Бездны', role: 'plain', member_count: 96, is_member: false, warned_count: 7, chat_sanctioned: true },
    { chat_id: -100555, chat_title: 'Звёздный Совет', role: 'main', member_count: 412, linked_title: 'Совет · админка', is_member: true, warned_count: 1, chat_sanctioned: false },
    { chat_id: -100666, chat_title: 'Совет · админка', role: 'admin', member_count: 12, linked_title: 'Звёздный Совет', is_member: true, warned_count: 0, chat_sanctioned: false },
    { chat_id: -100777, chat_title: 'Око Ночи', role: 'plain', member_count: 51, is_member: false, warned_count: 0, chat_sanctioned: false },
    { chat_id: -100888, chat_title: 'Гильдия Рассвета', role: 'plain', member_count: 233, is_member: false, warned_count: 4, chat_sanctioned: false },
    { chat_id: -100999, chat_title: 'Северный Чертог', role: 'plain', member_count: 74, is_member: false, warned_count: 0, chat_sanctioned: false },
  ] },
  'GET /admin/global/chats/-100111/members': {
    total: 214, page: 1, page_size: 20, can_warn: true, can_restrict: true, can_ban: true,
    members: Array.from({ length: 20 }, (_, i) => ({
      user_tg_id: 1000 + i,
      user_tg_username: ['moon_witch', 'grimm', 'night_raven', 'sunny', 'void_walker', 'ash_knight', 'tide_maiden', 'rock_ward', 'owl_luna', 'pooh_ham'][i % 10] + (i >= 10 ? '_' + i : ''),
      is_vip: i % 5 === 0, user_level: 34 - i, global_rank: 0, global_rank_name: 'Пользователь',
      user_messages_count_all_time: 21450 - i * 900, joined_at: '2026-0' + ((i % 6) + 1) + '-12 10:00:00',
      last_message_at: '2026-07-1' + (i % 4) + ' 0' + (i % 9) + ':15:00',
      can_warn: true, can_restrict: true, can_ban: true,
    })),
  },
  'GET /admin/global/sanctions': (u) => {
    const t = u.searchParams.get('type');
    const types = ['warn', 'restrict', 'ban'];
    const reasons = ['спам-реклама сторонних ботов', 'оскорбления модерации', 'мультиаккаунт (абуз рефералки)',
      'слив закрытых наград ивента', 'попытка скупки за реал', 'NSFW в общем чате', 'токсичность после 3 предупреждений'];
    const all = Array.from({ length: 25 }, (_, i) => ({
      id: 300 - i, sanction_type: types[i % 3], target_type: i % 6 === 5 ? 'chat' : 'user',
      target_id: i % 6 === 5 ? -100444 : 2000 + i,
      target_name: i % 6 === 5 ? 'Культ Бездны' : '@' + ['dark_fox', 'spam_lord', 'x_hunter', 'nagibator', 'crystal', 'wolf_77'][i % 6] + '_' + i,
      reason: reasons[i % 7], issued_by_name: i % 4 === 0 ? '@star_seeker' : '@helper_one',
      expires_at: i % 3 === 2 ? null : '2026-07-2' + (i % 9) + ' 12:00:00',
      created_at: '2026-07-1' + (i % 4) + ' 0' + (i % 9) + ':30:00', is_active: true, revoked_by_name: null,
    }));
    return { sanctions: t ? all.filter(s => s.sanction_type === t) : all };
  },
  'GET /admin/global/log': {
    total: 137, page: 1, page_size: 25,
    logs: Array.from({ length: 25 }, (_, i) => ({
      id: 300 - i, sanction_type: ['warn', 'restrict', 'ban'][i % 3], target_type: 'user',
      target_name: '@' + ['dark_fox', 'spam_lord', 'x_hunter'][i % 3] + '_' + i,
      issued_by_name: i % 4 ? '@helper_one' : '@star_seeker', reason: i % 5 ? 'спам-реклама' : 'оскорбления',
      created_at: '2026-07-' + String(13 - (i % 10)).padStart(2, '0') + ' 14:0' + (i % 9) + ':00',
      is_active: i < 8, revoked_by_name: i >= 8 && i % 2 ? '@star_seeker' : null,
    })),
  },
  'GET /admin/global/appeals': (u) => {
    const st = u.searchParams.get('status') || 'pending';
    const mk = (id, status, extra) => ({
      id, user_name: '@repentant_' + id, sanction_type: ['ban', 'restrict', 'warn'][id % 3],
      sanction_active: true, sanction_reason: 'спам-реклама сторонних ботов',
      text: 'Здравствуйте! Это недоразумение — аккаунт взломали, рекламу слал не я. Готов подтвердить скриншотами. Прошу пересмотреть.',
      created_at: '2026-07-1' + (id % 4) + ' 09:1' + (id % 9) + ':00', status, ...extra,
    });
    if (st === 'pending') return { appeals: Array.from({ length: 8 }, (_, i) => mk(50 + i, 'pending', {})) };
    if (st === 'accepted') return { appeals: [mk(31, 'accepted', { resolved_by_name: '@star_seeker' })] };
    return { appeals: [mk(29, 'rejected', { resolved_by_name: '@helper_one' })] };
  },
  'GET /admin/global/user-case/2005': {
    username: 'crystal_5',
    sanctions: [
      { id: 295, sanction_type: 'ban', reason: 'попытка скупки за реал', revoked_at: null, expires_at: null, photos_json: '[]' },
      { id: 210, sanction_type: 'warn', reason: 'реклама в ЛС участникам', revoked_at: '2026-06-02', expires_at: null, photos_json: '[]' },
    ],
    appeals: [{ id: 51, status: 'pending' }],
  },

  // ── Консоль разработчика ──
  'GET /admin/dev/overview': {
    users_total: 1841, chats_total: 23, messages_today: 4120, vips_active: 37,
    appeals_pending: 8, sanctions_active: 25,
    mora_total: 48213400, diamonds_total: 9120.5, zarniki_total: 184230,
    bp_season: { id: 's2', label: 'Сезон 2 — Кровавая Луна', ends_at: '2026-08-31' },
  },
  'GET /admin/dev/flags': { flags: [
    { key: 'module_global_gacha', label: '🎰 Гача (глобально)', enabled: true },
    { key: 'module_global_auction', label: '🏛 Аукцион (глобально)', enabled: true },
    { key: 'module_global_exchange', label: '📈 Биржа (глобально)', enabled: true },
    { key: 'module_global_duels', label: '⚔️ Дуэли (глобально)', enabled: false },
    { key: 'module_global_events', label: '🎪 Ивенты (глобально)', enabled: true },
    { key: 'module_global_payments', label: '💳 Платежи Stars', enabled: true },
  ] },
  'GET /admin/dev/chats': { chats: [
    { chat_id: -100111, title: 'Предвестники Ночи', role: 'main', linked_title: 'Тайный Орден' },
    { chat_id: -100222, title: 'Тайный Орден', role: 'admin', linked_title: 'Предвестники Ночи' },
    { chat_id: -100333, title: 'Логово Дракона', role: 'main' },
    { chat_id: -100444, title: 'Культ Бездны', role: 'plain' },
    { chat_id: -100555, title: 'Звёздный Совет', role: 'main', linked_title: 'Совет · админка' },
  ] },
  'GET /admin/dev/chat-members': { members: Array.from({ length: 12 }, (_, i) => ({
    user_tg_id: 2000 + i, username: ['dark_fox', 'spam_lord', 'x_hunter', 'nagibator', 'crystal', 'wolf_77'][i % 6] + '_' + i,
    user_level: 25 - i, msgs: 9000 - i * 640,
  })) },
  'GET /admin/dev/user': {
    user_tg_id: 2005, user_tg_username: 'crystal_5', global_rank: 0, global_rank_name: '👤 Пользователь',
    mora: 342100, diamonds: 18.5, dark_mora: 90, zarniki: 20, active_theme: 'starfall',
    vip: { tier: 'silver', active: false, expires_at: '2026-05-01 00:00:00', started_at: '2026-04-01 00:00:00', days_left: 0, span_days: 30, total_days: 61 },
    battle_pass: { season: 's2', xp: 1240, level: 13 },
    chats: [
      { chat_tg_id: -100111, chat_title: 'Предвестники Ночи', local_rank: 0, rank_name: '👤 Участник', user_level: 21, user_messages_count_all_time: 8033, warnings: 2, is_left: false, role: 'main', group_key: 'g1' },
      { chat_tg_id: -100222, chat_title: 'Тайный Орден', local_rank: 0, rank_name: '👤 Участник', user_level: 3, user_messages_count_all_time: 120, warnings: 0, is_left: false, role: 'admin', group_key: 'g1' },
      { chat_tg_id: -100444, chat_title: 'Культ Бездны', local_rank: 0, rank_name: '👤 Участник', user_level: 9, user_messages_count_all_time: 1420, warnings: 1, is_left: true, role: 'plain', group_key: 'g2' },
    ],
    sanctions: [{ id: 295, sanction_type: 'ban', reason: 'попытка скупки за реал', expires_at: null }],
    sanctions_all: [
      { id: 295, sanction_type: 'ban', reason: 'попытка скупки за реал', expires_at: null, created_at: '2026-07-10 12:00:00', revoked_at: null, issued_by: 1460945748, issued_by_name: 'star_seeker', active: true },
      { id: 210, sanction_type: 'warn', reason: 'реклама в ЛС участникам', expires_at: null, created_at: '2026-05-28 09:00:00', revoked_at: '2026-06-02 10:00:00', issued_by: 77, issued_by_name: 'helper_one', active: false },
      { id: 118, sanction_type: 'restrict', reason: 'абуз обменника', expires_at: '2026-04-01 00:00:00', created_at: '2026-03-25 15:00:00', revoked_at: null, issued_by: 1460945748, issued_by_name: 'star_seeker', active: false },
    ],
    appeals: [
      { id: 51, sanction_id: 295, status: 'pending', created_at: '2026-07-12 09:11:00' },
      { id: 29, sanction_id: 118, status: 'rejected', created_at: '2026-03-26 11:00:00' },
    ],
    grant_log: [
      { action: 'balance', detail: '🪙 Мора', amount: -50000, reason: 'откат абуза биржи', created_at: '2026-07-13 21:14:00', admin_name: 'star_seeker' },
      { action: 'item', detail: '🎟 Жетон крутки', amount: 3, reason: 'компенсация бага', created_at: '2026-07-01 10:00:00', admin_name: 'star_seeker' },
    ],
    mod_log: [
      { chat_id: -100111, chat_title: 'Предвестники Ночи', action: 'warn', reason: 'флуд', created_at: '2026-07-11 20:30:00', admin_name: 'moon_witch' },
      { chat_id: -100111, chat_title: 'Предвестники Ночи', action: 'mute', reason: 'оскорбления', created_at: '2026-07-09 18:12:00', admin_name: 'moon_witch' },
    ],
    last_seen: { at: '2026-07-13 22:40:00', chat_title: 'Предвестники Ночи' },
    inventory: [
      { item_id: 'food_apple', quantity: 14, name: '🍎 Яблоко' }, { item_id: 'food_meat', quantity: 3, name: '🍖 Мясо' },
      { item_id: 'spin_token_mora', quantity: 7, name: '🎟 Жетон крутки' }, { item_id: 'gacha_luck', quantity: 2, name: '🍀 Зелье удачи' },
      { item_id: 'exp_boost_2h', quantity: 1, name: '⏩ Ускоритель похода' },
    ],
  },
  'GET /admin/dev/admin-log': { log: [
    { created_at: '2026-07-13 21:14:00', admin_id: 1460945748, admin_name: 'star_seeker', target_id: 2005, target_name: 'crystal_5', action: 'balance', detail: '🪙 Мора', amount: -50000, before_val: 392100, after_val: 342100, reason: 'откат абуза биржи' },
    { created_at: '2026-07-13 20:02:00', admin_id: 1460945748, admin_name: 'star_seeker', target_id: 2001, target_name: 'spam_lord_1', action: 'give_item', detail: '🎟 Жетон крутки', amount: 3, before_val: 0, after_val: 3, reason: 'компенсация бага гачи' },
    { created_at: '2026-07-12 18:40:00', admin_id: 1460945748, admin_name: 'star_seeker', target_id: 0, action: 'sql_mutation', detail: 'UPDATE users SET user_balance_mora=... WHERE user_tg_id=2001' },
    { created_at: '2026-07-12 15:11:00', admin_id: 1460945748, admin_name: 'star_seeker', target_id: 2010, target_name: 'wolf_77_4', action: 'balance', detail: '💎 Алмазы', amount: 5, before_val: 0, after_val: 5, reason: '' },
    { created_at: '2026-07-11 12:00:00', admin_id: 1460945748, admin_name: 'star_seeker', target_id: 0, action: 'season_upsert', detail: 's2 · Сезон 2 — Кровавая Луна' },
  ] },
  'GET /admin/dev/analytics': {
    dau: 214, wau: 619, mau: 1204,
    top_tabs: [
      { tab: 'profile', views: 4820, users: 201, avg_dwell_sec: 74 }, { tab: 'zoo', views: 3110, users: 188, avg_dwell_sec: 122 },
      { tab: 'market', views: 2470, users: 164, avg_dwell_sec: 96 }, { tab: 'arena', views: 1980, users: 141, avg_dwell_sec: 210 },
      { tab: 'bp', views: 940, users: 96, avg_dwell_sec: 48 }, { tab: 'admin', views: 320, users: 18, avg_dwell_sec: 260 },
    ],
    top_subtabs: [
      { tab: 'market/gacha', views: 1710, users: 130, avg_dwell_sec: 84 }, { tab: 'profile/inv', views: 1320, users: 150, avg_dwell_sec: 40 },
      { tab: 'arena/gates', views: 880, users: 92, avg_dwell_sec: 190 },
    ],
    daily: Array.from({ length: 14 }, (_, i) => ({ date: '2026-07-' + String(i + 1).padStart(2, '0'), sessions: 300 + i * 12, users: 150 + i * 6 })),
  },
  'GET /admin/dev/bp/seasons': { frozen: false, seasons: [
    { id: 's1', label: 'Сезон 1 — Пробуждение', active: false, starts_at: '2026-04-01', ends_at: '2026-06-30', source: 'registry' },
    { id: 's2', label: 'Сезон 2 — Кровавая Луна', active: true, starts_at: '2026-07-01', ends_at: '2026-08-31', source: 'db' },
  ] },
  'GET /admin/dev/bp/rewards': { season_id: 's2', rewards: Array.from({ length: 20 }, (_, i) => {
    const level = Math.floor(i / 2) + 1, track = i % 2 ? 'paid' : 'free';
    return { level, track, mora: track === 'paid' ? level * 900 : level * 300, diamonds: track === 'paid' && level % 3 === 0 ? 5 : 0,
      items: level % 4 === 0 ? [['spin_token_mora', 1]] : [], source: level % 5 === 0 ? 'db' : 'registry' };
  }) },
  'GET /admin/dev/bp/cosmetics-catalog': {},
  'GET /admin/dev/bp/xp-actions': { xp_per_level: 100, weekend_boost_pct: 25, actions: [
    { metric: 'messages', label: 'Сообщения в чате', weight: 2, daily_cap: 120, enabled: true, is_override: false },
    { metric: 'gacha_spins', label: 'Крутки гачи', weight: 10, daily_cap: 100, enabled: true, is_override: true },
    { metric: 'expedition_done', label: 'Завершённые походы', weight: 25, daily_cap: 0, enabled: true, is_override: false },
    { metric: 'duel_wins', label: 'Победы в дуэлях', weight: 30, daily_cap: 150, enabled: false, is_override: true },
    { metric: 'quest_done', label: 'Выполненные квесты', weight: 20, daily_cap: 0, enabled: true, is_override: false },
  ] },
  'GET /admin/dev/broadcast/audience-counts': { main: 14, admin: 9, main_admin: 23, dm_admin: 251, dm: 242, all: 265 },
  'GET /admin/dev/promocodes': { promocodes: [
    { code: 'LUNA2026', is_active: true, activations_count: 141, max_activations: 500, valid_until: '2026-08-01 00:00' },
    { code: 'SORRY-GACHA', is_active: true, activations_count: 89, max_activations: 0, valid_until: null },
    { code: 'START30', is_active: false, activations_count: 500, max_activations: 500, valid_until: null },
    { code: 'VIP-COMP', is_active: true, activations_count: 4, max_activations: 20, valid_until: '2026-07-20 00:00' },
  ] },
  'GET /admin/dev/items': { items: [
    { item_id: 'food_apple', name: '🍎 Яблоко', category: 'food', description: '+20 усталости' },
    { item_id: 'food_meat', name: '🍖 Мясо', category: 'food', description: '+50 усталости' },
    { item_id: 'spin_token_mora', name: '🎟 Жетон крутки', category: 'utility', description: 'Бесплатная крутка' },
    { item_id: 'gacha_luck', name: '🍀 Зелье удачи', category: 'booster', description: '+15% к шансу' },
  ] },
  'GET /admin/dev/theme-templates': { templates: [] },
  'GET /admin/dev/chat-modules/-100111': { modules: { module_shop: 1, module_gacha: 1, module_expeditions: 1, module_auction: 0, module_games: 1, module_exchange: 1, module_quests: 1, module_zoo: 1, module_warps: 0, module_daily_deal: 1 } },

  // ── Темы чата ──
  'GET /themes/': [
    { theme_id: 'classic', name: 'Классика', rarity: 'common', badge: '⬜', rarity_label: 'Обычная', source: 'start', desc: 'Стандартная рамка сообщений бота.', top: '━━━━━━━━━━', bot_line: '━━━━━━━━━━', accent: '▪', price_mora: null, price_diamonds: null, price_dark: null, price_zarniki: null, owned: true, active: true, gacha: false, it: false, premium: false },
    { theme_id: 'starfall', name: 'Звездопад', rarity: 'rare', badge: '🟦', rarity_label: 'Редкая', source: 'shop_mora', desc: 'Падающие звёзды обрамляют каждое сообщение.', top: '✦ ˚ · . ✦ ˚ ·', bot_line: '· ˚ ✦ . · ˚ ✦', accent: '✦', price_mora: 15000, price_diamonds: null, price_dark: null, price_zarniki: null, owned: true, active: false, gacha: false, it: false, premium: false },
    { theme_id: 'bloodmoon', name: 'Кровавая Луна', rarity: 'epic', badge: '🟪', rarity_label: 'Эпическая', source: 'shop_diamond', desc: 'Багровое сияние затмения.', top: '🌘━━━━━━━🌒', bot_line: '🌘━━━━━━━🌒', accent: '🌑', price_mora: null, price_diamonds: 25, price_dark: null, price_zarniki: null, owned: false, active: false, gacha: false, it: false, premium: false },
    { theme_id: 'golden_dawn', name: 'Золотой Рассвет', rarity: 'legendary', badge: '🟨', rarity_label: 'Легендарная', source: 'gacha_premium', desc: 'Первый луч солнца в вечной тьме.', top: '☀️═══════☀️', bot_line: '☀️═══════☀️', accent: '✨', price_mora: null, price_diamonds: null, price_dark: null, price_zarniki: null, owned: false, active: false, gacha: true, it: false, premium: false },
    { theme_id: 'neon_terminal', name: 'Неоновый Терминал', rarity: 'zarniki', badge: '✨', rarity_label: 'Зарниковая', source: 'zarniki', desc: 'IT-стиль: зелёный курсор, поток кода.', top: '▚▞▚▞▚▞▚▞▚▞', bot_line: '▞▚▞▚▞▚▞▚▞▚', accent: '▓', price_mora: null, price_diamonds: null, price_dark: null, price_zarniki: 440, owned: false, active: false, gacha: false, it: true, premium: true },
    // Реальные длинные/безпробельные строки из core/themes.py (theme_system_override,
    // theme_bloodmoon) — воспроизводят баг «вкладка Темы растягивает сайт по ширине».
    { theme_id: 'system_override', name: '💻 System Override', rarity: 'zarniki', badge: '✨', rarity_label: 'Зарниковая', source: 'zarniki', desc: 'Взлом системы. Кибер-терминальный стиль.', top: '▼ 💻 ＳＹＳＴＥＭ_ＯＶＥＲＲＩＤＥ 💻 ▼', bot_line: '*>_ Проснись, Нео. Ты всё ещё в чате… ▮* 🟢', accent: '💻', price_mora: null, price_diamonds: null, price_dark: null, price_zarniki: 400, owned: false, active: false, gacha: false, it: true, premium: true },
    { theme_id: 'bloodmoon2', name: '🩸 Кровавая Луна', rarity: 'mythic', badge: '🟥', rarity_label: 'Мифическая', source: 'zarniki', desc: 'Багровое сияние затмения.', top: '🩸🌕 КРОВАВАЯ ЛУНА 🌕🩸\n🩸🌕🩸🌕🩸🌕🩸🌕🩸🌕🩸', bot_line: '🩸🌕🩸🌕🩸🌕🩸🌕🩸🌕🩸', accent: '🩸', price_mora: null, price_diamonds: null, price_dark: null, price_zarniki: 500, owned: false, active: false, gacha: false, it: false, premium: false },
  ],

  // ── Инвентарь ──
  'GET /inventory/': [
    { item_id: 'food_apple', name: '🍎 Яблоко', quantity: 5, category: 'food', description: 'Восстанавливает 20 усталости питомца.', fatigue_restore: 20 },
    { item_id: 'food_meat', name: '🍖 Мясо', quantity: 2, category: 'food', description: 'Восстанавливает 50 усталости питомца.', fatigue_restore: 50 },
    { item_id: 'exp_boost_2h', name: '⏩ Ускоритель похода (2ч)', quantity: 1, category: 'utility', description: 'Сокращает текущий поход на 2 часа.', boost_hours: 2 },
    { item_id: 'spin_token_mora', name: '🎟 Жетон крутки', quantity: 3, category: 'utility', description: 'Одна бесплатная крутка Гачи за Мору.', spin_type: 'mora' },
    { item_id: 'study_notes', name: '📚 Конспекты', quantity: 1, category: 'booster', description: '+50% XP чата на 4 часа.' },
  ],

  // ── Аукцион: мои лоты / резерв ──
  'GET /auction/my-lots': { lots: [], bids: [] },
  'GET /auction/reserved': { reserved: 0 },

  // ── Обменник и биржа ──
  'GET /exchange/': {
    active: false, policy_version: 'owner-v3-provisional-1',
    mora: 125430, diamonds: 42.5,
    title: 'У валют разные задачи',
    mora_rule: 'Мора оплачивает подготовку, торговлю и проекты.',
    diamonds_rule: 'Алмазы выдаются за испытания и сезонные рубежи.',
    blocked_rule: 'Покупка и продажа Алмазов за Мору отключены.',
  },
  'GET /exchange/crypto': {
    coins: [
      { id: 'lunite', name: 'Лунит', emoji: '🌙', price: 1240, change_24h: 4.2, candles: [{o:1180,h:1250,l:1170,c:1210},{o:1210,h:1260,l:1200,c:1235},{o:1235,h:1280,l:1220,c:1240},{o:1240,h:1255,l:1190,c:1225},{o:1225,h:1265,l:1215,c:1240}], holding: 12.5, value: 15500, avg_buy: 1100, pnl_abs: 1750, pnl_pct: 12.7, starred: true },
      { id: 'voidshard', name: 'Осколок Пустоты', emoji: '🌑', price: 480, change_24h: -2.8, candles: [{o:520,h:530,l:490,c:500},{o:500,h:510,l:470,c:485},{o:485,h:495,l:460,c:470},{o:470,h:500,l:465,c:490},{o:490,h:495,l:475,c:480}], holding: 0, value: 0, avg_buy: 0, pnl_abs: 0, pnl_pct: 0, starred: false },
      { id: 'stardust', name: 'Звёздная Пыль', emoji: '✨', price: 92, change_24h: 11.5, candles: [{o:78,h:85,l:76,c:82},{o:82,h:88,l:80,c:86},{o:86,h:95,l:84,c:90},{o:90,h:96,l:88,c:93},{o:93,h:97,l:89,c:92}], holding: 340, value: 31280, avg_buy: 60, pnl_abs: 10880, pnl_pct: 53.3, starred: false },
    ],
    mora: 125430, portfolio_value: 46780, total_pnl: 12630,
  },
  'GET /exchange/crypto/alerts': { alerts: [] },

  // ── Премиум-хаб ──
  'GET /payments/zarniki/packages': {
    per_star: 10,
    packages: [
      { stars: 20, zarniki: 200, bonus: 15, total: 215, popular: false },
      { stars: 50, zarniki: 500, bonus: 50, total: 550, popular: false },
      { stars: 100, zarniki: 1000, bonus: 100, total: 1100, popular: true },
      { stars: 200, zarniki: 2000, bonus: 200, total: 2200, popular: false },
      { stars: 300, zarniki: 3000, bonus: 300, total: 3300, popular: false },
      { stars: 400, zarniki: 4000, bonus: 400, total: 4400, popular: false },
    ],
    custom_min: 1, custom_max: 100000,
  },
  'GET /vip/status': {
    active: true, tier: '1m', tier_label: 'VIP-1М', expires_at: '2026-09-22T00:00:00',
    days_left: 20, seniority_days: 96, seniority_months: 3,
    perks: ['👑 Оформление имени и профиля', '🎨 Дополнительные образы', '📊 Расширенная личная история', '🤖 Больше вопросов ИИ'],
    tiers: [
      { tier: '1m', label: 'VIP-1М', tagline: 'Все сервисные возможности на 30 дней', price_zarniki: 150, base_price_zarniki: 200, savings_zarniki: 50, duration_days: 30, service_only: true },
      { tier: '2m', label: 'VIP-2М', tagline: 'Тот же сервис на более выгодный срок', price_zarniki: 250, base_price_zarniki: 400, savings_zarniki: 150, duration_days: 60, service_only: true },
    ],
  },

  // ── Магазин расходников ──
  'GET /shop/': {
    active: false, mora: 125430, diamonds: 42.5, zarniki: 1250, items: [],
    message: 'Мастерская обновляется: старые расходники больше не продаются, потому что их механики закрыты. Баланс не списывается.',
  },


  // ── События ──
  'GET /events/': { retired: true, exchange_retired: true, daily_deals: [], gacha_types: [], message: 'Старые случайные события закрыты.' },

  // ── Акции дня + витрина недели ──
  'GET /daily-deal/': {
    active: false, refreshes_at: '2026-08-24T00:00:00Z', mora: 125430, diamonds: 42.5, deals: [],
    message: 'Случайная акция закрыта. Следующая витрина покажет точный товар и цену без скрытой ротации.',
  },
  'GET /showcase/': {
    week: 'W2026-30', rotates_in_sec: 3 * 86400 + 5 * 3600,
    slots: [
      { slot_idx: 0, slot: 'name_glow', rarity: 'epic', revealed: true, purchased: false,
        cosmetic_id: 'glow_violet', name: 'Фиолетовая аура', discount_pct: 20, price_base: 440, price: 352 },
      { slot_idx: 1, slot: 'avatar_frame', rarity: 'rare', revealed: false, purchased: false },
      { slot_idx: 2, slot: 'profile_bg', rarity: 'legendary', revealed: false, purchased: false },
    ],
    bundle: { count: 3, price: 900, sum: 1200, base_sum: 1500, savings: 600 },
  },
  'POST /showcase/buy-bundle': { ok: true, count: 3, price: 900, message: '🎁 Куплен весь набор (3 шт.) за 900✨!' },

  // ── Косметика (экран «Внешний вид») ──
  // Редизайн 2026-07-29: редкость → линейки (core/cosmetics.py::LINEUPS). Мок ниже —
  // репрезентативная выборка РЕАЛЬНЫХ id/css из старых линеек; три новые японские
  // линейки включены целиком (по 15 предметов), чтобы владелец мог проверить три
  // варианта ключевых эффектов до production.
  'GET /cosmetics/': {
    vip: false,
    balances: { zarniki: 1250, mora: 125430, diamonds: 42, dark_mora: 340 },
    currency_icons: { zarniki: '✨', mora: '🪙', diamonds: '💎' },
    lineups: {
      forest:    { name: '🌲 Лесной Странник', rarity: 'common', price: [{ zarniki: 250 }], vip_required: false, blurb: 'Тёплое дерево и зелень леса — самая доступная линейка, видна всем без VIP.' },
      threshold: { name: '🔮 Порог', rarity: 'rare', price: [{ zarniki: 440 }], vip_required: true, blurb: 'Фиолетовые разломы и спокойная бирюза стражей на границе Бездны.' },
      frost:     { name: '❄️ Изморозь', rarity: 'rare', price: [{ zarniki: 440 }], vip_required: true, blurb: 'Лёд, иней и морозная тишина.' },
      inferno:   { name: '🔥 Инферно', rarity: 'epic', price: [{ zarniki: 630 }], vip_required: true, blurb: 'Пламя, угли и раскалённый металл.' },
      hanami: { name: '🌸 Ханами', rarity: 'epic', price: [{ zarniki: 630 }], vip_required: true, blurb: 'Сакура, тёплая тушь и сумеречная бумага васи — красота одного короткого цветения.' },
      celestial: { name: '✨ Небесное Сияние', rarity: 'legendary', price: [{ zarniki: 820 }], vip_required: true, blurb: 'Рассвет, аврора и солнечная корона — тёплое золото на холодном небе.' },
      void:      { name: '🌌 Бездна', rarity: 'mythic', price: [{ zarniki: 1000 }], vip_required: true, blurb: 'Глубокий космос, разломы и тихое затмение.' },
      artifact:  { name: '⚡ Артефакт', rarity: 'artifact', price: [{ zarniki: 1500 }], vip_required: true, blurb: 'Голографическая энергия: циан+магента+золото, техно-язык.' },
      moon_lotus: { name: '🪷 Лунный Лотос', rarity: 'artifact', price: [{ zarniki: 1500 }], vip_required: true, blurb: 'Перламутровый лотос на ночной воде: серебряный свет, тихая рябь и глубокий индиго.' },
      ryujin_tide: { name: '🐉 Прилив Рюдзина', rarity: 'artifact', price: [{ zarniki: 1500 }], vip_required: true, blurb: 'Драконий поток в языке суми-э: штормовая вода, чёрный лак и прожилки кинцуги.' },
    },
    curated_looks: [
      { id: 'hanami_washi_dawn', name: 'Рассвет на васи', mood: 'Тихий сад, живая тушь и первый лепесток.', lineup: 'hanami', owned_count: 0, total_count: 6, missing_price: 3780, fully_owned: false,
        items: { name_glow: 'cos_name_glow_hanami_ink', avatar_frame: 'cos_avatar_frame_hanami_branches', avatar_halo: 'cos_avatar_halo_hanami_petals', title: 'cos_title_hanami_witness', profile_bg: 'cos_profile_bg_hanami_washi', card_fx: 'cos_card_fx_hanami_drift' } },
      { id: 'hanami_lantern_rain', name: 'Фонари после дождя', mood: 'Тёплый свет, мокрый лак и мотыльки в сумерках.', lineup: 'hanami', owned_count: 0, total_count: 6, missing_price: 3780, fully_owned: false,
        items: { name_glow: 'cos_name_glow_hanami_lantern', avatar_frame: 'cos_avatar_frame_hanami_goldleaf', avatar_halo: 'cos_avatar_halo_hanami_afterglow', title: 'cos_title_hanami_witness', profile_bg: 'cos_profile_bg_hanami_rain', card_fx: 'cos_card_fx_hanami_moths' } },
      { id: 'lotus_full_moon', name: 'Тишина полнолуния', mood: 'Перламутровый цветок и круги на неподвижной воде.', lineup: 'moon_lotus', owned_count: 0, total_count: 6, missing_price: 9000, fully_owned: false,
        items: { name_glow: 'cos_name_glow_moon_lotus', avatar_frame: 'cos_avatar_frame_moon_lotus', avatar_halo: 'cos_avatar_halo_moon_ripple', title: 'cos_title_moon_lotus', profile_bg: 'cos_profile_bg_moon_lotus', card_fx: 'cos_card_fx_moon_lotus' } },
      { id: 'lotus_eclipse_garden', name: 'Сад затмения', mood: 'Жемчужная дорожка, тёмная луна и живые огни.', lineup: 'moon_lotus', owned_count: 0, total_count: 6, missing_price: 9000, fully_owned: false,
        items: { name_glow: 'cos_name_glow_lotus_pearl', avatar_frame: 'cos_avatar_frame_lotus_petal_orbit', avatar_halo: 'cos_avatar_halo_lotus_moonwake', title: 'cos_title_moon_lotus', profile_bg: 'cos_profile_bg_lotus_eclipse', card_fx: 'cos_card_fx_lotus_fireflies' } },
      { id: 'ryujin_storm_ink', name: 'Чернила шторма', mood: 'Суми-э поток, морская чешуя и короткая золотая вспышка.', lineup: 'ryujin_tide', owned_count: 0, total_count: 6, missing_price: 9000, fully_owned: false,
        items: { name_glow: 'cos_name_glow_ryujin_ink', avatar_frame: 'cos_avatar_frame_ryujin_scale', avatar_halo: 'cos_avatar_halo_ryujin_tide', title: 'cos_title_ryujin_heir', profile_bg: 'cos_profile_bg_ryujin_storm', card_fx: 'cos_card_fx_ryujin_lightning' } },
      { id: 'ryujin_sunken_palace', name: 'Дворец под приливом', mood: 'Затонувшие врата, око тайфуна и след живого дракона.', lineup: 'ryujin_tide', owned_count: 0, total_count: 6, missing_price: 9000, fully_owned: false,
        items: { name_glow: 'cos_name_glow_ryujin_foam', avatar_frame: 'cos_avatar_frame_ryujin_torii', avatar_halo: 'cos_avatar_halo_ryujin_eye', title: 'cos_title_ryujin_heir', profile_bg: 'cos_profile_bg_ryujin_palace', card_fx: 'cos_card_fx_ryujin_ink_serpent' } },
    ],
    slots: {
      name_glow: [
        { id: 'cos_name_glow_moon', name: 'Лунный свет', lineup: 'forest', rarity: 'common', css: 'glow-moon', owned: true, equipped: true, price: [{ zarniki: 250 }] },
        { id: 'cos_name_glow_frost', name: 'Ледяная вязь', lineup: 'frost', rarity: 'rare', css: 'glow-frost', owned: false, price: [{ zarniki: 440 }], desc: 'Хрустальное ледяное свечение вокруг ника. Отображается при активной VIP.' },
        { id: 'cos_name_glow_neon', name: 'Неоновая трубка', lineup: 'artifact', rarity: 'artifact', css: 'glow-neon-tube', owned: false, price: [{ zarniki: 1500 }], vip_required: true, desc: 'Ник светится как неоновая вывеска. Показывается при активной VIP.' },
        { id: 'cos_name_glow_hanami_ink', name: 'Сакура в туши', lineup: 'hanami', rarity: 'epic', css: 'glow-hanami-ink', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_name_glow_hanami_lantern', name: 'Свет бумажного фонаря', lineup: 'hanami', rarity: 'epic', css: 'glow-hanami-lantern', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_name_glow_hanami_dew', name: 'Роса на сакуре', lineup: 'hanami', rarity: 'epic', css: 'glow-hanami-dew', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_name_glow_moon_lotus', name: 'Перламутр луны', lineup: 'moon_lotus', rarity: 'artifact', css: 'glow-moon-lotus', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_name_glow_lotus_reflection', name: 'Серебро на воде', lineup: 'moon_lotus', rarity: 'artifact', css: 'glow-lotus-reflection', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_name_glow_lotus_pearl', name: 'Жемчужная дорожка', lineup: 'moon_lotus', rarity: 'artifact', css: 'glow-lotus-pearl', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_name_glow_ryujin_ink', name: 'Грозовая каллиграфия', lineup: 'ryujin_tide', rarity: 'artifact', css: 'glow-ryujin-ink', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_name_glow_ryujin_gold', name: 'Золото в прибое', lineup: 'ryujin_tide', rarity: 'artifact', css: 'glow-ryujin-gold', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_name_glow_ryujin_foam', name: 'Пена драконьей волны', lineup: 'ryujin_tide', rarity: 'artifact', css: 'glow-ryujin-foam', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
      ],
      avatar_frame: [
        { id: 'cos_avatar_frame_oak', name: 'Дубовая оправа', lineup: 'forest', rarity: 'common', css: 'frame-oak', owned: true, equipped: false, price: [{ zarniki: 240 }] },
        { id: 'cos_avatar_frame_abyss', name: 'Оправа Бездны', lineup: 'threshold', rarity: 'rare', css: 'frame-abyss', owned: false, price: [{ zarniki: 440 }], desc: 'Рамка из застывшей Тёмной Моры. Отображается при активной VIP.' },
        { id: 'cos_avatar_frame_inferno', name: 'Инферно', lineup: 'inferno', rarity: 'epic', css: 'frame-inferno', owned: false, price: [{ zarniki: 630 }], desc: 'Живое пламя лижет края аватара.' },
        { id: 'cos_avatar_frame_crystal', name: 'Кристальная грань', lineup: 'frost', rarity: 'rare', css: 'frame-crystal', owned: false, price: [{ zarniki: 420 }], desc: 'Чёткая ледяная кромка с ребристым блеском.' },
        { id: 'cos_avatar_frame_hanami_branches', name: 'Ветви ханами', lineup: 'hanami', rarity: 'epic', css: 'frame-hanami-branches', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_avatar_frame_hanami_lacquer', name: 'Лак и сакура', lineup: 'hanami', rarity: 'epic', css: 'frame-hanami-lacquer', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_avatar_frame_hanami_goldleaf', name: 'Золотой лист на лаке', lineup: 'hanami', rarity: 'epic', css: 'frame-hanami-goldleaf', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_avatar_frame_moon_lotus', name: 'Жемчужный лотос', lineup: 'moon_lotus', rarity: 'artifact', css: 'frame-moon-lotus', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_avatar_frame_lotus_silver', name: 'Серебряная орбита', lineup: 'moon_lotus', rarity: 'artifact', css: 'frame-lotus-silver', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_avatar_frame_lotus_petal_orbit', name: 'Орбита лепестков', lineup: 'moon_lotus', rarity: 'artifact', css: 'frame-lotus-petal-orbit', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_avatar_frame_ryujin_kintsugi', name: 'Кинцуги Рюдзина', lineup: 'ryujin_tide', rarity: 'artifact', css: 'frame-ryujin-kintsugi', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_avatar_frame_ryujin_scale', name: 'Чешуя морского дракона', lineup: 'ryujin_tide', rarity: 'artifact', css: 'frame-ryujin-scale', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_avatar_frame_ryujin_torii', name: 'Врата в шторм', lineup: 'ryujin_tide', rarity: 'artifact', css: 'frame-ryujin-torii', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
      ],
      avatar_halo: [
        { id: 'cos_avatar_halo_void', name: 'Кольцо Бездны', lineup: 'void', rarity: 'mythic', css: 'halo-void', owned: false, price: [{ zarniki: 1000 }], desc: 'Тёмное кольцо с багровыми всполохами.' },
        { id: 'cos_avatar_halo_ice', name: 'Ледяной сполох', lineup: 'frost', rarity: 'rare', css: 'halo-ice', owned: false, price: [{ zarniki: 370 }], desc: 'Хрустальный ледяной ореол.' },
        { id: 'cos_avatar_halo_hanami_petals', name: 'Венец лепестков', lineup: 'hanami', rarity: 'epic', css: 'halo-hanami-petals', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_avatar_halo_hanami_afterglow', name: 'Послесвечение цветения', lineup: 'hanami', rarity: 'epic', css: 'halo-hanami-afterglow', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_avatar_halo_moon_ripple', name: 'Лунная рябь', lineup: 'moon_lotus', rarity: 'artifact', css: 'halo-moon-ripple', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_avatar_halo_lotus_moonwake', name: 'След полной луны', lineup: 'moon_lotus', rarity: 'artifact', css: 'halo-lotus-moonwake', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_avatar_halo_ryujin_tide', name: 'Драконий прилив', lineup: 'ryujin_tide', rarity: 'artifact', css: 'halo-ryujin-tide', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_avatar_halo_ryujin_eye', name: 'Око тайфуна', lineup: 'ryujin_tide', rarity: 'artifact', css: 'halo-ryujin-eye', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
      ],
      title: [
        { id: 'cos_title_dawnchild', name: 'Дитя Зари', lineup: 'celestial', rarity: 'legendary', css: 'title-dawnchild', text: 'Дитя Зари', owned: true, equipped: true, price: [{ zarniki: 820 }] },
        { id: 'cos_title_frostchild', name: 'Дитя Стужи', lineup: 'frost', rarity: 'rare', css: 'title-frostchild', text: 'Дитя Стужи', owned: false, price: [{ zarniki: 310 }], desc: 'Рождённый среди вечных льдов.' },
        { id: 'cos_title_hanami_witness', name: 'Свидетель Ханами', lineup: 'hanami', rarity: 'epic', css: 'title-hanami-witness', text: 'Свидетель Ханами', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_title_moon_lotus', name: 'Хранитель Лунного Лотоса', lineup: 'moon_lotus', rarity: 'artifact', css: 'title-moon-lotus', text: 'Хранитель Лунного Лотоса', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_title_ryujin_heir', name: 'Наследник Рюдзина', lineup: 'ryujin_tide', rarity: 'artifact', css: 'title-ryujin-heir', text: 'Наследник Рюдзина', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
      ],
      profile_bg: [
        { id: 'cos_profile_bg_forest', name: 'Изумрудный лес', lineup: 'forest', rarity: 'common', css: 'pbg-forest', owned: true, equipped: true, price: [{ zarniki: 310 }] },
        { id: 'cos_profile_bg_snowpeak', name: 'Снежная вершина', lineup: 'frost', rarity: 'rare', css: 'pbg-snowpeak', owned: false, price: [{ zarniki: 550 }], desc: 'Заснеженная горная вершина в морозной дымке.' },
        { id: 'cos_profile_bg_starfall', name: 'Звездопад Богов', lineup: 'void', rarity: 'mythic', css: 'pbg-starfall', owned: false, price: [{ zarniki: 1000 }], desc: 'Глубокий космос с падающими звёздами.' },
        { id: 'cos_profile_bg_hanami_washi', name: 'Сад на васи', lineup: 'hanami', rarity: 'epic', css: 'pbg-hanami-washi', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_profile_bg_hanami_lanterns', name: 'Аллея фонарей', lineup: 'hanami', rarity: 'epic', css: 'pbg-hanami-lanterns', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_profile_bg_hanami_rain', name: 'Весенний дождь на васи', lineup: 'hanami', rarity: 'epic', css: 'pbg-hanami-rain', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_profile_bg_moon_lotus', name: 'Озеро полнолуния', lineup: 'moon_lotus', rarity: 'artifact', css: 'pbg-moon-lotus', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_profile_bg_lotus_sanctuary', name: 'Святилище зеркальной воды', lineup: 'moon_lotus', rarity: 'artifact', css: 'pbg-lotus-sanctuary', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_profile_bg_lotus_eclipse', name: 'Сад во время затмения', lineup: 'moon_lotus', rarity: 'artifact', css: 'pbg-lotus-eclipse', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_profile_bg_ryujin_storm', name: 'Чернила шторма', lineup: 'ryujin_tide', rarity: 'artifact', css: 'pbg-ryujin-storm', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_profile_bg_ryujin_tempest', name: 'Храм перед бурей', lineup: 'ryujin_tide', rarity: 'artifact', css: 'pbg-ryujin-tempest', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_profile_bg_ryujin_palace', name: 'Дворец под приливом', lineup: 'ryujin_tide', rarity: 'artifact', css: 'pbg-ryujin-palace', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
      ],
      card_fx: [
        { id: 'cos_card_fx_void_echo', name: 'Эхо Пустоты', lineup: 'threshold', rarity: 'rare', css: 'cfx-void-echo', owned: false, price: [{ zarniki: 440 }], desc: 'Кольца эха расходятся из центра карточки.' },
        { id: 'cos_card_fx_snow', name: 'Снегопад', lineup: 'frost', rarity: 'rare', css: 'cfx-snow', owned: false, price: [{ zarniki: 590 }], desc: 'Тихо падающие снежинки поверх профиля.' },
        { id: 'cos_card_fx_hanami_drift', name: 'Тихий листопад', lineup: 'hanami', rarity: 'epic', css: 'cfx-hanami-drift', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_card_fx_hanami_ink_bloom', name: 'Цветение туши', lineup: 'hanami', rarity: 'epic', css: 'cfx-hanami-ink-bloom', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_card_fx_hanami_moths', name: 'Мотыльки у фонаря', lineup: 'hanami', rarity: 'epic', css: 'cfx-hanami-moths', owned: false, price: [{ zarniki: 630 }] },
        { id: 'cos_card_fx_moon_lotus', name: 'Отражение лотоса', lineup: 'moon_lotus', rarity: 'artifact', css: 'cfx-moon-lotus', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_card_fx_lotus_caustics', name: 'Жемчужная каустика', lineup: 'moon_lotus', rarity: 'artifact', css: 'cfx-lotus-caustics', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_card_fx_lotus_fireflies', name: 'Светлячки над водой', lineup: 'moon_lotus', rarity: 'artifact', css: 'cfx-lotus-fireflies', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_card_fx_ryujin_current', name: 'Течение Рюдзина', lineup: 'ryujin_tide', rarity: 'artifact', css: 'cfx-ryujin-current', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_card_fx_ryujin_lightning', name: 'Молния над морем', lineup: 'ryujin_tide', rarity: 'artifact', css: 'cfx-ryujin-lightning', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
        { id: 'cos_card_fx_ryujin_ink_serpent', name: 'Живые чернила Рюдзина', lineup: 'ryujin_tide', rarity: 'artifact', css: 'cfx-ryujin-ink-serpent', owned: false, price: [{ zarniki: 1500 }], vip_required: true },
      ],
    },
    welcome: { current: 'scanner', options: [
      { id: 'scanner', name: 'Сканер', rarity: 'common', current: true, desc: 'Классический прелоадер' },
      { id: 'nova', name: 'Вспышка', rarity: 'epic', locked: true, vip_required: true, current: false, desc: 'Премиум-приветствие' },
    ] },
  },
  'GET /cosmetics/presets': { presets: [{ id: 1, name: 'Золотой образ', loadout: {
    name_glow: 'cos_name_glow_moon', avatar_frame: 'cos_avatar_frame_oak',
    title: 'cos_title_dawnchild', profile_bg: 'cos_profile_bg_forest',
  } }] },
  'GET /cosmetics/gift/catalog': (u) => ({
    recipient_id: Number(u.searchParams.get('recipient_id')) || 999,
    items: [
      { id: 'cos_title_frostchild', name: 'Дитя Стужи', slot: 'title', rarity: 'rare', css: 'title-frostchild', text: 'Дитя Стужи', zarniki: previewCosmeticPrice('cos_title_frostchild',310), owned: false },
      { id: 'cos_avatar_halo_ice', name: 'Ледяной сполох', slot: 'avatar_halo', rarity: 'rare', css: 'halo-ice', text: null, zarniki: previewCosmeticPrice('cos_avatar_halo_ice',370), owned: false },
      { id: 'cos_avatar_frame_crystal', name: 'Кристальная грань', slot: 'avatar_frame', rarity: 'rare', css: 'frame-crystal', text: null, zarniki: previewCosmeticPrice('cos_avatar_frame_crystal',420), owned: false },
      { id: 'cos_name_glow_frost', name: 'Ледяная вязь', slot: 'name_glow', rarity: 'rare', css: 'glow-frost', text: null, zarniki: previewCosmeticPrice('cos_name_glow_frost',440), owned: false },
      { id: 'cos_avatar_frame_inferno', name: 'Инферно', slot: 'avatar_frame', rarity: 'epic', css: 'frame-inferno', text: null, zarniki: previewCosmeticPrice('cos_avatar_frame_inferno',600), owned: false },
      { id: 'cos_avatar_halo_void', name: 'Кольцо Бездны', slot: 'avatar_halo', rarity: 'mythic', css: 'halo-void', text: null, zarniki: previewCosmeticPrice('cos_avatar_halo_void',850), owned: false },
      { id: 'cos_name_glow_moon', name: 'Лунный свет', slot: 'name_glow', rarity: 'common', css: 'glow-moon', text: null, zarniki: previewCosmeticPrice('cos_name_glow_moon',250), owned: true },
    ],
  }),
  'POST /cosmetics/gift': { ok: true, message: '🎁 Подарок отправлен! −310✨' },
  // Модалка «Сюрпризы и Крафт» (_openSurprisesModal) — сундуки/крафт ОСОЗНАННО остались
  // на старой редкостной системе (r-{rarity}, без lineup), не тронуты редизайном
  // линеек (2026-07-29). Формы сняты с services/cosmetics.py::chest_catalog()/craft_catalog().
  'GET /cosmetics/chests': { chests: [
    { id: 'chest_common', name: '📦 Обычный сундук', zarniki: 150, owned: 2, odds: [
      { label: '🔹 5 осколков', pct: 50, rarity: null },
      { label: 'Косметика · Редкая', pct: 35, rarity: 'rare' },
      { label: 'Косметика · Эпическая', pct: 15, rarity: 'epic' },
    ] },
    { id: 'chest_gold', name: '🎁 Золотой сундук', zarniki: 500, owned: 0, odds: [
      { label: 'Косметика · Эпическая', pct: 60, rarity: 'epic' },
      { label: 'Косметика · Легендарная', pct: 30, rarity: 'legendary' },
      { label: 'Косметика · Мифическая', pct: 10, rarity: 'mythic' },
    ] },
  ] },
  'GET /cosmetics/craft': { shards: 42, items: [
    { id: 'cos_glow_ember', name: 'Тлеющее сияние', slot: 'name_glow', rarity: 'rare', css: 'glow-ember', text: null, cost: 15, owned: false, can: true },
    { id: 'cos_title_ashborn', name: 'Пепельнорождённый', slot: 'title', rarity: 'epic', css: null, text: 'Пепельнорождённый', cost: 30, owned: false, can: true },
    { id: 'cos_frame_iron', name: 'Железная рамка', slot: 'avatar_frame', rarity: 'rare', css: 'frame-iron', text: null, cost: 15, owned: true, can: false },
  ] },
  'POST /cosmetics/chest/buy': { ok: true, message: '🎁 Обычный сундук куплен за 150✨! Открой его ниже.' },
  'POST /cosmetics/chest/open': { message: 'Из сундука выпало!', drop: { kind: 'shards', shards: 5, name: '🔹 5 осколков' } },
  'POST /cosmetics/craft': { message: '✅ Скрафчено!' },
  'POST /cosmetics/buy-lineup': { ok: true, message: '🎨 Линейка собрана полностью! Докуплено — за ✨' },
  'POST /cosmetics/buy-many': { ok: true, message: '🎨 Локальный стенд: цены предложения показаны в каталоге.' },
  'POST /cosmetics/buy': { ok: true, message: '✨ Локальная покупка подтверждена.' },
  'POST /cosmetics/equip': { ok: true },
  'POST /cosmetics/unequip': { ok: true },

  // ── Админка чата ──
  'GET /admin/-100111/dashboard': {
    my_rank_name: '🏆 Владелец', member_count: 214, active_today: 58,
    warned_count: 3, ban_count: 1,
    can_warn: true, can_mute: true, can_kick: true, can_ban: true,
  },
  // Функция: реагирует на ?filter=banned (block 7.2). is_banned/was_kicked/global_ban —
  // как chat_sanctions_map на реальном бэке; при фильтре отдаём только их.
  'GET /admin/-100111/users': (u) => {
    const all = [
      { user_tg_id: 2, user_tg_username: 'moon_witch', is_vip: true, user_level: 34, local_rank: 4, warnings: 0, user_messages_count_all_time: 21450, joined_at: '2025-11-02 10:00:00', last_message_at: '2026-07-13 09:15:00', can_act: true, can_warn: true, can_mute: true, can_kick: true, can_ban: true, can_shield: true, can_immune: true, can_set_rank: true, is_immune: false, is_left: false, muted_until: null, is_banned: false, was_kicked: false, global_ban: false },
      { user_tg_id: 3, user_tg_username: 'grimm', is_vip: false, user_level: 22, local_rank: 1, warnings: 2, user_messages_count_all_time: 12200, joined_at: '2026-01-15 18:30:00', last_message_at: '2026-07-12 22:47:00', can_act: true, can_warn: true, can_mute: true, can_kick: true, can_ban: true, can_shield: true, can_immune: true, can_set_rank: true, is_immune: false, is_left: false, muted_until: '2026-07-14 12:00:00', is_banned: false, was_kicked: false, global_ban: false },
      { user_tg_id: 4, user_tg_username: 'night_raven', is_vip: false, user_level: 15, local_rank: 0, warnings: 0, user_messages_count_all_time: 8033, joined_at: '2026-03-08 12:00:00', last_message_at: '2026-07-13 08:02:00', can_act: true, can_warn: true, can_mute: true, can_kick: true, can_ban: true, can_shield: true, can_immune: true, can_set_rank: true, is_immune: true, is_left: false, muted_until: null, is_banned: false, was_kicked: false, global_ban: false },
      { user_tg_id: 5, user_tg_username: 'sunny', is_vip: false, user_level: 9, local_rank: 0, warnings: 0, user_messages_count_all_time: 5410, joined_at: '2026-05-20 09:10:00', last_message_at: '2026-06-30 16:20:00', can_act: true, can_warn: true, can_mute: true, can_kick: true, can_ban: true, can_shield: true, can_immune: true, can_set_rank: true, is_immune: false, is_left: true, muted_until: null, is_banned: true, was_kicked: false, global_ban: false },
      { user_tg_id: 6, user_tg_username: 'troublemaker_with_a_very_long_name', is_vip: false, user_level: 4, local_rank: 0, warnings: 3, user_messages_count_all_time: 210, joined_at: '2026-06-01 09:10:00', last_message_at: '2026-06-15 16:20:00', can_act: true, can_warn: true, can_mute: true, can_kick: true, can_ban: true, can_shield: true, can_immune: true, can_set_rank: true, is_immune: false, is_left: true, muted_until: null, is_banned: false, was_kicked: true, global_ban: false },
    ];
    const banned = u.searchParams.get('filter') === 'banned';
    const users = banned ? all.filter(x => x.is_banned || x.was_kicked || x.global_ban) : all;
    return { total: banned ? users.length : 214, page_size: 20, max_assignable_rank: 4, users };
  },
  'POST /admin/-100111/action': { ok: true, telegram_ok: true },
};

// Состояние локального стенда: темы покупаются и надеваются по-настоящему в
// памяти процесса, чтобы интерфейс после CTA показывал владение, а не ложный
// успешный тост. Reset нужен только регрессионным тестам, которые не должны
// зависеть от покупок предыдущего прогона.
const PREVIEW_THEME_SNAPSHOT = JSON.stringify(MOCKS['GET /themes/']);
const PREVIEW_BALANCE_SNAPSHOT = {
  mora: PROFILE.mora, diamonds: PROFILE.diamonds, dark_mora: PROFILE.dark_mora, zarniki: PROFILE.zarniki,
};
const PREVIEW_THEME_PURCHASES = new Map();
const PREVIEW_WEARABLE_COSMETIC_SLOTS = new Set([
  'name_glow', 'avatar_frame', 'avatar_halo', 'title', 'profile_bg', 'card_fx',
]);

// Production pricing proposal approved by the owner: the collection defines
// its segment, while the actual item price follows the visual weight of slot.
// Keep this fixture matrix byte-for-byte aligned with core/cosmetics.py; the
// server-side contract test guards the authoritative Python registry.
const PREVIEW_COSMETIC_SLOT_PRICES = {
  250:  {title:180,avatar_halo:210,avatar_frame:240,name_glow:250,profile_bg:310,card_fx:340},
  440:  {title:310,avatar_halo:370,avatar_frame:420,name_glow:440,profile_bg:550,card_fx:590},
  630:  {title:440,avatar_halo:540,avatar_frame:600,name_glow:630,profile_bg:790,card_fx:850},
  820:  {title:570,avatar_halo:700,avatar_frame:780,name_glow:820,profile_bg:1020,card_fx:1110},
  1000: {title:700,avatar_halo:850,avatar_frame:950,name_glow:1000,profile_bg:1250,card_fx:1350},
  1500: {title:800,avatar_halo:1100,avatar_frame:1250,name_glow:1350,profile_bg:1500,card_fx:1650},
};
function applyPreviewCosmeticPrices() {
  const catalog=MOCKS['GET /cosmetics/'];
  const byId=new Map();
  Object.entries(catalog.slots).forEach(([slot,items])=>items.forEach(item=>{
    const meta=catalog.lineups[item.lineup];
    const base=Number(meta?.price?.[0]?.zarniki)||0;
    const price=PREVIEW_COSMETIC_SLOT_PRICES[base]?.[slot];
    if(price) item.price=[{zarniki:price}];
    byId.set(item.id,{...item,slot});
  }));
  Object.values(catalog.lineups).forEach(meta=>{
    const base=Number(meta?.price?.[0]?.zarniki)||0;
    const values=Object.values(PREVIEW_COSMETIC_SLOT_PRICES[base]||{});
    if(values.length) meta.price_range={min:Math.min(...values),max:Math.max(...values)};
  });
  catalog.curated_looks.forEach(look=>{
    look.missing_price=Object.values(look.items).reduce((sum,id)=>sum+(byId.get(id)?.price?.[0]?.zarniki||0),0);
  });
}
applyPreviewCosmeticPrices();

// Saved looks are a full wearable snapshot in production: omitted slots are
// deliberately cleared, while the independent welcome animation is untouched.
// Keep the preview's catalog and /profile/me response coupled the same way.
const PREVIEW_COSMETICS_SNAPSHOT = JSON.stringify({
  catalog: MOCKS['GET /cosmetics/'],
  presets: MOCKS['GET /cosmetics/presets'],
  profileCosmetics: PROFILE.cosmetics,
});

function previewCosmeticPrice(cosmeticId,fallback=0){
  const catalog=MOCKS['GET /cosmetics/'];
  for(const items of Object.values(catalog.slots||{})){
    const item=items.find(candidate=>candidate.id===cosmeticId);
    if(item) return Number(item.price?.[0]?.zarniki)||fallback;
  }
  return fallback;
}

function previewActiveCosmetics() {
  const catalog=MOCKS['GET /cosmetics/'];
  const out={welcome: PROFILE.cosmetics?.welcome || 'scanner'};
  for(const slot of PREVIEW_WEARABLE_COSMETIC_SLOTS){
    const item=(catalog.slots?.[slot]||[]).find(candidate=>candidate.equipped);
    if(!item) continue;
    if(slot==='title'){
      out.title=item.text||item.name;
      if(item.css) out.title_css=item.css;
      continue;
    }
    out[slot]={css:item.css, name:item.name, lineup:item.lineup};
  }
  for(const source_slot of ['avatar_frame','avatar_halo','card_fx','profile_bg']){
    const item=out[source_slot];
    if(item?.lineup){
      out.lineage={id:item.lineup,source_slot};
      break;
    }
  }
  return out;
}

function applyPreviewPreset(presetId) {
  const presets=MOCKS['GET /cosmetics/presets'].presets||[];
  const preset=presets.find(item=>Number(item.id)===Number(presetId));
  if(!preset) return {ok:false, detail:'Пресет не найден.'};
  if(!preset.loadout || typeof preset.loadout!=='object' || Array.isArray(preset.loadout)) {
    return {ok:false, detail:'Не удалось применить образ: сохранённый набор повреждён. Текущий внешний вид не изменён.'};
  }

  const catalog=MOCKS['GET /cosmetics/'];
  const selected=[];
  for(const [slot, cosmeticId] of Object.entries(preset.loadout)){
    if(!PREVIEW_WEARABLE_COSMETIC_SLOTS.has(slot) || typeof cosmeticId!=='string') {
      return {ok:false, detail:'Не удалось применить образ: сохранённый набор повреждён. Текущий внешний вид не изменён.'};
    }
    const item=(catalog.slots?.[slot]||[]).find(candidate=>candidate.id===cosmeticId);
    if(!item || !item.owned) {
      return {ok:false, detail:'Не удалось применить образ: один из предметов больше недоступен. Текущий внешний вид не изменён. Сохрани образ заново.'};
    }
    selected.push(item);
  }

  // Mutation starts only after the whole snapshot has passed validation.
  for(const slot of PREVIEW_WEARABLE_COSMETIC_SLOTS){
    for(const item of catalog.slots?.[slot]||[]) item.equipped=false;
  }
  for(const item of selected) item.equipped=true;
  PROFILE.cosmetics=previewActiveCosmetics();
  return {ok:true, message:`✅ Образ «${preset.name}» применён!`};
}

function resetPreviewThemeState() {
  const themes = MOCKS['GET /themes/'];
  themes.splice(0, themes.length, ...JSON.parse(PREVIEW_THEME_SNAPSHOT));
  Object.assign(PROFILE, PREVIEW_BALANCE_SNAPSHOT);
  const cosmetics=JSON.parse(PREVIEW_COSMETICS_SNAPSHOT);
  MOCKS['GET /cosmetics/']=cosmetics.catalog;
  MOCKS['GET /cosmetics/presets']=cosmetics.presets;
  PROFILE.cosmetics=cosmetics.profileCosmetics;
  PREVIEW_THEME_PURCHASES.clear();
}
async function readJsonBody(req) {
  const chunks=[];
  for await (const chunk of req) chunks.push(chunk);
  const raw=Buffer.concat(chunks).toString('utf8').trim();
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return null; }
}
function themePrice(t) {
  if (t.price_mora) return { balance: 'mora', amount: t.price_mora };
  if (t.price_diamonds) return { balance: 'diamonds', amount: t.price_diamonds };
  if (t.price_zarniki) return { balance: 'zarniki', amount: t.price_zarniki };
  if (t.price_dark) return { balance: 'dark_mora', amount: t.price_dark };
  return null;
}

function send(res, status, body, type = 'application/json; charset=utf-8') {
  res.writeHead(status, {
    'content-type': type,
    'access-control-allow-origin': '*',
    'cache-control': 'no-store',
  });
  res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

function methodNotAllowed(res, methods) {
  res.writeHead(405, {
    'content-type': 'application/json; charset=utf-8',
    'access-control-allow-origin': '*',
    'cache-control': 'no-store',
    allow: methods.join(', '),
  });
  res.end(JSON.stringify({detail:'Method Not Allowed'}));
}

const PREVIEW_GET_ONLY_PATHS = new Set([
  '/', '/index.html', '/game', '/__preview/reconstruction-lab',
  '/static/app.css', '/static/app.js', '/static/app.devmode.js',
  '/static/reconstruction-lab.css', '/static/reconstruction-lab.js', '/static/icons/x.svg',
  '/manifest.json', '/updates.json',
]);
const PREVIEW_POST_ONLY_PATHS = new Set([
  '/themes/buy', '/themes/equip', '/payments/zarniki/invoice', '/__preview/reset',
]);
const retiredMutationPaths = new Set([
  '/gacha/spin', '/gacha/spin-multi', '/shop/buy', '/daily-deal/buy',
  '/cosmetics/chest/buy', '/cosmetics/chest/open', '/cosmetics/craft',
  '/battle_pass/buy-level', '/auction/create', '/auction/create-pet',
  '/auction/bid', '/barracks/starter', '/barracks/summon',
  '/barracks/levelup', '/barracks/engrave', '/barracks/unlock', '/barracks/squad',
]);

function allowedMethodsForPreviewPath(pathname) {
  // Mocks are the first source of the adapter's contract: retain every method
  // declared for an exact path instead of allowing a typo to look successful.
  const methods=new Set(Object.keys(MOCKS)
    .filter(key=>key.slice(key.indexOf(' ')+1)===pathname)
    .map(key=>key.slice(0,key.indexOf(' '))));
  if(PREVIEW_GET_ONLY_PATHS.has(pathname)
    || pathname.startsWith('/profile/u/') || pathname.startsWith('/themes/preview/')) methods.add('GET');
  if(PREVIEW_POST_ONLY_PATHS.has(pathname)) methods.add('POST');
  if(/^\/cosmetics\/presets\/\d+\/apply$/.test(pathname)) methods.add('POST');
  if(/^\/cosmetics\/presets\/\d+$/.test(pathname)) {
    methods.add('PATCH'); methods.add('DELETE');
  }
  if(retiredMutationPaths.has(pathname)) methods.add('POST');
  return methods.size ? [...methods] : null;
}

function redirectTrailingSlash(req, res, canonicalPath) {
  res.writeHead(307, {
    // Starlette's RedirectResponse writes an absolute Location based on the
    // request host.  Preserve that observable contract in the local mirror.
    location: new URL(canonicalPath, `http://${req.headers.host || `localhost:${PORT}`}`).toString(),
    'cache-control': 'no-store',
  });
  res.end();
}

function publicTrailingSlashTarget(pathname, search) {
  if (pathname.length <= 1 || !pathname.endsWith('/')) return null;
  const target = pathname.slice(0, -1);
  const publicRoute = target === '/game' || target === '/index.html'
    || target === '/manifest.json' || target === '/updates.json'
    || target === '/reconstruction' || target.startsWith('/reconstruction/')
    || [
      '/static/app.css', '/static/app.js', '/static/app.devmode.js',
      '/static/reconstruction-lab.css', '/static/reconstruction-lab.js',
      '/static/icons/x.svg',
    ].includes(target);
  return publicRoute ? `${target}${search}` : null;
}

function proxyReconstruction(req, res, pathname, { productionContract = false } = {}) {
  const suffix = pathname.slice('/__reconstruction'.length);
  const bridgePath = productionContract && !suffix.startsWith('/companions')
    ? `/production${suffix}`
    : (suffix || '/state');
  const session = req.headers['x-reconstruction-session'] || req.headers['x-session-token'] || 'default';
  const upstream = http.request({
    hostname: '127.0.0.1',
    port: RECON_PREVIEW_PORT,
    path: bridgePath,
    method: req.method,
    headers: {
      'content-type': req.headers['content-type'] || 'application/json',
      'x-reconstruction-session': session,
      ...(req.headers['x-reconstruction-test-clock']
        ? { 'x-reconstruction-test-clock': req.headers['x-reconstruction-test-clock'] }
        : {}),
      ...(req.headers['content-length'] ? { 'content-length': req.headers['content-length'] } : {}),
    },
  }, (upstreamRes) => {
    res.writeHead(upstreamRes.statusCode || 502, {
      'content-type': upstreamRes.headers['content-type'] || 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    });
    upstreamRes.pipe(res);
  });
  upstream.on('error', (error) => send(res, 503, {
    detail: `Движок реконструкции ещё запускается: ${error.code || error.message}`,
  }));
  req.pipe(upstream);
}

function attachLiveReload(req, res) {
  res.writeHead(200, {
    'content-type': 'text/event-stream; charset=utf-8',
    'cache-control': 'no-store',
    connection: 'keep-alive',
    'access-control-allow-origin': '*',
  });
  res.write('retry: 500\n: connected\n\n');
  liveReloadClients.add(res);
  req.on('close', () => liveReloadClients.delete(res));
}

function scheduleLiveReload(changedPath = '') {
  clearTimeout(liveReloadTimer);
  liveReloadTimer = setTimeout(() => {
    const payload = `event: reload\ndata: ${JSON.stringify({changedPath, at: Date.now()})}\n\n`;
    for (const client of liveReloadClients) client.write(payload);
  }, 120);
}

const staticWatcher = fs.watch(STATIC, {recursive: true}, (_event, changedPath) => {
  scheduleLiveReload(changedPath ? String(changedPath) : 'static');
});
const reconstructionWatchers = RECONSTRUCTION_WATCH_FILES.map((filePath) => fs.watch(
  filePath,
  () => scheduleReconstructionRestart(path.relative(path.join(HERE, '..'), filePath)),
));

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, `http://localhost:${PORT}`);
  const p = u.pathname;

  // FastAPI's redirect_slashes normalizes the public routes below with a 307.
  // Match that behavior rather than sending a request for a production-valid
  // URL to a non-existent bridge/static path in the local mirror.
  const slashTarget = publicTrailingSlashTarget(p, u.search);
  if (slashTarget) return redirectTrailingSlash(req, res, slashTarget);

  if (p === '/__preview/live' && req.method === 'GET') return attachLiveReload(req, res);
  if (p.startsWith('/__reconstruction')) return proxyReconstruction(req, res, p);
  if (p === '/reconstruction' || p.startsWith('/reconstruction/')) {
    return proxyReconstruction(
      req,
      res,
      `/__reconstruction${p.slice('/reconstruction'.length)}`,
      { productionContract: true },
    );
  }
  if (p === '/__preview/reconstruction-lab') return send(res, 200, read('reconstruction-lab.html'), 'text/html; charset=utf-8');
  const allowedMethods=allowedMethodsForPreviewPath(p);
  if (allowedMethods && !allowedMethods.includes(req.method)) return methodNotAllowed(res, allowedMethods);
  if (p === '/game') return send(res, 200, reconstructionGameHtml(), 'text/html; charset=utf-8');
  if (p === '/' || p === '/index.html') return send(res, 200, indexHtml(), 'text/html; charset=utf-8');
  if (p === '/static/app.css') return send(res, 200, read('app.css'), 'text/css; charset=utf-8');
  if (p === '/static/app.js') return send(res, 200, PARTS.map(read).join(''), 'application/javascript; charset=utf-8');
  if (p === '/static/app.devmode.js') return send(res, 200, read('app.devmode.js'), 'application/javascript; charset=utf-8');
  if (p === '/static/reconstruction-lab.css') return send(res, 200, read('reconstruction-lab.css'), 'text/css; charset=utf-8');
  if (p === '/static/reconstruction-lab.js') return send(res, 200, read('reconstruction-lab.js'), 'application/javascript; charset=utf-8');
  // One-release compatibility route for Telegram clients that still have the
  // old saved-look stylesheet cached. New CSS must not request this asset.
  if (p === '/static/icons/x.svg') return send(res, 200, fs.readFileSync(path.join(STATIC, 'icons', 'x.svg')), 'image/svg+xml');
  // Keep the preview's public static surface aligned with FastAPI/main.py.
  // Internal captures and arbitrary files in FastAPI/static must never look
  // deployable merely because they happen to be present on a developer machine.
  if (p.startsWith('/static/')) return send(res, 404, { detail: 'нет публичного ресурса' });
  if (p === '/manifest.json') {
    const f = path.join(STATIC, 'manifest.json');
    if (fs.existsSync(f)) return send(res, 200, fs.readFileSync(f), 'application/json');
    return send(res, 200, { name: 'Предвестник', display: 'standalone' });
  }
  if (p === '/updates.json') {
    const f = path.join(STATIC, 'updates.json');
    if (fs.existsSync(f)) return send(res, 200, fs.readFileSync(f), 'application/json');
    return send(res, 404, { detail: 'нет файла' });
  }
  // Публичный профиль (БЛОК4: карточка целиком в косметике) — насыщенный мок
  // со всеми слотами занятыми, чтобы видеть фон/частицы/рамку на всей карточке.
  if (p.startsWith('/profile/u/')) {
    return send(res, 200, {
      user_id: 999, username: 'lilith_hhh', rank: '🌙 Владычица Бездны',
      avatar: null,
      level: 47, combat_power: null, messages: 39710, streak: 53, achievements: 8,
      achievements_total: 12,
      is_vip: true, vip_tier_label: 'VIP Gold',
      gates_floor: null, duel_wins: 237,
      joined_date: '2025-11-02T10:00:00',
      partner: 'moonlight_whisperer_of_the_abyss',
      best_achievement: { icon: '🛒', name: 'Меценат', level: 9 },
      pets: [
        { name: 'Уголёк', species_id: 'salamander', pet_level: 9, placement: 'active' },
        { name: 'Нюша', species_id: 'boar', pet_level: 6, placement: 'stash' },
      ],
      clan: { name: 'Тёмный Орден', tag: 'DARK', emblem: '🛡', role: 'leader' },
      cosmetics: {
        profile_bg: { css: 'pbg-galaxy', name: 'Галактика', lineup: 'void' },
        card_fx: { css: 'cfx-sparks', name: 'Искры', lineup: 'void' },
        avatar_frame: { css: 'frame-arcane', name: 'Аркана', lineup: 'void' },
        avatar_halo: { css: 'halo-eclipse', name: 'Затмение', lineup: 'void' },
        name_glow: { css: 'glow-rift', name: 'Разлом', lineup: 'void' },
        title: 'Владычица Бездны', title_css: 'title-harbinger',
        lineage: { id: 'void', source_slot: 'avatar_frame' },
      },
      sanction: null, chat_warnings: 0, muted_until: null,
    });
  }
  // Тема-превью (Render Raw String): синтетическая строка из top/name/bot_line
  // мока темы — реальный бэк отдаёт разметку профиля в этом же формате.
  if (p.startsWith('/themes/preview/')) {
    const tid = decodeURIComponent(p.slice('/themes/preview/'.length));
    const themes = MOCKS['GET /themes/'] || [];
    const t = themes.find(x => x.theme_id === tid);
    if (!t) return send(res, 404, { detail: 'тема не найдена' });
    return send(res, 200, { text: `${t.top}\n<b>@star_seeker</b>\n${t.bot_line}` });
  }
  if (p === '/__preview/reset' && req.method === 'POST') {
    resetPreviewThemeState();
    return send(res, 200, { ok: true });
  }
  if (p === '/themes/buy' && req.method === 'POST') {
    const body=await readJsonBody(req);
    if (!body || !body.theme_id) return send(res, 400, { detail: 'Нужен theme_id.' });
    const requestKey=String(req.headers['idempotency-key']||'').trim();
    if (!requestKey || requestKey.length>180) return send(res, 400, { detail: 'Idempotency-Key должен содержать 1–180 символов.' });
    const prior=PREVIEW_THEME_PURCHASES.get(requestKey);
    if (prior) {
      if (prior.theme_id!==body.theme_id) return send(res, 400, { detail: 'Этот запрос уже использован для другой покупки.' });
      return send(res, 200, { ok: true, theme_name: prior.theme_name, applied: false, replayed: true, already_owned: false });
    }
    const theme=MOCKS['GET /themes/'].find(t=>t.theme_id===body.theme_id);
    if (!theme) return send(res, 404, { detail: 'Тема не найдена.' });
    if (theme.owned) return send(res, 200, { ok: true, theme_name: theme.name, applied: false, replayed: false, already_owned: true });
    if (['shop_mora','shop_diamond'].includes(theme.source)) {
      return send(res, 410, { detail: 'Старый каталог тем за Мору и Алмазы закрыт. Уже купленные темы сохранены.' });
    }
    if (!['zarniki','dark'].includes(theme.source)) {
      return send(res, 400, { detail: 'Эта тема не продаётся напрямую.' });
    }
    const price=themePrice(theme);
    if (!price) return send(res, 400, { detail: 'У темы не задана цена.' });
    if (PROFILE[price.balance] < price.amount) return send(res, 400, { detail: 'Недостаточно валюты.' });
    PROFILE[price.balance]-=price.amount;
    theme.owned=true;
    PREVIEW_THEME_PURCHASES.set(requestKey,{theme_id:theme.theme_id,theme_name:theme.name});
    return send(res, 200, { ok: true, theme_name: theme.name, applied: true, replayed: false, already_owned: false });
  }
  if (p === '/themes/equip' && req.method === 'POST') {
    const body=await readJsonBody(req);
    if (!body || !body.theme_id) return send(res, 400, { detail: 'Нужен theme_id.' });
    const themes=MOCKS['GET /themes/'];
    const theme=themes.find(t=>t.theme_id===body.theme_id);
    if (!theme) return send(res, 404, { detail: 'Тема не найдена.' });
    if (!theme.owned) return send(res, 400, { detail: 'Сначала добавьте тему в коллекцию.' });
    themes.forEach(t=>{ t.active=false; });
    theme.active=true;
    return send(res, 200, { ok: true, theme_name: theme.name });
  }
  if (p === '/payments/zarniki/invoice' && req.method === 'POST') {
    // A local preview must never create or imitate a real Telegram Stars
    // invoice. Keep the user path explicit instead of returning a misleading
    // empty success response and record the live contract in its GET fixture.
    return send(res, 503, { detail: 'Локальный стенд не создаёт реальный счёт Stars. Проверьте каталог и контракт; оплату тестируйте только после отдельного разрешения.' });
  }
  if (req.method === 'POST' && /^\/cosmetics\/presets\/\d+\/apply$/.test(p)) {
    const id=Number(p.split('/')[3]);
    const result=applyPreviewPreset(id);
    return send(res, result.ok?200:400, result);
  }
  if (req.method === 'PATCH' && /^\/cosmetics\/presets\/\d+$/.test(p)) {
    const body=await readJsonBody(req);
    const id=Number(p.split('/').pop());
    const preset=(MOCKS['GET /cosmetics/presets'].presets||[]).find(item=>item.id===id);
    if (!preset) return send(res, 404, { detail: 'Образ не найден.' });
    const name=(typeof body?.name==='string'?body.name.trim().slice(0,30):'')||'Образ';
    return send(res, 200, { ok: true, message: `✎ Образ «${name}» переименован.`, preset: {...preset,name} });
  }
  if (req.method === 'DELETE' && /^\/cosmetics\/presets\/\d+$/.test(p)) {
    return send(res, 200, { ok: true, message: '🗑 Образ удалён.' });
  }

  if (req.method === 'POST' && retiredMutationPaths.has(p)) {
    return send(res, 410, { detail: 'Этот маршрут прежней экономики закрыт; тестовый баланс не изменён.' });
  }

  const key = `${req.method} ${p}`;
  const hit = Object.prototype.hasOwnProperty.call(MOCKS, key) ? MOCKS[key] : null;
  if (hit !== null) {
    const val = typeof hit === 'function' ? hit(u) : hit;
    if (Array.isArray(val) && typeof val[0] === 'number') return send(res, val[0], val[1]);
    return send(res, 200, val);
  }
  fs.appendFileSync(UNKNOWN_LOG, key + '\n');
  // A local adapter must never turn a missing production contract into a
  // plausible success. Keep the evidence log, then mirror FastAPI's default
  // fail-closed response so UI and smoke checks expose the missing route.
  return send(res, 404, { detail: 'Not Found' });
});
server.on('upgrade', (_req, socket) => socket.destroy()); // WS не поддерживаем
server.on('close', () => {
  shuttingDown = true;
  clearTimeout(reconstructionRestartTimer);
  staticWatcher.close();
  for (const watcher of reconstructionWatchers) watcher.close();
  if (reconstructionApi) reconstructionApi.kill('SIGTERM');
});
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => {
    shuttingDown = true;
    if (reconstructionApi) reconstructionApi.kill('SIGTERM');
    for (const client of liveReloadClients) client.end();
    liveReloadClients.clear();
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 800).unref();
  });
}
server.listen(PORT, () => console.log(`preview on http://localhost:${PORT}/`));
