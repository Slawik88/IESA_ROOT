// app.devmode.js — БЛОК 25: dev-mod оверлей (плавающая отладочная панель).
// Отдельный classic-script, НЕ входит в склейку app.js. Грузится всем, но
// активируется ТОЛЬКО после 200 от /admin/dev-overlay/check — все данные за
// гейтом на бэке (DEVELOPER_ID + DEVELOPER_HELPER_IDS), фронт лишь рисует.
(function () {
  'use strict';

  // ── Лог последних fetch-запросов (вкладка «API») ─────────────────────────
  var API_LOG = [];
  var _origFetch = window.fetch;
  window.fetch = function (input, init) {
    var url = (typeof input === 'string') ? input : ((input && input.url) || '');
    var method = (init && init.method) || (input && input.method) || 'GET';
    var t0 = Date.now();
    return _origFetch.apply(this, arguments).then(function (res) {
      try {
        API_LOG.unshift({ url: url, method: method, status: res.status, ms: Date.now() - t0 });
        if (API_LOG.length > 10) API_LOG.pop();
        if (window._devmodeRenderApi) window._devmodeRenderApi();
      } catch (e) {}
      return res;
    });
  };

  var MY_ID = 0;
  var panelOpen = false;

  function boot() {
    if (typeof api !== 'function') { setTimeout(boot, 600); return; }
    api('/admin/dev-overlay/check')
      .then(function (r) { if (r && r.ok) { MY_ID = r.id; initUI(); } })
      .catch(function () { /* не дев — молча ничего не показываем */ });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function initUI() {
    var st = document.createElement('style');
    st.textContent = [
      // UX-фикс (скрин юзера): FAB 44px непрозрачный наезжал на кнопки контента
      // («Питомцы» в профиле) — теперь меньше, полупрозрачный и прижат к краю,
      // при нажатии/наведении проявляется
      '#devmode-fab{position:fixed;bottom:66px;right:4px;z-index:9998;width:36px;height:36px;opacity:.45;',
      ' border-radius:50%;background:#1c2733;border:1px solid #3a4a5c;color:#ffd166;font-size:16px;',
      ' display:flex;align-items:center;justify-content:center;box-shadow:0 2px 10px rgba(0,0,0,.5);cursor:pointer;',
      ' transition:opacity .2s}',
      '#devmode-fab:active,#devmode-fab:hover{opacity:1}',
      '#devmode-panel{position:fixed;inset:auto 8px 122px 8px;max-height:62vh;z-index:9999;',
      ' background:#12181f;border:1px solid #3a4a5c;border-radius:12px;display:none;flex-direction:column;',
      ' font:12px/1.45 monospace;color:#cfe3f5;box-shadow:0 6px 24px rgba(0,0,0,.6)}',
      '#devmode-panel.open{display:flex}',
      '.dm-tabs{display:flex;gap:4px;padding:8px 8px 0}',
      '.dm-tab{flex:1;padding:6px 4px;text-align:center;background:#1c2733;border-radius:8px 8px 0 0;cursor:pointer;color:#8fa8c0}',
      '.dm-tab.on{background:#25313f;color:#ffd166}',
      '.dm-body{overflow:auto;padding:8px;border-top:1px solid #3a4a5c;-webkit-overflow-scrolling:touch}',
      '.dm-kv{display:grid;grid-template-columns:minmax(90px,40%) 1fr;gap:2px 8px;word-break:break-all}',
      '.dm-kv b{color:#8fa8c0;font-weight:400}',
      '.dm-sec{margin:8px 0 4px;color:#ffd166;font-weight:700}',
      '.dm-pre{white-space:pre-wrap;word-break:break-all;background:#0d1218;border-radius:6px;padding:6px;margin:4px 0}',
      '.dm-row-ok{color:#7fd67f}.dm-row-bad{color:#ff7b7b;font-weight:700}',
      '.dm-inp{width:130px;background:#0d1218;border:1px solid #3a4a5c;color:#cfe3f5;border-radius:6px;padding:4px 6px;font:inherit}',
      '.dm-btn{background:#25313f;border:1px solid #3a4a5c;color:#ffd166;border-radius:6px;padding:4px 10px;font:inherit;cursor:pointer}',
    ].join('');
    document.head.appendChild(st);

    var fab = document.createElement('button');
    fab.id = 'devmode-fab'; fab.type = 'button'; fab.textContent = '🛠';
    fab.title = 'Dev-режим (Ctrl+Shift+D)';
    document.body.appendChild(fab);

    var panel = document.createElement('div');
    panel.id = 'devmode-panel';
    panel.innerHTML =
      '<div class="dm-tabs">' +
      '  <div class="dm-tab on" data-t="reg">Реестр</div>' +
      '  <div class="dm-tab" data-t="data">Данные</div>' +
      '  <div class="dm-tab" data-t="api">API</div>' +
      '  <div class="dm-tab" data-t="diff">Расхождения</div>' +
      '</div>' +
      '<div class="dm-body" id="dm-body">…</div>';
    document.body.appendChild(panel);

    function toggle() { panelOpen = !panelOpen; panel.classList.toggle('open', panelOpen); if (panelOpen) render(); }
    fab.addEventListener('click', toggle);
    document.addEventListener('keydown', function (e) {
      if (e.ctrlKey && e.shiftKey && (e.key === 'D' || e.key === 'd')) { e.preventDefault(); toggle(); }
    });

    var curTab = 'reg';
    panel.querySelectorAll('.dm-tab').forEach(function (t) {
      t.addEventListener('click', function () {
        panel.querySelectorAll('.dm-tab').forEach(function (x) { x.classList.remove('on'); });
        t.classList.add('on'); curTab = t.dataset.t; render();
      });
    });

    var body = panel.querySelector('#dm-body');
    var lastSnap = null, lastSnapId = MY_ID;

    function kvTable(obj) {
      if (!obj) return '<i>нет строки</i>';
      var h = '<div class="dm-kv">';
      Object.keys(obj).forEach(function (k) { h += '<b>' + esc(k) + '</b><span>' + esc(obj[k]) + '</span>'; });
      return h + '</div>';
    }

    function renderData() {
      var top = '<div style="display:flex;gap:6px;margin-bottom:6px">' +
        '<input class="dm-inp" id="dm-uid" inputmode="numeric" value="' + (lastSnapId || MY_ID) + '">' +
        '<button class="dm-btn" id="dm-load">Загрузить</button></div>';
      var content = '';
      if (lastSnap) {
        content += '<div class="dm-sec">users (сырая строка)</div>' + kvTable(lastSnap.users);
        content += '<div class="dm-sec">daily_login (chat_id=0, глоб. стрик)</div>' + kvTable(lastSnap.daily_login_global);
        var lists = [['user_chat_stats', 'чаты'], ['pets', 'питомцы'], ['inventory', 'инвентарь'],
                     ['achievements', 'ачивки'], ['wallet_log_recent', 'кошелёк (15)'],
                     ['global_sanctions_recent', 'санкции (5)']];
        lists.forEach(function (pair) {
          var arr = lastSnap[pair[0]] || [];
          content += '<div class="dm-sec">' + pair[1] + ' — ' + arr.length + '</div>' +
            '<div class="dm-pre">' + esc(JSON.stringify(arr, null, 1)) + '</div>';
        });
      } else { content = '<i>Введите Telegram ID и нажмите «Загрузить»</i>'; }
      body.innerHTML = top + content;
      body.querySelector('#dm-load').addEventListener('click', function () {
        var uid = parseInt(body.querySelector('#dm-uid').value, 10) || MY_ID;
        api('/admin/dev-overlay/user/' + uid).then(function (r) {
          lastSnap = r; lastSnapId = uid; if (curTab === 'data') renderData();
        }).catch(function (e) { body.innerHTML = top + '<span class="dm-row-bad">' + esc(e) + '</span>'; });
      });
    }

    function renderApi() {
      body.innerHTML = API_LOG.length
        ? API_LOG.map(function (r) {
            var cls = r.status < 400 ? 'dm-row-ok' : 'dm-row-bad';
            return '<div><span class="' + cls + '">' + r.status + '</span> ' + esc(r.method) +
                   ' ' + esc(r.url) + ' <i>(' + r.ms + 'мс)</i></div>';
          }).join('')
        : '<i>Запросов пока нет</i>';
    }
    window._devmodeRenderApi = function () { if (panelOpen && curTab === 'api') renderApi(); };

    function renderDiff() {
      body.innerHTML = '<i>Сверяю /profile/me с сырой строкой users…</i>';
      Promise.all([api('/profile/me'), api('/admin/dev-overlay/user/' + MY_ID)])
        .then(function (res) {
          var me = res[0], raw = res[1].users || {}, login = res[1].daily_login_global || {};
          var rows = [
            ['🪙 mora',        me.mora,          raw.user_balance_mora],
            ['💎 diamonds',    me.diamonds,      raw.user_balance_diamonds],
            ['🌑 dark_mora',   me.dark_mora,     raw.user_balance_dark_mora],
            ['✨ zarniki',     me.zarniki,       raw.user_balance_zarniki],
            ['⭐ level',       me.account_level, raw.account_level],
            ['🔥 streak',      me.streak,        login.streak],
          ];
          body.innerHTML = '<div class="dm-kv"><b>поле</b><span><b>UI (/profile/me)  |  БД (raw)</b></span></div>' +
            rows.map(function (r) {
              var a = Number(r[1] == null ? 0 : r[1]), b = Number(r[2] == null ? 0 : r[2]);
              var same = Math.abs(a - b) < 0.001;
              // account_level может ЛЕГИТИМНО расходиться: /profile/me считает
              // живьём из account_xp, в БД лежит кэш — расхождение = устаревший кэш.
              var cls = same ? 'dm-row-ok' : 'dm-row-bad';
              return '<div class="' + cls + '">' + esc(r[0]) + ': ' + a + ' | ' + b + (same ? '' : '  ← РАСХОЖДЕНИЕ') + '</div>';
            }).join('');
        })
        .catch(function (e) { body.innerHTML = '<span class="dm-row-bad">' + esc(e) + '</span>'; });
    }

    // ── Реестр всех игровых сущностей ────────────────────────────────────────
    // Главный сценарий: собираешь сезон БП/промокод → ищешь предмет → тап по
    // строке копирует ID в буфер. Поиск в реальном времени по ID и названию.
    var REG = null, regQuery = '', regCat = '';

    function copyId(id) {
      var done = function () {
        var t = document.getElementById('dm-copied');
        if (t) { t.textContent = '📋 Скопировано: ' + id; t.style.opacity = '1';
                 setTimeout(function () { t.style.opacity = '.5'; }, 1200); }
      };
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(id).then(done, function () { fallback(); });
        } else { fallback(); }
      } catch (e) { fallback(); }
      function fallback() {
        try {
          var ta = document.createElement('textarea');
          ta.value = id; document.body.appendChild(ta); ta.select();
          document.execCommand('copy'); document.body.removeChild(ta); done();
        } catch (e) { window.prompt('Скопируйте ID вручную:', id); }
      }
    }
    window._dmCopyId = copyId;
    window._dmRegQ = function (v) { regQuery = (v || '').toLowerCase(); drawRegList(); };
    window._dmRegCat = function (c) { regCat = c === regCat ? '' : c; renderRegistry(true); };

    function drawRegList() {
      var listEl = document.getElementById('dm-reg-list');
      if (!listEl || !REG) return;
      var q = regQuery, cat = regCat, shown = 0, LIMIT = 120;
      var html = '';
      for (var i = 0; i < REG.length; i++) {
        var e2 = REG[i];
        if (cat && e2.cat !== cat) continue;
        if (q && e2.id.toLowerCase().indexOf(q) === -1 &&
            String(e2.name).toLowerCase().indexOf(q) === -1) continue;
        if (shown >= LIMIT) { html += '<div style="color:#8fa8c0;padding:4px 0">…уточните запрос (показано ' + LIMIT + ')</div>'; break; }
        shown++;
        html += '<div style="display:flex;gap:6px;align-items:center;padding:4px 0;border-bottom:1px solid #1c2733;cursor:pointer" ' +
                'onclick="_dmCopyId(\'' + esc(e2.id) + '\')" title="Тап — скопировать ID">' +
                '<code style="color:#ffd166;flex-shrink:0">' + esc(e2.id) + '</code>' +
                '<span style="flex:1">' + esc(e2.name) + '</span>' +
                '<i style="color:#8fa8c0;font-size:10px;flex-shrink:0">' + esc(e2.extra || '') + '</i></div>';
      }
      listEl.innerHTML = html || '<i style="color:#8fa8c0">Ничего не найдено</i>';
      var cnt = document.getElementById('dm-reg-count');
      if (cnt) cnt.textContent = shown + (cat ? ' · ' + cat : '') + (q ? ' · «' + q + '»' : '');
    }

    function renderRegistry(keepData) {
      if (!REG && !keepData) {
        body.innerHTML = '<i>Загружаю реестр…</i>';
        api('/admin/dev-overlay/registry').then(function (r) {
          REG = r.entries || []; renderRegistry(true);
        }).catch(function (e) { body.innerHTML = '<span class="dm-row-bad">' + esc(e) + '</span>'; });
        if (!REG) return;
      }
      var cats = [];
      for (var i = 0; i < REG.length; i++)
        if (cats.indexOf(REG[i].cat) === -1) cats.push(REG[i].cat);
      var chips = cats.map(function (c) {
        var on = c === regCat;
        return '<span style="padding:2px 7px;border-radius:8px;cursor:pointer;white-space:nowrap;' +
               (on ? 'background:#ffd166;color:#12181f' : 'background:#1c2733;color:#8fa8c0') +
               '" onclick="_dmRegCat(\'' + esc(c) + '\')">' + esc(c) + '</span>';
      }).join('');
      body.innerHTML =
        '<input class="dm-inp" style="width:100%;box-sizing:border-box" placeholder="🔎 Поиск по ID и названию…" ' +
        'value="' + esc(regQuery) + '" oninput="_dmRegQ(this.value)">' +
        '<div style="display:flex;gap:4px;overflow-x:auto;padding:6px 0">' + chips + '</div>' +
        '<div style="display:flex;justify-content:space-between;color:#8fa8c0;font-size:10px;margin-bottom:2px">' +
        '<span id="dm-reg-count"></span><span id="dm-copied" style="opacity:.5;transition:opacity .3s">тап по строке — копия ID</span></div>' +
        '<div id="dm-reg-list"></div>';
      drawRegList();
    }

    function render() {
      if (curTab === 'reg') renderRegistry();
      else if (curTab === 'data') renderData();
      else if (curTab === 'api') renderApi();
      else renderDiff();
    }
  }

  boot();
})();
