// tools/preview_server.mjs — локальный предпросмотр мини-аппа БЕЗ бэка и БД.
// Запуск: node tools/preview_server.mjs  →  http://localhost:8402/
// Отдаёт index.html (BASE=''), склеенный app.js (порядок как в main.py), app.css;
// все /api/* — реалистичные мок-JSON (формы сняты с реальных роутеров 2026-07-13).
// Сессия пре-сидится в localStorage → логин-оверлей не мешает.
// Незамоканные эндпоинты логируются в unknown-api.log рядом со скриптом.
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const STATIC = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'FastAPI', 'static');
const HERE = path.dirname(fileURLToPath(import.meta.url));
const UNKNOWN_LOG = path.join(HERE, 'unknown-api.log');
const PORT = 8402;

const read = (n) => fs.readFileSync(path.join(STATIC, n), 'utf8');
const PARTS = Array.from({ length: 11 }, (_, i) => `app.${String(i + 1).padStart(2, '0')}.js`);

function indexHtml() {
  let h = read('index.html')
    .replaceAll('{{BASE}}', '')
    .replaceAll('{{ASSET_VER}}', String(Date.now()))
    .replaceAll('{{BOT_USERNAME}}', 'devbot');
  // Сессия до загрузки app.js → логин-оверлей не появляется; сборщик ошибок для скриншот-прогона.
  h = h.replace('<body>', `<body>\n<script>
try{localStorage.setItem('pv_sess','dev-session');}catch(e){}
window.__errs=[];
window.addEventListener('error',e=>window.__errs.push(String(e.message)));
window.addEventListener('unhandledrejection',e=>window.__errs.push('rej: '+String(e.reason)));
</script>`);
  return h;
}

// ── Мок-данные ────────────────────────────────────────────────────────────────
const PROFILE = {
  user_id: 1460945748,
  username: 'star_seeker',
  rank: '🌟 Легенда',
  mora: 125430, diamonds: 42.5, dark_mora: 340, zarniki: 1250,
  streak: 17, achievements: 23,
  account_level: 27, account_xp: 48210, xp_into: 1210, xp_to_next: 3400, xp_per_level: 3400,
  combat_power: 15680,
  cp_breakdown: { total: 15680, level_part: 2700, squad_units: 9200, reserve_units: 1400, pet_collection: 680, cosmetics_set: 800, relics: 900 },
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
  cosmetics: { name_glow: { css: 'glow-gold', name: 'Золотое сияние' }, title: 'Предвестник Рассвета' },
  system_flags: [
    { key: 'tab_zoo', enabled: true }, { key: 'tab_market', enabled: true },
    { key: 'tab_bp', enabled: true }, { key: 'tab_auction', enabled: true },
  ],
};

