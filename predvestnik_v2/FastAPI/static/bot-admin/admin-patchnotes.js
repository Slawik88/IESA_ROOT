// ── Патч-ноуты: посты обновлений для официального канала ─────────────────────────
// Предвестник готовит пост дня из файла выпуска, создатель проверяет, правит текст и фото до буквы и сам жмёт «Отправить».
// Картинки черновиков не публичны: читаются через API с подписью и показываются как blob-адреса.

const PN = {list: null, note: null, dirty: false, blobs: new Map()};
const PN_STATES = {draft: ['Черновик', ''], failed: ['Не отправлено', 'bad'], sending: ['Отправляется', 'warn'], unknown: ['Нужна сверка', 'warn'], sent: ['Опубликовано', 'ok'], skipped: ['Не публикуем', 'off']};
const PN_KIND = {new: 'Новое', better: 'Улучшили', fix: 'Исправили'};
const PN_MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const PN_TOOLS = [['b', 'Ж', 'Жирный'], ['i', 'К', 'Курсив'], ['u', 'Ч', 'Подчёркнутый'], ['s', 'З̶', 'Зачёркнутый'], ['tg-spoiler', '▒', 'Спойлер'], ['blockquote', '❝', 'Цитата'], ['blockquote expandable', '❝▾', 'Свёрнутая цитата'], ['code', '<>', 'Моноширинный'], ['a', '🔗', 'Ссылка']];

const pnDate = d => { const [y, m, day] = String(d).split('-').map(Number); return `${day} ${PN_MONTHS[m - 1] || ''}${y !== new Date().getFullYear() ? ' ' + y : ''}`; };
const pnState = s => { const [t, c] = PN_STATES[s] || [s, '']; return `<span class="chip ${c}">${esc(t)}</span>`; };
const pnLen = text => { const plain = pnPlain(text); let n = 0; for (const ch of plain) n += ch.codePointAt(0) > 0xffff ? 2 : 1; return n; };
function pnPlain(text) { const box = document.createElement('div'); box.innerHTML = pnHtml(text); return box.textContent || ''; }

