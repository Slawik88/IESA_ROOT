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

function pnPreviewMarkup() {
  const w = PN.work, imgs = w.images;
  const gallery = imgs.length ? `<div class="pn-gallery n${Math.min(imgs.length, 4)}">${imgs.map(i => pnImg(i)).join('')}</div>` : '';
  const btn = w.button ? `<div class="pn-tgbtn">${esc(w.button.label)}</div>` : '';
  return `<div class="pn-phone">${gallery}<div class="pn-bubble">${pnHtml(w.text).replace(/\n/g, '<br>')}</div>${btn}</div>`;
}
async function pnRefreshPreview(main) {
  const box = $('#pn-preview', main);
  if (!box) return;
  box.innerHTML = pnPreviewMarkup();
  await pnPaintImages(box, PN.note.note_id);
  const n = pnLen(PN.work.text), lim = PN.list ? PN.list.limits : {message: 4000, caption: 1024};
  const issue = pnMarkupIssue(PN.work.text);
  $('#pn-count', main).innerHTML = `${num(n)} / ${num(lim.message)} знаков${PN.work.images.length === 1 && n <= lim.caption ? ' · поместится подписью к фото' : ''}${issue ? ` · <span class="warn">${esc(issue)}</span>` : ''}`;
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
  const n = PN.note, edit = pnEditable();
  const link = n.status === 'sent' && n.message_ids.length ? `<a class="btn small" href="https://t.me/predvestnik_official/4/${n.message_ids[n.message_ids.length - 1]}" target="_blank" rel="noopener">Открыть в канале</a>` : '';
  main.innerHTML = `<button class="btn small" id="pn-back">‹ Все патч-ноуты</button>
    ${pageHead('📣', `Пост за ${pnDate(n.note_date)}`, PN_STATES[n.status] ? PN_STATES[n.status][0] : n.status)}
    ${n.error ? `<p class="warn">${esc(n.error)}</p>` : ''}
    ${n.source_newer && edit ? '<div class="card"><p class="warn">Предвестник дополнил этот пост после ваших правок. Ваша версия сохранена.</p><div class="actions"><button class="btn small" id="pn-src">Посмотреть его версию</button><button class="btn small" id="pn-reset2">Взять его версию</button></div></div>' : ''}
    ${(n.disabled_flags || []).length ? `<p class="warn">В посте есть функции, выключенные для игроков: ${esc(n.disabled_flags.join(', '))}. Включите их или уберите из текста.</p>` : ''}
    <div class="card"><h3>Так увидят игроки</h3><div id="pn-preview"></div><p class="sub" id="pn-plan">${esc(n.plan)}</p></div>
    <div class="card"><h3>Текст поста</h3>${edit ? `<div class="pn-tools" role="toolbar" aria-label="Разметка">${PN_TOOLS.map(([t, l, h]) => `<button class="btn small" data-pntag="${t}" title="${h}" aria-label="${h}">${esc(l)}</button>`).join('')}</div>` : ''}
      <textarea id="pn-text" rows="14" ${edit ? '' : 'readonly'}>${esc(PN.work.text)}</textarea><div class="sub" id="pn-count"></div>
      <p class="sub">Разметка Telegram: выделите слова и нажмите кнопку сверху. Пустая строка — новый абзац.</p></div>
    <div class="card"><h3>Картинки</h3><div id="pn-images">${pnImagesMarkup()}</div></div>
    <div class="card"><h3>Кнопка под постом</h3><div id="pn-button">${pnButtonMarkup()}</div></div>
    <div class="actions pn-bar">${edit ? '<button class="btn" id="pn-save">Сохранить</button><button class="btn primary" id="pn-send">Проверить и отправить</button>' : ''}
      ${['sending', 'unknown'].includes(n.status) ? '<button class="btn primary" id="pn-recon">Сверить отправку</button>' : ''}${link}
      ${edit && n.edited ? '<button class="btn small" id="pn-reset">Вернуть версию Предвестника</button>' : ''}
      ${edit ? '<button class="btn small danger" id="pn-skip">Не публиковать</button>' : ''}${n.status === 'skipped' ? '<button class="btn small" id="pn-unskip">Вернуть в черновики</button>' : ''}</div>`;
  pnWire(main);
  pnRefreshPreview(main);
  pnPaintImages($('#pn-images', main), n.note_id);
}

function pnWrap(area, tag) {
  const [name] = tag.split(' ');
  let open = `<${tag}>`;
  if (name === 'a') {
    const url = prompt('Адрес ссылки (https://…)', 'https://');
    if (!url || !/^(https|tg):\/\//.test(url)) return;
    open = `<a href="${url.replace(/"/g, '%22')}">`;
  }
  const {selectionStart: s, selectionEnd: e, value: v} = area;
  area.value = v.slice(0, s) + open + v.slice(s, e) + `</${name}>` + v.slice(e);
  area.focus(); area.selectionStart = s + open.length; area.selectionEnd = e + open.length;
  area.dispatchEvent(new Event('input'));
}

function pnRedrawImages(main) {
  $('#pn-images', main).innerHTML = pnImagesMarkup();
  pnWireImages(main); pnPaintImages($('#pn-images', main), PN.note.note_id); pnRefreshPreview(main);
}
function pnChanged(main) { PN.dirty = true; pnRefreshPreview(main); }
