// ── Патч-ноуты: кнопки редактора — сохранить, фото, сверка и отправка в канал ──────────

function pnPlanText(n, images) {   // то же правило, что services/patch_notes_send.py: plan()
  if (!images) return 'Одно сообщение с текстом и кнопкой.';
  if (images === 1 && n <= 1024) return 'Одно фото, под ним текст и кнопка.';
  return `Сначала ${images === 1 ? 'фото' : `альбом из ${images} фото`}, сразу следом текст с кнопкой (текст длиннее 1024 знаков или фото несколько).`;
}

function pnWire(main) {
  const area = $('#pn-text', main), back = $('#pn-back', main);
  back.onclick = () => patchNotesView(main);
  if (area && pnEditable()) {
    area.oninput = () => { PN.work.text = area.value; pnChanged(main); $('#pn-plan', main).textContent = pnPlanText(pnLen(area.value), PN.work.images.length); };
    main.querySelectorAll('[data-pntag]').forEach(b => b.onclick = () => pnWrap(area, b.dataset.pntag));
  }
  const key = $('#pn-bkey', main), label = $('#pn-blabel', main);
  if (key) key.onchange = () => {
    const opt = ((PN.list && PN.list.buttons) || []).find(o => o.key === key.value);
    PN.work.button = opt ? {key: opt.key, label: opt.label} : null;
    label.value = opt ? opt.label : ''; label.disabled = !opt; pnChanged(main);
  };
  if (label) label.oninput = () => { if (PN.work.button) { PN.work.button.label = label.value; pnChanged(main); } };
  const on = (id, fn) => { const b = $('#' + id, main); if (b) b.onclick = () => fn(main).catch(e => toast(e.message, true)); };
  on('pn-save', pnSave); on('pn-send', pnSendSheet); on('pn-recon', pnReconcileSheet);
  on('pn-reset', pnReset); on('pn-reset2', pnReset); on('pn-src', pnSourceSheet);
  on('pn-skip', m => pnSkip(m, true)); on('pn-unskip', m => pnSkip(m, false));
  pnWireImages(main);
}

function pnWireImages(main) {
  const imgs = PN.work.images;
  main.querySelectorAll('[data-pnmove]').forEach(b => b.onclick = () => {
    const [i, d] = b.dataset.pnmove.split(':').map(Number);
    [imgs[i], imgs[i + d]] = [imgs[i + d], imgs[i]]; PN.dirty = true; pnRedrawImages(main);
  });
  main.querySelectorAll('[data-pndel]').forEach(b => b.onclick = () => { imgs.splice(+b.dataset.pndel, 1); PN.dirty = true; pnRedrawImages(main); });
  main.querySelectorAll('[data-pnalt]').forEach(b => b.onclick = () => {
    const img = imgs[+b.dataset.pnalt], cover = img.ref === 'cover';
    const value = prompt(cover ? 'Заголовок на обложке' : 'Что на фото (видите только вы, для порядка)', cover ? img.title : img.alt || '');
    if (value === null) return;
    if (cover) { img.title = value.trim().slice(0, 80); img.alt = `Обложка: ${img.title}`; } else img.alt = value.trim().slice(0, 200);
    PN.dirty = true; pnRedrawImages(main);
  });
  const file = $('#pn-file', main);
  if (file) file.onchange = () => pnUpload(main, file.files[0]).catch(e => toast(e.message, true));
  const lib = $('#pn-lib', main);
  if (lib) lib.onclick = () => sheet('Картинка из выпуска', `<div class="field"><select id="pn-libsel">${PN.list.library.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join('')}</select></div>`, 'Добавить', () => {
    imgs.push({ref: 'repo:' + $('#pn-libsel').value, alt: ''}); PN.dirty = true; pnRedrawImages(main);
  });
  const cover = $('#pn-cover', main);
  if (cover) cover.onclick = () => sheet('Фирменная обложка', `${hint('Тёмная карточка Предвестника с крупным заголовком. Подходит, когда показать на скриншоте нечего.')}
    <div class="field"><label>Заголовок</label><input id="pn-ctitle" maxlength="80"/></div><div class="field"><label>Метка</label><select id="pn-ckind">${Object.entries(PN_KIND).map(([k, t]) => `<option value="${k}">${t}</option>`).join('')}</select></div>`, 'Добавить', () => {
    const title = $('#pn-ctitle').value.trim();
    if (title.length < 3) throw new Error('Заголовок: хотя бы 3 знака.');
    imgs.push({ref: 'cover', title, kind: $('#pn-ckind').value, alt: `Обложка: ${title}`}); PN.dirty = true; pnRedrawImages(main);
  });
}

