// ── Общие хелперы страницы ──────────────────────
// Админка чата, глобальная модерация и консоль разработчика удалены (код);
// новая админка пишется с нуля.
function esc(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// Refresh current page data
function refreshPage() {
  const page = _activePage;
  const rb = document.querySelector('.hdr-refresh');
  if (rb) { rb.classList.remove('spinning'); void rb.offsetWidth; rb.classList.add('spinning'); }
  const loaders = {
    profile:loadProfile, more:loadProfile, arena:loadArena
  };
  if(page && loaders[page]) { _loaded.delete(page); loaders[page](); toast('Данные обновлены'); }
}
