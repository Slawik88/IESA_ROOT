// ── ADMPROFILE-20261019: «карточка игрока» для всей админки ─────────────────────
// Owner-запрос: в админке людей видно только по нику — добавить фото и полезную
// инфу с первого взгляда. Единый визуальный язык для всех админ-экранов:
//   • admAvaHtml    — аватар Telegram (подписанная ссылка /admin/avatar) + фолбэк-инициал;
//   • admPlayerCard — карточка игрока (списки участников, Центр игрока);
//   • admMiniUser   — компактная строка «фото + ник + хвост» для журналов/санкций/апелляций.
// Все хелперы переживают отсутствие полей (кэшированный ответ, старая строка).

const _ADM_AVA_COLORS = ['#4f7fe0', '#a765e0', '#2fae68', '#d9992f', '#dd5a76', '#2fa9bd', '#7a6cf0', '#c0673c'];

function admNum(v) { const n = parseInt(v, 10); return isNaN(n) ? 0 : n; }
function admAvaColor(uid) { return _ADM_AVA_COLORS[Math.abs(admNum(uid)) % _ADM_AVA_COLORS.length]; }

function admInitial(name) {
  const s = String(name || '').replace(/^@/, '').trim();
  if (!s || /^\d+$/.test(s) || /^id\d+$/i.test(s)) return '👤';
  return s[0].toUpperCase();
}

// Аватар: сначала фото (ленивая загрузка, кэш браузера), под ним — инициал.
// onerror снимает битую картинку, инициал остаётся видимым (нет «дырок»).
function admAvaHtml(uid, name, url, size, cls) {
  size = size || 34;
  const img = url
    ? `<img src="${BASE}${url}" alt="" loading="lazy" decoding="async" onerror="this.remove()"/>`
    : '';
  return `<span class="adm-ava ${cls || ''}" style="width:${size}px;height:${size}px;background:${admAvaColor(uid)}">${img}<i style="font-size:${Math.max(10, Math.round(size * 0.42))}px">${esc(admInitial(name))}</i></span>`;
}

function admDate(s) {
  if (!s) return null;
  const str = String(s);
  const d = new Date(str.includes('T') ? str : str.replace(' ', 'T') + 'Z');
  return isNaN(d) ? null : d;
}

// «5 мин назад» — админу важнее свежесть, чем точная метка времени.
function admRel(s) {
  const d = admDate(s);
  if (!d) return '';
  const sec = (Date.now() - d.getTime()) / 1000;
  if (sec < 90) return 'только что';
  if (sec < 3600) return Math.floor(sec / 60) + ' мин назад';
  if (sec < 86400) return Math.floor(sec / 3600) + ' ч назад';
  if (sec < 30 * 86400) return Math.floor(sec / 86400) + ' дн назад';
  return fmtUTC(s);
}

function admChip(text, cls) { return `<span class="adm-chip ${cls || ''}">${text}</span>`; }

// Иконка вместо фото — чаты/каналы и служебные цели: тот же размер и ритм строки.
function admIconHtml(icon, size, cls) {
  size = size || 34;
  return `<span class="adm-ava ${cls || ''}" style="width:${size}px;height:${size}px;background:#39445c;font-size:${Math.max(11, Math.round(size * 0.5))}px">${icon}</span>`;
}

// Статусы модерации одной строкой — баны/муты/варны/иммунитет/ушёл/VIP.
function admStatusChips(u) {
  const out = [];
  if (u.is_vip) out.push(admChip('👑 VIP', 'adm-c-gold'));
  if (u.is_banned) out.push(admChip('🚫 бан', 'adm-c-red'));
  if (u.global_ban) out.push(admChip('⛔ глоб.ЧС', 'adm-c-red'));
  const mu = admDate(u.muted_until);
  if (mu && mu.getTime() > Date.now()) out.push(admChip('🔇 до ' + fmtUTC(u.muted_until), 'adm-c-gold'));
  if ((u.warnings || 0) > 0) out.push(admChip('⚠️ ' + u.warnings, 'adm-c-gold'));
  const iu = admDate(u.immune_until);
  if (u.is_immune || (iu && iu.getTime() > Date.now())) out.push(admChip('🛡 иммун', 'adm-c-blue'));
  if (u.was_kicked && !u.is_banned) out.push(admChip('👢 кикали'));
  if (u.is_left) out.push(admChip('👋 ушёл'));
  if (u.has_sanction) out.push(admChip('⚖️ санкция', 'adm-c-red'));
  return out.join('');
}

function admNameOf(u) {
  const uid = admNum(u.user_tg_id || u.user_id || u.target_id || u.id);
  const src = u.user_tg_username || u.username || u.target_name || u.user_name;
  let raw = String(src == null || src === '' ? ('ID' + uid) : src).replace(/^@/, '').trim();
  if (!raw) raw = 'ID' + uid;
  // Ник в Telegram не бывает чисто цифровым — значит это служебный «ID123»/«123»,
  // и «@» к нему не лепим (иначе получается «@ID123»). Иначе — привычный @ник.
  const label = /^id\d+$/i.test(raw) ? raw : (/^\d+$/.test(raw) ? 'ID' + raw : '@' + raw);
  return { uid, raw, label };
}

