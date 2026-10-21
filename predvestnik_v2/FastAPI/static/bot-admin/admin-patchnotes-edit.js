// ── Патч-ноуты: редактор одного поста, предпросмотр как в Telegram и отправка ─────────

async function patchNoteOpen(main, noteId) {
  showSectionLoading(main, 'patchnotes');
  const note = await loadSectionData(main, `/patch-notes/${encodeURIComponent(noteId)}`, () => patchNoteOpen(main, noteId), 'patchnotes');
  if (!note) return;
  PN.note = note; PN.dirty = false;
  PN.work = {text: note.text_html, images: note.images.map(i => ({...i})), button: note.button ? {...note.button} : null};
  pnEditor(main);
}

const pnEditable = () => ['draft', 'failed'].includes(PN.note.status);
const pnTextEditable = () => pnEditable() || (PN.note.status === 'sent' && PN.note.message_ids.length > 0);
// Те же «слова разработчика», что проверяет сервер (core/patch_notes.py: JARGON); \w в JS не видит кириллицу.
function pnJargon(text) {
  const list = (PN.list && PN.list.jargon) || [];
  if (!list.length) return [];
  const re = new RegExp('(?<![\\p{L}\\d_-])(?:' + list.map(p => p.replace(/\\w/g, '[\\p{L}\\d_]')).join('|') + ')(?![\\p{L}\\d_-])', 'giu');
  return [...new Set((pnPlain(text).match(re) || []).map(w => w.toLowerCase()))];
}

function pnPreviewMarkup() {
  const w = PN.work, imgs = w.images;
  const gallery = imgs.length ? `<div class="pn-gallery n${Math.min(imgs.length, 4)}">${imgs.map(i => pnImg(i)).join('')}</div>` : '';
  const album = imgs.length > 1;   // у альбома нет кнопок: бот ставит ссылку в конце подписи
  const btn = w.button && !album ? `<div class="pn-tgbtn">${esc(w.button.label)}</div>` : '';
  const link = w.button && album ? `<br><br>👉 <a>${esc(w.button.label)}</a>` : '';
  return `<div class="pn-phone">${gallery}<div class="pn-bubble">${pnHtml(w.text).replace(/\n/g, '<br>')}${link}</div>${btn}</div>`;
}
async function pnRefreshPreview(main) {
  const box = $('#pn-preview', main);
  if (!box) return;
  box.innerHTML = pnPreviewMarkup();
  const plan = $('#pn-plan', main);
  if (plan && typeof pnPlanNow === 'function') plan.textContent = pnPlanNow();
  await pnPaintImages(box, PN.note.note_id);
  const n = pnLen(PN.work.text), lim = PN.list ? PN.list.limits : {message: 990, caption: 1024};
  const issue = pnMarkupIssue(PN.work.text), words = pnJargon(PN.work.text);
  const tone = n <= 500 ? 'коротко, отлично' : n <= lim.message ? 'можно короче' : 'слишком длинно — сократите';
  $('#pn-count', main).innerHTML = `${num(n)} / ${num(lim.message)} знаков · ${tone}${issue ? ` · <span class="warn">${esc(issue)}</span>` : ''}${words.length ? ` · <span class="warn">технические слова: ${esc(words.join(', '))}</span>` : ''}`;
  $('#pn-count', main).classList.toggle('warn', n > lim.message);
}

function pnImagesMarkup() {
  const imgs = PN.work.images, edit = pnEditable();
  const lib = (PN.list && PN.list.library) || [];
  return `${imgs.length ? '' : '<p class="sub">Без картинок пост уйдёт одним текстовым сообщением.</p>'}
    <div class="pn-thumbs">${imgs.map((img, i) => `<figure class="pn-thumb">${pnImg(img)}
      <figcaption>${img.ref === 'cover' ? `Обложка: ${esc(img.title)}` : esc(img.alt || (img.ref.startsWith('upload:') ? 'Ваше фото' : img.ref.slice(5)))}</figcaption>
      ${edit ? `<div class="actions"><button class="btn small" data-pnmove="${i}:-1" ${i ? '' : 'disabled'} aria-label="Выше">↑</button><button class="btn small" data-pnmove="${i}:1" ${i < imgs.length - 1 ? '' : 'disabled'} aria-label="Ниже">↓</button>
        <button class="btn small" data-pnalt="${i}">Подпись</button><button class="btn small danger" data-pndel="${i}">Убрать</button></div>` : ''}</figure>`).join('')}</div>
    ${edit && imgs.length < 10 ? `<div class="actions" style="margin-top:8px"><label class="btn small pn-upload">📷 Загрузить фото<input type="file" id="pn-file" accept="image/png,image/jpeg,image/webp" hidden/></label>
      ${lib.length ? '<button class="btn small" id="pn-lib">🗂 Из выпуска</button>' : ''}<button class="btn small" id="pn-cover">🎴 Обложка</button></div>` : ''}`;
}

