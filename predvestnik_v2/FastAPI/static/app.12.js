// Питомцы, сундуки, квесты, достижения и трекер чатов (внешний вид теперь в app.20–24.js).
(function(){
  const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  function dateLabel(value){
    if(!value) return '—';
    const parsed=new Date(value);
    return Number.isNaN(parsed.getTime())?esc(String(value).replace('T',' ').slice(0,16)):parsed.toLocaleDateString('ru-RU');
  }
  const chatTracker = {
    query: '',
    sort: 'recent',
    items: [],
    nextOffset: null,
    summary: {},
    filteredCount: 0,
    busy: false,
    debounce: null,
    requestGeneration: 0,
    error: '',
    pendingFocus: '',
  };
  const CHAT_SORTS = Object.freeze({
    recent: 'Недавние',
    week: 'За неделю',
    messages: 'За всё время',
    rank: 'По рангу',
  });
  const SANCTION_LABELS = Object.freeze({
    warn: 'Предупреждение',
    mute: 'Мут',
    kick: 'Исключение',
    ban: 'Блокировка',
  });

  function sanctionLabel(action) {
    return SANCTION_LABELS[action] || 'Модерация';
  }

  function chatTrackerSanctionSummary(chat) {
    if (chat.muted_until) return `Мут до ${dateLabel(chat.muted_until)}`;
    if (chat.warnings) return `Предупреждений: ${fmt(chat.warnings)}`;
    return 'Санкций сейчас нет';
  }

  function chatTrackerHistory(chat) {
    const entries = chat.sanction_history || [];
    if (!entries.length) return '';

    const rows = entries.map((entry) => (
      `<li><span>${esc(sanctionLabel(entry.action))}</span>`
      + `<time>${dateLabel(entry.created_at)}</time></li>`
    )).join('');
    return `<details class="chat-tracker-history">`
      + `<summary>История модерации · ${entries.length}</summary>`
      + `<ul>${rows}</ul></details>`;
  }

  function chatTrackerCard(chat) {
    const hasSanction = Boolean(chat.warnings || chat.muted_until);
    const streak = chat.activity_streak_days
      ? `<span class="chat-tracker-streak" title="Дни активности подряд">🔥 ${fmt(chat.activity_streak_days)}</span>`
      : '';

    return `<article class="chat-tracker-card">
      <header>
        <div>
          <h2>${esc(chat.chat_title || 'Чат без названия')}</h2>
          <small>Активность ${dateLabel(chat.last_message_at)}</small>
        </div>
        ${streak}
      </header>
      <div class="chat-tracker-metrics">
        <span><b>${fmt(chat.user_messages_count_per_day || 0)}</b><small>сегодня</small></span>
        <span><b>${fmt(chat.user_messages_count_per_week || 0)}</b><small>за неделю</small></span>
        <span><b>${fmt(chat.user_messages_count_all_time || 0)}</b><small>всего</small></span>
      </div>
      <div class="chat-tracker-meta">
        <span>Уровень ${fmt(chat.user_level || 1)}</span>
        <span>${chat.local_rank ? `Ранг ${fmt(chat.local_rank)}` : 'Ранг ещё не получен'}</span>
        <span class="${hasSanction ? 'has-sanction' : ''}">${chatTrackerSanctionSummary(chat)}</span>
      </div>
      ${chatTrackerHistory(chat)}
    </article>`;
  }

  function chatTrackerEmptyState(hasQuery) {
    if (chatTracker.error) {
      return `<div class="chat-tracker-empty is-error">
        <b>Не удалось загрузить чаты</b>
        <span>${esc(chatTracker.error)}</span>
        <button type="button" onclick="loadChatTracker()">Повторить</button>
      </div>`;
    }

    const title = hasQuery ? 'Ничего не найдено' : 'Здесь пока тихо';
    const message = hasQuery
      ? 'По этому запросу активных чатов не найдено.'
      : 'Ты пока не состоишь в активных чатах с собранной статистикой.';
    return `<div class="chat-tracker-empty"><b>${title}</b><span>${message}</span></div>`;
  }

  function chatTrackerStatus(hasQuery) {
    if (chatTracker.busy) return 'Обновляем…';
    if (hasQuery) return `Найдено: ${fmt(chatTracker.filteredCount)}`;
    return `Показано: ${fmt(chatTracker.items.length)} из ${fmt(chatTracker.filteredCount)}`;
  }

  function restoreChatTrackerFocus(root, focusState) {
    if (focusState.search) {
      const input = root.querySelector('.chat-tracker-tools input');
      input?.focus({ preventScroll: true });
      if (focusState.selection) {
        input?.setSelectionRange(focusState.selection[0], focusState.selection[1]);
      }
      return;
    }
    if (focusState.sort) {
      root.querySelector(`[data-chat-sort="${focusState.sort}"]`)?.focus({ preventScroll: true });
      return;
    }
    if (focusState.more && !chatTracker.busy) {
      const target = root.querySelector('[data-chat-more="true"]')
        || root.querySelector('.chat-tracker-status');
      target?.focus({ preventScroll: true });
      chatTracker.pendingFocus = '';
    }
  }

  function renderChatTracker() {
    const root = el('pg-chat-tracker');
    if (!root) return;

    const active = document.activeElement;
    const restoreSearch = active?.matches?.('.chat-tracker-tools input');
    const focusState = {
      search: restoreSearch,
      selection: restoreSearch ? [active.selectionStart, active.selectionEnd] : null,
      sort: active?.dataset?.chatSort || '',
      more: active?.dataset?.chatMore === 'true' || chatTracker.pendingFocus === 'more',
    };
    const summary = chatTracker.summary || {};
    const hasQuery = Boolean(chatTracker.query);
    const rows = chatTracker.items.map(chatTrackerCard).join('');
    const sortButtons = Object.entries(CHAT_SORTS).map(([key, label]) => (
      `<button type="button" data-chat-sort="${key}" class="${chatTracker.sort === key ? 'is-active' : ''}"`
      + ` aria-pressed="${chatTracker.sort === key}" onclick="chatTrackerSort('${key}')">${label}</button>`
    )).join('');

    root.innerHTML = `<div class="chat-tracker-head">
        <button class="looks-back" onclick="goTo('profile')" aria-label="Назад">‹</button>
        <div><span class="v3-eyebrow">Ваша активность</span><h1>Трекер чатов</h1><p>Прогресс и история в каждом чате.</p></div>
      </div>
      <section class="chat-tracker-summary" aria-label="Сводка">
        <div><b>${fmt(summary.chat_count || 0)}</b><span>активных чатов</span></div>
        <div><b>${fmt(summary.messages_week || 0)}</b><span>сообщений за неделю</span></div>
        <div><b>${fmt(summary.messages_all_time || 0)}</b><span>сообщений всего</span></div>
      </section>
      <section class="chat-tracker-tools">
        <label><span class="sr-only">Найти чат</span><input type="search" value="${esc(chatTracker.query)}" maxlength="64" placeholder="Найти чат по названию" oninput="chatTrackerSearch(this.value)"></label>
        <div class="chat-tracker-sorts" role="group" aria-label="Сортировка">${sortButtons}</div>
        <p class="chat-tracker-status" tabindex="-1" role="status" aria-live="polite">${chatTrackerStatus(hasQuery)}</p>
      </section>
      <section class="chat-tracker-list">${rows || chatTrackerEmptyState(hasQuery)}</section>
      ${chatTracker.error && rows ? `<div class="chat-tracker-page-error" role="alert"><span>Следующую страницу загрузить не удалось.</span><button type="button" onclick="chatTrackerLoadMore()">Повторить</button></div>` : ''}
      ${chatTracker.nextOffset !== null ? `<button type="button" data-chat-more="true" class="chat-tracker-more" onclick="chatTrackerLoadMore()" ${chatTracker.busy ? 'disabled' : ''}>${chatTracker.busy ? 'Загружаем…' : 'Показать ещё'}</button>` : ''}`;

    v3EnterSync(root);
    restoreChatTrackerFocus(root, focusState);
  }

  async function loadChatTracker({ append = false } = {}) {
    const generation = ++chatTracker.requestGeneration;
    chatTracker.busy = true;
    chatTracker.error = '';
    if (append) renderChatTracker();

    const offset = append ? chatTracker.nextOffset || 0 : 0;
    const query = new URLSearchParams({
      limit: '12',
      offset: String(offset),
      sort: chatTracker.sort,
      query: chatTracker.query,
    });
    try {
      const data = await api(`/profile/me/chat-tracker?${query}`);
      if (generation !== chatTracker.requestGeneration) return;

      chatTracker.summary = data.summary || {};
      chatTracker.filteredCount = Number(data.filtered_count) || 0;
      chatTracker.nextOffset = data.next_offset;
      chatTracker.items = append
        ? chatTracker.items.concat(data.items || [])
        : (data.items || []);
    } catch (error) {
      if (generation !== chatTracker.requestGeneration) return;
      chatTracker.error = String(error || 'Неизвестная ошибка');
      toast(error, false);
      if (!append) {
        chatTracker.items = [];
        chatTracker.filteredCount = 0;
      }
    } finally {
      if (generation === chatTracker.requestGeneration) {
        chatTracker.busy = false;
        renderChatTracker();
      }
    }
  }

  window.chatTrackerSearch = function (value) {
    chatTracker.query = String(value || '').slice(0, 64);
    clearTimeout(chatTracker.debounce);
    chatTracker.debounce = setTimeout(() => loadChatTracker(), 260);
  };
  window.chatTrackerSort = function (value) {
    if (!CHAT_SORTS[value] || value === chatTracker.sort) return;
    chatTracker.sort = value;
    loadChatTracker();
  };
  window.chatTrackerLoadMore = function () {
    if (chatTracker.busy || chatTracker.nextOffset === null) return;
    chatTracker.pendingFocus = 'more';
    loadChatTracker({ append: true });
  };
  window.loadChatTracker = loadChatTracker;
  window.openChatTracker = function () {
    switchPage('chat-tracker');
    const root = el('pg-chat-tracker');
    if (!root) return;
    root.innerHTML = '<div class="loader" style="margin-top:44px">Собираем статистику чатов…</div>';
    loadChatTracker();
  };
  const PET_ACTIVITY_KINDS = Object.freeze(['trek', 'expedition']);
  const PET_ROUTE_LABELS = Object.freeze({
    careful: 'Осторожный маршрут',
    steady: 'Ровный маршрут',
    bold: 'Рискованный маршрут',
    scout: 'Разведка',
  });
  const PET_ROUTES_CLASSIC = Object.freeze(['careful', 'steady', 'bold']);

  const PET_RARITY = Object.freeze({
    common: 'Обычный', uncommon: 'Необычный', rare: 'Редкий', epic: 'Эпический',
    legendary: 'Легендарный', mythic: 'Мифический', shadow: 'Теневой', seasonal: 'Сезонный',
  });
  const petRarityName = (id) => PET_RARITY[id] || String(id || 'Особый');
  const petRarityClass = (id) => `r-${String(id || 'common').replace(/[^a-z]/g, '')}`;
  let _petPanel = 'owned';
  let _petDexFilter = 'all';

  function petMeter(pet) {
    const value = Math.max(0, Math.min(100, Number(pet.endurance) || 0));
    const tone = value < 25 ? 'is-low' : value < 60 ? 'is-mid' : 'is-full';
    return `<div class="pt-meter ${tone}" role="img" aria-label="Выносливость ${value} из 100"><span aria-hidden="true">⚡</span>`
      + `<div aria-hidden="true"><i style="width:${value}%"></i></div><b>${value}<small>/100</small></b></div>`;
  }

  function petFoodButtons(pet, foods) {
    if (Number(pet.endurance) >= 100) return '';
    if (!foods.length) {
      return '<p class="pt-note">Еды нет. Её можно найти в сундуках.</p>';
    }
    const buttons = foods.map((food) => (
      `<button type="button" onclick="petsV1Feed(${pet.id},'${esc(food.id)}')"`
      + ` title="+${food.restore} выносливости" aria-label="Покормить: ${esc(food.name || food.id)}, +${food.restore} выносливости, осталось ${food.quantity}">`
      + `<span aria-hidden="true">${esc(food.icon)}</span><b>+${food.restore}</b><small>${food.quantity} шт.</small></button>`
    )).join('');
    return `<div class="pt-food"><small>Покормить</small><div class="pet-food-row">${buttons}</div></div>`;
  }

  function petStage(pet) {
    const e = pet.effects || {};
    return `Ур. ${pet.level}/16 · ${esc(e.visual_stage || 'начальный облик')} · маршрут +${e.expedition_route_bonus_percent || 0}%`;
  }

  function petRouteList(routeOptions) {
    if (routeOptions && routeOptions.rewards_enabled && routeOptions.routes && routeOptions.routes.length) return routeOptions.routes;
    return PET_ROUTES_CLASSIC.map((id) => ({ id }));
  }

  function activePetActivity(activity, routeOptions) {
    const title = activity.kind === 'trek' ? 'Поход' : 'Экспедиция';
    const needsDecision = activity.status === 'ready'
      && activity.kind === 'expedition'
      && !activity.decision;
    const status = activity.status === 'ready'
      ? (needsDecision ? 'Таймер завершён. Выбери маршрут:' : 'Награда уже получена.')
      : `Питомец занят до ${esc(String(activity.ends_at).replace('T', ' ').slice(0, 16))}.`;
    const routes = needsDecision
      ? `<div class="pet-route-grid">${petRouteList(routeOptions).map((route) => (
        `<button type="button" class="v3-pill v3-pill--ghost" onclick="petsV1Choose('${route.id}')">${esc(PET_ROUTE_LABELS[route.id] || route.id)}`
        + (route.chance_percent != null ? `<small class="pet-route-odds"> · ${route.chance_percent}% · ${fmt(route.reward_mora)} 🪙</small>` : '')
        + `</button>`
      )).join('')}</div>${routeOptions && routeOptions.rewards_enabled && !routeOptions.hint ? '<small>С 4 уровня питомец покажет шансы маршрутов.</small>' : ''}${routeOptions && routeOptions.rewards_enabled ? `<small>Награды маршрутов на этой неделе: осталось ${fmt(routeOptions.weekly_remaining_mora)} 🪙 из ${fmt(routeOptions.weekly_cap_mora)}.</small>` : ''}`
      : '';
    return `<section class="pt-sec pet-activity ${needsDecision ? 'is-attn' : ''}"><h3>${title}${needsDecision ? ' · нужен выбор' : ''}</h3><p>${status}</p>${routes}</section>`;
  }

  let _petKind = 'trek';
  function petActivityChoices(data, activePet) {
    if (!data.active_pet_id) return '';
    const costs = data.activity_costs || {};
    const endurance = Number(activePet && activePet.endurance) || 0;
    const seg = PET_ACTIVITY_KINDS.map((kind) => (
      `<button type="button" role="tab" aria-selected="${kind === _petKind}" onclick="petKind('${kind}')">${kind === 'trek' ? 'Поход' : 'Экспедиция'}</button>`
    )).join('');
    const keys = data.activity_key_counts || { trek: 1, expedition: 1 };
    const hint = _petKind === 'trek' ? `Спокойная прогулка. По возвращении: ${keys.trek} 🗝.` : `После таймера выберешь маршрут. По итогу: ${keys.expedition} 🗝.`;
    const title = _petKind === 'trek' ? 'Поход' : 'Экспедиция';
    const buttons = data.durations.map((hours) => {
      const cost = Number(costs[hours]) || 0;
      const locked = !activePet || endurance < cost;
      const hoursWord = Number(hours) === 3 ? 'часа' : 'часов';
      return `<button type="button" class="pt-go" onclick="petsV1Start('${_petKind}',${hours})" ${locked ? 'disabled' : ''}`
        + ` aria-label="${title} на ${hours} ${hoursWord}, ${cost} выносливости, награда ${_petKind === 'trek' ? keys.trek : keys.expedition} 🗝">`
        + `<b>${hours} ч</b><small>${cost} ⚡</small></button>`;
    }).join('');
    const minCost = Math.min(...data.durations.map((h) => Number(costs[h]) || 0));
    const tired = endurance < minCost ? '<p class="pt-note">Не хватает выносливости. Покорми питомца.</p>' : '';
    return `<section class="pt-sec pet-activity"><h3>Отправить в путь</h3>
      <div class="pt-seg" role="tablist">${seg}</div><p>${hint}</p>
      <div class="pt-go-row">${buttons}</div>${tired}</section>`;
  }

  function petBestiaryCard(pet) {
    const state = pet.owned ? 'is-owned' : 'is-locked';
    const icon = esc(pet.icon);
    const name = esc(pet.name);
    return `<button type="button" class="bestiary-card ${state} ${petRarityClass(pet.rarity)}" data-rar="${esc(pet.rarity)}" onclick="petDexOpen('${esc(pet.id)}')"`
      + ` aria-label="${name}, ${esc(petRarityName(pet.rarity))}, подробнее"><span class="bc-ic" aria-hidden="true">${icon}</span>`
      + `<b>${name}</b><small>${esc(petRarityName(pet.rarity))}</small>`
      + `<em>${pet.owned ? '✓ Открыт' : 'Не найден'}</em></button>`;
  }

  function petDex(data) {
    const list = data.bestiary || [];
    const owned = Number(data.bestiary_owned || 0);
    const total = Number(data.bestiary_total || 0);
    const pct = Math.round(100 * owned / Math.max(1, total));
    const rarities = [...new Set(list.map((p) => p.rarity))];
    const chips = [`<button type="button" aria-pressed="true" data-rar-chip="all" onclick="petDexFilter('all')">Все <small>${total}</small></button>`]
      .concat(rarities.map((r) => {
        const sub = list.filter((p) => p.rarity === r);
        return `<button type="button" aria-pressed="false" data-rar-chip="${esc(r)}" onclick="petDexFilter('${esc(r)}')">${esc(petRarityName(r))} <small>${sub.filter((p) => p.owned).length}/${sub.length}</small></button>`;
      })).join('');
    const sorted = list.slice().sort((a, b) => Number(b.owned) - Number(a.owned));
    return `<section class="pt-dex-head"><div><small>Собрано</small><h2>${fmt(owned)} <span>из ${fmt(total)}</span></h2></div>
      <div class="pt-dex-bar" role="img" aria-label="Собрано ${pct}%"><i style="width:${pct}%"></i></div></section>
      <div class="pt-chips" role="group" aria-label="Редкость">${chips}</div>
      <div class="bestiary-grid">${sorted.map(petBestiaryCard).join('')}</div>`;
  }

  let _petData = null;
  let _petSel = null;

  function petAvatar(pet, icon, selected, away) {
    const badge = pet.active ? '<i class="pt-b pt-b--on" title="Активный">★</i>' : '';
    return `<button type="button" class="pt-av ${petRarityClass(pet.rarity)}" role="tab" aria-selected="${selected}" onclick="petSelect(${pet.id})"`
      + ` aria-label="${esc(pet.name)}${pet.active ? ', активный' : ''}${away ? ', в пути' : ''}">`
      + `<span class="pt-ic" aria-hidden="true">${esc(icon)}</span>${badge}${away ? '<i class="pt-b pt-b--trip">🧭</i>' : ''}<small>${esc(pet.name)}</small></button>`;
  }

  // «Улучшить»: цена следующего шага (карты, Мора, на уровнях 5/10/15 ещё Эссенция). Блок виден только при включённом флаге; что именно не хватает, написано сразу
  function petLevelUp(pet, data) {
    const lu = data.level_up;
    if (!lu || !lu.enabled) return '';
    const step = (lu.steps || {})[pet.id];
    if (step === undefined) return '';
    if (!step) return `<section class="pt-sec pt-up"><h3>Уровень ${Number(pet.level)} из ${Number(lu.max_level)}</h3><p>Максимальный уровень.</p></section>`;
    // Мору и Эссенцию не блокируем на клиенте: баланс в панели обновляется не сразу, сервер сам откажет с понятной ошибкой
    const left = Math.max(0, Number(step.cards) - Number(step.cards_have));
    const word = left % 10 === 1 && left % 100 !== 11 ? 'карта' : (left % 10 >= 2 && left % 10 <= 4 && (left % 100 < 12 || left % 100 > 14) ? 'карты' : 'карт');
    const need = left ? [`ещё ${fmt(left)} ${word}`] : [];
    const pct = Math.min(100, Math.round(100 * Number(step.cards_have) / Math.max(1, Number(step.cards))));
    const mark = [5, 10, 15].includes(Number(step.level_after)) ? ` <small class="pt-up-mark">веха</small>` : '';
    return `<section class="pt-sec pt-up" aria-label="Улучшение питомца">
      <h3>Уровень ${Number(pet.level)} → ${Number(step.level_after)}${mark}</h3>
      <ul class="pt-up-cost">
        <li class="${Number(step.cards_have) < Number(step.cards) ? 'is-short' : ''}"><span>🃏 Карты</span><b>${fmt(Number(step.cards_have))} / ${fmt(Number(step.cards))}</b><i style="--p:${pct}"></i></li>
        <li><span>🪙 Мора</span><b>${fmt(Number(step.mora))}</b></li>
        ${Number(step.essence) > 0 ? `<li><span>🔮 Эссенция</span><b>${fmt(Number(step.essence))}</b></li>` : ''}
      </ul>
      <button type="button" class="pt-main" onclick="petsV1LevelUp(${Number(pet.id)})" ${need.length ? 'disabled' : ''}>Улучшить</button>
      ${need.length ? `<p class="pt-note" role="status">Не хватает: ${need.join(', ')}.</p>` : ''}
    </section>`;
  }

  function petDetail(pet, data, icon, away, lore) {
    const foods = data.food || [];
    const activePet = (data.pets || []).find((p) => p.active);
    const tag = pet.active ? 'Активный' : 'В запасе';
    let action = '';
    if (pet.active) {
      if (!data.activity) action = petActivityChoices(data, activePet);
      else if (data.activity.pet_id === pet.id) action = activePetActivity(data.activity, data.route_options);
      else action = '<section class="pt-sec"><p class="pt-note">Другой питомец ещё в пути. Выйти в поход можно после его возвращения.</p></section>';
    } else {
      const trip = data.activity && activePet
        ? '<p class="pt-note">Текущий питомец в пути: новый сможет выйти после его возвращения.</p>' : '';
      action = `<section class="pt-sec"><button type="button" class="pt-main" onclick="petsV1Activate(${pet.id})">Сделать активным</button>`
        + `<p class="pt-note">Смена стоит 5 выносливости у текущего активного питомца.</p>${trip}</section>`;
    }
    return `<section class="pt-hero ${petRarityClass(pet.rarity)}" aria-label="${esc(pet.name)}">
      <div class="pt-hero-top"><span class="pt-ic" aria-hidden="true">${esc(icon)}</span>
        <div><small>${tag}${away ? ' · в пути' : ''} · ${esc(petRarityName(pet.rarity))}</small><h2>${esc(pet.name)}</h2><p>${petStage(pet)}</p></div></div>
      <button type="button" class="pt-more" onclick="petDexOpen('${esc(pet.species_id)}')">Всё об этом питомце</button>
      ${lore ? `<p class="pt-lore">${esc(lore)}</p>` : ''}${petMeter(pet)}${petFoodButtons(pet, foods)}
    </section>${petLevelUp(pet, data)}${action}`;
  }

  function petOwnedPanel(data) {
    const pets = data.pets || [];
    const dex = data.bestiary || [];
    const info = (pet) => dex.find((x) => x.id === pet.species_id) || {};
    const earned = (data.activity_rewards || []).length
      ? '<div class="pet-key-earned" role="status"><div><b>🗝 Ключ получен</b><span>Награда уже зачислена в сундуки.</span></div><button type="button" onclick="openChestsV1()">К сундукам</button></div>'
      : '';
    if (!pets.length) {
      return `${earned}<div class="pt-empty"><span aria-hidden="true">🥚</span><b>Питомцев пока нет</b><p>Первую карточку питомца можно найти в сундуке.</p><button type="button" onclick="openChestsV1()">К сундукам</button></div>`;
    }
    if (!pets.some((p) => p.id === _petSel)) {
      _petSel = (pets.find((p) => p.active) || pets[0]).id;
    }
    const sel = pets.find((p) => p.id === _petSel);
    const awayId = data.activity ? data.activity.pet_id : null;
    const strip = pets.length > 1
      ? `<div class="pt-strip" role="tablist" aria-label="Мои питомцы">${pets.map((p) => petAvatar(p, info(p).icon || '🐾', p.id === _petSel, p.id === awayId)).join('')}</div>`
      : '';
    const lead = !data.active_pet_id
      ? '<p class="pt-note pt-note--lead">Выбери активного питомца: только он ходит в походы.</p>' : '';
    const guide = '<details class="pt-info"><summary>Как работает выносливость</summary><p>Она уменьшается примерно на 10 в сутки. Еда из сундуков восстанавливает её сразу. Поход и экспедиция списывают выносливость при старте и дают ключ. В путь ходит один активный питомец.</p></details>';
    return `${earned}${lead}${strip}${petDetail(sel, data, info(sel).icon || '🐾', sel.id === awayId, info(sel).lore)}${guide}`;
  }

  function renderPetsV1(root, data) {
    _petData = data;
    const pets = data.pets || [];
    const ownedTab = _petPanel === 'owned';
    root.innerHTML = `<div class="looks-head"><button class="looks-back" onclick="goTo('profile')" aria-label="Назад">‹</button><div class="looks-htitle">🐾 Питомцы</div></div>
      <div class="pet-tabs" role="tablist"><button type="button" role="tab" aria-selected="${ownedTab}" onclick="showPetPanel('owned',this)">Мои питомцы <small>${pets.length}</small></button><button type="button" role="tab" aria-selected="${!ownedTab}" onclick="showPetPanel('bestiary',this)">Бестиарий <small>${data.bestiary_owned || 0}/${data.bestiary_total || 0}</small></button></div>
      <div data-pet-panel="owned" ${ownedTab ? '' : 'hidden'}>${petOwnedPanel(data)}</div>
      <div data-pet-panel="bestiary" ${ownedTab ? 'hidden' : ''}>${petDex(data)}</div>`;
    if (_petDexFilter !== 'all') window.petDexFilter(_petDexFilter);
  }

  function petRefreshOwned() {
    const panel = el('pg-pets').querySelector('[data-pet-panel="owned"]');
    if (panel && _petData) panel.innerHTML = petOwnedPanel(_petData);
  }
  window.petSelect = function (id) { _petSel = Number(id); petRefreshOwned(); };
  window.petKind = function (kind) { _petKind = kind; petRefreshOwned(); };

  window.openPetsV1 = async function () {
    switchPage('pets');
    const root = el('pg-pets');
    root.innerHTML = '<div class="loader" style="margin-top:44px">Загрузка питомцев…</div>';
    try {
      renderPetsV1(root, await api('/pets-v1/me'));
    } catch (error) {
      root.innerHTML = `<div class="v3-err" style="margin:16px">${esc(error)}</div>`;
    }
  };
  window.showPetPanel = function (name, button) {
    const root = el('pg-pets');
    _petPanel = name;
    root.querySelectorAll('[data-pet-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.petPanel !== name;
    });
    root.querySelectorAll('.pet-tabs button').forEach((tab) => {
      tab.setAttribute('aria-selected', String(tab === button));
    });
    window.scrollTo?.({ top: 0 });
  };
  function petInfoBody(sp, mine, data) {
    const info = sp.info || {};
    const feat = data.features || {};
    const soon = (feature) => (feature && !feat[feature] ? ' <em class="pt-soon">скоро</em>' : '');
    const list = (rows) => `<ul class="pt-sheet-list">${rows.join('')}</ul>`;
    const row = (title, text) => `<li><b>${esc(title)}</b><span>${text}</span></li>`;
    const out = [`<p class="pt-lore">${esc(sp.lore || '')}</p>`];
    if (mine.length) {
      out.push('<h4>У тебя</h4>' + list(mine.map((p) => row(p.name, `${petStage(p)} · ⚡ ${p.endurance}/100`))));
    } else {
      out.push('<p class="pt-note">Этот питомец ещё не найден. Карточки выпадают из сундуков.</p>');
    }
    const t = info.trail_traits;
    if (t) {
      const sign = (n) => (n > 0 ? `+${n}` : String(n));
      out.push(`<h4>Особенности вида${soon('trail')}</h4>` + list([
        row('Любимое место', esc(t.favorite_route)),
        row('Запас сил', `${sign(t.energy_bonus)} к запасу`),
        row('Отдых', `${sign(t.rest_bonus)} к восстановлению в час`),
        row('Чаще находит', esc(t.favored_find)),
      ]));
    }
    out.push(`<h4>Что даёт уровень${soon('route_rewards')}</h4>` + list((data.level_milestones || []).map((m) => row(`Ур. ${m.level}`, esc(m.text)))));
    const src = (info.card_sources || []).map((x) => `${x.stars}★ · ${x.percent}%`).join(', ');
    out.push('<h4>Откуда берётся</h4>' + list([row('Карточки в сундуках', esc(src) + '<br>Доля карточек этой редкости среди всех карточек сундука этой звёздности.')]));
    const c = info.level_cost;
    if (c) {
      out.push(`<h4>Как прокачать${soon('level_up')}</h4>` + list([row(`С 1 до ${c.max_level} уровня`, `${fmt(c.cards)} карточек вида · ${fmt(c.mora)} 🪙 · ${fmt(c.essence)} 🔮`)]));
    }
    out.push('<h4>Где пригодится</h4>' + list((info.uses || []).map((u) => `<li><span>${esc(u.text)}${soon(u.feature)}</span></li>`)));
    return out.join('');
  }
  window.petDexOpen = function (id) {
    const data = _petData || {};
    const sp = (data.bestiary || []).find((x) => String(x.id) === String(id));
    if (!sp) return;
    const mine = (data.pets || []).filter((p) => p.species_id === sp.id);
    const root = el('pg-pets');
    root.querySelector('.pt-sheet-wrap')?.remove();
    const body = petInfoBody(sp, mine, data);
    const wrap = document.createElement('div');
    wrap.className = 'pt-sheet-wrap';
    wrap.innerHTML = `<div class="pt-sheet-bg" onclick="petDexClose()"></div><div class="pt-sheet ${petRarityClass(sp.rarity)}" role="dialog" aria-modal="true" aria-label="${esc(sp.name)}">`
      + `<span class="pt-ic" aria-hidden="true">${esc(sp.icon)}</span><small>${esc(petRarityName(sp.rarity))}${sp.owned ? '' : ' · не найден'}</small><h3>${esc(sp.name)}</h3>${body}`
      + '<button type="button" class="pt-main" onclick="petDexClose()">Закрыть</button></div>';
    root.appendChild(wrap);
    wrap.querySelector('.pt-main').focus();
    document.addEventListener('keydown', _petSheetKey);
  };
  function _petSheetKey(event) { if (event.key === 'Escape') window.petDexClose(); }
  window.petDexClose = function () {
    document.removeEventListener('keydown', _petSheetKey);
    el('pg-pets').querySelector('.pt-sheet-wrap')?.remove();
  };
  window.petDexFilter = function (rar) {
    _petDexFilter = rar;
    const root = el('pg-pets');
    root.querySelectorAll('[data-rar-chip]').forEach((chip) => {
      chip.setAttribute('aria-pressed', String(chip.dataset.rarChip === rar));
    });
    root.querySelectorAll('.bestiary-card').forEach((card) => {
      card.hidden = rar !== 'all' && card.dataset.rar !== rar;
    });
  };
  const _petsV1PendingActions=new Map();
  const _questsV1PendingActions=new Map();
  const _chestsV1PendingActions=new Map();
  function _pendingAction(store,key,prefix){
    const existing=store.get(key);
    if(existing)return existing;
    const value=prefix+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36));
    store.set(key,value);return value;
  }
  window.petsV1Activate=function(id){
    const key=`activate:${id}`,action=_pendingAction(_petsV1PendingActions,key,'pet-activate-');
    api('/pets-v1/active',{method:'POST',body:JSON.stringify({pet_id:id,action_id:action})}).then(()=>{_petsV1PendingActions.delete(key);toast('Активный питомец выбран');openPetsV1();}).catch(e=>{toast(`${e} Проверяем актуальное состояние.`,false);openPetsV1();});
  };
  window.petsV1Start=function(kind,hours){
    const key=`activity:${kind}:${hours}`,action=_pendingAction(_petsV1PendingActions,key,'pet-activity-');
    api('/pets-v1/activity',{method:'POST',body:JSON.stringify({kind:kind,hours:hours,action_id:action})}).then(()=>{_petsV1PendingActions.delete(key);toast('Таймер запущен');openPetsV1();}).catch(e=>{toast(`${e} Проверяем запущенный таймер.`,false);openPetsV1();});
  };
  window.petsV1LevelUp=function(petId){
    const key=`levelup:${petId}`,action=_pendingAction(_petsV1PendingActions,key,'pet-levelup-');
    api('/pets-v1/level-up',{method:'POST',body:JSON.stringify({pet_id:petId,action_id:action})}).then(()=>{_petsV1PendingActions.delete(key);toast('Уровень повышен');openPetsV1();}).catch(e=>{toast(`${e} Проверяем актуальное состояние.`,false);openPetsV1();});
  };
  window.petsV1Feed=function(petId,foodId){
    const key=`feed:${petId}:${foodId}`,action=_pendingAction(_petsV1PendingActions,key,'pet-feed-');
    api('/pets-v1/feed',{method:'POST',body:JSON.stringify({pet_id:petId,food_id:foodId,action_id:action})}).then(d=>{_petsV1PendingActions.delete(key);toast(`Выносливость восстановлена до ${d.endurance}/100`);openPetsV1();}).catch(e=>toast(`${e} Повтори: запрос будет отправлен с тем же номером операции.`,false));
  };
  function petRouteToast(d){
    const r=d.route,keys=d.amount_keys?` · +${d.amount_keys} 🗝`:'';
    if(!r)return d.amount_keys?`Экспедиция завершена${keys}`:'Маршрут выбран';
    if(!r.success)return`Маршрут не удался, Мора не потрачена${keys}`;
    if(r.capped)return Number(r.paid_mora)>0?`Маршрут пройден · +${fmt(r.paid_mora)} 🪙, недельный лимит наград маршрутов достигнут${keys}`:`Маршрут пройден, но недельный лимит наград маршрутов уже достигнут${keys}`;
    return`Маршрут пройден · +${fmt(r.paid_mora)} 🪙${keys}`;
  }
  window.petsV1Choose=function(decision){
    const key=`decision:${decision}`,action=_pendingAction(_petsV1PendingActions,key,'pet-decision-');
    api('/pets-v1/expedition/decision',{method:'POST',body:JSON.stringify({decision:decision,action_id:action})}).then(d=>{_petsV1PendingActions.delete(key);toast(petRouteToast(d));openPetsV1();}).catch(e=>{toast(`${e} Проверяем итог маршрута.`,false);openPetsV1();});
  };
  let _chestsV1Data=null,_chestsV1Busy=false,_chestsV1Prepared=null,_chestsV1LastResult=null,_chestsV1Tier=1,_chestsV1RevealView=null;
  function chestRevealArt(step=0){
    return `<span class="chest-art" style="--ch-lift:${Math.min(10,Math.max(0,step))}"><svg viewBox="0 0 160 140" aria-hidden="true"><ellipse class="chest-shadow" cx="80" cy="125" rx="55" ry="8"/><path class="chest-body" d="M25 65h110v46a10 10 0 0 1-10 10H35a10 10 0 0 1-10-10Z"/><path class="chest-band" d="M39 65v56m82-56v56M25 82h110"/><g class="chest-lid"><path d="M23 63v-9a57 32 0 0 1 114 0v9Z"/><path class="chest-band" d="M39 60V37m82 23V37"/></g><rect class="chest-lock" x="69" y="68" width="22" height="26" rx="5"/><path class="chest-keyhole" d="M80 77v8"/></svg></span>`;
  }
  function chestRevealScene(){
    const v=_chestsV1RevealView,done=v.step>=v.stars;
    const stars=Array.from({length:10},(_,i)=>`<i class="${i<v.step?'is-lit':''}">★</i>`).join('');
    return `<section class="chest-reveal${done?' is-complete':''}" style="--ch-power:${v.step/10}" aria-label="Раскрытие сундука">
      ${done?`<div class="chest-result-origin" aria-label="Сундук на ${v.stars} звёзд"><div class="chest-reveal-final">${chestRevealArt(v.step)}</div><div class="chest-reveal-stars" aria-hidden="true">${stars}</div></div>`:`<button type="button" class="chest-reveal-tap" onclick="chestsV1RevealStep()" aria-label="Открыть следующую звезду">${chestRevealArt(v.step)}</button><div class="chest-reveal-stars" aria-hidden="true">${stars}</div>`}
      <div class="chest-reveal-status" role="status" aria-live="polite">${done?`<h2>Получено</h2>${chestLootCards(v.result)}`:`<b>${v.step} ${achievementWord(v.step,'звезда','звезды','звёзд')}</b><span>Коснись сундука ещё раз</span>`}</div>
      ${done?'<button type="button" class="v3-pill v3-pill--full" onclick="chestsV1FinishReveal()">Готово</button>':'<button type="button" class="v3-link" onclick="chestsV1SkipReveal()">Сразу показать награду</button>'}
    </section>`;
  }
  function chestRevealPaint(){
    if(_activePage!=='chests')return;
    renderChestsV1();
    requestAnimationFrame(()=>el('pg-chests')?.querySelector('.chest-reveal-tap, .chest-reveal .v3-pill')?.focus({preventScroll:true}));
  }
  function chestRevealCelebrate(){
    const v=_chestsV1RevealView;
    if(v&&v.step>=v.stars&&!v.celebrated){v.celebrated=true;if(_activePage==='chests'){v3Reward();if(typeof _haptic==='function')_haptic('success');}}
  }
  window.chestsV1RevealStep=function(){
    const v=_chestsV1RevealView;if(!v||v.step>=v.stars)return;
    v.step++;if(typeof _haptic==='function')_haptic('light');chestRevealPaint();chestRevealCelebrate();
  };
  window.chestsV1SkipReveal=function(){if(!_chestsV1RevealView)return;_chestsV1RevealView.step=_chestsV1RevealView.stars;chestRevealPaint();chestRevealCelebrate();};
  window.chestsV1FinishReveal=function(){if(!_chestsV1RevealView||_chestsV1RevealView.step<_chestsV1RevealView.stars)return;_chestsV1LastResult=_chestsV1RevealView.result;_chestsV1RevealView=null;_chestsV1RefreshVisible();};
  const CHEST_PRICE_ICONS={mora:'🪙',diamonds:'💎',zarniki:'✨',essence:'💧'};
  function chestPriceText(price){return Object.entries(price||{}).map(([k,v])=>`${fmt(v)} ${CHEST_PRICE_ICONS[k]||k}`).join(' + ');}
  function chestTierInfo(d,tier){return (d.key_tiers||[]).find(t=>Number(t.tier)===Number(tier))||null;}
  function chestTierBalance(d,tier){const b=d.key_balances;return b?Number(b[String(tier)]||0):(Number(tier)===1?Number(d.key_balance||0):0);}
  function chestRewardsText(result){
    return (Array.isArray(result?.rewards)&&result.rewards.length?result.rewards:[result?.reward]).map(chestRewardText).join(' + ');
  }
  function chestLootCards(result){
    const rewards=[];
    for(const reward of (Array.isArray(result?.rewards)&&result.rewards.length?result.rewards:[result?.reward]).filter(Boolean)){
      const same=reward.kind==='food'&&rewards.find(r=>r.kind==='food'&&r.ref===reward.ref);
      if(same)same.amount=Number(same.amount||0)+Number(reward.amount||0);
      else rewards.push({...reward});
    }
    return `<ul class="chest-loot-cards${rewards.length===1?' is-single':''}" aria-label="Выпавшие награды">${rewards.filter(Boolean).map(reward=>{
      const kind=['mora','diamonds','zarniki','food','pet_card','joker','vip_days','vip_cosmetic'].includes(reward.kind)?reward.kind:'item';
      const unit=kind==='vip_days'?achievementWord(Number(reward.amount)||0,'день','дня','дней'):['food','pet_card','joker'].includes(kind)?'шт.':'';
      return `<li class="chest-loot-card is-${kind}"><div class="chest-loot-icon" aria-hidden="true">${esc(reward.icon||'🎁')}</div><strong>+${fmt(reward.amount||0)}${unit?` <small>${unit}</small>`:''}</strong><p>${esc(reward.name||reward.kind||'Награда')}</p></li>`;
    }).join('')}</ul>`;
  }
  function chestRewardText(reward){
    if(!reward)return'Награда';
    const amount=fmt(reward.amount||0),name=esc(reward.name||reward.kind||'Награда'),icon=esc(reward.icon||'🎁');
    if(['mora','diamonds','zarniki'].includes(reward.kind))return`${amount} ${icon} ${name}`;
    if(reward.kind==='vip_days')return`${amount} дня ${icon} VIP`;
    return`${icon} ${name}${Number(reward.amount||0)>1?` · ${amount} шт.`:''}`;
  }
  function chestAmountText(outcome){
    const amount=outcome?.amount||{};
    if(amount.unit==='vip_days')return`${fmt(amount.fixed)} дня`;
    if(Number.isFinite(Number(amount.fixed)))return`${fmt(amount.fixed)} шт.`;
    if(Number.isFinite(Number(amount.min))&&Number.isFinite(Number(amount.max)))return amount.min===amount.max?fmt(amount.min):`${fmt(amount.min)}–${fmt(amount.max)}`;
    return'';
  }
  function chestOddsDetails(outcome){
    const parts=[];
    if(outcome?.rarity_odds)parts.push(`Редкости: ${Object.entries(outcome.rarity_odds).map(([rarity,percent])=>`${rarLabel(rarity)} ${percent}%`).join(' · ')}`);
    if(Array.isArray(outcome?.pool)&&outcome.pool.length){
      const names=outcome.pool.map(item=>typeof item==='object'?(item.name||item.id):item).filter(Boolean);
      parts.push(`Пул: ${names.join(', ')}`);
    }
    if(outcome?.fallback)parts.push(outcome.fallback);
    return parts.length?`<small>${esc(parts.join(' · '))}</small>`:'';
  }
  // Сундуки: ключи крупной цифрой, одно главное действие (раскрыть подготовленный · открыть ключом · купить ключ, если ключей нет),
  // ключи по звёздам и добыча — строками, шансы и правила — свёрнуты внизу. Правила вида: docs/MINIAPP_DESIGN_RULES.md. Стили: chests-v3.css.
  function renderChestsV1(){
    const d=_chestsV1Data,root=el('pg-chests');if(!d||!root)return;
    if(_chestsV1RevealView){
      root.innerHTML=`${v3Head('Сундуки')}${chestRevealScene()}`;
      v3EnterSync(root);return;
    }
    if((_chestsV1Tier!==1&&!chestTierInfo(d,_chestsV1Tier))||chestTierBalance(d,_chestsV1Tier)<1)_chestsV1Tier=(d.key_tiers||[]).map(t=>Number(t.tier)).filter(t=>t>1&&chestTierBalance(d,t)>0).sort((a,b)=>b-a)[0]||1;
    const tierInfo=chestTierInfo(d,_chestsV1Tier),odds=((tierInfo&&tierInfo.star_odds)||d.star_odds||[]).map(row=>`<li><span>${row.stars}★</span><b>${String(row.percent).replace('.',',')}%</b></li>`).join('');
    const rewards=(d.rewards||[]).map(row=>`<details class="chest-tier"><summary><b>${row.stars}★</b><span>${String(row.star_percent).replace('.',',')}% сундуков</span></summary><ul>${(row.outcomes||[]).map(outcome=>`<li><span><b>${esc(outcome.label)}</b>${chestOddsDetails(outcome)}</span><em>${outcome.conditional_percent}%${chestAmountText(outcome)?` · ${chestAmountText(outcome)}`:''}</em></li>`).join('')}</ul></details>`).join('');
    const paid=d.funding||{},remaining=Math.max(0,Number(paid.remaining_today)||0),price=Number(paid.price_zarniki)||0,canBuy=paid.paid!==false;
    const tierBal=chestTierBalance(d,_chestsV1Tier),tierName=tierInfo?tierInfo.name:'Обычный',busy=_chestsV1Busy||!!_chestsV1Prepared||!!_chestsV1RevealView;
    const inv=d.inventory||{},owned=Object.keys(inv.unlocked_pets||{}).length,cards=Object.values(inv.pet_cards||{}).reduce((a,b)=>a+Number(b||0),0),food=Object.values(inv.foods||{}).reduce((a,b)=>a+Number(b||0),0),jokers=Object.values(inv.jokers||{}).reduce((a,b)=>a+Number(b||0),0);
    // Ключи разных уровней — выбор, каким открыть; показываются, только если есть ключ выше обычного
    const higher=(d.key_tiers||[]).some(t=>Number(t.tier)>1&&chestTierBalance(d,t.tier)>0);
    const tiers=higher?`<div class="ch-tiers" role="group" aria-label="Каким ключом открыть">${(d.key_tiers||[]).filter(t=>Number(t.tier)===1||chestTierBalance(d,t.tier)>0).map(t=>`<button type="button" class="chest-tier-chip${Number(t.tier)===_chestsV1Tier?' is-on':''}" aria-pressed="${Number(t.tier)===_chestsV1Tier}" onclick="chestsV1PickTier(${Number(t.tier)})">${esc(t.name)}${Number(t.tier)>1?` ${t.tier}★+`:''} · <b>${fmt(chestTierBalance(d,t.tier))}</b></button>`).join('')}</div>`:'';
    let action;
    if(_chestsV1RevealView)action=chestRevealScene();
    else if(_chestsV1Prepared)action=`<button type="button" class="chest-orb" onclick="chestsV1Reveal()" ${_chestsV1Busy?'disabled':''} aria-label="Раскрыть подготовленный сундук">${chestRevealArt(0)}<b>${_chestsV1Busy?'Раскрываю…':'Коснись, чтобы раскрыть'}</b><small>Награда уже сохранена сервером</small></button>`;
    else if(tierBal>0)action=`<button type="button" class="v3-pill chest-open-btn" onclick="chestsV1Prepare()" ${busy?'disabled':''}>${_chestsV1Tier>1?`Открыть: ${esc(tierName)} ключ`:'Открыть за 1 ключ'}</button>${canBuy?`<button type="button" class="v3-link ch-buy-more" onclick="chestsV1AskBuy(this)" ${busy||remaining<1?'disabled':''}>Купить ${_chestsV1Tier>1?'обычный':'ещё'} ключ за ${fmt(price)} ✨</button>`:''}`;
    else if(canBuy&&remaining>0)action=`<button type="button" class="v3-pill chest-open-btn" onclick="chestsV1AskBuy(this)" ${busy?'disabled':''}>Купить ключ за ${fmt(price)} ✨</button><p class="ch-hint">Сегодня можно купить ещё ${remaining} из ${paid.daily_limit}. Бесплатно ключ дают за полный день и неделю заданий.</p>`;
    else action=`<p class="ch-hint">${canBuy?'Покупки на сегодня закончились. ':''}Ключ дают за полный день и неделю заданий.</p><button type="button" class="v3-pill v3-pill--ghost chest-open-btn" onclick="openQuestsV1()">К заданиям</button>`;
    const result=!_chestsV1RevealView&&!_chestsV1Prepared&&_chestsV1LastResult?`<p class="ch-last" role="status"><span aria-hidden="true">${'★'.repeat(Math.min(10,Number(_chestsV1LastResult.stars)||1))}</span> Последний: ${chestRewardsText(_chestsV1LastResult)}</p>`:'';
    const offers=d.tiers_enabled?(d.offers||[]).map(o=>{
      const left=Number(o.remaining)>0?`осталось ${o.remaining} из ${o.limit} ${o.window==='day'?'сегодня':'на неделе'}`:(o.window==='day'?'лимит на сегодня исчерпан':'лимит на неделю исчерпан');
      return `<div class="ch-row"><span class="ch-tx"><b>${esc(o.name)} ${o.key_tier}★+</b><small>${left}</small></span><button type="button" class="v3-pill v3-pill--sm v3-pill--ghost chest-offer" data-offer="${esc(o.offer_id)}" onclick="chestsV1AskOffer(this.dataset.offer,this)" ${busy||Number(o.remaining)<1?'disabled':''}>${chestPriceText(o.price)}</button></div>`;
    }).join(''):'';
    const loot=`${owned}/12 питомцев · ${fmt(cards)} карт · ${fmt(food)} еды · ${fmt(jokers)} джокеров`;
    root.innerHTML=`${v3Head('Сундуки',{sub:'Награду фиксирует сервер до раскрытия',end:v3GuideBtn('chests')})}
      <div class="ch-keys"><b>${fmt(tierBal)}</b><span>${_chestsV1Tier>1?`${esc(tierName)} ${_chestsV1Tier}★+`:achievementWord(tierBal,'ключ','ключа','ключей')}</span></div>
      ${tiers}<div class="ch-action">${action}</div>${result}
      ${offers?`<div class="v3-sec"><span class="v3-eyebrow">Ключи по звёздам</span></div><p class="ch-hint">Тот же сундук, но звёзды ниже N становятся N.</p><div class="ch-list">${offers}</div>`:''}
      <div class="v3-sec"><span class="v3-eyebrow">Добыча из сундуков</span></div>
      <button type="button" class="v3-row ch-loot" onclick="openInventory()"><span><span class="ch-loot-t">В инвентаре</span><small>${loot}</small></span><span class="v3-end">›</span></button>
      <details class="v3-more chest-odds"><summary>Точные шансы и размеры наград</summary>
        <section><h2>Шанс звёздности${_chestsV1Tier>1?` · ${esc(tierName)} ключ`:''}</h2><ul>${odds}</ul></section>
        <section class="chest-reward-tiers"><h2>Основная награда</h2>${d.provisions?`<p>${esc(d.provisions)}</p>`:''}${rewards}</section>
        ${d.tiers_enabled?'<p>Ключ уровня N поднимает звёзды ниже N до N.</p>':''}
        ${d.message?`<p>${esc(d.message)}</p>`:''}<p><b>Карты не пропадут.</b> ${esc(d.surplus_policy||'Лишние карты сохраняются в инвентаре.')}</p>
      </details>`;
    v3EnterSync(root);
  }
  // Повторный вызов при открытом экране (после открытия, покупки, раскрытия) только перечитывает: без switchPage и без заглушки
  let _chestsV1Seq=0;
  window.openChestsV1=function(){
    if(_activePage!=='chests')switchPage('chests');
    const root=el('pg-chests');
    if(!_chestsV1Data)root.innerHTML=`${v3Head('Сундуки',{sub:'Награду фиксирует сервер до раскрытия',end:v3GuideBtn('chests')})}<div class="sk" style="height:64px;border-radius:14px"></div><div class="sk" style="height:52px;border-radius:99px;margin-top:16px"></div>`;
    const mine=++_chestsV1Seq;
    api('/chests-v1/me').then(d=>{if(mine!==_chestsV1Seq)return;if(d.pending_open)[..._chestsV1PendingActions.keys()].filter(k=>k.startsWith('prepare:')).forEach(k=>_chestsV1PendingActions.delete(k));   // сундук уже подготовлен: старый номер операции больше не нужен
      _chestsV1Data=d;_chestsV1Prepared=d.pending_open&&d.pending_open.open_id!==_chestsV1RevealView?.result.open_id?d.pending_open:null;_chestsV1LastResult=d.last_result||null;renderChestsV1();}).catch(e=>{
      if(mine!==_chestsV1Seq)return;
      const text=String(e?.message||e||'Ошибка').replace(/^Error:\s*/,'');
      if(_chestsV1Data){toast(`Сундуки не обновились: ${text}`,false);return;}
      root.innerHTML=`${v3Head('Сундуки')}<div class="v3-empty" role="alert"><b>Сундуки не загрузились</b><span>${esc(text)}</span> <button type="button" class="v3-link" onclick="openChestsV1()">Повторить</button></div>`;
    });
  };
  function _chestsV1RefreshVisible(){if(_activePage==='chests')openChestsV1();}
  // После подготовки экран перечитывает /me: остаток ключей по уровням знает только сервер
  window.chestsV1Prepare=function(){
    if(_chestsV1Busy||_chestsV1RevealView||_chestsV1Prepared||!_chestsV1Data)return;_chestsV1Busy=true;_chestsV1Seq++;renderChestsV1();
    const tier=_chestsV1Tier,key=`prepare:${tier}`,action=_pendingAction(_chestsV1PendingActions,key,'chest-open-');
    api('/chests-v1/prepare',{method:'POST',body:JSON.stringify({action_id:action,catalog_version:_chestsV1Data.catalog_version,catalog_digest:_chestsV1Data.catalog_digest,key_tier:tier})}).then(d=>{_chestsV1PendingActions.delete(key);_chestsV1Prepared=d;_chestsV1Data.key_balance=d.key_balance;_chestsV1Busy=false;renderChestsV1();requestAnimationFrame(()=>el('pg-chests')?.querySelector('.chest-orb')?.focus());_chestsV1RefreshVisible();}).catch(e=>{_chestsV1Busy=false;toast(`${e} Повтори: ключ не спишется второй раз.`,false);_chestsV1RefreshVisible();});
  };
  window.chestsV1Buy=function(){
    if(_chestsV1Busy||_chestsV1RevealView||!_chestsV1Data||Number(_chestsV1Data.funding?.remaining_today||0)<1)return;_chestsV1Busy=true;_chestsV1Seq++;renderChestsV1();
    const key='purchase',action=_pendingAction(_chestsV1PendingActions,key,'chest-buy-');
    api('/chests-v1/purchase',{method:'POST',body:JSON.stringify({action_id:action,catalog_version:_chestsV1Data.catalog_version,catalog_digest:_chestsV1Data.catalog_digest})}).then(d=>{_chestsV1PendingActions.delete(key);toast(`Ключ куплен за ${fmt(d.price_zarniki)} ✨`);_chestsV1Busy=false;_chestsV1RefreshVisible();}).catch(e=>{_chestsV1Busy=false;toast(`${e} Повтори: покупка сохранит тот же номер операции.`,false);_chestsV1RefreshVisible();});
  };
  window.chestsV1PickTier=function(tier){if(_chestsV1Busy||_chestsV1Prepared||_chestsV1RevealView)return;_chestsV1Tier=Number(tier)||1;renderChestsV1();};
  window.chestsV1AskOffer=function(offerId,trigger){
    if(_chestsV1Busy||_chestsV1RevealView||!_chestsV1Data)return;
    const o=(_chestsV1Data.offers||[]).find(x=>x.offer_id===offerId);if(!o)return;
    const info=chestTierInfo(_chestsV1Data,o.key_tier),top=info&&info.star_odds&&info.star_odds[0];
    if(trigger)trigger.dataset.modalTrigger='true';
    OM('Купить ключ',`<div class="chest-buy-confirm"><b>${esc(o.name)} ключ ${o.key_tier}★+</b><p>Отдаёшь: ${chestPriceText(o.price)}.<br>Получаешь: 1 ключ, звёзды ниже ${o.key_tier} становятся ${o.key_tier}${top?` (ровно ${o.key_tier}★ — ${String(top.percent).replace('.',',')}%)`:''}.</p><p>После покупки останется ${Math.max(0,Number(o.remaining)-1)} из ${o.limit} ${o.window==='day'?'сегодня':'на этой неделе'}.</p><small>Покупка необратима: ключ не возвращается.</small></div>`,[{l:`Купить за ${chestPriceText(o.price)}`,c:'primary',f:`chestsV1BuyOffer('${esc(o.offer_id)}');CM()`},{l:'Отмена',c:'ghost',f:'CM()'}]);
  };
  window.chestsV1BuyOffer=function(offerId){
    if(_chestsV1Busy||_chestsV1RevealView||!_chestsV1Data)return;_chestsV1Busy=true;_chestsV1Seq++;renderChestsV1();
    const key=`offer:${offerId}`,action=_pendingAction(_chestsV1PendingActions,key,'chest-offer-');
    api(`/chests-v1/offers/${encodeURIComponent(offerId)}/buy`,{method:'POST',body:JSON.stringify({action_id:action,catalog_version:_chestsV1Data.catalog_version,catalog_digest:_chestsV1Data.catalog_digest})}).then(d=>{_chestsV1PendingActions.delete(key);toast('Ключ куплен');_chestsV1Tier=Number(d.key_tier)||_chestsV1Tier;_chestsV1Busy=false;_chestsV1RefreshVisible();}).catch(e=>{_chestsV1Busy=false;toast(`${e} Повтори: покупка сохранит тот же номер операции.`,false);_chestsV1RefreshVisible();});
  };
  window.chestsV1AskBuy=function(trigger){
    if(_chestsV1Busy||_chestsV1RevealView||!_chestsV1Data)return;
    const funding=_chestsV1Data.funding||{},price=Number(funding.price_zarniki)||0,remaining=Number(funding.remaining_today)||0;
    if(trigger)trigger.dataset.modalTrigger='true';
    OM('Купить ключ',`<div class="chest-buy-confirm"><b>1 ключ за ${fmt(price)} ✨</b><p>Шансы полностью совпадают с бесплатным ключом. Сегодня после покупки останется ${Math.max(0,remaining-1)} из ${funding.daily_limit||0} покупок.</p><small>Неиспользованный купленный ключ можно вернуть через поддержку.</small></div>`,[{l:`Купить за ${fmt(price)} ✨`,c:'primary',f:'chestsV1Buy();CM()'},{l:'Отмена',c:'ghost',f:'CM()'}]);
  };
  window.chestsV1Reveal=function(){
    if(_chestsV1Busy||_chestsV1RevealView||!_chestsV1Prepared)return;
    const openId=_chestsV1Prepared.open_id;_chestsV1Busy=true;_chestsV1Seq++;renderChestsV1();
    api(`/chests-v1/${encodeURIComponent(openId)}/reveal`,{method:'POST'}).then(d=>{
      if(!d||d.open_id!==openId||!d.revealed||!Number.isInteger(Number(d.stars))||Number(d.stars)<1||Number(d.stars)>10||!d.reward)throw new Error('Не удалось прочитать награду. Повторите раскрытие: сервер сохранит тот же результат.');
      _chestsV1Busy=false;_chestsV1Prepared=null;_chestsV1LastResult=d;
      _chestsV1RevealView={result:d,stars:Math.max(1,Math.min(10,Math.floor(Number(d.stars)||1))),step:1,celebrated:false};
      chestRevealPaint();chestRevealCelebrate();
    }).catch(e=>{_chestsV1Busy=false;toast(e,false);if(_activePage==='chests')renderChestsV1();});
  };
  // ── Задания: строка на задание (значок, что сделать, одна полоса, «2/4» справа); переход к игре и замена — в листе по нажатию.
  // Готовая награда — одна строка с «Забрать» над вкладками: это главное действие экрана. Правила вида: docs/MINIAPP_DESIGN_RULES.md. Стили: quests-v3.css.
  let _questsV1Data=null,_questsV1Tab='daily',_questsV1Busy=false;
  const QUEST_REWARD_LABELS={daily:'За день',weekly:'За неделю',combined:'За всё'};
  function questMetricMeta(metric){
    if(metric==='game_completed')return{icon:'◆',label:'Выбрать игру',action:"goTo('arena','game')"};
    if(metric.startsWith('rhythm_'))return{icon:'ᚱ',label:'Открыть Ритм',action:'openRhythmV2Game()'};
    if(metric.startsWith('minesweeper_'))return{icon:'▦',label:'Открыть Сапёр',action:'openMinesweeperGame()'};
    if(metric.startsWith('mafia_'))return{icon:'◈',label:'Открыть игры',action:"goTo('arena','game')"};
    if(metric==='chest_revealed')return{icon:'✦',label:'К сундукам',action:'openChestsV1()'};
    if(['pet_fed','pet_activity_completed','pet_trek_completed','pet_expedition_completed','pet_watch_completed'].includes(metric))return{icon:'🐾',label:'К питомцам',action:'openPetsV1()'};
    return{icon:'◆',label:'К играм',action:"goTo('arena','game')"};
  }
  function questRewardValue(reward){
    const keys=_sysFlags.content_chests_v1?Number(reward?.amount_keys||0):0,ess=Number(reward?.amount_essence||0);
    // Names stay readable without relying on small emoji glyphs; whole values wrap together.
    return [`${fmt(reward?.amount_mora||0)} Моры`,ess?`${fmt(ess)} Эссенции`:'',keys?`${fmt(keys)} ${achievementWord(keys,'ключ','ключа','ключей')}`:''].filter(Boolean).map(x=>`<span class="qs-nw">${x}</span>`).join(' + ');
  }
  function questRow(quest,period){
    const progress=Math.max(0,Number(quest.progress)||0),target=Math.max(1,Number(quest.target)||1);
    const percent=Math.min(100,Math.round(progress/target*100)),meta=questMetricMeta(quest.metric),done=!!quest.completed;
    return `<button type="button" class="quest-card qs-row${done?' is-done':''}" data-q="${period}-${quest.slot}" onclick="questsV1Open('${period}',${Number(quest.slot)})" aria-label="${esc(quest.title)}: ${done?'выполнено':`${Math.min(progress,target)} из ${target}`}">
      <span class="quest-card-icon qs-ic" aria-hidden="true">${done?'✓':meta.icon}</span>
      <span class="qs-tx"><b>${esc(quest.title)}</b><small>${esc(quest.help)}</small>${done?'':`<i class="qs-bar" aria-hidden="true"><i style="width:${percent}%"></i></i>`}</span>
      ${done?'':`<span class="qs-end">${fmt(Math.min(progress,target))}<small>/${fmt(target)}</small></span>`}
    </button>`;
  }
  function questPeriodSummary(period){
    const quests=_questsV1Data?.[period]?.quests||[],done=quests.filter(q=>q.completed).length;
    return {done,total:quests.length};
  }
  // Награда за период: под названием — сколько дают; справа «Забрать», пока готова, иначе прогресс или «Получено»
  function questRewardRow(kind,reward,daily,weekly,primary=true){
    const target=kind==='daily'?daily:kind==='weekly'?weekly:null;
    const state=kind==='combined'?`${daily.done}/${daily.total} · ${weekly.done}/${weekly.total}`:`${target.done}/${target.total}`;
    const end=reward.claimable?`<button class="v3-pill v3-pill--sm${primary?'':' v3-pill--ghost'} quest-reward-claim" type="button" onclick="questsV1Claim('${kind}')" ${_questsV1Busy?'disabled':''}>${_questsV1Busy?'…':'Забрать'}</button>`
      :`<span class="qs-end">${reward.claimed?'Получено':state}</span>`;
    return `<div class="qs-reward${reward.claimed?' is-claimed':''}"><span class="qs-tx"><b>${QUEST_REWARD_LABELS[kind]}</b><small>${questRewardValue(reward)}</small></span>${end}</div>`;
  }
  function renderQuestsV1(){
    const d=_questsV1Data,root=el('pg-questlog'); if(!d||!root)return;
    const daily=questPeriodSummary('daily'),weekly=questPeriodSummary('weekly'),items=d.rewards?.items||{};
    const kinds=['daily','weekly','combined'],ready=kinds.find(k=>items[k]?.claimable);
    // Готовая награда над вкладками: на «Наградах» она и так в списке
    const banner=ready&&_questsV1Tab!=='rewards'?`<div class="qs-ready">${questRewardRow(ready,items[ready],daily,weekly)}</div>`:'';
    let body;
    if(_questsV1Tab==='rewards'){
      const keys=_sysFlags.content_chests_v1?` · у тебя ${fmt(Number(d.rewards?.key_balance)||0)} 🗝`:'';
      body=`<p class="qs-state">Каждая выдаётся один раз${keys}</p><div class="qs-list">${kinds.map(k=>questRewardRow(k,items[k]||{amount_mora:0},daily,weekly,k===ready)).join('')}</div>${d.rewards?.message?`<details class="v3-more qs-help"><summary>Как выдаются награды</summary><p>${esc(d.rewards.message)}</p></details>`:''}`;
    }else{
      const period=_questsV1Tab,sum=period==='weekly'?weekly:daily,quests=d[period]?.quests||[];
      // Невыполненные выше, выполненные — внизу списка
      const rows=[...quests].sort((a,b)=>Number(!!a.completed)-Number(!!b.completed)).map(q=>questRow(q,period)).join('');
      body=`<p class="qs-state">${sum.done}/${sum.total} · за все ${questRewardValue(items[period])}</p>${rows?`<div class="qs-list">${rows}</div>`:'<div class="v3-empty"><b>Нет доступных заданий</b><span>Задания появятся, как только откроется доступная игра.</span> <button type="button" class="v3-link" onclick="openQuestsV1()">Обновить</button></div>'}`;
    }
    const tab=(id,label)=>`<button type="button" id="quest-tab-${id}" class="v3-tab${_questsV1Tab===id?' on':''}" role="tab" tabindex="${_questsV1Tab===id?'0':'-1'}" aria-selected="${_questsV1Tab===id}" aria-controls="quest-panel" onclick="questsV1SetTab('${id}')">${label}</button>`;
    root.innerHTML=`${v3Head('Задания',{sub:'Цели на день и неделю',end:v3GuideBtn('quests')})}${banner}<nav class="v3-tabs v3-tabs--wide quest-tabs${ready?' has-ready':''}" role="tablist" aria-label="Разделы заданий" onkeydown="questsV1TabKey(event)">${tab('daily','Сегодня')}${tab('weekly','Неделя')}${tab('rewards','Награды')}</nav><section id="quest-panel" role="tabpanel" aria-labelledby="quest-tab-${_questsV1Tab}">${body}</section>`;
    v3EnterSync(root);
    if(typeof v3QuestsDone==='function')v3QuestsDone(root);
  }
  // Лист задания: что сделать, прогресс, переход к игре и замена (лимит замен — общий на неделю)
  window.questsV1Open=function(period,slot){
    const quest=(_questsV1Data?.[period]?.quests||[]).find(q=>Number(q.slot)===Number(slot));if(!quest)return;
    _haptic('select');
    const progress=Math.max(0,Number(quest.progress)||0),target=Math.max(1,Number(quest.target)||1),meta=questMetricMeta(quest.metric),rr=_questsV1Data.rerolls||{remaining:0,limit:0};
    const body=`<div class="qs-sheet"><p>${esc(quest.help)}</p><div class="qs-meter"><span>${quest.completed?'Выполнено':'Прогресс'}</span><b>${fmt(Math.min(progress,target))} / ${fmt(target)}</b><i class="qs-bar"><i style="width:${Math.min(100,Math.round(progress/target*100))}%"></i></i></div>${quest.completed?'':`<p class="qs-note">Замен на этой неделе: ${rr.remaining||0} из ${rr.limit||0}</p>`}</div>`;
    const btns=quest.completed?[{l:'Закрыть',c:'ghost',f:'CM()'}]:[{l:meta.label,c:'primary',f:`CM();${meta.action}`},{l:'Сменить ↻',c:'ghost',f:`CM();questsV1AskReroll('${period}',${Number(quest.slot)})`,d:!(Number(rr.remaining)>0)||_questsV1Busy}];
    OM(quest.title,body,btns);
  };
  window.questsV1SetTab=function(tab){if(!['daily','weekly','rewards'].includes(tab)||tab===_questsV1Tab)return;_haptic('select');_questsV1Tab=tab;renderQuestsV1();};
  // Стрелки двигают выбор по вкладкам; фокус переносится только при управлении с клавиатуры
  window.questsV1TabKey=function(event){
    const tabs=['daily','weekly','rewards'],index=tabs.indexOf(_questsV1Tab);let next=null;
    if(event.key==='ArrowRight')next=tabs[(index+1)%tabs.length];
    if(event.key==='ArrowLeft')next=tabs[(index-1+tabs.length)%tabs.length];
    if(event.key==='Home')next=tabs[0]; if(event.key==='End')next=tabs[tabs.length-1];
    if(next){event.preventDefault();questsV1SetTab(next);requestAnimationFrame(()=>el(`quest-tab-${_questsV1Tab}`)?.focus());}
  };
  // Хук обновления (app.01.js) зовёт это же при открытом экране: тогда только перечитываем, без switchPage и без заглушки
  let _questsV1Seq=0;
  window.openQuestsV1=function(tab){
    if(['daily','weekly','rewards'].includes(tab))_questsV1Tab=tab;
    if(_activePage!=='questlog')switchPage('questlog');
    const root=el('pg-questlog');
    if(!_questsV1Data)root.innerHTML=`${v3Head('Задания',{sub:'Цели на день и неделю',end:v3GuideBtn('quests')})}<div class="sk" style="height:44px;border-radius:12px"></div><div class="sk" style="height:260px;border-radius:18px;margin-top:18px"></div>`;
    else renderQuestsV1();
    const mine=++_questsV1Seq;
    api('/quests-v1/me').then(d=>{if(mine!==_questsV1Seq)return;_questsV1Data=d;renderQuestsV1();}).catch(e=>{
      if(mine!==_questsV1Seq)return;
      const text=String(e?.message||e||'Ошибка').replace(/^Error:\s*/,'');
      if(_questsV1Data){toast(`Задания не обновились: ${text}`,false);return;}
      root.innerHTML=`${v3Head('Задания',{sub:'Цели на день и неделю'})}<div class="v3-empty" role="alert"><b>Задания не загрузились</b><span>${esc(text)}</span> <button type="button" class="v3-link" onclick="openQuestsV1()">Повторить</button></div>`;
    });
  };
  window.questsV1AskReroll=function(period,slot,trigger){
    if(_questsV1Busy){toast('Дождись завершения текущего действия.',false);return;}
    const quest=(_questsV1Data?.[period]?.quests||[]).find(q=>Number(q.slot)===Number(slot));
    if(!quest||quest.completed)return;
    const remaining=Number(_questsV1Data?.rerolls?.remaining)||0;
    if(remaining<=0){toast('Лимит замен на эту неделю исчерпан.',false);return;}
    if(trigger)trigger.dataset.modalTrigger='true';
    OM('↻ Заменить задание',`<div class="quest-reroll-confirm"><b>${esc(quest.title)}</b><p>Сервер подберёт другой тип задания из доступных игр. Вернуть этот вариант нельзя.</p><span>После замены останется: ${remaining-1}</span></div>`,[{l:'Заменить',c:'primary',f:`questsV1Reroll('${period}',${slot});CM()`},{l:'Отмена',c:'ghost',f:'CM()'}]);
  };
  window.questsV1Reroll=function(period,slot){
    if(_questsV1Busy)return;
    _questsV1Busy=true;_questsV1Seq++;renderQuestsV1();   // ответ /me, запрошенный до замены, уже устарел
    const key=`reroll:${period}:${slot}`,action=_pendingAction(_questsV1PendingActions,key,'quest-reroll-');
    api('/quests-v1/reroll',{method:'POST',body:JSON.stringify({period,slot,action_id:action})}).then(d=>{_questsV1PendingActions.delete(key);_questsV1Data=d;toast('Квест заменён');}).catch(e=>toast(`${e} Повтори: лимит не спишется второй раз.`,false)).finally(()=>{_questsV1Busy=false;renderQuestsV1();});
  };
  window.questsV1Claim=function(kind){
    if(_questsV1Busy)return;
    const box=document.querySelector(`#pg-questlog .quest-reward-claim[onclick*="'${kind}'"]`)?.getBoundingClientRect(),origin=box?{x:box.left+box.width/2,y:box.top+box.height/2}:null;   // откуда полетят монеты
    _questsV1Busy=true;_questsV1Seq++;renderQuestsV1();
    api('/quests-v1/claim-reward',{method:'POST',body:JSON.stringify({kind})}).then(d=>{
      _questsV1Data=d;if(!d.reward_result?.already_claimed&&Number(d.reward_result?.amount_mora)>0)v3Fly(origin,'mora','🪙');const keys=_sysFlags.content_chests_v1?(Number(d.reward_result?.amount_keys)||0):0,essence=Number(d.reward_result?.amount_essence)||0;toast(d.reward_result?.already_claimed?'Награда уже получена':`Получено: ${d.reward_result?.amount_mora||0} 🪙${essence?` + ${essence} Эссенции`:''}${keys?` + ${keys} 🗝`:''}`);
    }).catch(e=>toast(e,false)).finally(()=>{_questsV1Busy=false;renderQuestsV1();});
  };
  // ── Достижения: пути (GET /achievements-v1/me) и достижения чата (GET /achievements-v1/chat) ──
  // Строка списка — значок, название, что осталось до следующего уровня и одна полоса; подробности и вехи — в листе по нажатию.
  // Правила вида: docs/MINIAPP_DESIGN_RULES.md. Стили: achievements-v3.css.
  let _achievementsV1Data = null;
  let _achievementsV1Filter = 'all';
  let _chatAchievementsData = null;
  const ACHIEVEMENT_FILTERS = Object.freeze([['all', 'Все'], ['games', 'Игры'], ['collection', 'Приключения'], ['progression', 'Развитие'], ['chat', 'Чат']]);
  const ACHIEVEMENT_ACTIONS = Object.freeze({
    rhythm: 'openRhythmV2Game()',
    minesweeper: 'openMinesweeperGame()',
    mafia: 'openMafiaStats()',
    chests: 'openChestsV1()',
    pets: 'openPetsV1()',
    care: 'openPetsV1()',
    builder: 'openPetsV1()',
    stylist: 'openLooksModal()',
    quester: 'openQuestsV1()',
  });

  function achievementPct(value, target) {
    if (!target) return 100;
    const percent = Math.round(Number(value || 0) * 100 / Number(target));
    return Math.max(0, Math.min(100, percent));
  }

  function achievementWord(value, one, few, many) {
    const lastTwoDigits = Math.abs(Number(value)) % 100;
    const lastDigit = lastTwoDigits % 10;
    if (lastTwoDigits > 10 && lastTwoDigits < 20) return many;
    if (lastDigit === 1) return one;
    if (lastDigit >= 2 && lastDigit <= 4) return few;
    return many;
  }

  // Цель следующего уровня пути: для пройденного пути — последняя веха и предел активных недель
  function achievementTargets(family) {
    const final = (family.milestones || []).find((m) => Number(m.level) === Number(family.max_level));
    return {
      events: Number(family.next?.events_required) || Number(final?.events_required) || 1,
      weeks: Number(family.next?.weeks_required ?? final?.weeks_required ?? family.week_gate ?? _achievementsV1Data?.max_active_weeks ?? 156),
    };
  }

  // Путь и достижение чата в одном виде: строка списка и лист подробностей читают только его
  function achievementPathItem(family) {
    const t = achievementTargets(family);
    const events = Number(family.completed_events || 0), weeks = Number(family.active_weeks || 0);
    const leftE = Math.max(0, t.events - events), leftW = Math.max(0, t.weeks - weeks);
    const left = [leftE ? `${fmt(leftE)} ${achievementWord(leftE, ...(family.measure || ['завершение', 'завершения', 'завершений']))}` : '',
      leftW ? `${fmt(leftW)} ${achievementWord(leftW, 'неделя', 'недели', 'недель')}` : ''].filter(Boolean);
    // Номер следующего уровня читается из «0/40» справа, награда за него — под ним: подсказке остаётся только «что сделать»
    const hint = family.next ? (left.length ? `Ещё ${left.join(' и ')}` : 'Условия выполнены') : 'Путь пройден';
    return {
      key: `path:${family.id}`, icon: family.icon, title: family.title, level: Number(family.level || 0), max: Number(family.max_level || 40),
      // Уровень требует обоих условий, поэтому полоса — по отстающему
      pct: family.next ? Math.min(achievementPct(events, t.events), achievementPct(weeks, t.weeks)) : 100,
      hint, reward: family.next ? `+${fmt(family.next.reward_mora)} 🪙` : '', done: !family.next, family,
    };
  }
  function achievementChatItem(item) {
    const target = Number(item.next_threshold || 0), base = Number(item.prev_threshold || 0), value = Number(item.value || 0);
    return {
      key: `chat:${item.id || item.title}`, icon: item.icon, title: item.title, level: Number(item.level || 0), max: Number(item.max_level || 0),
      pct: target ? achievementPct(value - base, target - base) : 100,
      hint: target ? `${fmt(value)} / ${fmt(target)} · ${item.measure}` : `Все уровни · ${item.measure}`,   // число первым: на 320 px обрезается пояснение, а не прогресс
      done: !target, chat: item,
    };
  }

  // Ближе к следующему уровню — выше; пройденные — в конце
  const achievementOrder = (a, b) => (a.done - b.done) || (b.pct - a.pct) || (b.level - a.level);

  function achievementRow(item, index) {
    return `<button type="button" class="ach-row" onclick="achievementsV1Open(${index})" aria-label="${esc(item.title)}: уровень ${item.level} из ${item.max}. ${esc(item.hint)}${item.reward ? `, за следующий ${esc(item.reward)}` : ''}">
      <span class="ach-ic" aria-hidden="true">${esc(item.icon)}</span>
      <span class="ach-tx"><b>${esc(item.title)}</b><small>${esc(item.hint)}</small><i class="ach-bar" aria-hidden="true"><i style="width:${item.pct}%"></i></i></span>
      <span class="ach-lv">${item.level}<small>/${item.max}</small>${item.reward ? `<em>${item.reward}</em>` : ''}</span>
    </button>`;
  }

  let _achievementsShown = [];
  function achievementSections() {
    const families = _achievementsV1Data.families || [];
    const chat = _chatAchievementsData?.achievements || [];
    const groups = [
      ['games', 'Игры', families.filter((f) => f.category === 'games').map(achievementPathItem)],
      ['collection', 'Приключения', families.filter((f) => f.category === 'collection').map(achievementPathItem)],
      ['progression', 'Развитие', families.filter((f) => f.category === 'progression').map(achievementPathItem)],
      ['chat', 'Чат', chat.map(achievementChatItem)],
    ].filter(([id]) => _achievementsV1Filter === 'all' || _achievementsV1Filter === id);
    _achievementsShown = [];
    return groups.map(([id, label, items]) => {
      if (id === 'chat' && !_chatAchievementsData) {
        return `<div class="v3-empty" role="alert"><b>Достижения чата не загрузились</b> <button type="button" class="v3-link" onclick="openAchievementsV1()">Повторить</button></div>`;
      }
      if (!items.length) return _achievementsV1Filter === 'all' ? '' : '<p class="v3-empty">В этой категории пока ничего нет.</p>';
      const rows = items.sort(achievementOrder).map((item) => achievementRow(item, _achievementsShown.push(item) - 1)).join('');
      const head = _achievementsV1Filter === 'all' ? `<div class="v3-sec"><span class="v3-eyebrow">${label}</span></div>` : '';
      return `${head}<div class="ach-list">${rows}</div>`;
    }).join('');
  }

  function achievementTabs() {
    return `<nav class="v3-tabs v3-tabs--wide ach-tabs" role="tablist" aria-label="Категории достижений" onkeydown="achievementsV1TabKey(event)">${ACHIEVEMENT_FILTERS.map(([id, label]) =>
      `<button type="button" id="ach-tab-${id}" class="v3-tab${_achievementsV1Filter === id ? ' on' : ''}" role="tab" data-achievement-filter="${id}" aria-selected="${_achievementsV1Filter === id}" aria-controls="ach-panel" tabindex="${_achievementsV1Filter === id ? 0 : -1}" onclick="achievementsV1Filter('${id}')">${label}</button>`).join('')}</nav>`;
  }

  function renderAchievementsV1() {
    const root = el('pg-achievements-v1');
    if (!root || !_achievementsV1Data) return;
    const summary = _achievementsV1Data.summary || {};
    const chatSummary = _chatAchievementsData?.summary || {};
    const total = Number(summary.total_levels || 0) + Number(chatSummary.total_levels || 0);
    const max = Number(summary.max_levels ?? (_achievementsV1Data.families || []).reduce((n,f)=>n+Number(f.max_level || 40),0)) + Number(chatSummary.max_levels || 0);
    const sub = `${fmt(total)} из ${fmt(max)} уровней · получено ${fmt(summary.claimed_mora || 0)} 🪙`;
    root.innerHTML = `${v3Head('Достижения', { back: 'achievementsV1Back()', sub, end: v3GuideBtn('ach') })}${achievementTabs()}
      <div id="ach-panel" role="tabpanel" aria-labelledby="ach-tab-${_achievementsV1Filter}">${achievementSections()}</div>`;
    v3EnterSync(root);
  }

  function achievementMeter(label, value, target) {
    const done = value >= target;
    return `<div class="ach-meter"><span>${label}</span><b>${fmt(value)}${done ? ' ✓' : ` / ${fmt(target)}`}</b><i class="ach-bar"><i style="width:${achievementPct(value, target)}%"></i></i></div>`;
  }
  function achievementMilestones(family) {
    return (family.milestones || []).map((m) => {
      const mark = m.status === 'claimed' ? '✓' : (m.status === 'reached' ? '•' : '');
      return `<li class="is-${esc(m.status)}"><b>${m.level} ур.</b><small>${fmt(m.events_required)} ${achievementWord(m.events_required, ...(family.measure || ['завершение', 'завершения', 'завершений']))}${m.weeks_required ? ` · ${m.weeks_required} нед.` : ''}</small><span>+${fmt(m.reward_mora)} 🪙 ${mark}</span></li>`;
    }).join('');
  }

  // Лист подробностей: прогресс по обоим условиям, вехи и переход к самой активности
  window.achievementsV1Open = function (index) {
    const item = _achievementsShown[index];
    if (!item) return;
    _haptic('select');
    const title = `${item.icon} ${item.title} · ${item.level}/${item.max}`;
    if (item.chat) {
      const c = item.chat, target = Number(c.next_threshold || 0);
      const reward = c.next_reward ? `<p class="ach-note">На ${c.next_reward.level}-м уровне · +${fmt(c.next_reward.essence)} 🔮</p>` : '';
      OM(title, `<div class="ach-sheet"><p>${esc(c.group_title)} · ${esc(c.measure)}</p>${target ? achievementMeter('До следующего уровня', Number(c.value || 0), target) : '<p class="ach-note">Все уровни пройдены 👑</p>'}${reward}</div>`, [{ l: 'Закрыть', f: 'CM()', c: 'ghost' }]);
      return;
    }
    const f = item.family, t = achievementTargets(f);
    const action = ACHIEVEMENT_ACTIONS[f.id] || "goTo('activities')";
    OM(title, `<div class="ach-sheet"><p>${esc(f.help)}</p>
      ${achievementMeter(f.category === 'progression' ? 'Подтверждено' : 'Завершения', Number(f.completed_events || 0), t.events)}
      ${t.weeks ? achievementMeter('Активные недели', Number(f.active_weeks || 0), t.weeks) : ''}
      <div class="v3-sec"><span class="v3-eyebrow">Вехи · Мора за сам уровень</span></div>
      <ul class="ach-steps">${achievementMilestones(f)}</ul></div>`,
      [{ l: esc(f.action_label || 'К активности'), f: `CM();${action}`, c: 'primary' }]);
  };

  window.achievementsV1Back = function () { if (_navStack.length) navBack(); else switchPage('profile', null, true); };
  window.achievementsV1Filter = function (category) {
    const next = ACHIEVEMENT_FILTERS.some(([id]) => id === category) ? category : 'all';
    if (next === _achievementsV1Filter) return;
    _haptic('select');
    _achievementsV1Filter = next;
    renderAchievementsV1();
  };
  // Стрелки двигают выбор по вкладкам; фокус переносится только при управлении с клавиатуры
  window.achievementsV1TabKey = function (event) {
    const ids = ACHIEVEMENT_FILTERS.map(([id]) => id), at = ids.indexOf(_achievementsV1Filter);
    const to = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: ids.length - 1 }[event.key];
    if (to === undefined) return;
    event.preventDefault();
    window.achievementsV1Filter(ids[(to + ids.length) % ids.length]);
    requestAnimationFrame(() => el('pg-achievements-v1')?.querySelector(`[data-achievement-filter="${_achievementsV1Filter}"]`)?.focus());
  };
  // Хук обновления (app.01.js) зовёт это же при открытом экране: тогда только перечитываем, без switchPage (он прокручивает наверх и уводит фокус)
  let _achievementsSeq = 0;
  window.openAchievementsV1 = async function () {
    if (_activePage !== 'achievements-v1') switchPage('achievements-v1');
    const root = el('pg-achievements-v1');
    if (!_achievementsV1Data) {
      root.innerHTML = `${v3Head('Достижения', { back: 'achievementsV1Back()', end: v3GuideBtn('ach') })}<div class="sk" style="height:44px;border-radius:12px"></div><div class="sk" style="height:320px;border-radius:18px;margin-top:18px"></div>`;
    }
    const mine = ++_achievementsSeq;
    try {
      const [paths, chat] = await Promise.all([
        api('/achievements-v1/reconcile', {method:'POST'}),
        api('/achievements-v1/chat').catch(() => null),
      ]);
      if (mine !== _achievementsSeq) return;
      _achievementsV1Data = paths;
      _chatAchievementsData = chat || _chatAchievementsData;   // разовый сбой чата не стирает уже показанное
      renderAchievementsV1();
    } catch (error) {
      if (mine !== _achievementsSeq) return;
      const text = String(error?.message || error || 'Ошибка').replace(/^Error:\s*/, '');
      if (_achievementsV1Data) { toast(`Достижения не обновились: ${text}`, false); return; }
      root.innerHTML = `${v3Head('Достижения', { back: 'achievementsV1Back()' })}<div class="v3-empty" role="alert">
        <b>Достижения не загрузились</b><span>${esc(text)}</span>
        <button type="button" class="v3-link" onclick="openAchievementsV1()">Повторить</button>
      </div>`;
    }
  };
})();
