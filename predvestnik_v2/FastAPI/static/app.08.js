// ── 🛠 Консоль разработчика (только DEVELOPER_ID, global_rank=3) ──────────────────
// loadGlobalDev() был одной функцией на ~400 строк со всем HTML сразу — разбит по
// вкладкам (см. IMPLEMENTATION_BLOCKS/БЛОК34), каждая вкладка — своя функция-шаблон.
let _devItems=null;
let _devUserId=0;   // ID игрока из последнего «Досье» — для визуального инвентаря (БЛОК 4.1)
function _devTabBtnsHtml(){
  return `<div class="dev-tabs tab-inner" style="margin-bottom:8px;display:flex;flex-wrap:wrap;gap:2px">
    <button class="tb active" onclick="swDev('sys',this)">🖥 Система</button>
    <button class="tb" onclick="swDev('players',this)">👥 Игроки</button>
    <button class="tb" onclick="swDev('content',this)">🎫 Контент</button>
    <button class="tb" onclick="swDev('bc',this)">📢 Вещание</button>
    <button class="tb" onclick="swDev('sql',this)">🖥 SQL</button>
    <button class="tb" onclick="swDev('metrics',this)">📊 Метрики</button>
    <button class="tb" onclick="swDev('themes',this)">🎨 Темы</button>
  </div>
`;
}
function _devSysTabHtml(){
  return `<div id="dev-t-sys">
    <div id="dev-overview"><div class="loader">Загрузка...</div></div>
    <div class="card">
      <div class="card-title">🔌 Глобальные модули <button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px" onclick="loadDevFlags()">🔄</button></div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:8px">Отключение блокирует и бот-команды, и вкладку на сайте.</div>
      <div id="dev-flags"><div class="loader">Загрузка...</div></div>
    </div>
    <div class="card">
      <div class="card-title">🧩 Модули чата <button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px" onclick="devLoadChatMods(el('dev-mod-chat-sel')?.value)">🔄</button></div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:8px">Включить/выключить модуль для конкретного чата.</div>
      <select id="dev-mod-chat-sel" class="num-input" style="margin-bottom:8px" onchange="devLoadChatMods(this.value)"><option value="">— выбрать чат —</option></select>
      <div id="dev-mod-modules"></div>
    </div>
  </div>
`;
}
function _devPlayersTabHtml(){
  return `<div id="dev-t-players" style="display:none">
    <div class="card">
      <div class="card-title">🔎 Досье на игрока</div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <select id="dev-chat-sel" class="num-input" style="flex:1;margin:0" onchange="devLoadMembers()"><option value="">— выбрать чат —</option></select>
        <select id="dev-member-sel" class="num-input" style="flex:1;margin:0" onchange="devPickMember()"><option value="">— участник —</option></select>
      </div>
      <div style="display:flex;gap:6px">
        <input id="dev-q" type="text" class="num-input" style="flex:1;margin:0" placeholder="или ID / @username"/>
        <button class="btn btn-gold" onclick="devLookupUser()">Найти</button>
      </div>
      <div id="dev-user-result"></div>
    </div>
    <div class="card">
      <div class="card-title">💰 Баланс (+/−)</div>
      <input id="dev-bal-uid" type="number" class="num-input" style="margin-bottom:6px" placeholder="ID пользователя"/>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <select id="dev-bal-cur" class="num-input" style="flex:1;margin:0">
          <option value="mora">🪙 Мора</option>
          <option value="diamonds">💎 Алмазы</option>
          <option value="dark_mora">🌑 Тёмная мора</option>
          <option value="zarniki">✨ Зарники</option>
        </select>
        <input id="dev-bal-amt" type="number" step="any" class="num-input" style="flex:1;margin:0" placeholder="Сумма (− забрать)"/>
      </div>
      <input id="dev-bal-reason" class="num-input" style="margin-bottom:6px" placeholder="Причина (обязательно · покажется игроку)"/>
      <button class="btn btn-gold btn-full" onclick="devAdjustBalance()">Применить</button>
    </div>
    <div class="card">
      <div class="card-title">🎁 Выдать предмет (− забрать)</div>
      <input id="dev-item-uid" type="number" class="num-input" style="margin-bottom:6px" placeholder="ID пользователя"/>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-item-id" list="dev-items-dl" class="num-input" style="flex:1.6;margin:0" placeholder="item_id (или 📋 каталог)"/>
        <datalist id="dev-items-dl"></datalist>
        <input id="dev-item-qty" type="number" class="num-input" style="flex:1;margin:0" placeholder="Кол-во" value="1"/>
      </div>
      <button class="btn btn-ghost btn-sm btn-full" style="margin-bottom:6px" onclick="devItemCatalog()">📋 Каталог предметов (полный список)</button>
      <input id="dev-item-reason" class="num-input" style="margin-bottom:6px" placeholder="Причина (обязательно · покажется игроку)"/>
      <button class="btn btn-gold btn-full" onclick="devGiveItem()">Применить</button>
    </div>
    <div class="card">
      <div class="card-title">📜 Журнал выдач <button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px" onclick="loadDevLog()">🔄</button></div>
      <div id="dev-log"><div class="loader">Загрузка...</div></div>
    </div>
    <div class="card">
      <div class="card-title">👑 VIP — управление</div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-vip-uid" type="number" class="num-input" style="flex:2;margin:0" placeholder="ID пользователя"/>
        <button class="btn btn-ghost btn-sm" style="flex:1" onclick="devVipStatus()">🔍 Статус</button>
      </div>
      <div id="dev-vip-status" style="font-size:10px;color:var(--muted);margin-bottom:6px"></div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <select id="dev-vip-tier" class="num-input" style="flex:1;margin:0">
          <option value="1m">VIP-1М</option><option value="3m">VIP-3М</option>
          <option value="8m">VIP-8М</option><option value="12m">VIP-12М</option>
        </select>
        <input id="dev-vip-days" type="number" step="1" class="num-input" style="flex:1;margin:0" placeholder="Дней" value="30"/>
      </div>
      <div style="display:flex;gap:4px;margin-bottom:6px">
        ${[7,30,90,180,365].map(n=>`<button class="btn btn-ghost btn-sm" style="flex:1;padding:3px 0" onclick="el('dev-vip-days').value=${n}">${n}д</button>`).join('')}
      </div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <button class="btn btn-gold" style="flex:1" onclick="devGiveVip()">➕ Выдать/продлить</button>
        <button class="btn btn-ghost" style="flex:1" onclick="devVipAdjust()">➖ Убавить дни</button>
      </div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-ghost" style="flex:1" onclick="devVipReplace()">🔄 Заменить тариф</button>
        <button class="btn btn-red" style="flex:1" onclick="devVipRevoke()">🚫 Отозвать</button>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-top:6px">«Заменить» сбрасывает старый VIP и начисляет бонус-пакет нового тарифа. «Убавить» сокращает срок на N дней (тариф не меняется).</div>
    </div>
  </div>
`;
}
function _devContentTabHtml(){
  return `<div id="dev-t-content" style="display:none">
    <div class="card">
      <div class="card-title">🎫 БП · Шаг 1 — Сезоны</div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px">Порядок работы: 1️⃣ сезон → 2️⃣ выбрать его в таблице → 3️⃣ править награды → 4️⃣ настроить XP за действия.</div>
      <div id="dev-seasons"><div class="loader">Загрузка...</div></div>
      <div style="display:flex;gap:6px;margin:8px 0 6px">
        <input id="dev-s-id" type="text" class="num-input" style="flex:1;margin:0" placeholder="id (s2)"/>
        <input id="dev-s-label" type="text" class="num-input" style="flex:1.4;margin:0" placeholder="Название"/>
      </div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-s-start" type="date" class="num-input" style="flex:1;margin:0"/>
        <input id="dev-s-end" type="date" class="num-input" style="flex:1;margin:0"/>
      </div>
      <button class="btn btn-gold btn-full" onclick="devSaveSeason()">💾 Создать/обновить сезон</button>
      <div style="font-size:10px;color:var(--muted);margin-top:4px">id из registry (s1) можно перекрыть, создав БД-сезон с тем же id. Награды уровней общие для всех сезонов.</div>
      <div class="divider"></div>
      <div class="card-title" style="margin-top:4px">⚡ Начислить BP XP</div>
      <div style="display:flex;gap:6px">
        <input id="dev-bp-uid" type="number" class="num-input" style="flex:1.4;margin:0" placeholder="ID пользователя"/>
        <input id="dev-bp-xp" type="number" class="num-input" style="flex:1;margin:0" placeholder="XP (− снять)"/>
        <button class="btn btn-gold" onclick="devBpXp()">OK</button>
      </div>
    </div>
    <div class="card">
      <div class="card-title">🎫 БП · Шаг 2 — Таблица наград (Free / VIP) <button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px" onclick="loadBpSeasons()">🔄</button></div>
      <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
        <span style="font-size:11px;color:var(--muted);white-space:nowrap">Сезон:</span>
        <select id="dev-bp-season-sel" class="num-input" style="margin:0;flex:1" onchange="onBpSeasonChange()"></select>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px">Клик по ячейке → подставить в форму ниже. 🔧 = в БД. <b>Все правки/импорт идут в ВЫБРАННЫЙ сезон.</b></div>
      <div id="dev-bp-table" style="overflow-x:auto"><div class="loader">Загрузка...</div></div>
    </div>
    <div class="card">
      <div class="card-title">🎫 БП · Шаг 3 — Редактор наград</div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-br-season" type="text" class="num-input" style="flex:1;margin:0" placeholder="сезон" readonly title="Сезон выбирается селектором над таблицей"/>
        <input id="dev-br-level" type="number" class="num-input" style="flex:1;margin:0" placeholder="уровень"/>
        <select id="dev-br-track" class="num-input" style="flex:1;margin:0">
          <option value="free">🆓 Free</option><option value="paid">👑 VIP</option>
        </select>
      </div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-br-mora" type="number" class="num-input" style="flex:1;margin:0" placeholder="🪙 мора"/>
        <input id="dev-br-dia" type="number" class="num-input" style="flex:1;margin:0" placeholder="💎 алмазы"/>
      </div>
      <input id="dev-br-items" type="text" class="num-input" style="margin-bottom:6px" placeholder='предметы: food_basic:2, spin_token:1'/>
      <input id="dev-br-theme" type="text" class="num-input" style="margin-bottom:6px" placeholder="theme_id (необяз.)"/>
      <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);margin-bottom:6px">
        <input id="dev-br-choice" type="checkbox" onchange="el('dev-br-opt2').style.display=this.checked?'':'none'"/>
        🔀 Сделать ВЫБОРОМ из 2 наград (поля выше = вариант 1)
      </label>
      <input id="dev-br-opt2" type="text" class="num-input" style="margin-bottom:6px;display:none" placeholder='вариант 2: мора;алмазы;предметы;тема — напр. 0;5;;'/>
      <div style="display:flex;gap:6px">
        <button class="btn btn-gold" style="flex:2" onclick="devBpRewardSet()">💾 Сохранить</button>
        <button class="btn btn-red" style="flex:1" onclick="devBpRewardReset()">↩ Сброс</button>
      </div>
      <div class="divider"></div>
      <div class="card-title" style="margin-top:4px">⚙️ Массовое заполнение</div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-bk-from" type="number" class="num-input" style="flex:1;margin:0" placeholder="с ур."/>
        <input id="dev-bk-to" type="number" class="num-input" style="flex:1;margin:0" placeholder="по ур."/>
        <select id="dev-bk-track" class="num-input" style="flex:1;margin:0">
          <option value="free">🆓 Free</option><option value="paid">👑 VIP</option>
        </select>
      </div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-bk-mora" type="number" class="num-input" style="flex:1;margin:0" placeholder="🪙 база"/>
        <input id="dev-bk-mstep" type="number" class="num-input" style="flex:1;margin:0" placeholder="🪙 +шаг"/>
        <input id="dev-bk-dia" type="number" class="num-input" style="flex:1;margin:0" placeholder="💎 база"/>
      </div>
      <button class="btn btn-ghost btn-full" onclick="devBpBulk()">⚙️ Заполнить диапазон (база+шаг)</button>
      <div class="card-title" style="margin-top:10px">🎲 Раскидать пул автоматически</div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">Укажи ОБЩИЙ пул и диапазон — система распределит по уровням сама. Сумма точно сойдётся.</div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-ds-from" type="number" class="num-input" style="flex:1;margin:0" placeholder="с ур."/>
        <input id="dev-ds-to" type="number" class="num-input" style="flex:1;margin:0" placeholder="по ур."/>
        <select id="dev-ds-track" class="num-input" style="flex:1;margin:0">
          <option value="free">🆓 Free</option><option value="paid">👑 VIP</option>
        </select>
      </div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-ds-mora" type="number" class="num-input" style="flex:1;margin:0" placeholder="🪙 всего"/>
        <input id="dev-ds-dia" type="number" class="num-input" style="flex:1;margin:0" placeholder="💎 всего"/>
        <select id="dev-ds-curve" class="num-input" style="flex:1.2;margin:0">
          <option value="linear">📈 Линейно</option>
          <option value="flat">➖ Поровну</option>
          <option value="progressive">🚀 Прогрессивно</option>
        </select>
      </div>
      <button class="btn btn-ghost btn-full" onclick="devBpDistribute()">🎲 Раскидать пул по уровням</button>
      <div class="divider"></div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <button class="btn btn-ghost" style="flex:1" onclick="devBpSummary()">📊 Ценность сезона</button>
      </div>
      <div style="display:flex;gap:6px">
        <input id="dev-cp-from" type="text" class="num-input" style="flex:1;margin:0" placeholder="из сезона"/>
        <input id="dev-cp-to" type="text" class="num-input" style="flex:1;margin:0" placeholder="в сезон"/>
        <button class="btn btn-ghost" onclick="devBpCopy()">📋 Копир.</button>
      </div>
      <div id="dev-bp-out" style="font-size:11px;color:var(--muted);margin-top:6px"></div>
      <div class="divider"></div>
      <div class="card-title" style="margin-top:4px">📥 Импорт наград из JSON</div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">Вставь JSON и импортируй пачкой — не вбивая вручную. <span onclick="devBpShowExample()" style="color:var(--gold2);cursor:pointer;text-decoration:underline">Показать пример формата</span></div>
      <textarea id="dev-bp-json" class="num-input" style="margin:0 0 6px;min-height:84px;resize:vertical;font-family:monospace;font-size:10px" placeholder='{"season_id":"s1","rewards":[{"level":1,"track":"free","mora":500}, ...]}'></textarea>
      <button class="btn btn-gold btn-full" onclick="devBpImport()">📥 Импортировать JSON</button>
      <div id="dev-bp-import-out" style="font-size:10px;margin-top:4px"></div>
    </div>
    <div class="card" id="bp-xp-card">
      <div class="card-title">🎫 БП · Шаг 4 — XP за действия <button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px" onclick="loadBpXpActions()">🔄</button></div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px">Сколько XP даёт каждое действие, дневной потолок (анти-абуз) и вкл/выкл. 🔧 = оверрайд в БД. <b id="dev-bpxp-perlevel">…</b></div>
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;padding:6px;background:var(--bg2,var(--s));border-radius:8px">
        <span style="font-size:11px;white-space:nowrap">⚡ Weekend boost</span>
        <input id="dev-bpxp-weekend" type="number" class="num-input" style="width:60px;margin:0;padding:3px 5px" placeholder="%"/>
        <span style="font-size:10px;color:var(--muted)">% XP (0=выкл · сб/вс)</span>
        <button class="btn btn-sm btn-gold" style="margin-left:auto" onclick="devBpWeekendSet()">💾</button>
      </div>
      <div id="dev-bpxp-list"><div class="loader">Загрузка...</div></div>
      <div class="divider"></div>
      <div class="card-title" style="margin-top:4px">➕ Кастомное действие</div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">metric — точка инкремента из кода (a-z, 0-9, _).</div>
      <input id="dev-bpxp-metric" type="text" class="num-input" style="margin-bottom:6px" placeholder="metric (напр. duel_wins)"/>
      <input id="dev-bpxp-label" type="text" class="num-input" style="margin-bottom:6px" placeholder="ярлык (для справки игроку)"/>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-bpxp-weight" type="number" class="num-input" style="flex:1;margin:0" placeholder="вес XP"/>
        <input id="dev-bpxp-cap" type="number" class="num-input" style="flex:1;margin:0" placeholder="потолок/д (0=∞)"/>
      </div>
      <button class="btn btn-gold btn-full" onclick="devBpXpSet()">💾 Сохранить действие</button>
    </div>
    <div class="card">
      <div class="card-title">🎟 Промокоды <button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px" onclick="devPromoLoad()">🔄</button></div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px">Управление и здесь, и в чате: <code>бот dev промокод создать/список/инфо</code>. Активация игроками — «бот промокод» или сайт.</div>
      <div id="dev-promo-list"><div class="loader">Загрузка...</div></div>
      <div style="border-top:1px solid var(--dim);margin:8px 0;padding-top:8px;font-size:11px;color:var(--gold2)">➕ Новый промокод</div>
      <input id="dev-promo-code" type="text" class="num-input" style="margin-bottom:6px" placeholder="КОД (3–32, буквы/цифры/-/_)"/>
      <input id="dev-promo-desc" type="text" class="num-input" style="margin-bottom:6px" placeholder="описание (видно только вам)"/>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-promo-mora" type="number" class="num-input" style="flex:1;margin:0" placeholder="🪙 мора"/>
        <input id="dev-promo-dia" type="number" class="num-input" style="flex:1;margin:0" placeholder="💎 алмазы"/>
      </div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-promo-dark" type="number" class="num-input" style="flex:1;margin:0" placeholder="🌑 тёмная"/>
        <input id="dev-promo-zar" type="number" class="num-input" style="flex:1;margin:0" placeholder="✨ зарники"/>
      </div>
      <input id="dev-promo-items" type="text" class="num-input" style="margin-bottom:6px" placeholder="предметы: spin_token:3, food_elite:1"/>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-promo-max" type="number" class="num-input" style="flex:1;margin:0" placeholder="лимит активаций (0=∞)"/>
        <input id="dev-promo-until" type="text" class="num-input" style="flex:1;margin:0" placeholder="до: 2026-08-01 00:00"/>
      </div>
      <button class="btn btn-gold btn-full" onclick="devPromoCreate()">🎟 Создать промокод</button>
    </div>
  </div>
`;
}
function _devBcTabHtml(){
  return `<div id="dev-t-bc" style="display:none">
    <div class="card">
      <div class="card-title">📢 Рассылка</div>
      <textarea id="dev-bc-text" class="num-input" style="margin:0 0 6px;min-height:110px;resize:vertical;line-height:1.4" placeholder="Текст (HTML: <b>, <i>, <u>, <a href>, <code>…)" oninput="_bcPreview()"></textarea>
      <div style="font-size:10px;color:var(--muted);margin-bottom:2px">Кому отправить:</div>
      <select id="dev-bc-audience" class="num-input" style="margin:0 0 6px" onchange="_bcPreview()">
        <option value="main">🏠 Только основные чаты</option>
        <option value="admin">🛡 Только админ-чаты</option>
        <option value="main_admin">🏠+🛡 Основные и админки</option>
        <option value="dm_admin">✉️+🛡 ЛС и админки</option>
        <option value="dm">✉️ Только ЛС</option>
        <option value="all">🌐 Все чаты (всё подряд)</option>
      </select>
      <div id="dev-bc-count" style="font-size:11px;color:var(--gold2);margin-bottom:6px">…</div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:2px">Превью (как увидят):</div>
      <div id="dev-bc-preview" class="bc-preview">—</div>
      <button class="btn btn-teal btn-full" style="margin-bottom:6px" onclick="devBroadcastTest()">🧪 Тест себе (в ЛС)</button>
      <button class="btn btn-red btn-full" onclick="devBroadcast()">📢 Отправить рассылку</button>
    </div>
  </div>
`;
}
function _devSqlTabHtml(){
  return `<div id="dev-t-sql" style="display:none">
    <div class="card">
      <div class="card-title">🖥 SQL-консоль</div>
      <textarea id="dev-sql" class="num-input" style="margin:0 0 6px;min-height:70px;resize:vertical;font-family:monospace;font-size:11px" placeholder="SELECT * FROM users LIMIT 5"></textarea>
      <button class="btn btn-red btn-full" onclick="devRunSql()">▶ Выполнить</button>
      <div id="dev-sql-result" style="overflow-x:auto;margin-top:6px"></div>
    </div>
  </div>
`;
}
function _devMetricsTabHtml(){
  return `<div id="dev-t-metrics" style="display:none">
    <div class="card">
      <div class="card-title">📊 Аудитория <button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px" onclick="loadDevMetrics()">🔄</button></div>
      <div id="dev-metrics-kpi" style="display:flex;gap:6px;margin-bottom:14px"><div class="loader">Загрузка...</div></div>
      <div class="card-title" style="margin:12px 0 6px">🔝 Страницы <span style="font-size:10px;font-weight:400;color:var(--muted)">(30 дн)</span></div>
      <div id="dev-metrics-tabs"></div>
      <div class="card-title" style="margin:14px 0 6px">📂 Под-вкладки <span style="font-size:10px;font-weight:400;color:var(--muted)">(7 дн)</span></div>
      <div id="dev-metrics-subtabs"></div>
      <div class="card-title" style="margin:14px 0 6px">📅 По дням <span style="font-size:10px;font-weight:400;color:var(--muted)">(30 дн)</span></div>
      <div id="dev-metrics-daily" style="overflow-x:auto;max-height:220px;overflow-y:auto"></div>
    </div>
  </div>
`;
}
function _devThemesTabHtml(){
  return `<div id="dev-t-themes" style="display:none">
    <div class="card" id="tl-card">
      <div class="card-title">🎨 Theme Lab — редактор премиум-тем</div>
      <select id="dev-tl-template" class="num-input" style="margin-bottom:6px" onchange="devTLLoad()"></select>
      <div id="dev-tl-vars" class="tl-chips" style="margin-bottom:6px"></div>
      <div class="tl-grid">
        <div class="tl-editor">
          <div class="tl-editor-wrap">
            <div id="dev-tl-linenos" class="tl-linenos">1</div>
            <textarea id="dev-tl-text" class="num-input tl-textarea" oninput="_devTLUpdateLinenos();_devTLStats()" onscroll="_devTLSyncScroll()"></textarea>
          </div>
          <div id="dev-tl-stats" style="font-size:11px;color:var(--muted);margin-bottom:6px"></div>
          <div style="display:flex;gap:6px;margin-bottom:6px">
            <button class="btn btn-ghost" style="flex:1" onclick="devTLPreview()">👁 Превью</button>
            <button class="btn btn-ghost" style="flex:1" onclick="_devTLCopy()">📋 Копия</button>
          </div>
          <div style="display:flex;gap:6px;margin-bottom:6px">
            <button class="btn btn-gold" style="flex:1" onclick="devTLSave()">💾 Сохранить</button>
            <button class="btn btn-red" style="flex:1" onclick="devTLReset()">↩️ Сброс</button>
          </div>
          <button class="btn btn-ghost btn-full" style="margin-bottom:6px" onclick="devTLSendTest()">📤 Тест в Telegram (себе в ЛС)</button>
          <div id="dev-tl-status" style="font-size:10px;margin-bottom:6px"></div>
        </div>
        <div class="tl-preview-col">
          <select id="dev-tl-device" class="num-input" style="margin:0 0 6px" onchange="_devTLApplyFrame()">
            <option value="360">📱 Android compact (360px)</option>
            <option value="375">📱 iPhone SE (375px)</option>
            <option value="390" selected>📱 iPhone 14/15 (390px)</option>
            <option value="412">📱 Android (412px)</option>
            <option value="430">📱 iPhone Pro Max (430px)</option>
            <option value="500">🖥 Telegram Desktop (500px)</option>
          </select>
          <div class="tl-fontsize-row">
            <span>Aa</span>
            <input id="dev-tl-fontsize" type="range" min="12" max="20" step="0.5" value="16" oninput="_devTLApplyFrame()"/>
            <span id="dev-tl-fontsize-val">16px</span>
          </div>
          <div style="font-size:9px;color:var(--muted);margin-bottom:6px">Сверь со своим Telegram: Настройки → Внешний вид → Размер текста</div>
          <div class="tl-frame-wrap">
            <div id="dev-tl-frame" class="tl-frame">
              <div id="dev-tl-preview"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="card" id="tl-meta-card">
      <div class="card-title">🔧 Метаданные темы (цены, редкость, описание)</div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:8px">Выберите тему в Theme Lab выше → нажмите «Загрузить метаданные». Цена/редкость реально применяются при покупке (и в боте, и на сайте). Чтобы сменить валюту цены — занулите старое поле явно (0), иначе сработает старая валюта.</div>
      <button class="btn btn-ghost btn-full" style="margin-bottom:8px" onclick="devTLMetaLoad()">⬇ Загрузить метаданные</button>
      <div id="dev-tl-meta-form" style="display:none">
        <input type="hidden" id="dev-tl-meta-tid"/>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px">
          <div>
            <div style="font-size:10px;color:var(--muted);margin-bottom:2px">Имя</div>
            <input id="dev-tl-meta-name" type="text" class="num-input" style="margin:0" placeholder="Название темы"/>
          </div>
          <div>
            <div style="font-size:10px;color:var(--muted);margin-bottom:2px">Редкость</div>
            <select id="dev-tl-meta-rarity" class="num-input" style="margin:0">
              <option value="common">⬜ Обычная</option><option value="uncommon">🟩 Необычная</option>
              <option value="rare">🟦 Редкая</option><option value="epic">🟣 Эпическая</option>
              <option value="legendary">🟡 Легендарная</option><option value="mythic">🔴 Мифическая</option>
              <option value="shadow">🌑 Теневая</option><option value="zarniki">✨ Зарниковая</option>
              <option value="seasonal">🗓 Сезонная</option>
            </select>
          </div>
          <div>
            <div style="font-size:10px;color:var(--muted);margin-bottom:2px">Источник</div>
            <select id="dev-tl-meta-source" class="num-input" style="margin:0">
              <option value="">— не указан —</option>
              <option value="start">🎁 Стартовая</option><option value="shop_mora">🪙 Магазин (мора)</option>
              <option value="shop_diamond">💎 Магазин (алмазы)</option><option value="gacha_novice">🎲 Гача ученик</option>
              <option value="gacha_standard">🎲 Гача стандарт</option><option value="gacha_premium">🎲 Гача премиум</option>
              <option value="gacha_diamond">💎 Гача алмазная</option><option value="dark">🌑 Чёрный рынок</option>
              <option value="zarniki">✨ Зарники</option><option value="event">🎪 Ивент</option>
              <option value="auction">⚖️ Аукцион</option><option value="bp">🎫 Боевой пропуск</option>
            </select>
          </div>
          <div>
            <div style="font-size:10px;color:var(--muted);margin-bottom:2px">Цена Мора 🪙</div>
            <input id="dev-tl-meta-pmora" type="number" class="num-input" style="margin:0" placeholder="0"/>
          </div>
          <div>
            <div style="font-size:10px;color:var(--muted);margin-bottom:2px">Цена Алмазы 💎</div>
            <input id="dev-tl-meta-pdia" type="number" step="0.1" class="num-input" style="margin:0" placeholder="0"/>
          </div>
          <div>
            <div style="font-size:10px;color:var(--muted);margin-bottom:2px">Цена Зарники ✨</div>
            <input id="dev-tl-meta-pzar" type="number" class="num-input" style="margin:0" placeholder="0"/>
          </div>
          <div>
            <div style="font-size:10px;color:var(--muted);margin-bottom:2px">Цена Тёмная мора 🌑</div>
            <input id="dev-tl-meta-pdark" type="number" class="num-input" style="margin:0" placeholder="0"/>
          </div>
          <div style="display:flex;align-items:center;gap:6px;padding-top:14px">
            <input id="dev-tl-meta-bp" type="checkbox" style="width:16px;height:16px"/>
            <label for="dev-tl-meta-bp" style="font-size:11px;color:var(--muted)">🎫 Получаема в БП</label>
          </div>
        </div>
        <div style="margin-bottom:6px">
          <div style="font-size:10px;color:var(--muted);margin-bottom:2px">Описание</div>
          <textarea id="dev-tl-meta-desc" class="num-input" style="margin:0;min-height:50px;resize:vertical" placeholder="Описание темы для магазина"></textarea>
        </div>
        <div style="display:flex;gap:6px">
          <button class="btn btn-gold" style="flex:1" onclick="devTLMetaSave()">💾 Сохранить</button>
          <button class="btn btn-red" style="flex:none" onclick="devTLMetaDelete()">🗑 Сбросить</button>
        </div>
        <div id="dev-tl-meta-status" style="font-size:10px;margin-top:4px"></div>
      </div>
    </div>
  </div>`;
}
function loadGlobalDev() {
  el('glb-dev').innerHTML = _devTabBtnsHtml()+_devSysTabHtml()+_devPlayersTabHtml()+_devContentTabHtml()+_devBcTabHtml()+_devSqlTabHtml()+_devMetricsTabHtml()+_devThemesTabHtml();
  devLoadOverview();
  devLoadSeasons();
  devTLInit();
  loadDevLog();
  loadDevFlags();
  devLoadChats();
  devLoadChatsMod();
  loadDevMetrics();
  loadBpSeasons();
  loadBpXpActions();
  _bcLoadCounts();
  if(!_devItems) api('/admin/dev/items').then(d=>{
    _devItems=d.items||[];
    const dl=el('dev-items-dl');
    if(dl) dl.innerHTML=_devItems.map(i=>`<option value="${i.item_id}">${esc(i.name)}</option>`).join('');
  }).catch(()=>{});
  else { const dl=el('dev-items-dl'); if(dl) dl.innerHTML=_devItems.map(i=>`<option value="${i.item_id}">${esc(i.name)}</option>`).join(''); }
}
function loadDevLog() {
  const box = el('dev-log'); if(!box) return;
  api('/admin/dev/admin-log').then(d=>{
    const log = d.log || [];
    if(!log.length){ box.innerHTML='<div style="font-size:11px;color:var(--muted)">Журнал пуст.</div>'; return; }
    box.innerHTML = log.map(e=>{
      const when = e.created_at ? fmtUTC(e.created_at) : '';
      const admin = esc(e.admin_name || ('ID'+e.admin_id));
      const isSys = !e.target_id || e.target_id===0;
      if(isSys){
        // Системное действие (season_upsert/delete, bp_freeze, ...)
        return `<div style="padding:6px 0;border-bottom:1px solid var(--border2);font-size:11px">
          <div><span style="color:var(--muted)">${when}</span> · <b>${admin}</b> · <span style="color:var(--dim)">${esc(e.action||'')}</span></div>
          <div style="color:var(--bright)">${esc(e.detail||'—')}</div>
        </div>`;
      }
      const target = esc(e.target_name || ('ID'+e.target_id));
      const amt = e.amount || 0;
      const sign = amt>0?'+':'';
      const reason = (e.reason||'').trim();
      return `<div style="padding:6px 0;border-bottom:1px solid var(--border2);font-size:11px">
        <div><span style="color:var(--muted)">${when}</span> · <b>${admin}</b> → ${target}</div>
        <div style="color:var(--gold)">${esc(e.detail||'')}: <b>${sign}${fmt(amt)}</b> · было ${fmt(e.before_val)} → стало ${fmt(e.after_val)}</div>
        ${reason?`<div style="color:var(--muted)">📝 ${esc(reason)}</div>`:'<div style="color:var(--red);font-size:10px">⚠ без причины</div>'}
      </div>`;
    }).join('');
  }).catch(e=>{ box.innerHTML=`<div class="err">${e}</div>`; });
}
// Конструктор БП (БЛОК 4.4): визуальная таблица наград Free/VIP по уровням.
let _bpTableData=null;
let _bpSeason=null;   // ЕДИНЫЙ источник сезона: таблица + save + bulk + import
function loadBpSeasons() {
  const sel=el('dev-bp-season-sel'); if(!sel) return;
  api('/admin/dev/bp/seasons').then(d=>{
    const seasons=d.seasons||[];
    if(!seasons.length){
      sel.innerHTML='<option value="">— нет сезонов —</option>';
      _bpSeason=null; loadBpTable(); return;
    }
    const active=seasons.find(s=>s.active);
    if(!_bpSeason || !seasons.some(s=>s.id===_bpSeason)) _bpSeason=(active||seasons[0]).id;
    sel.innerHTML=seasons.map(s=>`<option value="${esc(s.id)}" ${s.id===_bpSeason?'selected':''}>${esc(s.label||s.id)}${s.active?' · 🟢 активный':''}</option>`).join('');
    const f=el('dev-br-season'); if(f) f.value=_bpSeason;
    loadBpTable();
  }).catch(e=>{el('dev-bp-table').innerHTML=`<div class="err">${e}</div>`;});
}
function onBpSeasonChange() {
  _bpSeason=el('dev-bp-season-sel')?.value||null;
  const f=el('dev-br-season'); if(f) f.value=_bpSeason||'';
  loadBpTable();
}
function _bpRewardFmt(r) {
  if(!r) return '—';
  if(r.options) return '🔀 выбор ×'+r.options.length;
  const p=[];
  if(r.mora) p.push('🪙'+fmt(r.mora));
  if(r.diamonds) p.push('💎'+fmtF(r.diamonds));
  (r.items||[]).forEach(it=>p.push('📦'+esc(it[0])+(it[1]>1?'×'+it[1]:'')));
  if(r.theme||r.theme_id) p.push('🎨'+esc(r.theme||r.theme_id));
  return p.length?p.join(' '):'—';
}
// «Сочность» награды — единая оценка ценности для подсветки ячеек таблицы.
function _bpCellScore(r) {
  if(!r) return 0;
  if(r.options) {
    return Math.max(0,...r.options.map(o=>_bpCellScore(o)));
  }
  return (Number(r.mora)||0) + (Number(r.diamonds)||0)*60
       + (r.items||[]).reduce((s,it)=>s+200*(Number(it[1])||1),0)
       + ((r.theme||r.theme_id)?150:0);
}
function loadBpTable() {
  const box=el('dev-bp-table'); if(!box) return;
  const q=_bpSeason?`?season_id=${encodeURIComponent(_bpSeason)}`:'';
  api('/admin/dev/bp/rewards'+q).then(d=>{
    _bpTableData=d;
    if(d.season_id){ _bpSeason=d.season_id; const f=el('dev-br-season'); if(f) f.value=d.season_id; }
    if(!d.season_id){
      box.innerHTML='<div style="color:var(--gold2);font-size:11px;padding:6px 0">⚠ Нет активного сезона и сезон не выбран. Создай/активируй сезон в разделе сезонов — без сезона награды некуда сохранять.</div>';
      return;
    }
    const byLvl={};
    (d.rewards||[]).forEach(r=>{ (byLvl[r.level]=byLvl[r.level]||{})[r.track]=r; });
    // Подсветка «сочности»: оценка ценности → уровень интенсивности относительно макс. по таблице.
    const maxScore=Math.max(1,...(d.rewards||[]).map(_bpCellScore));
    const juicy=s=>{ if(s<=0) return ''; const f=s/maxScore;
      return f>=.75?' bp-j4':f>=.5?' bp-j3':f>=.25?' bp-j2':' bp-j1'; };
    const cell=(r,lv,track)=>{
      const s=_bpCellScore(r);
      const cls='bp-cell'+(r?juicy(s):' bp-empty')+(r&&r.source==='db'?' bp-db':'');
      return `<td class="${cls}" title="${s?'ценность ≈ '+Math.round(s):'пусто'}" onclick="devBpRewardPrefill(${lv},'${track}')">${r&&r.source==='db'?'🔧 ':''}${_bpRewardFmt(r)}</td>`;
    };
    const rows=Object.keys(byLvl).map(n=>parseInt(n)).sort((a,b)=>a-b).map(lv=>
      `<tr><td class="bp-cell bp-lvl">${lv}</td>${cell(byLvl[lv].free,lv,'free')}${cell(byLvl[lv].paid,lv,'paid')}</tr>`
    ).join('');
    box.innerHTML=`<div style="font-size:10px;color:var(--muted);margin-bottom:4px">Сезон: <b>${esc(d.season_id||'—')}</b> · подсветка = ценность награды (ярче = «сочнее»)</div>
      <table class="bp-table"><thead><tr>
        <th>Ур.</th><th>🆓 Free</th><th>👑 VIP</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
  }).catch(e=>{box.innerHTML=`<div class="err">${e}</div>`;});
}
function devBpRewardPrefill(lv, track) {
  if(!_bpTableData) return;
  const r=(_bpTableData.rewards||[]).find(x=>x.level===lv&&x.track===track)||{};
  const set=(id,v)=>{const e2=el(id);if(e2)e2.value=v;};
  set('dev-br-season', _bpTableData.season_id||'s1');
  set('dev-br-level', lv);
  const tsel=el('dev-br-track'); if(tsel) tsel.value=track;
  set('dev-br-mora', r.mora||'');
  set('dev-br-dia', r.diamonds||'');
  set('dev-br-items', (r.items||[]).map(it=>it[0]+':'+it[1]).join(', '));
  set('dev-br-theme', r.theme||r.theme_id||'');
  toast(`Ур.${lv} ${track==='free'?'🆓':'👑'} → форма ниже`);
  el('dev-br-level')?.scrollIntoView({behavior:'smooth',block:'center'});
}
function devLoadOverview() {
  api('/admin/dev/overview').then(d=>{
    el('dev-overview').innerHTML=`<div class="card">
      <div class="card-title">📊 Система <button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px" onclick="devLoadOverview()">🔄</button></div>
      <div class="irow"><span class="ik">Игроков / Чатов</span><span class="iv">${d.users_total} / ${d.chats_total}</span></div>
      <div class="irow"><span class="ik">Сообщений сегодня</span><span class="iv">${d.messages_today}</span></div>
      <div class="irow"><span class="ik">Активных VIP</span><span class="iv">👑 ${d.vips_active}</span></div>
      <div class="irow"><span class="ik">Санкции / Апелляции</span><span class="iv">${d.sanctions_active} / ⏳${d.appeals_pending}</span></div>
      <div class="irow"><span class="ik">Всего 🪙/💎/✨ в экономике</span><span class="iv" style="font-size:10px">${fmtF(d.mora_total)} / ${fmtF(d.diamonds_total)} / ${fmtF(d.zarniki_total)}</span></div>
      <div class="irow"><span class="ik">Сезон БП</span><span class="iv">${d.bp_season?esc(d.bp_season.label)+' (до '+d.bp_season.ends_at+')':'— нет активного'}</span></div>
    </div>`;
  }).catch(e=>{el('dev-overview').innerHTML=`<div class="err">${e}</div>`;});
}
// Дропдаун «чат → юзер» в карточке игрока (БЛОК 4.1): выбор без знания ID.
function devLoadChats() {
  const sel = el('dev-chat-sel'); if(!sel) return;
  api('/admin/dev/chats').then(d=>{
    sel.innerHTML = '<option value="">— выбрать чат —</option>' +
      (d.chats||[]).map(c=>{
        const mark=c.role==='admin'?'🛡 ':(c.role==='main'?'🏠 ':'');
        const suff=c.role==='admin'&&c.linked_title?` (админка · ${c.linked_title})`
                  :(c.role==='main'&&c.linked_title?' (+админка)':'');
        return `<option value="${c.chat_id}">${mark}${esc(c.title)}${esc(suff)}</option>`;
      }).join('');
  }).catch(()=>{});
}
function devLoadMembers() {
  const cid = el('dev-chat-sel')?.value;
  const msel = el('dev-member-sel'); if(!msel) return;
  if(!cid){ msel.innerHTML='<option value="">— участник —</option>'; return; }
  msel.innerHTML='<option value="">загрузка…</option>';
  api('/admin/dev/chat-members?chat_id='+encodeURIComponent(cid)).then(d=>{
    msel.innerHTML = '<option value="">— участник —</option>' +
      (d.members||[]).map(u=>`<option value="${u.user_tg_id}">@${esc(u.username)} · ур.${u.user_level||1} · ${u.msgs||0} сообщ.</option>`).join('');
  }).catch(()=>{ msel.innerHTML='<option value="">— участник —</option>'; });
}
function devPickMember() {
  const uid = el('dev-member-sel')?.value;
  if(!uid) return;
  const q = el('dev-q'); if(q) q.value = uid;
  devLookupUser();
}
// VIP-строка досье: статус + осталось дней / на сколько в целом / стаж (БЛОК 1)
function _devVipLine(v){
  if(!v) return '<div class="irow"><span class="ik">VIP</span><span class="iv">—</span></div>';
  const exp=v.expires_at?v.expires_at.slice(0,10):'—';
  const head=(v.active?'👑 ':'(истёк) ')+esc(v.tier);
  const sub=v.active
    ? `осталось <b style="color:var(--gold2)">${v.days_left}</b> дн. из ${v.span_days} · до ${exp} · стаж ${v.total_days} дн.`
    : `истёк ${exp} · стаж ${v.total_days} дн.`;
  return `<div class="irow"><span class="ik">VIP</span><span class="iv" style="font-size:10px">${head}</span></div>
    <div style="font-size:10px;color:var(--muted);margin:-3px 0 3px;text-align:right">${sub}</div>`;
}
// Одна строка чата в досье (с меткой роли: основной / админка)
function _devChatRow(c){
  const mark=c.role==='admin'?'🛡 ':(c.role==='main'?'🏠 ':'');
  const role=c.role==='admin'?'админка':(c.role==='main'?'основной':'');
  return `<div class="irow"><span class="ik" style="font-size:10px">${mark}${esc(c.chat_title)}${role?` <span style="color:var(--muted)">· ${role}</span>`:''}</span>`
    +`<span class="iv" style="font-size:10px">${esc(c.rank_name)} · ур.${c.user_level||1} · ${fmt(c.user_messages_count_all_time||0)} сообщ.${c.is_left?' · 👋':''}</span></div>`;
}
// Чаты досье: «основной + админка» одной группой в выделенной рамке (БЛОК 1)
function _devChatsHtml(chats){
  if(!chats||!chats.length) return '<div style="font-size:10px;color:var(--muted)">— нет групп —</div>';
  const shown=chats.slice(0,20); let html=''; let i=0;
  while(i<shown.length){
    const c=shown[i];
    if(c.role==='main'||c.role==='admin'){
      const gk=c.group_key, grp=[];
      while(i<shown.length && shown[i].group_key===gk && (shown[i].role==='main'||shown[i].role==='admin')){ grp.push(shown[i]); i++; }
      html+=`<div class="dev-chat-grp">${grp.map(_devChatRow).join('')}</div>`;
    } else { html+=_devChatRow(c); i++; }
  }
  return html;
}
function devLookupUser() {
  const q=el('dev-q')?.value.trim();
  if(!q) return toast('Введите ID или @username',false);
  el('dev-user-result').innerHTML='<div class="loader">Поиск...</div>';
  api(`/admin/dev/user?q=${encodeURIComponent(q)}`).then(d=>{
    _devUserId = d.user_tg_id;
    el('dev-user-result').innerHTML=`
      <div class="divider"></div>
      <div class="irow"><span class="ik">@${esc(d.user_tg_username||'—')}</span><span class="iv">ID: ${d.user_tg_id}</span></div>
      <div class="irow"><span class="ik">Глоб. ранг</span><span class="iv">${d.global_rank_name}</span></div>
      <div class="irow"><span class="ik">Балансы <span style="color:var(--muted);font-size:9px">(клик = ±)</span></span><span class="iv" style="font-size:11px">${[
        ['mora','🪙 Мора','🪙'+fmtF(d.mora)],
        ['diamonds','💎 Алмазы','💎'+fmtF(d.diamonds)],
        ['dark_mora','🌑 Тёмная Мора','🌑'+fmtF(d.dark_mora)],
        ['zarniki','✨ Зарники','✨'+fmtF(d.zarniki)],
      ].map(([cur,lbl,txt])=>`<span style="cursor:pointer;text-decoration:underline;margin-left:6px" onclick="devBalanceAction('${cur}','${lbl}')">${txt}</span>`).join('')}</span></div>
      ${_devVipLine(d.vip)}
      <div class="irow"><span class="ik">Боевой пропуск</span><span class="iv">${d.battle_pass?`Ур.${d.battle_pass.level} (${fmtF(d.battle_pass.xp)} XP)`:'—'}</span></div>
      ${d.sanctions.length?`<div class="irow"><span class="ik" style="color:var(--red)">Санкции</span><span class="iv" style="font-size:10px">${d.sanctions.map(s=>esc(s.sanction_type)+(s.expires_at?' до '+s.expires_at.slice(0,10):'')).join(', ')}</span></div>`:''}
      <div style="font-size:11px;font-weight:700;margin:6px 0 2px">Чаты (${d.chats.length}):</div>
      ${_devChatsHtml(d.chats)}
      ${d.inventory&&d.inventory.length?`<div style="font-size:11px;font-weight:700;margin:8px 0 4px">🎒 Инвентарь (${d.inventory.length}) — клик = выдать/забрать:</div>
      <div style="display:flex;flex-wrap:wrap;gap:5px">${d.inventory.map(it=>`<button class="btn btn-ghost btn-sm" style="font-size:10px;padding:3px 7px" onclick="devItemAction('${it.item_id}',${it.quantity})">${esc(it.name)} ×${it.quantity}</button>`).join('')}</div>`:'<div style="font-size:10px;color:var(--muted);margin-top:6px">🎒 Инвентарь пуст</div>'}
      <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
        <a class="btn btn-sm btn-ghost" style="flex:1;text-decoration:none;text-align:center" href="tg://user?id=${d.user_tg_id}">🔗 Открыть в TG</a>
        ${d.user_tg_username?`<a class="btn btn-sm btn-ghost" style="flex:1;text-decoration:none;text-align:center" href="https://t.me/${esc(d.user_tg_username)}" target="_blank">@${esc(d.user_tg_username)}</a>`:''}
        <button class="btn btn-sm btn-ghost" style="flex:1" onclick="devPrefill(${d.user_tg_id})">⚙️ Подставить ID в формы</button>
      </div>`;
  }).catch(e=>{el('dev-user-result').innerHTML=`<div class="err">${e}</div>`;});
}
// Клик по валюте в карточке игрока → ±баланс с причиной (БЛОК 4.1)
function devBalanceAction(cur, label) {
  if(!_devUserId){ toast('Сначала найди игрока в Досье', false); return; }
  OM('💰 ' + label, `
    <input id="dev-ba-amt" type="number" step="any" class="num-input" style="margin:0 0 6px" placeholder="Сумма (− забрать)"/>
    <input id="dev-ba-reason" class="num-input" style="margin:0 0 8px" placeholder="Причина (обязательно)"/>
    <button class="btn btn-gold btn-full" onclick="devBalanceActionDo('${cur}')">Применить</button>
    <div id="dev-ba-result" style="margin-top:8px"></div>`,
    [{l:'Закрыть', c:'btn-ghost', f:'CM()'}]);
}
function devBalanceActionDo(cur) {
  const amt = parseFloat(el('dev-ba-amt')?.value || '0');
  if(!amt){ el('dev-ba-result').innerHTML = '<div class="err">Укажите сумму</div>'; return; }
  const reason = (el('dev-ba-reason')?.value || '').trim();
  if(!reason){ el('dev-ba-result').innerHTML = '<div class="err">Укажите причину (обязательно)</div>'; return; }
  const body = {user_id:_devUserId, mora:0, diamonds:0, dark_mora:0, zarniki:0, reason};
  body[cur] = amt;
  api('/admin/dev/balance', {method:'POST', body: JSON.stringify(body)})
    .then(()=>{ toast(`✅ ${amt>0?'+':''}${amt} ${cur}`); CM(); loadDevLog(); devLookupUser(); })
    .catch(e=>{ el('dev-ba-result').innerHTML = `<div class="err">${e}</div>`; });
}
// Клик по предмету в карточке игрока → выдать/забрать с причиной (БЛОК 4.1)
function devItemAction(itemId, ownedQty) {
  OM('🎒 ' + itemId, `
    <div style="font-size:12px;color:var(--muted);margin-bottom:8px">У игрока сейчас: <b>${ownedQty}</b> шт.</div>
    <input id="dev-ia-qty" type="number" class="num-input" value="1" min="1" style="margin:0 0 6px" placeholder="Количество"/>
    <input id="dev-ia-reason" class="num-input" style="margin:0 0 8px" placeholder="Причина (обязательно)"/>
    <div style="display:flex;gap:8px">
      <button class="btn btn-sm btn-gold" style="flex:1" onclick="devItemActionDo('${itemId}',1)">➕ Выдать</button>
      <button class="btn btn-sm btn-red" style="flex:1" onclick="devItemActionDo('${itemId}',-1)">➖ Забрать</button>
    </div>
    <div id="dev-ia-result" style="margin-top:8px"></div>`,
    [{l:'Закрыть', c:'btn-ghost', f:'CM()'}]);
}
function devItemActionDo(itemId, sign) {
  const qty = (parseInt(el('dev-ia-qty')?.value || '0') || 0) * sign;
  if(!qty) return toast('Укажите количество', false);
  const reason = (el('dev-ia-reason')?.value || '').trim();
  if(!reason){ el('dev-ia-result').innerHTML = '<div class="err">Укажите причину (обязательно)</div>'; return; }
  if(!_devUserId){ el('dev-ia-result').innerHTML = '<div class="err">Сначала найди игрока в Досье</div>'; return; }
  api('/admin/dev/give-item', {method:'POST', body: JSON.stringify({user_id:_devUserId, item_id:itemId, qty, reason})})
    .then(r=>{ toast(`✅ ${qty>0?'+':''}${qty}× ${r.item_name}`); CM(); loadDevLog(); devLookupUser(); })
    .catch(e=>{ el('dev-ia-result').innerHTML = `<div class="err">${e}</div>`; });
}
function devPrefill(uid) {
  ['dev-bal-uid','dev-item-uid','dev-vip-uid','dev-bp-uid'].forEach(id=>{const e2=el(id);if(e2)e2.value=uid;});
  toast('ID подставлен в формы');
}
function devAdjustBalance() {
  const uid=parseInt(el('dev-bal-uid')?.value||'0');
  const cur=el('dev-bal-cur')?.value;
  const amt=parseFloat(el('dev-bal-amt')?.value||'0');
  if(!uid||!amt) return toast('Заполните ID и сумму',false);
  const reason=(el('dev-bal-reason')?.value||'').trim();
  if(!reason) return toast('Укажите причину (обязательно для журнала)',false);
  const body={user_id:uid,mora:0,diamonds:0,dark_mora:0,zarniki:0,reason};
  body[cur]=amt;
  api('/admin/dev/balance',{method:'POST',body:JSON.stringify(body)})
    .then(()=>{toast(`✅ ${amt>0?'+':''}${amt} ${cur} → ID${uid}`);loadDevLog();})
    .catch(e=>toast(e,false));
}
// Полный каталог предметов с поиском (БЛОК 1): клик = подставить item_id в форму.
function devItemCatalog(){
  if(!_devItems||!_devItems.length){ toast('Список предметов ещё грузится…',false); return; }
  OM('📋 Каталог предметов',
    `<input id="dev-cat-q" class="num-input" style="margin:0 0 8px" placeholder="🔎 поиск: название / id / категория" oninput="_devItemCatalogRender(this.value)"/>
     <div id="dev-cat-list" style="max-height:52vh;overflow-y:auto"></div>`,
    [{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
  _devItemCatalogRender('');
}
function _devItemCatalogRender(q){
  const box=el('dev-cat-list'); if(!box) return;
  q=(q||'').trim().toLowerCase();
  const items=_devItems.filter(it=>!q||(it.name||'').toLowerCase().includes(q)
    ||(it.item_id||'').toLowerCase().includes(q)||(it.category||'').toLowerCase().includes(q));
  if(!items.length){ box.innerHTML='<div style="font-size:11px;color:var(--muted);padding:8px">Ничего не найдено.</div>'; return; }
  const byCat={};
  items.forEach(it=>{(byCat[it.category||'—']=byCat[it.category||'—']||[]).push(it);});
  box.innerHTML=Object.keys(byCat).sort().map(cat=>
    `<div style="font-size:10px;font-weight:700;color:var(--gold2);margin:8px 0 3px;text-transform:uppercase">${esc(cat)} (${byCat[cat].length})</div>`
    +byCat[cat].map(it=>`<div class="dev-cat-item" onclick="_devPickItem('${it.item_id}')" title="${esc(it.description||'')}">
        <span>${esc(it.name)}</span>
        <span style="color:var(--muted);font-size:9px;font-family:monospace">${esc(it.item_id)}</span></div>`).join('')
  ).join('');
}
function _devPickItem(iid){
  const f=el('dev-item-id'); if(f) f.value=iid;
  CM(); toast('Предмет выбран: '+iid);
  el('dev-item-id')?.scrollIntoView({behavior:'smooth',block:'center'});
}
function devGiveItem() {
  const uid=parseInt(el('dev-item-uid')?.value||'0');
  const item=el('dev-item-id')?.value.trim();
  const qty=parseInt(el('dev-item-qty')?.value||'0');
  if(!uid||!item||!qty) return toast('Заполните все поля',false);
  const reason=(el('dev-item-reason')?.value||'').trim();
  if(!reason) return toast('Укажите причину (обязательно для журнала)',false);
  api('/admin/dev/give-item',{method:'POST',body:JSON.stringify({user_id:uid,item_id:item,qty,reason})})
    .then(r=>{toast(`✅ ${qty>0?'+':''}${qty}× ${r.item_name}`);loadDevLog();})
    .catch(e=>toast(e,false));
}
function devGiveVip() {
  const uid=parseInt(el('dev-vip-uid')?.value||'0');
  const tier=el('dev-vip-tier')?.value;
  const days=parseInt(el('dev-vip-days')?.value||'0');
  if(!uid||!days||days<0) return toast('Укажите ID и положительные дни',false);
  api('/admin/dev/give-vip',{method:'POST',body:JSON.stringify({user_id:uid,tier,days})})
    .then(r=>{toast(`👑 ${r.label} на ${days} дн. → ID${uid}`); devVipStatus();})
    .catch(e=>toast(e,false));
}
// ➖ Убавить срок VIP на N дней (тариф не трогаем). БЛОК 1.
function devVipAdjust() {
  const uid=parseInt(el('dev-vip-uid')?.value||'0');
  const n=Math.abs(parseInt(el('dev-vip-days')?.value||'0'));
  if(!uid||!n) return toast('Укажите ID и дни',false);
  api('/admin/dev/adjust-vip-days',{method:'POST',body:JSON.stringify({user_id:uid,days:-n})})
    .then(r=>{toast(`➖ −${n} дн. VIP → осталось ${r.days_left} дн.`); devVipStatus();})
    .catch(e=>toast(e,false));
}
// 🔄 Заменить тариф (со сбросом старого VIP + бонус-пакет). Подтверждение через модалку.
function devVipReplace() {
  const uid=parseInt(el('dev-vip-uid')?.value||'0');
  const tier=el('dev-vip-tier')?.value;
  const days=parseInt(el('dev-vip-days')?.value||'0');
  if(!uid||!days||days<0) return toast('Укажите ID и положительные дни',false);
  OM('🔄 Заменить VIP', `<div style="font-size:12px;line-height:1.5">Заменить текущий VIP у <b>ID${uid}</b> на <b>${esc(tier)}</b> (${days} дн.)?<br><span style="color:var(--muted)">Старый срок и бонусы сгорают, начисляется бонус-пакет нового тарифа.</span></div>`,
    [{l:'Заменить',c:'btn-gold',f:`_devVipReplaceDo(${uid},'${tier}',${days})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _devVipReplaceDo(uid,tier,days){
  api('/admin/dev/set-vip',{method:'POST',body:JSON.stringify({user_id:uid,tier,days})})
    .then(r=>{CM();toast(`🔄 VIP заменён: ${r.label} на ${days} дн.`); devVipStatus();})
    .catch(e=>toast(e,false));
}
// 🚫 Отозвать VIP (мгновенно). Подтверждение через модалку.
function devVipRevoke() {
  const uid=parseInt(el('dev-vip-uid')?.value||'0');
  if(!uid) return toast('Укажите ID',false);
  OM('🚫 Отозвать VIP', `<div style="font-size:12px">Отозвать VIP у <b>ID${uid}</b>? Он сразу потеряет статус.</div>`,
    [{l:'Отозвать',c:'btn-red',f:`_devVipRevokeDo(${uid})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _devVipRevokeDo(uid){
  api('/admin/dev/revoke-vip',{method:'POST',body:JSON.stringify({user_id:uid})})
    .then(r=>{CM();toast(`🚫 VIP отозван (${esc(r.revoked_tier)})`); devVipStatus();})
    .catch(e=>toast(e,false));
}
// 🔍 Текущий статус VIP игрока (осталось / срок / стаж) — переиспользует /user.
function devVipStatus() {
  const uid=parseInt(el('dev-vip-uid')?.value||'0');
  const box=el('dev-vip-status'); if(!box) return;
  if(!uid){ box.innerHTML=''; return; }
  box.innerHTML='<span style="color:var(--muted)">проверка…</span>';
  api('/admin/dev/user?q='+uid).then(d=>{
    const v=d.vip;
    if(!v){ box.innerHTML='VIP: <b>нет</b>'; return; }
    box.innerHTML=v.active
      ? `VIP: <b style="color:var(--gold2)">${esc(v.tier)}</b> · осталось <b>${v.days_left}</b> дн. из ${v.span_days} · до ${v.expires_at.slice(0,10)} · стаж ${v.total_days} дн.`
      : `VIP: <b>(истёк)</b> ${esc(v.tier)} · стаж ${v.total_days} дн.`;
  }).catch(e=>{box.innerHTML=`<span class="err">${typeof e==='string'?esc(e):'ошибка'}</span>`;});
}
function devBpXp() {
  const uid=parseInt(el('dev-bp-uid')?.value||'0');
  const xp=parseInt(el('dev-bp-xp')?.value||'0');
  if(!uid||!xp) return toast('Заполните ID и XP',false);
  api('/admin/dev/bp/xp',{method:'POST',body:JSON.stringify({user_id:uid,xp})})
    .then(r=>toast(`🎫 Теперь: Ур.${r.level} (${r.xp} XP)`))
    .catch(e=>toast(e,false));
}

// ── 📊 Метрики посещаемости (БЛОК 35) ───────────────────────────────────────
var _PAGE_LABELS={'profile':'👤 Профиль','zoo':'🐾 Питомцы','arena':'⚔️ Арена',
  'market':'🛍 Магазин','auction':'🏛 Аукцион','bp':'🎫 Боевой пропуск',
  'help':'❓ Помощь','global':'🌍 Глобал','admin':'🛡 Админка'};
function _fmtDwell(sec){
  sec = Math.round(sec||0);
  if(sec<60) return sec+'с';
  var m=Math.floor(sec/60), s=sec%60;
  return m+'м'+(s?' '+s+'с':'');
}
function _metricsBar(rows,emptyText){
  if(!rows||!rows.length) return '<div style="color:var(--muted);font-size:11px;text-align:center;padding:8px">'+emptyText+'</div>';
  var max=0; for(var i=0;i<rows.length;i++){if(rows[i].views>max)max=rows[i].views;}
  return rows.map(function(r){
    var pct=max?Math.round(r.views/max*100):0;
    var label=_PAGE_LABELS[r.tab]||esc(r.tab||'');
    return '<div style="display:flex;align-items:center;gap:6px;padding:3px 0">'
      +'<div style="min-width:110px;max-width:110px;font-size:10px;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+label+'</div>'
      +'<div style="flex:1;background:var(--bg2);border-radius:3px;height:14px;overflow:hidden">'
      +'<div style="width:'+pct+'%;height:14px;background:var(--gold2);border-radius:3px;transition:width .3s"></div></div>'
      +'<div style="min-width:28px;text-align:right;font-size:10px;font-weight:700;color:var(--gold2)">'+r.views+'</div>'
      +'<div style="min-width:34px;text-align:right;font-size:10px;color:var(--muted)">👤 '+r.users+'</div>'
      +'<div style="min-width:46px;text-align:right;font-size:10px;color:var(--muted)" title="Среднее время на вкладке за визит">⏱ '+_fmtDwell(r.avg_dwell_sec)+'</div>'
      +'</div>';
  }).join('');
}
function loadDevMetrics() {
  var kpi=el('dev-metrics-kpi'),daily=el('dev-metrics-daily'),tabs=el('dev-metrics-tabs'),subtabs=el('dev-metrics-subtabs');
  if(!kpi) return;
  kpi.innerHTML='<div class="loader">Загрузка...</div>';
  api('/admin/dev/analytics').then(function(d){
    kpi.innerHTML=
      '<div style="flex:1;text-align:center;background:var(--bg2);border-radius:10px;padding:10px 6px">'
        +'<div style="font-size:22px;font-weight:800;color:var(--gold2)">'+d.dau+'</div>'
        +'<div style="font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-top:2px">DAU · 24ч</div></div>'
      +'<div style="flex:1;text-align:center;background:var(--bg2);border-radius:10px;padding:10px 6px">'
        +'<div style="font-size:22px;font-weight:800;color:var(--gold2)">'+d.wau+'</div>'
        +'<div style="font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-top:2px">WAU · 7 дн</div></div>'
      +'<div style="flex:1;text-align:center;background:var(--bg2);border-radius:10px;padding:10px 6px">'
        +'<div style="font-size:22px;font-weight:800;color:var(--gold2)">'+d.mau+'</div>'
        +'<div style="font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-top:2px">MAU · 30 дн</div></div>';
    if(tabs) tabs.innerHTML=_metricsBar(d.top_tabs,'Нет данных за 30 дней');
    if(subtabs) subtabs.innerHTML=_metricsBar(d.top_subtabs,'Пока нет данных по под-вкладкам');
    var TH='style="padding:3px 6px;border-bottom:1px solid var(--border2)"';
    var TDL='style="padding:3px 6px;border-bottom:1px solid var(--border2)"';
    var TDR='style="text-align:right;padding:3px 6px;border-bottom:1px solid var(--border2)"';
    if(daily){
      if(d.daily&&d.daily.length){
        daily.innerHTML='<table style="width:100%;font-size:11px;border-collapse:collapse">'
          +'<thead><tr>'
          +'<th '+TH+' style="text-align:left">Дата</th>'
          +'<th '+TH+' style="text-align:right">Сессии</th>'
          +'<th '+TH+' style="text-align:right">Юзеры</th>'
          +'</tr></thead><tbody>'
          +d.daily.slice().reverse().map(function(r){
            return '<tr><td '+TDL+'>'+esc(r.date||'')+'</td>'
                  +'<td '+TDR+'>'+r.sessions+'</td>'
                  +'<td '+TDR+'>'+r.users+'</td></tr>';
          }).join('')+'</tbody></table>';
      } else {
        daily.innerHTML='<div style="color:var(--muted);font-size:11px;text-align:center;padding:8px">Нет данных</div>';
      }
    }
  }).catch(function(e){if(kpi)kpi.innerHTML='<div class="err">'+esc(String(e))+'</div>';});
}
// ── 🗂 Dev-подвкладки ────────────────────────────────────────────────────────
function swDev(tab, btn) {
  if(btn) btn.closest('.dev-tabs').querySelectorAll('.tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  ['sys','players','content','bc','sql','metrics','themes'].forEach(t=>{
    const d=el('dev-t-'+t); if(d) d.style.display=t===tab?'':'none';
  });
  if(tab==='content'){ try{devPromoLoad();}catch(e){} }
}
function devLoadChatsMod() {
  const sel=el('dev-mod-chat-sel'); if(!sel) return;
  api('/admin/dev/chats').then(d=>{
    sel.innerHTML='<option value="">— выбрать чат —</option>'+(d.chats||[]).map(c=>{
      const mark=c.role==='admin'?'🛡 ':(c.role==='main'?'🏠 ':'');
      return `<option value="${c.chat_id}">${mark}${esc(c.title)}</option>`;
    }).join('');
  }).catch(()=>{});
}
function devLoadChatMods(chatId) {
  const box=el('dev-mod-modules'); if(!box) return;
  if(!chatId){box.innerHTML='<div style="color:var(--muted);font-size:11px">Выберите чат.</div>';return;}
  box.innerHTML='<div class="loader">Загрузка...</div>';
  api('/admin/dev/chat-modules/'+encodeURIComponent(chatId)).then(d=>{
    const mods=[
      ['module_shop','🛒','Магазин'],['module_gacha','🎰','Гача'],
      ['module_expeditions','🗺','Экспедиции'],['module_auction','🏛','Аукцион'],
      ['module_games','🎲','Мини-игры'],['module_exchange','💱','Конвертер'],
      ['module_quests','📋','Квесты'],['module_zoo','🐾','Зоопарк'],
      ['module_warps','🤝','Варп-команды'],['module_daily_deal','🏷','Акция дня'],
    ];
    box.innerHTML='<div style="display:flex;flex-wrap:wrap;gap:4px">'+mods.map(function(m){
      const key=m[0],icon=m[1],name=m[2];
      const on=(d.modules[key]!==undefined?d.modules[key]:1)===1;
      return '<button class="btn '+(on?'btn-gold':'btn-ghost')+'" style="font-size:11px;padding:4px 8px" onclick="devSetChatMod('+chatId+',\''+key+'\','+(on?0:1)+')">'+icon+' '+name+': '+(on?'✅':'❌')+'</button>';
    }).join('')+'</div>';
  }).catch(function(e){box.innerHTML='<div class="err">'+esc(String(e))+'</div>';});
}
function devSetChatMod(chatId, key, val) {
  api('/admin/dev/chat-modules/'+encodeURIComponent(chatId),{
    method:'POST',body:JSON.stringify({module_key:key,enabled:val===1})
  }).then(function(){toast(val?'✅ '+key+' включён':'🔴 '+key+' выключен');devLoadChatMods(chatId);})
  .catch(function(e){toast(e,false);});
}
// ── 🔌 Флаги модулей ─────────────────────────────────────────────────────────
function loadDevFlags() {
  const box=el('dev-flags'); if(!box) return;
  box.innerHTML='<div class="loader">Загрузка...</div>';
  api('/admin/dev/flags').then(d=>{
    const flags=d.flags||[];
    if(!flags.length){box.innerHTML='<div class="empty-state">Нет флагов</div>';return;}
    box.innerHTML=flags.map(f=>`
      <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border2)">
        <span style="font-size:12.5px">${esc(f.label||f.key)}</span>
        <label class="dev-flag-toggle" title="${esc(f.key)}">
          <input type="checkbox" ${f.enabled?'checked':''} onchange="devSetFlag('${esc(f.key)}',this.checked)"/>
          <span class="dev-flag-slider"></span>
        </label>
      </div>`).join('');
  }).catch(e=>{box.innerHTML=`<div class="err">${esc(String(e))}</div>`;});
}
function devSetFlag(key,enabled){
  api('/admin/dev/flags/'+key,{method:'POST',body:JSON.stringify({enabled})})
    .then(()=>toast(enabled?`✅ ${key} включён`:`🔴 ${key} выключен`))
    .catch(e=>{toast(e,false);loadDevFlags();});
}