function pnButtonMarkup() {
  const b = PN.work.button, opts = (PN.list && PN.list.buttons) || [], dis = pnEditable() ? '' : 'disabled';
  return `<div class="grid2"><div class="field"><label>Куда ведёт кнопка</label><select id="pn-bkey" ${dis}><option value="">Без кнопки</option>
    ${opts.map(o => `<option value="${o.key}" ${b && b.key === o.key ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select></div>
    <div class="field"><label>Подпись кнопки</label><input id="pn-blabel" maxlength="40" value="${esc(b ? b.label : '')}" ${b && !dis ? '' : 'disabled'}/></div></div>`;
}

function pnEditor(main) {
  const n = PN.note, edit = pnEditable(), textEdit = pnTextEditable(), sent = n.status === 'sent';
  const link = n.status === 'sent' && n.message_ids.length ? `<a class="btn small" href="https://t.me/predvestnik_official/4/${n.message_ids[n.message_ids.length - 1]}" target="_blank" rel="noopener">Открыть в канале</a>` : '';
  main.innerHTML = `<button class="btn small" id="pn-back">‹ Все патч-ноуты</button>
    ${pageHead('📣', `Пост за ${pnDate(n.note_date)}`, PN_STATES[n.status] ? PN_STATES[n.status][0] : n.status)}
    ${n.error ? `<p class="warn">${esc(n.error)}</p>` : ''}
    ${n.source_newer && edit ? '<div class="card"><p class="warn">Предвестник дополнил этот пост после ваших правок. Ваша версия сохранена.</p><div class="actions"><button class="btn small" id="pn-src">Посмотреть его версию</button><button class="btn small" id="pn-reset2">Взять его версию</button></div></div>' : ''}
    ${(n.older_pending || []).length ? `<p class="warn">Сначала есть неотправленные посты за более ранние дни (${esc(n.older_pending.map(pnDate).join(', '))}). Отправляйте по порядку или пометьте их «Не публиковать».</p>` : ''}
    ${(n.issues || []).length ? `<p class="warn">${esc(n.issues.join('; '))}. Перепишите языком игрока.</p>` : ''}
    ${(n.disabled_flags || []).length ? `<p class="warn">В посте есть функции, выключенные для игроков: ${esc(n.disabled_flags.join(', '))}. Включите их или уберите из текста.</p>` : ''}
    <div class="card"><h3>Так увидят игроки</h3><div id="pn-preview"></div><p class="sub" id="pn-plan">${esc(n.plan)}</p></div>
    <div class="card"><h3>Текст поста</h3>${sent && textEdit ? '<p class="sub">Пост уже в канале. Можно исправить опечатку в тексте — фото и кнопка останутся.</p>' : ''}${textEdit ? `<div class="pn-tools" role="toolbar" aria-label="Разметка">${PN_TOOLS.map(([t, l, h]) => `<button class="btn small" data-pntag="${t}" title="${h}" aria-label="${h}">${esc(l)}</button>`).join('')}</div>` : ''}
      <textarea id="pn-text" rows="10" ${textEdit ? '' : 'readonly'}>${esc(PN.work.text)}</textarea><div class="sub" id="pn-count"></div>
      <p class="sub">Одна строка на новинку: «эмодзи <b>название</b> — суть». Чем короче, тем больше людей дочитают.</p></div>
    <div class="card"><h3>Картинки</h3><div id="pn-images">${pnImagesMarkup()}</div></div>
    <div class="card"><h3>Кнопка под постом</h3><div id="pn-button">${pnButtonMarkup()}</div></div>
    <div class="actions pn-bar">${edit ? '<button class="btn" id="pn-save">Сохранить</button><button class="btn primary" id="pn-send">Проверить и отправить</button>' : ''}
      ${sent && textEdit ? '<button class="btn primary" id="pn-fix">Исправить текст в канале</button>' : ''}
      ${['sending', 'unknown'].includes(n.status) ? '<button class="btn primary" id="pn-recon">Сверить отправку</button>' : ''}${link}
      ${edit && n.edited ? '<button class="btn small" id="pn-reset">Вернуть версию Предвестника</button>' : ''}
      ${edit ? '<button class="btn small danger" id="pn-skip">Не публиковать</button>' : ''}${n.status === 'skipped' ? '<button class="btn small" id="pn-unskip">Вернуть в черновики</button>' : ''}</div>`;
  pnWire(main);
  pnRefreshPreview(main);
  pnPaintImages($('#pn-images', main), n.note_id);
}

// Ссылка — через свою шторку: window.prompt в WebView Telegram на части телефонов не открывается.
function pnWrap(area, tag) {
  const [name] = tag.split(' '), {selectionStart: s, selectionEnd: e} = area;
  if (name !== 'a') return pnInsert(area, s, e, `<${tag}>`, name);
  sheet('Ссылка', `<div class="field"><label>Адрес (https://…)</label><input id="pn-url" inputmode="url" value="https://"/></div>`, 'Вставить', () => {
    const url = $('#pn-url').value.trim();
    if (!/^(https|tg):\/\/\S+$/.test(url)) throw new Error('Адрес начинается с https://');
    pnInsert(area, s, e, `<a href="${url.replace(/"/g, '%22')}">`, 'a');
  });
}
function pnInsert(area, s, e, open, name) {
  const v = area.value;
  area.value = v.slice(0, s) + open + v.slice(s, e) + `</${name}>` + v.slice(e);
  area.focus(); area.selectionStart = s + open.length; area.selectionEnd = e + open.length;
  area.dispatchEvent(new Event('input'));
}

function pnRedrawImages(main) {
  $('#pn-images', main).innerHTML = pnImagesMarkup();
  pnWireImages(main); pnPaintImages($('#pn-images', main), PN.note.note_id); pnRefreshPreview(main);
}
function pnChanged(main) { PN.dirty = true; pnRefreshPreview(main); }
