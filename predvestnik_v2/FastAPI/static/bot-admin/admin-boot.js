// ── Старт приложения ────────────────────────────────────────────────────────
// Отдельный файл: запускает админку после того, как загрузились все разделы.

(async () => {
  if (TG) { try { TG.ready(); TG.expand(); } catch (_) {} }
  showSectionLoading($('#main'), 'start');
  try {
    try { ME = await api('/me'); }
    catch (e) { if (e.status === 403) ME = await ownerBoot(); else throw e; }   // не сотрудник: пробуем войти как владелец чата
  } catch (e) {
    $('#main').innerHTML = accessMarkup(e);
    const again = $('#main .load-retry');
    if (again) again.onclick = () => location.reload();
    return;
  }
  $('#who').textContent = ME.rank_name;
  const top = $('.top');
  const headBtn = (cls, label, text, handler) => { const b = document.createElement('button'); b.type = 'button'; b.className = 'hbtn ' + cls; b.setAttribute('aria-label', label); b.title = label; b.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${text}</svg>`; b.onclick = handler; top.append(b); };
  headBtn('theme', 'Оформление', '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>', themeSheet);
  if (window.matchMedia && matchMedia('(pointer: fine)').matches) headBtn('keys', 'Горячие клавиши (?)', '<rect x="3" y="6.5" width="18" height="11" rx="2.5"/><path d="M7 10.5h.01M10.5 10.5h.01M14 10.5h.01M17 10.5h.01M8 14h8"/>', hotkeysSheet);
  if (!ME.sections.length) { $('#main').innerHTML = '<div class="empty">Для вашей роли разделов пока нет.</div>'; return; }
  // Путеводитель администрации (admin-guide.js, экран — в Mini App): последним разделом — в доке или в «Ещё»; значок «?» в шапке открывает тему того раздела, где ты сейчас.
  ME.sections.push({key: 'guide', title: 'Путеводитель'});
  headBtn('help', 'Путеводитель: этот раздел', '<circle cx="12" cy="12" r="8.5"/><path d="M9.8 9.4a2.3 2.3 0 1 1 3.2 2.1c-.7.3-1 .8-1 1.6M12 16.5h.01"/>', agContext);
  let saved = '';
  try { saved = localStorage.getItem('pv_admin_tab') || ''; } catch (_) {}
  // Ссылка из бота («бот админ помощь»): ?open=guide в личке, startapp=admin_guide в группе
  let wanted = '';
  try { wanted = new URLSearchParams(location.search).get('open') || (TG && TG.initDataUnsafe && TG.initDataUnsafe.start_param === 'admin_guide' ? 'guide' : ''); } catch (_) {}
  if (saved === 'guide') saved = '';   // вкладка «Путеводитель» уводит в Mini App: при следующем входе — обычный раздел
  if (wanted === 'guide') saved = 'guide';
  open(ME.sections.some(s => s.key === saved) ? saved : ME.sections[0].key);
  refreshBadges();
  liveConnect();   // значок жалоб и ход «Чистки» — сразу; опрос ниже остаётся запасным
  setInterval(() => { if (!document.hidden) refreshBadges(); }, 60000);
})();
