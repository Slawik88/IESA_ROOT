// «Виджеты» (только создатель, S30): плитка на каждый HTML-виджет; нажатие присылает его вам в личку с ботом.
(() => {
  const tile = w => `<button type="button" class="mark-tile" data-widget="${esc(w.key)}"><span class="g">${esc(w.icon)}</span><b>${esc(w.title)}</b><small>${esc(w.hint)}</small></button>`;
  async function view(main) {
    const data = await loadSectionData(main, '/widgets', () => view(main), 'widgets');
    if (!data || CURRENT !== 'widgets') return;
    const off = data.off ? alertBox('warn', 'Виджеты выключены: «Функции» → «Виджеты в личке». Пока выключено, кнопки ниже не сработают.') : '';
    main.innerHTML = `${pageHead('🧩', 'Виджеты', 'Живые карточки прямо в сообщении. Приходят только вам в личку с ботом.')}
      ${off}
      ${alertBox('info', 'Нажмите плитку — бот пришлёт виджет вам в личку. Виджет сам спросит бота и обновится. Игроки этих виджетов пока не видят.')}
      ${section('widgets-grid', 'Прислать себе', `<div class="mark-grid">${data.items.map(tile).join('')}</div>`)}
      ${hint('Виджеты Telegram пока показывает только в личке с ботом: в группу, в переписку или пересылкой их не отправить.')}`;
    for (const button of main.querySelectorAll('[data-widget]')) button.onclick = async () => {
      button.disabled = true;
      try { toast((await api('/widgets/send', {method: 'POST', body: JSON.stringify({key: button.dataset.widget})})).message); }
      catch (e) { toast(e.message, true); }
      button.disabled = false;
    };
  }
  SECTIONS.widgets = view;
})();