async function pnUpload(main, f) {
  if (!f) return;
  if (f.size > 10e6) throw new Error('Фото больше 10 МБ.');
  const data = await new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => bad(new Error('Файл не читается.')); r.readAsDataURL(f); });
  toast('Загружаем фото…');
  const res = await api(`/patch-notes/${encodeURIComponent(PN.note.note_id)}/upload`, {method: 'POST', body: JSON.stringify({data_base64: data})});
  PN.work.images.push({ref: res.ref, alt: f.name.replace(/\.[a-z]+$/i, '').slice(0, 200)});
  PN.dirty = true; pnRedrawImages(main); toast('Фото добавлено. Не забудьте сохранить.');
}

async function pnSave(main, quiet = false) {
  const n = PN.note;
  const issue = pnMarkupIssue(PN.work.text);
  if (issue) throw new Error(issue);
  const fresh = await api(`/patch-notes/${encodeURIComponent(n.note_id)}`, {method: 'PUT', body: JSON.stringify({revision: n.revision, text: PN.work.text, images: PN.work.images, button: PN.work.button})});
  PN.note = fresh; PN.dirty = false;
  PN.work = {text: fresh.text_html, images: fresh.images.map(i => ({...i})), button: fresh.button ? {...fresh.button} : null};
  if (!quiet) { toast('Сохранено.'); pnEditor(main); }
  return fresh;
}

async function pnReset(main) {
  if (!confirm('Вернуть текст, фото и кнопку, которые подготовил Предвестник? Ваши правки пропадут.')) return;
  PN.note = await api(`/patch-notes/${encodeURIComponent(PN.note.note_id)}/reset`, {method: 'POST', body: JSON.stringify({revision: PN.note.revision})});
  PN.dirty = false; toast('Вернули версию Предвестника.'); patchNoteOpen(main, PN.note.note_id);
}

async function pnSourceSheet() {
  sheet('Версия Предвестника', `<div class="pn-phone"><div class="pn-bubble">${pnHtml(PN.note.source_text || '').replace(/\n/g, '<br>')}</div></div>
    <p class="sub">Можно скопировать нужные строки в свой текст или взять эту версию целиком.</p>`, 'Закрыть', () => {}, {info: true});
}

async function pnSkip(main, skip) {
  if (skip && !confirm('Не публиковать этот пост? Его можно будет вернуть в черновики.')) return;
  await api(`/patch-notes/${encodeURIComponent(PN.note.note_id)}/skip`, {method: 'POST', body: JSON.stringify({skip})});
  PN.dirty = false; toast(skip ? 'Пост убран из очереди.' : 'Пост снова в черновиках.'); patchNotesView(main);
}

async function pnSendSheet(main) {
  let n = PN.note;
  if (PN.dirty) n = await pnSave(main, true);
  pnEditor(main);
  const flags = n.disabled_flags || [];
  sheet('Отправить в канал', `${hint('Последний взгляд: ниже ровно то, что появится в теме «Обновления». После отправки пост не редактируется отсюда.')}
    <div id="pn-final">${pnPreviewMarkup()}</div><p class="sub">${esc(n.plan)}</p>
    ${flags.length ? `<div class="field switch"><input type="checkbox" id="pn-flags"/><label for="pn-flags" style="margin:0">Знаю, что ${esc(flags.join(', '))} выключено для игроков — всё равно отправить</label></div>` : ''}`,
    'Отправить в канал', async () => {
      const res = await api(`/patch-notes/${encodeURIComponent(n.note_id)}/publish`, {method: 'POST', body: JSON.stringify({expected_digest: n.digest, confirm_flags: !!($('#pn-flags') && $('#pn-flags').checked)})});
      toast(res.replayed ? 'Этот пост уже был опубликован.' : 'Опубликовано в канале.');
      patchNoteOpen(main, n.note_id);
    }, {cancelText: 'Ещё поправлю'});
  pnPaintImages($('#pn-final'), n.note_id);
}

async function pnReconcileSheet(main) {
  const n = PN.note;
  sheet('Сверить отправку', `<p>Ответ Telegram потерялся, пост мог дойти. Откройте <a href="https://t.me/predvestnik_official/4" target="_blank" rel="noopener">тему обновлений</a> и проверьте. Повторно ничего не отправляется.</p>
    <div class="field"><label>Что в теме</label><select id="pn-found"><option value="">Выберите</option><option value="1">Пост есть целиком</option><option value="0">Поста нет (обрывки я удалил)</option></select></div>
    <div class="field"><label>Номер сообщения (последнее число в ссылке, если пост есть)</label><input id="pn-msg" type="number" min="1"/></div>
    <div class="field"><label>Как проверили</label><input id="pn-why" maxlength="300" placeholder="Например: открыл тему, поста нет"/></div>`, 'Записать', async () => {
    const found = $('#pn-found').value;
    if (!found) throw new Error('Выберите, что в теме.');
    await api(`/patch-notes/${encodeURIComponent(n.note_id)}/reconcile`, {method: 'POST', body: JSON.stringify({found: found === '1', message_id: Number($('#pn-msg').value) || null, reason: $('#pn-why').value.trim()})});
    toast('Сверка записана.'); patchNoteOpen(main, n.note_id);
  });
}