// Ключ: "METHOD /path". Значение: объект | функция(url)→объект | [status, объект].
const MOCKS = {
  'GET /profile/me': PROFILE,
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
    mora: 125430, diamonds: 42.5,
    spin_types: [
      { spin_type: 'mora', label: 'Крутка за Мору', cost_mora: 500, cost_dia: 0, token_qty: 3, rates: { common: 62, uncommon: 20, rare: 11, epic: 5, legendary: 1.8, mythic: 0.2 }, pity: 23, pity_hard: 60, multi_cost_mora: 4500, multi_cost_dia: 0 },
      { spin_type: 'diamond', label: 'Крутка за Алмазы', cost_mora: 0, cost_dia: 1, token_qty: 0, rates: { rare: 55, epic: 30, legendary: 12, mythic: 3 }, pity: 4, pity_hard: 30, multi_cost_mora: 0, multi_cost_dia: 9 },
    ],
    multi_count: 10, multi_discount_pct: 10,
  },

  // ── Аукцион ──
  'GET /auction/lots': {
    lots: [
      { id: 11, seller_id: 2, item_name: 'Лунный амулет||amulet_moon', quantity: 1, min_bid: 500, buyout: 5000, ends_at: '2026-07-14 12:00:00', status: 'active', remaining_sec: 9500, current_bid: 1200, bid_count: 3, seller_name: 'moon_witch', seller_is_vip: true, item_rarity: 'epic', has_bids: true, min_next_bid: 1261, item_name_display: 'Лунный амулет', item_id_ref: 'amulet_moon', item_description: 'Слабое сияние отгоняет усталость питомцев.', item_category: 'артефакт' },
      { id: 12, seller_id: 3, item_name: '🍖 Мясо||food_meat', quantity: 5, min_bid: 200, buyout: 900, ends_at: '2026-07-13 21:30:00', status: 'active', remaining_sec: 2400, current_bid: 200, bid_count: 0, seller_name: 'grimm', seller_is_vip: false, has_bids: false, min_next_bid: 200, item_name_display: '🍖 Мясо', item_id_ref: 'food_meat', item_description: 'Восстанавливает 50 усталости.', item_category: 'еда' },
      { id: 13, seller_id: 4, item_name: 'Осколки юнита||unit_shards', quantity: 10, min_bid: 3000, buyout: 12000, ends_at: '2026-07-15 09:00:00', status: 'active', remaining_sec: 86000, current_bid: 4500, bid_count: 7, seller_name: 'night_raven', seller_is_vip: false, item_rarity: 'rare', has_bids: true, min_next_bid: 4726, item_name_display: 'Осколки юнита', item_id_ref: 'unit_shards', item_description: 'Для призыва и прокачки юнитов Казармы.', item_category: 'боёвка' },
    ],
    total: 3, page: 0, per_page: 20, has_more: false, min_bid_floor: 100,
  },

  // ── Боевой пропуск ──
  'GET /battle_pass/status': {
    active: true, season_label: 'Сезон 4 «Кровавая Луна»', frozen: false,
    level: 12, max_level: 30, xp: 6100, xp_in_level: 340, xp_per_level: 500, xp_to_next: 160,
    season_starts: '2026-07-01', season_ends: '2026-07-31',
    weekend_boost: { active: false, pct: 25 }, paid_track_open: true, buy_next: { level: 13, price: 3 },
    rewards: [
      { level: 11, free: { mora: 800, status: 'claimed' }, paid: { diamonds: 1, status: 'claimed' } },
      { level: 12, free: { mora: 1000, status: 'available' }, paid: { items: [{ item_id: 'cos_glow_ruby', name: 'Рубиновое сияние', qty: 1, is_cosmetic: true, slot: 'name_glow', rarity: 'epic' }], status: 'available' } },
      { level: 13, free: { mora: 1200, status: 'locked_level' }, paid: { diamonds: 2, status: 'locked_level' } },
      { level: 14, free: { items: [{ item_id: 'food_meat', name: '🍖 Мясо', qty: 3, is_cosmetic: false }], status: 'locked_level' }, paid: { mora: 5000, status: 'locked_level' } },
    ],
  },

  // ── Квесты / Ачивки / Топ ──
  'GET /quests/-100111': {
    quests: [
      { id: 'msg_15', progress: 15, target: 15, completed: true, reward: { mora: 150 } },
      { id: 'feed_pet', progress: 0, target: 1, completed: false, reward: { mora: 100 } },
      { id: 'gacha_3', progress: 1, target: 3, completed: false, reward: { mora: 250 } },
    ],
    bonus: { claimed: false, reward: { mora: 500 } },
    weekly: [
      { id: 'exped_4', progress: 2, target: 4, completed: false, reward: { mora: 900, diamonds: 1 } },
      { id: 'hug_5', progress: 5, target: 5, completed: true, reward: { mora: 600 } },
    ],
    weekly_bonus: { claimed: false, reward: { diamonds: 2 } },
  },
  'GET /achievements/': [
    { id: 'messages', icon: '💬', name: 'Голос чата', level: 3, max_level: 10, progress: 15873, next_threshold: 25000, pct: 63, completed: false, next_reward: { mora: 2000 } },
    { id: 'gacha_spins', icon: '🎰', name: 'Испытатель удачи', level: 2, max_level: 10, progress: 214, next_threshold: 500, pct: 43, completed: false, next_reward: { mora: 1500, diamonds: 1 } },
    { id: 'streak', icon: '🔥', name: 'Верность', level: 5, max_level: 5, progress: 30, next_threshold: null, pct: 100, completed: true, next_reward: null },
  ],
  'GET /top/local/-100111': [
    { user_tg_id: 2, username: 'moon_witch', nickname: 'Лунная Ведьма', count: 21450, is_vip: true },
    { user_tg_id: 1460945748, username: 'star_seeker', nickname: 'Звездочёт', count: 15873, is_vip: true },
    { user_tg_id: 3, username: 'grimm', nickname: null, count: 12200, is_vip: false },
    { user_tg_id: 4, username: 'night_raven', nickname: 'Ворон', count: 8033, is_vip: false },
    { user_tg_id: 5, username: 'sunny', nickname: null, count: 5410, is_vip: false },
  ],

  // ── Глобальная модерация ──
  'GET /admin/global/chats': { chats: [
    { chat_id: -100111, chat_title: 'Предвестники Ночи', role: 'main', member_count: 214 },
    { chat_id: -100222, chat_title: 'Тайный Орден', role: 'admin', member_count: 37, linked_title: 'Предвестники Ночи' },
  ] },

  // ── Темы чата ──
  'GET /themes/': [
    { theme_id: 'classic', name: 'Классика', rarity: 'common', badge: '⬜', rarity_label: 'Обычная', source: 'база', desc: 'Стандартная рамка сообщений бота.', top: '━━━━━━━━━━', bot_line: '━━━━━━━━━━', accent: '▪', price_mora: null, price_diamonds: null, price_dark: null, price_zarniki: null, owned: true, active: true, gacha: false, it: false, premium: false },
    { theme_id: 'starfall', name: 'Звездопад', rarity: 'rare', badge: '🟦', rarity_label: 'Редкая', source: 'магазин', desc: 'Падающие звёзды обрамляют каждое сообщение.', top: '✦ ˚ · . ✦ ˚ ·', bot_line: '· ˚ ✦ . · ˚ ✦', accent: '✦', price_mora: 15000, price_diamonds: null, price_dark: null, price_zarniki: null, owned: true, active: false, gacha: false, it: false, premium: false },
    { theme_id: 'bloodmoon', name: 'Кровавая Луна', rarity: 'epic', badge: '🟪', rarity_label: 'Эпическая', source: 'ивент', desc: 'Багровое сияние затмения.', top: '🌘━━━━━━━🌒', bot_line: '🌘━━━━━━━🌒', accent: '🌑', price_mora: null, price_diamonds: 25, price_dark: null, price_zarniki: null, owned: false, active: false, gacha: false, it: false, premium: false },
    { theme_id: 'golden_dawn', name: 'Золотой Рассвет', rarity: 'legendary', badge: '🟨', rarity_label: 'Легендарная', source: 'гача', desc: 'Первый луч солнца в вечной тьме.', top: '☀️═══════☀️', bot_line: '☀️═══════☀️', accent: '✨', price_mora: null, price_diamonds: null, price_dark: null, price_zarniki: null, owned: false, active: false, gacha: true, it: false, premium: false },
    { theme_id: 'neon_terminal', name: 'Неоновый Терминал', rarity: 'zarniki', badge: '✨', rarity_label: 'Зарниковая', source: 'донат', desc: 'IT-стиль: зелёный курсор, поток кода.', top: '▚▞▚▞▚▞▚▞▚▞', bot_line: '▞▚▞▚▞▚▞▚▞▚', accent: '▓', price_mora: null, price_diamonds: null, price_dark: null, price_zarniki: 440, owned: false, active: false, gacha: false, it: true, premium: true },
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
    mora: 125430, diamonds: 42.5, rate: 1200, sell_rate: 950,
    remaining: 8, daily_cap: 10, sell_remaining: 10, sell_daily_cap: 10,
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
    per_star: 2,
    packages: [
      { stars: 50, zarniki: 100, bonus: 0, total: 100, popular: false },
      { stars: 250, zarniki: 500, bonus: 50, total: 550, popular: true },
      { stars: 500, zarniki: 1000, bonus: 150, total: 1150, popular: false },
    ],
    custom_min: 1, custom_max: 10000,
  },
  'GET /vip/status': {
    active: true, tier: 'gold', tier_label: '👑 VIP Gold', expires_at: '2026-08-02T00:00:00',
    days_left: 20, seniority_days: 96, seniority_months: 3,
    perks: ['🎨 Эксклюзивная косметика', '🐾 +1 слот питомника', '📸 Аватарка из Telegram', '⚡ Приоритет в очереди боёв'],
    tiers: [
      { tier: 'silver', label: 'VIP Silver', tagline: 'Попробовать VIP', price_zarniki: 250, base_price_zarniki: 250, savings_zarniki: 0, duration_days: 30, gift_mora: 5000, gift_diamonds: 0, gift_items: [{ qty: 1, name: '🎟 Жетон крутки' }], weekly: [{ qty: 2, name: '🍖 Мясо' }], extra_slots: 0 },
      { tier: 'gold', label: 'VIP Gold', tagline: 'Максимум мистики', price_zarniki: 440, base_price_zarniki: 500, savings_zarniki: 60, duration_days: 30, gift_mora: 15000, gift_diamonds: 3, gift_items: [{ qty: 3, name: '🎟 Жетон крутки' }], weekly: [{ qty: 5, name: '🍖 Мясо' }, { qty: 1, name: '🍀 Зелье удачи' }], extra_slots: 1 },
    ],
  },

  // ── Магазин расходников ──
  'GET /shop/': {
    mora: 125430, diamonds: 42.5, zarniki: 1250,
    items: [
      { item_id: 'food_apple', name: '🍎 Яблоко', category: 'food', price_mora: 300, description: 'Восстанавливает 20 усталости.' },
      { item_id: 'food_meat', name: '🍖 Мясо', category: 'food', price_mora: 650, description: 'Восстанавливает 50 усталости.', discount_active: true },
      { item_id: 'exp_boost_2h', name: '⏩ Ускоритель похода (2ч)', category: 'utility', price_mora: 900, description: 'Сокращает поход на 2 часа.' },
      { item_id: 'gacha_luck', name: '🍀 Зелье удачи', category: 'booster', price_diamonds: 2, description: '+15% к шансу редкости на следующей крутке.' },
      { item_id: 'vip_30', name: '👑 VIP на 30 дней', category: 'donate', price_zarniki: 440, description: 'Все привилегии VIP на месяц.' },
    ],
  },

  // ── Врата (Боёвка 3.0) ──
  'GET /combat2/gates': {
    active_battle: null, cp: 15680, squad_cp: 6800, entries_left: 2,
    squad: [
      { emoji: '🔥', name: 'Рыцарь Пепла', level: 6 },
      { emoji: '🌊', name: 'Дева Прилива', level: 4 },
      { emoji: '⛰️', name: 'Страж Скалы', level: 3 },
    ],
    loot: { shard_chance_pct: 20, shard_range: [1, 3], unit_shard_chance_pct: 35, unit_shard_range: [1, 2] },
    floors: [
      { floor: 1, enemies: 3, reward_dark: 40, open: true, cp_gate: 0 },
      { floor: 2, enemies: 3, reward_dark: 70, open: true, cp_gate: 4000 },
      { floor: 3, enemies: 4, reward_dark: 110, open: true, cp_gate: 9000 },
      { floor: 4, enemies: 4, reward_dark: 160, open: false, cp_gate: 22000 },
      { floor: 5, enemies: 5, reward_dark: 220, open: false, cp_gate: 30000, unit_shards: true },
      { floor: 6, enemies: 5, reward_dark: 300, open: false, cp_gate: 40000, unit_shards: true },
    ],
  },

  // ── События ──
  'GET /events/': { exchange_active: false, events: [] },

  // ── Акции дня + витрина недели ──
  'GET /daily-deal/': {
    refreshes_at: '2026-07-14 00:00:00', mora: 125430, diamonds: 42.5,
    deals: [
      { slot: 0, item_name: '🍖 Мясо', item_description: 'Восстанавливает 50 усталости.', quantity: 3, price_mora: 1400, price_diamonds: 0, purchased: false },
      { slot: 1, item_name: '🍀 Зелье удачи', item_description: '+15% к шансу редкости на крутке.', quantity: 1, price_diamonds: 1.5, price_mora: 0, purchased: false },
      { slot: 2, item_name: '🎟 Жетон крутки', item_description: 'Бесплатная крутка Гачи.', quantity: 1, price_mora: 400, price_diamonds: 0, purchased: true },
    ],
  },
  'GET /showcase/': { slots: [], rotates_in_sec: 0 },

  // ── Админка чата ──
  'GET /admin/-100111/dashboard': {
    my_rank_name: '🏆 Владелец', member_count: 214, active_today: 58,
    warned_count: 3, ban_count: 1,
    can_warn: true, can_mute: true, can_kick: true, can_ban: true,
  },
  'GET /admin/-100111/users': {
    total: 214, page_size: 20, max_assignable_rank: 4,
    users: [
      { user_tg_id: 2, user_tg_username: 'moon_witch', is_vip: true, user_level: 34, local_rank: 4, warnings: 0, user_messages_count_all_time: 21450, joined_at: '2025-11-02 10:00:00', last_message_at: '2026-07-13 09:15:00', can_act: true, can_warn: true, can_mute: true, can_kick: true, can_ban: true, can_shield: true, can_immune: true, can_set_rank: true, is_immune: false, is_left: false, muted_until: null },
      { user_tg_id: 3, user_tg_username: 'grimm', is_vip: false, user_level: 22, local_rank: 1, warnings: 2, user_messages_count_all_time: 12200, joined_at: '2026-01-15 18:30:00', last_message_at: '2026-07-12 22:47:00', can_act: true, can_warn: true, can_mute: true, can_kick: true, can_ban: true, can_shield: true, can_immune: true, can_set_rank: true, is_immune: false, is_left: false, muted_until: '2026-07-14 12:00:00' },
      { user_tg_id: 4, user_tg_username: 'night_raven', is_vip: false, user_level: 15, local_rank: 0, warnings: 0, user_messages_count_all_time: 8033, joined_at: '2026-03-08 12:00:00', last_message_at: '2026-07-13 08:02:00', can_act: true, can_warn: true, can_mute: true, can_kick: true, can_ban: true, can_shield: true, can_immune: true, can_set_rank: true, is_immune: true, is_left: false, muted_until: null },
      { user_tg_id: 5, user_tg_username: 'sunny', is_vip: false, user_level: 9, local_rank: 0, warnings: 0, user_messages_count_all_time: 5410, joined_at: '2026-05-20 09:10:00', last_message_at: '2026-06-30 16:20:00', can_act: false, can_set_rank: false, is_immune: false, is_left: true, muted_until: null },
    ],
  },
};

