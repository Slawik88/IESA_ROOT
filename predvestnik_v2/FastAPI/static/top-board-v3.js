// ── Топ на страницах игр (Ритм, Сапёр): тот же подиум и те же строки, что «Топ» и «Топ-10» в Mini App ───────────
// Страница игры получает top-board.js = этот файл + части Mini App, которые рисуют топ (FastAPI/main.py, _TOP_BOARD_PARTS):
// app.17 (строка _v3RowButton), app.20 (образ, ник, аватар), app.22 (украшения), app.29 (регалия), app.32–38/48/53 (сцены и детали образов), app.50 (подиум v3Podium).
// Здесь только то, что в Mini App дают другие части: экранирование, число, адрес приложения и переход в профиль игрока.
const BASE = document.body.dataset.appBase || location.pathname.replace(/\/(rhythm-v2|minesweeper)\/?$/, '');
const fmt = n => Number(n).toLocaleString('ru');
function _profileEsc(value) { return String(value ?? '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c])); }
const esc = _profileEsc;
function openPublicProfile(ref) { if (/^[A-Za-z0-9_-]{16,64}$/.test(ref || '')) location.href = `${BASE}/?startapp=public&profile=${encodeURIComponent(ref)}`; }

// rows: [{place, name, ref, is_vip, is_me, look, mark, avatar, avatar_state, level}]; value(row) — подпись результата (число или строка).
// podium — у первой страницы тройка подиумом, дальше строки списка; без подиума все строки списком.
function gameTopBoardV3(podiumHost, listHost, rows, value, { podium = true } = {}) {
  const pod = podium ? v3Podium(rows, r => _profileEsc(value(r))) : '';
  const rest = pod ? rows.filter(r => r.place > 3) : rows;
  podiumHost.innerHTML = pod;
  listHost.innerHTML = rest.map(r => `<li class="${r.is_me ? 'is-me' : ''}">${_v3RowButton(r, value(r))}</li>`).join('');
  if (rest.length) listHost.setAttribute('start', String(rest[0].place));
}
// Строка ответа игры (place, player:{…}, …) → строка топа Mini App
const gameTopRowV3 = row => ({ place: row.place, name: row.player?.display_name || 'Игрок', ref: row.player?.profile_ref, is_vip: !!row.player?.is_vip, is_me: !!row.is_me,
  look: row.player?.look || null, mark: row.player?.mark || null, avatar: row.player?.avatar, avatar_state: row.player?.avatar_state, level: row.player?.level, raw: row });
