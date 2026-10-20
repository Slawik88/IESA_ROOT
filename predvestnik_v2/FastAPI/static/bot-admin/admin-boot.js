// ── Старт приложения ────────────────────────────────────────────────────────
// Последний файл: все разделы уже зарегистрировали свои адреса (route). Сначала всегда /me —
// он же обновляет куку разработчика, даже если админку открыли по ссылке на конкретный экран.

(async () => {
  if (TG) { try { TG.ready(); TG.expand(); } catch (_) {} }
  try {
    try { ME = await api('/me'); }
    catch (e) { if (e.status === 403) ME = await ownerBoot(); else throw e; }   // не сотрудник: пробуем войти как владелец чата
  } catch (e) {
    $('#main').innerHTML = accessMarkup(e);
    const again = $('#main .load-retry');
    if (again) again.onclick = () => location.reload();
    return;
  }
  if (!ME.owner) $('#hsearch').hidden = false;
  if (!ME.sections.length) { $('#main').innerHTML = emptyBox('Для вашей роли разделов пока нет.'); return; }
  NAV.depth = (history.state && history.state.adm) || 0;
  // Хэш Telegram (#tgWebAppData=…) или пустой адрес — главная. Старый выбор вкладки больше не нужен: есть адреса.
  if (!match(parseHash().path)) history.replaceState({adm: 0}, '', '#/' + homePath());
  else if (!history.state) history.replaceState({adm: 0}, '', location.hash);
  render('push');
  refreshBadges();
  setInterval(() => { if (!document.hidden) refreshBadges(); }, 60000);
})();