function send(res, status, body, type = 'application/json; charset=utf-8') {
  res.writeHead(status, { 'content-type': type, 'access-control-allow-origin': '*' });
  res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

const server = http.createServer((req, res) => {
  const u = new URL(req.url, `http://localhost:${PORT}`);
  const p = u.pathname;

  if (p === '/' || p === '/index.html') return send(res, 200, indexHtml(), 'text/html; charset=utf-8');
  if (p === '/static/app.css') return send(res, 200, read('app.css'), 'text/css; charset=utf-8');
  if (p === '/static/app.js') return send(res, 200, PARTS.map(read).join(''), 'text/javascript; charset=utf-8');
  if (p.startsWith('/static/')) {
    const f = path.join(STATIC, p.slice('/static/'.length));
    if (fs.existsSync(f) && fs.statSync(f).isFile()) return send(res, 200, fs.readFileSync(f), 'text/javascript; charset=utf-8');
    return send(res, 404, { detail: 'нет файла' });
  }
  if (p === '/manifest.json') {
    const f = path.join(STATIC, 'manifest.json');
    if (fs.existsSync(f)) return send(res, 200, fs.readFileSync(f), 'application/json');
    return send(res, 200, { name: 'Предвестник', display: 'standalone' });
  }

  const key = `${req.method} ${p}`;
  const hit = Object.prototype.hasOwnProperty.call(MOCKS, key) ? MOCKS[key] : null;
  if (hit !== null) {
    const val = typeof hit === 'function' ? hit(u) : hit;
    if (Array.isArray(val) && typeof val[0] === 'number') return send(res, val[0], val[1]);
    return send(res, 200, val);
  }
  fs.appendFileSync(UNKNOWN_LOG, key + '\n');
  return send(res, 200, {});
});
server.on('upgrade', (_req, socket) => socket.destroy()); // WS не поддерживаем
server.listen(PORT, () => console.log(`preview on http://localhost:${PORT}/`));