// Ник кликабелен в Центр игрока, если у актора есть право на досье.
function admNameHtml(u, klass) {
  const { uid, label } = admNameOf(u);
  const txt = esc(vipName(label, u.is_vip));
  const canOpen = typeof gp === 'function' && gp('dossier_view') && typeof openPlayerCenter === 'function';
  return canOpen
    ? `<span class="${klass || ''} adm-link" onclick="admOpenCenter(${uid})">${txt}</span>`
    : `<span class="${klass || ''}">${txt}</span>`;
}

function admOpenCenter(uid) {
  if (typeof openPlayerCenter === 'function') openPlayerCenter(uid);
}

// Карточка игрока: фото + ник + ID/уровень/ранги + статусы + активность.
// o: { actions:html, extra:html, stats:'html', meta:'html', center:false, cls:'', size:number }
function admPlayerCard(u, o) {
  o = o || {};
  const { uid, label } = admNameOf(u);
  const nick = u.nickname ? `<span class="adm-pcard-nick">«${esc(u.nickname)}»</span>` : '';
  const lvl = u.user_level || u.level || 1;
  const rankName = u.rank_name || (typeof _RANK_NAMES !== 'undefined' && u.local_rank != null ? (_RANK_NAMES[u.local_rank] || '') : '');
  // «👤 Пользователь» — не инфо, а шум: ранги показываем только когда они есть.
  const localRank = rankName && rankName !== '👤 Пользователь' ? rankName : '';
  const gRank = u.global_rank_name && u.global_rank_name !== '👤 Пользователь' ? u.global_rank_name : '';
  const meta = o.meta || [`ID ${uid}`, `ур. ${lvl}`, localRank, gRank].filter(Boolean).join(' · ');
  const msgs = (u.user_messages_count_all_time != null) ? u.user_messages_count_all_time : u.msgs;
  const stats = o.stats || [
    msgs != null ? `💬 ${fmt(msgs)}` : '',
    u.joined_at ? `📅 с ${fmtUTC(u.joined_at)}` : '',
    u.last_message_at ? `🕓 ${admRel(u.last_message_at)}` : '',
  ].filter(Boolean).join(' · ');
  const chips = admStatusChips(u) + (o.badges || '');
  const name = o.center === false
    ? `<span class="adm-pcard-name">${esc(vipName(label, u.is_vip))}</span>`
    : admNameHtml(u, 'adm-pcard-name');
  return `<div class="adm-pcard ${o.cls || ''}">
    ${admAvaHtml(uid, label, u.avatar_url || o.avatarUrl, o.size || 44)}
    <div class="adm-pcard-body">
      <div class="adm-pcard-top">${name}${nick}</div>
      <div class="adm-pcard-meta">${meta}</div>
      ${stats ? `<div class="adm-pcard-stats">${stats}</div>` : ''}
      ${chips ? `<div class="adm-pcard-chips">${chips}</div>` : ''}
      ${o.extra || ''}
    </div>
    ${o.actions ? `<div class="adm-pcard-actions">${o.actions}</div>` : ''}
  </div>`;
}

// Компактная строка «фото + ник + подпись + действия» — журналы, санкции, апелляции.
// o: { avatar:url|null|undefined, sub:html, tail:html, actions:html, size:number,
//      center:false, name:html (свой заголовок), icon:html (иконка вместо фото — чаты) }
function admMiniUser(u, o) {
  o = o || {};
  const { uid, raw, label } = admNameOf(u);
  const url = o.avatar !== undefined ? o.avatar
    : (u.avatar_url || u.user_avatar_url || u.target_avatar_url || u.admin_avatar_url || u.issued_by_avatar_url || u.resolved_by_avatar_url);
  const name = o.name || (o.center === false
    ? `<span class="adm-mini-name-txt">${esc(vipName(o.icon ? raw : label, u.is_vip))}</span>`
    : admNameHtml(u, 'adm-mini-name-txt'));
  return `<div class="adm-mini">
    ${o.icon ? admIconHtml(o.icon, o.size || 26) : admAvaHtml(uid, raw, url, o.size || 26)}
    <div class="adm-mini-main">
      <div class="adm-mini-name">${name}${o.tail ? ` ${o.tail}` : ''}</div>
      ${o.sub ? `<div class="adm-mini-sub">${o.sub}</div>` : ''}
    </div>
    ${o.actions ? `<div class="adm-mini-actions">${o.actions}</div>` : ''}
  </div>`;
}

// Компактная строка внутри плоского списка (журналы): аватар + подпись + хвост.
function admFlatUser(u, o) {
  o = o || {};
  const { uid, raw, label } = admNameOf(u);
  const url = o.avatar !== undefined ? o.avatar : (u.avatar_url || u.user_avatar_url || u.target_avatar_url || u.admin_avatar_url);
  return `<span class="adm-flat">
    ${admAvaHtml(uid, raw, url, o.size || 22)}
    ${o.center === false
      ? `<span class="adm-flat-name">${esc(vipName(o.icon ? raw : label, u.is_vip))}</span>`
      : admNameHtml(u, 'adm-flat-name')}
    ${o.tail ? `<span class="adm-flat-tail">${o.tail}</span>` : ''}
  </span>`;
}
