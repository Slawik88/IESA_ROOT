// Reports about technical problems, separate from disciplinary complaints.
(() => {
  const labels = {new:'Новые',investigating:'В работе',resolved:'Решены'};
  const categories = {avatar:'Фото',mafia:'Мафия и чат',games:'Игры',purchase:'Покупки и награды',display:'Внешний вид',other:'Другое'};
  let status = '', category = '', page = 0;
  const when = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('ru-RU'); };
  const yes = value => value === true ? 'да' : value === false ? 'нет' : '—';
  const options = (values,current,all) => `<option value="">${all}</option>`+Object.entries(values).map(([key,title]) => `<option value="${key}" ${current===key?'selected':''}>${esc(title)}</option>`).join('');
  async function list(main) {
    const query = new URLSearchParams({status,category,page:String(page)});
    const data = await loadSectionData(main,`/diagnostics?${query}`,() => list(main),'diagnostics');
    if (!data || CURRENT !== 'diagnostics') return;
    page = data.page;
    const totals = data.monitor?.totals || {};
    main.innerHTML = `<div class="support-admin"><div class="section-head"><h1>Проблемы приложения</h1><button class="btn" data-support-refresh>Обновить</button></div>
      <p class="sub">Обращения игроков · хранятся 30 дней · полный отчёт доступен в карточке.</p>
      <div class="support-admin-counts">${Object.entries(labels).map(([key,title]) => `<button class="card" data-status="${key}"><b>${num(data.counts[key]||0)}</b><span>${title}</span></button>`).join('')}</div>
      <details class="card"><summary>Работа сервиса за последний час</summary><p class="sub">Текущий процесс; после перезапуска счётчики начинают собираться заново.</p><div class="support-admin-counts">${[['requests','Запросы'],['errors_5xx','Ошибки 5xx'],['auth_401','Без авторизации'],['slow','Дольше 3 секунд'],['avatar_miss','Не получено фото']].map(([key,title]) => `<div><b>${num(totals[key]||0)}</b><span>${title}</span></div>`).join('')}</div></details>
      <div class="support-admin-filters"><label>Статус<select data-support-status>${options(labels,status,'Все статусы')}</select></label><label>Проблема<select data-support-category>${options(categories,category,'Все виды')}</select></label></div>
      <p class="sub">Обращений: ${num(data.total)}</p><div class="support-admin-list">${data.items.length ? data.items.map(item => `<button type="button" class="card support-admin-row" data-report="${esc(item.id)}"><span><b>${esc(item.code)}</b> · ${esc(categories[item.category]||item.category)}<small>${esc(when(item.created_at))} · Telegram ID ${esc(item.user_id)}</small><span>${esc(item.comment.slice(0,150)||'Без описания — сведения приложены в карточке')}</span></span><span class="pill">${esc(labels[item.status]||item.status)}</span></button>`).join('') : '<div class="empty">Таких обращений пока нет.</div>'}</div>
      <div class="support-admin-pages"><button class="btn" data-support-prev ${page===0?'disabled':''}>Назад</button><span>${page+1}</span><button class="btn" data-support-next ${(page+1)*30>=data.total?'disabled':''}>Дальше</button></div></div>`;
    main.querySelector('[data-support-refresh]').onclick = () => list(main);
    main.querySelector('[data-support-status]').onchange = event => { status=event.target.value;page=0;list(main); };
    main.querySelector('[data-support-category]').onchange = event => { category=event.target.value;page=0;list(main); };
    for (const button of main.querySelectorAll('[data-status]')) button.onclick = () => { status=button.dataset.status;page=0;list(main); };
    for (const button of main.querySelectorAll('[data-report]')) button.onclick = () => detail(button.dataset.report,main);
    main.querySelector('[data-support-prev]').onclick = () => { page--;list(main); };
    main.querySelector('[data-support-next]').onclick = () => { page++;list(main); };
  }
  function rows(events) {
    return events.slice(-100).reverse().map(event => `<tr><td>${esc(when(event.at))}</td><td>${esc(event.kind)}</td><td><code>${esc(JSON.stringify(event.data))}</code></td></tr>`).join('');
  }
  async function detail(id,main) {
    try {
      const data = await api(`/diagnostics/${encodeURIComponent(id)}`);
      if (CURRENT !== 'diagnostics') return;
      const payload = data.payload || {}, env = payload.environment || {}, server = data.server_context || {};
      const metadata = [['Платформа Telegram',env.telegram_platform],['Версия API Telegram',env.telegram_api_version],['Модель',env.model],['Платформа устройства',env.platform],['Версия ОС',env.os_version],['Браузер',env.browser_version],['Язык',env.language],['Регион языка',env.locale_region],['Часовой пояс',env.timezone],['Сеть',env.connection_type],['Экран',`${env.screen_width||'?'} × ${env.screen_height||'?'}`],['Область страницы',`${env.viewport_width||'?'} × ${env.viewport_height||'?'}`],['Версия приложения',env.app_version],['Фото в данных запуска (клиент)',yes(env.tg_photo_available)],['Фото в подписанном запуске (сервер)',yes(server.telegram_photo_available)],['Активный VIP (сервер)',yes(server.vip)],['User agent',env.user_agent]];
      sheet(data.code,`<div class="support-admin"><p>${esc(categories[data.category]||data.category)} · ${esc(when(data.created_at))}</p><p>Telegram ID: <b>${esc(data.user_id)}</b></p><p class="support-admin-comment">${esc(data.comment||'Описание не добавлено.')}</p>
        <label>Статус<select data-support-triage>${Object.entries(labels).map(([key,title]) => `<option value="${key}" ${key===data.status?'selected':''}>${title}</option>`).join('')}</select></label>
        <dl class="support-admin-meta">${metadata.map(([title,value]) => `<div><dt>${esc(title)}</dt><dd>${esc(value ?? '—')}</dd></div>`).join('')}</dl>
        <p class="sub">Снимок: ${esc(when(payload.captured_at))}. ${num(payload.events?.length||0)} событий; отброшено при ограничении размера: ${num(payload.dropped_events||0)}.</p>
        ${payload.include_diagnostics ? '' : '<p>Игрок отправил описание без технической истории.</p>'}
        <details><summary>События приложения · последние 100</summary><div class="support-admin-table"><table><thead><tr><th>Время</th><th>Вид</th><th>Сведения</th></tr></thead><tbody>${rows(payload.events||[])}</tbody></table></div></details>
        <details><summary>События сервера · текущий процесс</summary><div class="support-admin-table"><table><tbody>${rows(server.diagnostics?.events||[])}</tbody></table></div><p class="sub">${server.diagnostics?.truncated?'Показан ограниченный фрагмент.':'Только события этого пользователя, доступные в процессе при получении отчёта.'}</p></details>
        <button class="btn" type="button" data-support-export>Скачать полный JSON</button></div>`,'Сохранить статус',async () => {
        const select = document.querySelector('[data-support-triage]');
        await api(`/diagnostics/${encodeURIComponent(id)}/status`,{method:'POST',body:JSON.stringify({status:select.value})});
        toast('Статус сохранён'); refreshBadges(); list(main);
      });
      document.querySelector('[data-support-export]').onclick = async event => {
        const button = event.currentTarget; button.disabled = true;
        try {
          const report = await api(`/diagnostics/${encodeURIComponent(id)}/download`);
          const url = URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
          const link = document.createElement('a');link.href=url;link.download=`${report.code}.json`;link.click();
          setTimeout(() => URL.revokeObjectURL(url),1000);
        } catch (error) { toast(error.message,true); } finally { button.disabled=false; }
      };
    } catch (error) { toast(error.message,true); }
  }
  SECTIONS.diagnostics = list;
})();