// Разметка Telegram -> безопасный HTML предпросмотра: всё экранируется, назад пускаются только теги, которые понимает Telegram.
function pnHtml(text) {
  const safe = esc(text)
    .replace(/&lt;(\/?)(b|strong|i|em|u|ins|s|strike|del|code|pre|tg-spoiler)&gt;/g, '<$1$2>')
    .replace(/&lt;blockquote( expandable)?&gt;/g, (m, ex) => `<blockquote${ex ? ' class="pn-fold"' : ''}>`).replace(/&lt;\/blockquote&gt;/g, '</blockquote>')
    .replace(/&lt;a href=&quot;((?:https:\/\/|tg:\/\/)[^&"]*)&quot;&gt;/g, '<a href="$1" target="_blank" rel="noopener">').replace(/&lt;\/a&gt;/g, '</a>')
    .replace(/&amp;(lt|gt|amp|quot|#\d+|#x[0-9a-f]+);/gi, '&$1;');
  const open = [];
  const balanced = safe.replace(/<(\/?)([a-z-]+)[^>]*>/g, (m, close, tag) => {
    if (!close) { open.push(tag); return m; }
    const at = open.lastIndexOf(tag);
    if (at < 0) return '';
    return open.splice(at).reverse().map(t => `</${t}>`).join('');
  });
  return (balanced + open.reverse().map(t => `</${t}>`).join('')).replace(/<tg-spoiler>/g, '<span class="pn-spoiler">').replace(/<\/tg-spoiler>/g, '</span>');
}

// Подсказка до сохранения: незакрытые и неизвестные теги видно сразу (окончательно проверяет сервер).
function pnMarkupIssue(text) {
  const stack = [], known = /^(b|strong|i|em|u|ins|s|strike|del|code|pre|a|blockquote|tg-spoiler)$/;
  for (const m of text.matchAll(/<(\/?)([a-zA-Z-]+)[^>]*>/g)) {
    if (!known.test(m[2])) return `Тег <${m[2]}> Telegram не понимает.`;
    if (!m[1]) { stack.push(m[2]); continue; }
    if (stack.pop() !== m[2]) return `Тег </${m[2]}> закрыт не по порядку.`;
  }
  if (stack.length) return `Не закрыт тег <${stack.pop()}>.`;
  if (/<(?![a-zA-Z/])/.test(text)) return 'Знак < вне тега: напишите &lt;';
  return '';
}

async function pnBlob(noteId, image) {
  const key = `${noteId}|${image.ref}|${image.title || ''}|${image.kind || ''}`;
  if (PN.blobs.has(key)) return PN.blobs.get(key);
  const qs = new URLSearchParams({ref: image.ref, title: image.title || '', kind: image.kind || 'new'});
  const headers = {};
  if (INIT) headers['x-init-data'] = INIT;
  try { const s = localStorage.getItem('pv_sess'); if (s) headers['x-session-token'] = s; } catch (_) {}
  try {
    const res = await fetch(`${BASE}/bot-admin/api/patch-notes/${encodeURIComponent(noteId)}/image?${qs}`, {headers});
    if (!res.ok) return '';
    const url = URL.createObjectURL(await res.blob());
    PN.blobs.set(key, url);
    return url;
  } catch (_) { return ''; }
}
async function pnPaintImages(root, noteId) {
  for (const img of root.querySelectorAll('img[data-pnref]')) {
    const url = await pnBlob(noteId, {ref: img.dataset.pnref, title: img.dataset.pntitle, kind: img.dataset.pnkind});
    if (url) img.src = url; else img.alt = 'Картинка не найдена';
  }
}
const pnImg = (image, cls = '') => `<img class="${cls}" data-pnref="${esc(image.ref)}" data-pntitle="${esc(image.title || '')}" data-pnkind="${esc(image.kind || '')}" alt="${esc(image.alt || 'Картинка поста')}"/>`;

// ── Список ──────────────────────────────────────────────────────────────────

async function patchNotesView(main) {
  if (PN.dirty && !confirm('Есть несохранённые правки. Уйти без сохранения?')) return;
  PN.dirty = false; PN.note = null;
  const data = await loadSectionData(main, '/patch-notes', () => patchNotesView(main), 'patchnotes');
  if (!data) return;
  PN.list = data;
  const pending = data.items.filter(n => ['draft', 'failed', 'sending', 'unknown'].includes(n.status));
  const done = data.items.filter(n => !pending.includes(n));
  const row = n => `<div class="row pn-row" data-pn="${esc(n.note_id)}"><div class="head"><b>${esc(n.title || 'Пост обновления')}</b><span class="sub">${esc(pnDate(n.note_date))}</span></div>
    <div class="chips tags">${pnState(n.status)}${n.images ? `<span class="chip tag">🖼 ${n.images}</span>` : ''}${n.edited ? '<span class="chip tag">✎ правили вы</span>' : ''}${n.source_newer ? '<span class="chip warn">Предвестник дополнил</span>' : ''}</div>
    ${n.error ? `<div class="sub" style="margin-top:6px">${esc(n.error)}</div>` : ''}</div>`;
  main.innerHTML = `${pageHead('📣', 'Патч-ноуты', 'Посты обновлений для канала. В канал уходит только то, что вы проверили и отправили сами.')}
    <p class="sub">Куда: <a href="${esc(data.target)}" target="_blank" rel="noopener">тема «Обновления» в официальной группе</a>.</p>
    ${data.topic_verified ? '' : '<div class="card"><p class="warn">Бот ещё не видел сообщений в теме обновлений. Напишите там любое сообщение — без этого отправка заблокирована.</p></div>'}
    ${data.problems.length ? `<div class="card"><h3>Файлы с ошибками</h3>${data.problems.map(p => `<p><b>${esc(p.note_id)}</b>: ${esc(p.errors.join('; '))}</p>`).join('')}<p class="sub">Эти посты не показаны: их нужно поправить в выпуске.</p></div>` : ''}
    <div class="card"><h3>Ждут проверки · ${pending.length}</h3>${pending.length ? `<div class="list">${pending.map(row).join('')}</div>` : '<div class="empty">Новых постов нет. Предвестник подготовит пост, когда выйдет обновление.</div>'}</div>
    ${done.length ? `<div class="card"><h3>История</h3><div class="list">${done.map(row).join('')}</div></div>` : ''}`;
  main.querySelectorAll('[data-pn]').forEach(r => r.onclick = () => patchNoteOpen(main, r.dataset.pn));
}
SECTIONS.patchnotes = main => patchNotesView(main);
