const $ = id => document.getElementById(id);
const escapeText = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tiers = ['D','C','B','A','S','SS','SSS'];
const decisions = {keep:'Оставить',refine:'Довести детали',redraw:'Перерисовать'};
let visible = 6, selected = '', returnFocus = null;
const measurements = new Map(COMPARE.coverage.map(row => [row.key, row]));
const audit = typeof AUDIT === 'object' ? AUDIT : {};
const hasChanges = row => !!(row.has_changes || row.size_changed || row.changed_percent ||
  row.telegram_original?.size_changed || row.telegram_original?.changed_percent);
const changedCells = new Set(COMPARE.coverage.filter(hasChanges).map(row => `${row.skin}-${row.tier}`));
const percent = value => value === 0 ? '0' : value < .001 ? '<0,001' : value.toLocaleString('ru-RU',{maximumFractionDigits:3});
$('overview').textContent = changedCells.size
  ? 'Есть изменения: отличающиеся тиры выделены. Открой ячейку и сравни обе версии.'
  : 'Здесь — нынешний вид. Измеренные кадры «до» и «после» совпадают. Предложения относятся к будущей перерисовке.';
$('revisions').textContent = `До: ${COMPARE.before.revision.slice(0,9)} · После: ${COMPARE.after.revision.slice(0,9)} · ${Object.keys(COMPARE.skins).length} образа · ${COMPARE.coverage.length} сравнений`;
for (const tier of tiers) {
  $('rarity').add(new Option(tier,tier)); $('tier').add(new Option(tier,tier));
}
for (const id of [...new Set(Object.values(COMPARE.skins).map(skin => skin.set || 'solo'))]) {
  $('set').add(new Option(id === 'solo' ? 'Без набора' : COMPARE.sets?.[id]?.name || id,id));
}
function renderRows() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const rows = Object.entries(COMPARE.skins).filter(([id,skin]) =>
    (!query || `${id} ${skin.name}`.toLocaleLowerCase().includes(query)) &&
    (!$('set').value || (skin.set || 'solo') === $('set').value) &&
    (!$('rarity').value || skin.tier === $('rarity').value) &&
    (!$('decision').value || audit[id]?.decision === $('decision').value) &&
    (!$('score').value || String(audit[id]?.score) === $('score').value));
  $('count').textContent = `Найдено: ${rows.length}. Открой тир, чтобы рассмотреть детали и предложение.`;
  $('rows').innerHTML = rows.slice(0,visible).map(([id,skin]) => `<section class="skin"><div class="skin-head"><div><h2>${escapeText(skin.name)}</h2><p>${escapeText(skin.tier)} · ${escapeText(decisions[audit[id]?.decision] || 'Разбор готовится')}</p></div></div><div class="ladder">${tiers.map(tier => {
    const row = measurements.get(`${id}-${tier}-profile-high-normal`);
    if (!row?.images) return '';
    const changed = changedCells.has(`${id}-${tier}`);
    const proposed = audit[id]?.tiers[tiers.indexOf(tier)] && !/^Без изменений/i.test(audit[id].tiers[tiers.indexOf(tier)]);
    return `<button type="button" class="tile ${changed ? 'changed' : ''} ${proposed ? 'proposed' : ''}" data-skin="${id}" data-tier="${tier}" aria-label="${escapeText(skin.name)}, тир ${tier}: открыть сравнение"><span>${tier}<small>${changed ? 'Есть правки' : '0%'}</small></span><div class="thumb-labels"><span>До</span><span>После</span></div><div class="thumbs"><img src="${row.images[0]}" alt="До" loading="lazy" width="390" height="312"><img src="${row.images[1]}" alt="После" loading="lazy" width="390" height="312"></div><small class="proposal-label">${proposed ? 'Есть предложение' : 'Оставить'}</small></button>`;
  }).join('')}</div></section>`).join('') || '<p>Таких образов нет. Измени фильтры.</p>';
  $('more').hidden = rows.length <= visible;
}
function updatePreview() {
  if (!selected) return;
  const snapshot = $('device').value === 'reduced';
  if (snapshot) {$('mode').value='profile';$('phase').value='normal';}
  $('mode').disabled=snapshot; $('phase').disabled=snapshot; $('play').disabled=snapshot; $('pause').disabled=snapshot;
  const values = {skin:selected,tier:$('tier').value,mode:$('mode').value,device:$('device').value,phase:$('phase').value};
  const hash = new URLSearchParams(values).toString();
  const row = measurements.get(`${selected}-${values.tier}-${values.mode}-${values.device}-${values.phase}`);
  for (const [index,id] of ['before','after'].entries()) {
    const frame = $(id);
    frame.removeAttribute('srcdoc');
    if (snapshot) {
      frame.src='about:blank';
      frame.srcdoc = row?.images ? `<html lang="ru"><title>Кадр без движения</title><body style="margin:0;background:#08090c"><img alt="Проверенный кадр с настройкой браузера без движения" src="${escapeText(new URL(row.images[index],location.href).href)}" style="width:100%;height:auto"></body></html>` : '<p>Это сочетание ещё не снято.</p>';
    } else frame.src = `${index ? COMPARE.after_preview : 'before/preview.html'}#${hash}`;
  }
  $('diff').textContent = row ? `Отличие кадра до сжатия: ${percent(row.changed_percent)}%.${row.telegram_original ? ` Оригинал Telegram до уменьшения: ${percent(row.telegram_original.changed_percent)}%.` : ''}` : 'Интерактивный просмотр. Это сочетание отдельно не снималось; процент отличий для него не измерен.';
}
function openDetail(id,tier) {
  selected = id; returnFocus = document.activeElement;
  $('detail-title').textContent = COMPARE.skins[id].name;
  $('tier').value = tier;
  const item = audit[id];
  $('concept').innerHTML = item ? `<h3>Предложение · ${escapeText(decisions[item.decision])}</h3><p>${escapeText(item.issue)}</p><p>${escapeText(item.proposal)}</p><table><thead><tr><th>Тир</th><th>Что предлагается</th></tr></thead><tbody>${tiers.map((name,index) => `<tr><th>${name}</th><td>${escapeText(item.tiers[index])}</td></tr>`).join('')}</tbody></table><p>${escapeText(item.surfaces)}</p><p class="meta">План: ${escapeText(item.session)}. Фактические изменения оценивай по сравнению выше.</p>` : '<p>Концепт находится в документе аудита.</p>';
  $('notes-state').textContent = '';
  try { $('notes').value = localStorage.getItem(`skin-review:${id}`) || ''; } catch (_) { $('notes').value = ''; $('notes-state').textContent = 'Браузер не разрешил хранить заметки. Скопируй их перед закрытием.'; }
  updatePreview(); $('detail').showModal();
}
$('rows').addEventListener('click', event => {const button=event.target.closest('[data-skin]');if(button)openDetail(button.dataset.skin,button.dataset.tier);});
$('filters').addEventListener('input', () => {visible=6;renderRows();});
$('filters').addEventListener('submit', event => event.preventDefault());
$('more').onclick = () => {visible+=6;renderRows();};
for (const id of ['tier','mode','device','phase']) $(id).addEventListener('change',updatePreview);
$('close').onclick = () => $('detail').close();
$('detail').addEventListener('close', () => {for(const id of ['before','after'])$(id).src='about:blank';returnFocus?.focus();});
$('notes').addEventListener('input', () => {try{localStorage.setItem(`skin-review:${selected}`,$('notes').value);$('notes-state').textContent='Заметка сохранена в этом браузере.';}catch(_){$('notes-state').textContent='Заметка не сохранена. Скопируй её перед закрытием.';}});
for (const type of ['play','pause']) $(type).onclick = () => {for(const id of ['before','after'])$(id).contentWindow.postMessage({type:`lab-${type}`},'*');};
renderRows();
