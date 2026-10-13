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
  });

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

  function activePetActivity(activity) {
    const title = activity.kind === 'trek' ? 'Поход' : 'Экспедиция';
    const needsDecision = activity.status === 'ready'
      && activity.kind === 'expedition'
      && !activity.decision;
    const status = activity.status === 'ready'
      ? (needsDecision ? 'Таймер завершён. Выбери маршрут:' : 'Награда уже получена.')
      : `Питомец занят до ${esc(String(activity.ends_at).replace('T', ' ').slice(0, 16))}.`;
    const routes = needsDecision
      ? `<div class="pet-route-grid">${Object.entries(PET_ROUTE_LABELS).map(([id, label]) => (
        `<button type="button" class="v3-pill v3-pill--ghost" onclick="petsV1Choose('${id}')">${label}</button>`
      )).join('')}</div>`
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
    const hint = _petKind === 'trek' ? 'Спокойная прогулка. По возвращении: 1 🗝.' : 'После таймера выберешь маршрут. По итогу: 1 🗝.';
    const title = _petKind === 'trek' ? 'Поход' : 'Экспедиция';
    const buttons = data.durations.map((hours) => {
      const cost = Number(costs[hours]) || 0;
      const locked = !activePet || endurance < cost;
      const hoursWord = Number(hours) === 3 ? 'часа' : 'часов';
      return `<button type="button" class="pt-go" onclick="petsV1Start('${_petKind}',${hours})" ${locked ? 'disabled' : ''}`
        + ` aria-label="${title} на ${hours} ${hoursWord}, ${cost} выносливости, награда один ключ">`
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
    const icon = pet.owned ? esc(pet.icon) : '?';
    const name = pet.owned ? esc(pet.name) : 'Неизвестный питомец';
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
    const bal = (typeof _v3BarVals !== 'undefined' && _v3BarVals) || null;
    const need = [];
    if (Number(step.cards_have) < Number(step.cards)) need.push(`ещё ${fmt(Number(step.cards) - Number(step.cards_have))} ${Number(step.cards) - Number(step.cards_have) === 1 ? 'карта' : 'карт'}`);
    if (bal && Number(bal.mora) < Number(step.mora)) need.push(`ещё ${fmt(Number(step.mora) - Number(bal.mora))} Моры`);
    if (bal && Number(step.essence) > 0 && Number(bal.essence) < Number(step.essence)) need.push(`ещё ${fmt(Number(step.essence) - Number(bal.essence))} Эссенции`);
    const pct = Math.min(100, Math.round(100 * Number(step.cards_have) / Math.max(1, Number(step.cards))));
    const mark = [5, 10, 15].includes(Number(step.level_after)) ? ` <small class="pt-up-mark">веха</small>` : '';
    return `<section class="pt-sec pt-up" aria-label="Улучшение питомца">
      <h3>Уровень ${Number(pet.level)} → ${Number(step.level_after)}${mark}</h3>
      <ul class="pt-up-cost">
        <li class="${Number(step.cards_have) < Number(step.cards) ? 'is-short' : ''}"><span>🃏 Карты</span><b>${fmt(Number(step.cards_have))} / ${fmt(Number(step.cards))}</b><i style="--p:${pct}"></i></li>
        <li class="${bal && Number(bal.mora) < Number(step.mora) ? 'is-short' : ''}"><span>🪙 Мора</span><b>${fmt(Number(step.mora))}</b></li>
        ${Number(step.essence) > 0 ? `<li class="${bal && Number(bal.essence) < Number(step.essence) ? 'is-short' : ''}"><span>🔮 Эссенция</span><b>${fmt(Number(step.essence))}</b></li>` : ''}
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
      else if (data.activity.pet_id === pet.id) action = activePetActivity(data.activity);
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
  window.petDexOpen = function (id) {
    const data = _petData || {};
    const sp = (data.bestiary || []).find((x) => String(x.id) === String(id));
    if (!sp) return;
    const mine = (data.pets || []).filter((p) => p.species_id === sp.id);
    const root = el('pg-pets');
    root.querySelector('.pt-sheet-wrap')?.remove();
    const stats = mine.length
      ? mine.map((p) => `<li><b>${esc(p.name)}</b><span>${petStage(p)} · ⚡ ${p.endurance}/100</span></li>`).join('')
      : '';
    const body = sp.owned
      ? `<p class="pt-lore">${esc(sp.lore || '')}</p><h4>У тебя</h4><ul class="pt-sheet-list">${stats}</ul>`
        + '<p class="pt-note">Растёт по уровням от 1 до 16, вместе с уровнем меняется облик.</p>'
      : `<p class="pt-lore">Этот питомец ещё не найден. Он может выпасть из сундука: ищи карточки питомцев среди наград.</p>`
        + `<p class="pt-note">Редкость: ${esc(petRarityName(sp.rarity))}.</p>`;
    const wrap = document.createElement('div');
    wrap.className = 'pt-sheet-wrap';
    wrap.innerHTML = `<div class="pt-sheet-bg" onclick="petDexClose()"></div><div class="pt-sheet ${petRarityClass(sp.rarity)}" role="dialog" aria-modal="true" aria-label="${sp.owned ? esc(sp.name) : 'Неизвестный питомец'}">`
      + `<span class="pt-ic" aria-hidden="true">${sp.owned ? esc(sp.icon) : '?'}</span><small>${esc(petRarityName(sp.rarity))}</small><h3>${sp.owned ? esc(sp.name) : 'Неизвестный питомец'}</h3>${body}`
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
    api('/pets-v1/level-up',{method:'POST',body:JSON.stringify({pet_id:petId,action_id:action})}).then(()=>{_petsV1PendingActions.delete(key);toast('Питомец стал сильнее');openPetsV1();}).catch(e=>{toast(`${e} Проверяем актуальное состояние.`,false);openPetsV1();});
  };
  window.petsV1Feed=function(petId,foodId){
    const key=`feed:${petId}:${foodId}`,action=_pendingAction(_petsV1PendingActions,key,'pet-feed-');
    api('/pets-v1/feed',{method:'POST',body:JSON.stringify({pet_id:petId,food_id:foodId,action_id:action})}).then(d=>{_petsV1PendingActions.delete(key);toast(`Выносливость восстановлена до ${d.endurance}/100`);openPetsV1();}).catch(e=>toast(`${e} Повтори: запрос будет отправлен с тем же номером операции.`,false));
  };
  window.petsV1Choose=function(decision){
    const key=`decision:${decision}`,action=_pendingAction(_petsV1PendingActions,key,'pet-decision-');
    api('/pets-v1/expedition/decision',{method:'POST',body:JSON.stringify({decision:decision,action_id:action})}).then(d=>{_petsV1PendingActions.delete(key);toast(d.amount_keys?'Экспедиция завершена · +1 🗝':'Маршрут выбран');openPetsV1();}).catch(e=>{toast(`${e} Проверяем итог маршрута.`,false);openPetsV1();});
  };
  let _chestsV1Data=null,_chestsV1Busy=false,_chestsV1Prepared=null,_chestsV1LastResult=null;
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
  function renderChestsV1(){
    const d=_chestsV1Data,root=el('pg-chests');if(!d||!root)return;
    const odds=(d.star_odds||[]).map(row=>`<li><span>${row.stars}★</span><b>${String(row.percent).replace('.',',')}%</b></li>`).join('');
    const rewards=(d.rewards||[]).map(row=>`<details class="chest-tier"><summary><b>${row.stars}★</b><span>${String(row.star_percent).replace('.',',')}% сундуков</span></summary><ul>${(row.outcomes||[]).map(outcome=>`<li><span><b>${esc(outcome.label)}</b>${chestOddsDetails(outcome)}</span><em>${outcome.conditional_percent}%${chestAmountText(outcome)?` · ${chestAmountText(outcome)}`:''}</em></li>`).join('')}</ul></details>`).join('');
    const paid=d.funding||{},remaining=Math.max(0,Number(paid.remaining_today)||0),price=Number(paid.price_zarniki)||0;
    const inv=d.inventory||{},owned=Object.keys(inv.unlocked_pets||{}).length,cards=Object.values(inv.pet_cards||{}).reduce((a,b)=>a+Number(b||0),0),food=Object.values(inv.foods||{}).reduce((a,b)=>a+Number(b||0),0),jokers=Object.values(inv.jokers||{}).reduce((a,b)=>a+Number(b||0),0);
    const prepared=_chestsV1Prepared?`<section class="chest-reveal-zone"><button type="button" class="chest-orb" onclick="chestsV1Reveal()" ${_chestsV1Busy?'disabled':''} aria-label="Раскрыть подготовленный сундук"><span aria-hidden="true">✦</span><b>${_chestsV1Busy?'Раскрываю…':'Коснись, чтобы раскрыть'}</b><small>Награда уже сохранена сервером</small></button></section>`:'';
    const result=_chestsV1LastResult?`<section class="chest-result" role="status"><span>${'★'.repeat(Math.min(10,Number(_chestsV1LastResult.stars)||1))}</span><b>Получено: ${chestRewardText(_chestsV1LastResult.reward)}</b><small>Доставлено и записано · каталог ${esc(_chestsV1LastResult.catalog_version||'')}</small></section>`:'';
    root.innerHTML=`<header class="looks-head chest-head"><button class="looks-back" onclick="goTo('profile')" aria-label="Назад в профиль">‹</button><div><h1>🗝 Сундуки</h1><small>Одна попытка — одна честно зафиксированная награда</small></div></header><section class="chest-balance"><span>Твои ключи</span><b>${fmt(d.key_balance||0)} 🗝</b><small>Ещё по ключу дают полный день и неделя квестов</small></section><section class="chest-inventory" aria-label="Коллекция из сундуков"><span><b>${owned}/12</b> питомцев</span><span><b>${cards}</b> карт</span><span><b>${food}</b> еды</span><span><b>${jokers}</b> джокеров</span></section>${prepared}${!prepared?result:''}<div class="chest-actions"><button type="button" class="v3-pill chest-open-btn" onclick="chestsV1Prepare()" ${_chestsV1Busy||_chestsV1Prepared||Number(d.key_balance||0)<1?'disabled':''}>${Number(d.key_balance||0)<1?'Сначала получи ключ':'Открыть за 1 ключ'}</button><button type="button" class="chest-buy-btn" onclick="chestsV1AskBuy(this)" ${_chestsV1Busy||_chestsV1Prepared||remaining<1?'disabled':''}><span>Купить ключ</span><b>${price} ✨</b><small>${remaining?`доступно сегодня: ${remaining} из ${paid.daily_limit}`:'лимит на сегодня исчерпан'}</small></button></div><p class="chest-policy">${esc(d.message||'')}</p><details class="chest-odds"><summary>Точные шансы и размеры наград</summary><div><section><h2>Шанс звёздности</h2><ul>${odds}</ul></section><section class="chest-reward-tiers"><h2>Награда внутри звёздности</h2>${rewards}</section></div><p>Сначала сервер выбирает звёздность, затем одну награду по процентам внутри неё. Бесплатные и купленные ключи равны; скорость тапов ничего не меняет.</p></details><div class="chest-canary-note"><b>Карты не пропадут</b><span>${esc(d.surplus_policy||'Лишние карты сохраняются в инвентаре.')}</span></div>`;
  }
  window.openChestsV1=function(){
    switchPage('chests');const root=el('pg-chests');root.innerHTML='<div class="loader" style="margin-top:44px">Загрузка сундуков…</div>';
    api('/chests-v1/me').then(d=>{_chestsV1Data=d;_chestsV1Prepared=d.pending_open||null;_chestsV1LastResult=d.last_result||null;renderChestsV1();}).catch(e=>root.innerHTML=`<div class="v3-err quest-load-error" role="alert"><b>Сундуки не загрузились</b><span>${esc(e)}</span><button type="button" onclick="openChestsV1()">Повторить</button></div>`);
  };
  window.chestsV1Prepare=function(){
    if(_chestsV1Busy||_chestsV1Prepared||!_chestsV1Data)return;_chestsV1Busy=true;renderChestsV1();
    const key='prepare',action=_pendingAction(_chestsV1PendingActions,key,'chest-open-');
    api('/chests-v1/prepare',{method:'POST',body:JSON.stringify({action_id:action,catalog_version:_chestsV1Data.catalog_version,catalog_digest:_chestsV1Data.catalog_digest})}).then(d=>{_chestsV1PendingActions.delete(key);_chestsV1Prepared=d;_chestsV1Data.key_balance=d.key_balance;_chestsV1Busy=false;renderChestsV1();requestAnimationFrame(()=>el('pg-chests')?.querySelector('.chest-orb')?.focus());}).catch(e=>{_chestsV1Busy=false;toast(`${e} Повтори: ключ не спишется второй раз.`,false);openChestsV1();});
  };
  window.chestsV1Buy=function(){
    if(_chestsV1Busy||!_chestsV1Data||Number(_chestsV1Data.funding?.remaining_today||0)<1)return;_chestsV1Busy=true;renderChestsV1();
    const key='purchase',action=_pendingAction(_chestsV1PendingActions,key,'chest-buy-');
    api('/chests-v1/purchase',{method:'POST',body:JSON.stringify({action_id:action,catalog_version:_chestsV1Data.catalog_version,catalog_digest:_chestsV1Data.catalog_digest})}).then(d=>{_chestsV1PendingActions.delete(key);toast(`Ключ куплен за ${fmt(d.price_zarniki)} ✨`);_chestsV1Busy=false;openChestsV1();}).catch(e=>{_chestsV1Busy=false;toast(`${e} Повтори: покупка сохранит тот же номер операции.`,false);openChestsV1();});
  };
  window.chestsV1AskBuy=function(trigger){
    if(_chestsV1Busy||!_chestsV1Data)return;
    const funding=_chestsV1Data.funding||{},price=Number(funding.price_zarniki)||0,remaining=Number(funding.remaining_today)||0;
    if(trigger)trigger.dataset.modalTrigger='true';
    OM('Купить ключ',`<div class="chest-buy-confirm"><b>1 ключ за ${fmt(price)} ✨</b><p>Шансы полностью совпадают с бесплатным ключом. Сегодня после покупки останется ${Math.max(0,remaining-1)} из ${funding.daily_limit||0} покупок.</p><small>Неиспользованный купленный ключ можно вернуть через поддержку.</small></div>`,[{l:`Купить за ${fmt(price)} ✨`,c:'primary',f:'chestsV1Buy();CM()'},{l:'Отмена',c:'ghost',f:'CM()'}]);
  };
  window.chestsV1Reveal=function(){
    if(_chestsV1Busy||!_chestsV1Prepared)return;_chestsV1Busy=true;renderChestsV1();
    api(`/chests-v1/${encodeURIComponent(_chestsV1Prepared.open_id)}/reveal`,{method:'POST'}).then(d=>{_chestsV1Busy=false;_chestsV1Prepared=null;_chestsV1LastResult=d;toast(`${d.stars}★ · ${chestRewardText(d.reward)}`);v3Reward();openChestsV1();}).catch(e=>{_chestsV1Busy=false;toast(e,false);openChestsV1();});
  };
  let _questsV1Data=null,_questsV1Tab='daily',_questsV1Busy=false;
  function questMetricMeta(metric){
    if(metric==='game_completed')return{icon:'◆',label:'Выбрать игру',tone:'game',action:"goTo('arena','game')"};
    if(metric.startsWith('rhythm_'))return{icon:'ᚱ',label:'Открыть Ритм',tone:'rhythm',action:'openRhythmV2Game()'};
    if(metric.startsWith('minesweeper_'))return{icon:'▦',label:'Открыть Сапёр',tone:'mines',action:'openMinesweeperGame()'};
    if(metric.startsWith('mafia_'))return{icon:'◈',label:'Открыть игры',tone:'mafia',action:"goTo('arena','game')"};
    if(metric==='chest_revealed')return{icon:'✦',label:'К сундукам',tone:'chest',action:'openChestsV1()'};
    if(metric==='pet_fed'||metric==='pet_activity_completed')return{icon:'🐾',label:'К питомцам',tone:'pets',action:'openPetsV1()'};
    return{icon:'◆',label:'К играм',tone:'game',action:"goTo('arena','game')"};
  }
  function questCard(quest,period,rerolls){
    const progress=Math.max(0,Number(quest.progress)||0),target=Math.max(1,Number(quest.target)||1);
    const percent=Math.min(100,Math.round(progress/target*100)),meta=questMetricMeta(quest.metric);
    const status=quest.completed?'<span class="quest-status is-done">Готово</span>':`<span class="quest-status">${progress} / ${target}</span>`;
    const reroll=quest.completed?'':`<button class="quest-icon-action" type="button" onclick="questsV1AskReroll('${period}',${quest.slot},this)" aria-label="Заменить квест «${esc(quest.title)}»" ${rerolls.remaining>0&&!_questsV1Busy?'':'disabled'}><span>Сменить</span> ↻</button>`;
    const action=quest.completed?'<span class="quest-complete-note">✓ Задание выполнено</span>':`<button class="quest-route" type="button" onclick="${meta.action}">${meta.label}<span aria-hidden="true">›</span></button>${reroll}`;
    return `<article class="quest-card ${quest.completed?'is-done':''}" data-q="${period}-${quest.slot}"><div class="quest-card-icon quest-tone-${meta.tone}" aria-hidden="true">${meta.icon}</div><div class="quest-card-copy"><div class="quest-card-title"><strong>${esc(quest.title)}</strong>${status}</div><div class="quest-progress" role="progressbar" aria-label="${esc(quest.title)}: ${Math.min(progress,target)} из ${target}" aria-valuemin="0" aria-valuemax="${target}" aria-valuenow="${Math.min(progress,target)}"><i style="width:${percent}%"></i></div><div class="quest-card-meta"><span>${percent}%</span><span>${esc(quest.help)}</span></div><div class="quest-card-actions ${quest.completed?'is-complete':''}">${action}</div></div></article>`;
  }
  function questRewardCard(kind,reward,daily,weekly){
    const label={daily:'За день',weekly:'За неделю',combined:'За всё'}[kind]||kind;
    const target=kind==='daily'?daily:kind==='weekly'?weekly:null;
    const state=reward.claimed?'Получено':reward.claimable?'Готово к выдаче':kind==='combined'?`${daily.done}/${daily.total} за день · ${weekly.done}/${weekly.total} за неделю`:`${target.done}/${target.total} заданий`;
    const destination=kind==='weekly'?'weekly':kind==='combined'&&daily.done===daily.total?'weekly':'daily';
    const button=reward.claimable?`<button class="quest-reward-claim" type="button" onclick="questsV1Claim('${kind}')" ${_questsV1Busy?'disabled':''}>${_questsV1Busy?'Подожди…':'Забрать'}</button>`:(!reward.claimed?`<button class="quest-reward-go" type="button" onclick="questsV1SetTab('${destination}')">К заданиям</button>`:'');
    const keys=_sysFlags.content_chests_v1?Number(reward.amount_keys||0):0,value=`${reward.amount_mora} 🪙${Number(reward.amount_essence)?` + ${reward.amount_essence} Эссенции`:''}${keys?` + ${keys} 🗝`:''}`;
    return `<article class="quest-reward ${button?'has-action ':''}${reward.claimed?'is-claimed':reward.claimable?'is-ready':''}"><span class="quest-reward-mark" aria-hidden="true">${reward.claimed?'✓':keys?'🗝':'🪙'}</span><span><strong>${esc(label)}</strong><small>${esc(state)}</small></span><b>${value}</b>${button}</article>`;
  }
  function questPeriodSummary(period){
    const quests=_questsV1Data?.[period]?.quests||[],done=quests.filter(q=>q.completed).length;
    return {done,total:quests.length,percent:quests.length?Math.round(done/quests.length*100):0};
  }
  function renderQuestsV1(){
    const d=_questsV1Data,root=el('pg-questlog'); if(!d||!root)return;
    const rr=d.rerolls||{remaining:0,limit:0},daily=questPeriodSummary('daily'),weekly=questPeriodSummary('weekly');
    const active=_questsV1Tab==='weekly'?weekly:daily,period=_questsV1Tab==='weekly'?'weekly':'daily';
    const tasks=(d[period]?.quests||[]).map(q=>questCard(q,period,rr)).join('');
    const rewardKinds=['daily','weekly','combined'],rewardItems=d.rewards?.items||{};
    const rewardTotal=rewardKinds.reduce((sum,kind)=>sum+(Number(rewardItems[kind]?.amount_mora)||0),0),rewardEssence=rewardKinds.reduce((sum,kind)=>sum+(Number(rewardItems[kind]?.amount_essence)||0),0);
    const rewards=rewardKinds.map(kind=>questRewardCard(kind,rewardItems[kind]||{amount_mora:0},daily,weekly)).join('');
    const periodReward=Number(rewardItems[period]?.amount_mora)||0,periodEssence=Number(rewardItems[period]?.amount_essence)||0,periodKeys=_sysFlags.content_chests_v1?(Number(rewardItems[period]?.amount_keys)||0):0;
    const keySummary=_sysFlags.content_chests_v1?' + 2 🗝 за день и неделю':'',keyBalance=_sysFlags.content_chests_v1?`<div class="quest-head-stats"><small>У тебя</small><b>${Number(d.rewards?.key_balance)||0} 🗝</b></div>`:'';
    const content=_questsV1Tab==='rewards'?`<section class="quest-panel" id="quest-panel" role="tabpanel" aria-labelledby="quest-tab-rewards"><div class="quest-section-head"><div><span>Три понятные цели</span><h2>${rewardTotal} 🪙${rewardEssence?` + ${rewardEssence} Эссенции`:''}${keySummary}</h2></div>${keyBalance}</div><div class="quest-reward-list">${rewards}</div><p class="quest-policy">${esc(d.rewards?.message||'')}</p></section>`:`<section class="quest-panel" id="quest-panel" role="tabpanel" aria-labelledby="quest-tab-${period}"><div class="quest-section-head"><div><span>${period==='daily'?'Сегодня':'Эта неделя'}</span><h2>${active.done}/${active.total} выполнено → ${periodReward} 🪙${periodEssence?` + ${periodEssence} Эссенции`:''}${periodKeys?` + ${periodKeys} 🗝`:''}</h2></div><div class="quest-head-stats"><b>${active.percent}%</b><small>↻ ${rr.remaining||0}/${rr.limit||0}</small></div></div><div class="quest-list">${tasks||'<div class="quest-empty"><b>Нет доступных заданий</b><span>Как только откроется доступная игра, задания появятся здесь.</span><button onclick="openQuestsV1()">Обновить</button></div>'}</div></section>`;
    const tab=(id,label)=>`<button id="quest-tab-${id}" role="tab" tabindex="${_questsV1Tab===id?'0':'-1'}" aria-selected="${_questsV1Tab===id}" class="${_questsV1Tab===id?'is-active':''}" onclick="questsV1SetTab('${id}')" onkeydown="questsV1TabKey(event)" aria-controls="quest-panel">${label}</button>`;
    root.innerHTML=`<header class="quest-head"><h1 class="v3-title">Задания${v3GlintMark('Задания')}</h1><p class="v3-sub">Цели на день и неделю. За них дают Мору и Эссенцию для образов.</p></header><nav class="quest-tabs" role="tablist" aria-label="Разделы квестов">${tab('daily',`Сегодня <span>${daily.done}/${daily.total}</span>`)}${tab('weekly',`Неделя <span>${weekly.done}/${weekly.total}</span>`)}${tab('rewards','Награды')}</nav>${content}`;
    if(typeof v3QuestsDone==='function')v3QuestsDone(root);
  }
  window.questsV1SetTab=function(tab){if(!['daily','weekly','rewards'].includes(tab))return;_questsV1Tab=tab;renderQuestsV1();scrollTo(0,0);requestAnimationFrame(()=>el('pg-questlog')?.querySelector('.quest-tabs .is-active')?.focus());};
  window.questsV1TabKey=function(event){
    const tabs=['daily','weekly','rewards'],index=tabs.indexOf(_questsV1Tab);let next=null;
    if(event.key==='ArrowRight')next=tabs[(index+1)%tabs.length];
    if(event.key==='ArrowLeft')next=tabs[(index-1+tabs.length)%tabs.length];
    if(event.key==='Home')next=tabs[0]; if(event.key==='End')next=tabs[tabs.length-1];
    if(next){event.preventDefault();questsV1SetTab(next);}
  };
  window.openQuestsV1=function(tab){
    if(['daily','weekly','rewards'].includes(tab))_questsV1Tab=tab;
    switchPage('questlog'); const root=el('pg-questlog'); root.innerHTML='<div class="loader" style="margin-top:44px">Загрузка квестов…</div>';
    api('/quests-v1/me').then(d=>{_questsV1Data=d;renderQuestsV1();}).catch(e=>root.innerHTML=`<div class="v3-err quest-load-error" role="alert"><b>Квесты не загрузились</b><span>${esc(e)}</span><button type="button" onclick="openQuestsV1('${_questsV1Tab}')">Повторить</button></div>`);
  };
  window.questsV1AskReroll=function(period,slot,trigger){
    if(_questsV1Busy){toast('Дождись завершения текущего действия.',false);return;}
    const quest=(_questsV1Data?.[period]?.quests||[]).find(q=>Number(q.slot)===Number(slot));
    if(!quest||quest.completed)return;
    const remaining=Number(_questsV1Data?.rerolls?.remaining)||0;
    if(remaining<=0){toast('Лимит замен на эту неделю исчерпан.',false);return;}
    if(trigger)trigger.dataset.modalTrigger='true';
    OM('↻ Заменить квест',`<div class="quest-reroll-confirm"><b>${esc(quest.title)}</b><p>Сервер подберёт другой тип задания из доступных игр. Вернуть этот вариант нельзя.</p><span>После замены останется: ${remaining-1}</span></div>`,[{l:'Заменить',c:'primary',f:`questsV1Reroll('${period}',${slot});CM()`},{l:'Отмена',c:'ghost',f:'CM()'}]);
  };
  window.questsV1Reroll=function(period,slot){
    if(_questsV1Busy)return;
    _questsV1Busy=true;renderQuestsV1();
    const key=`reroll:${period}:${slot}`,action=_pendingAction(_questsV1PendingActions,key,'quest-reroll-');
    api('/quests-v1/reroll',{method:'POST',body:JSON.stringify({period,slot,action_id:action})}).then(d=>{_questsV1PendingActions.delete(key);_questsV1Data=d;toast('Квест заменён');}).catch(e=>toast(`${e} Повтори: лимит не спишется второй раз.`,false)).finally(()=>{_questsV1Busy=false;renderQuestsV1();});
  };
  window.questsV1Claim=function(kind){
    if(_questsV1Busy)return;
    const box=document.querySelector(`.quest-reward-claim[onclick*="'${kind}'"]`)?.getBoundingClientRect(),origin=box?{x:box.left+box.width/2,y:box.top+box.height/2}:null;   // откуда полетят монеты
    _questsV1Busy=true;renderQuestsV1();
    api('/quests-v1/claim-reward',{method:'POST',body:JSON.stringify({kind})}).then(d=>{
      _questsV1Data=d;if(!d.reward_result?.already_claimed&&Number(d.reward_result?.amount_mora)>0)v3Fly(origin,'mora','🪙');const keys=_sysFlags.content_chests_v1?(Number(d.reward_result?.amount_keys)||0):0;toast(d.reward_result?.already_claimed?'Награда уже получена':`Получено: ${d.reward_result?.amount_mora||0} 🪙${keys?` + ${keys} 🗝`:''}`);
    }).catch(e=>toast(e,false)).finally(()=>{_questsV1Busy=false;renderQuestsV1();});
  };
  let _achievementsV1Data = null;
  let _achievementsV1Filter = 'all';
  const ACHIEVEMENT_FILTERS = Object.freeze(['all', 'games', 'collection']);
  const ACHIEVEMENT_ACTIONS = Object.freeze({
    rhythm: 'openRhythmV2Game()',
    minesweeper: 'openMinesweeperGame()',
    mafia: 'openMafiaStats()',
    chests: 'openChestsV1()',
    pets: 'openPetsV1()',
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

  function achievementProgressCopy(value, target) {
    if (Number(value) >= target) return `${fmt(value)} · цель ${fmt(target)} ✓`;
    return `${fmt(value)} / ${fmt(target)}`;
  }

  function achievementNextCopy(family, eventTarget, weekTarget) {
    if (!family.next) return 'Все 40 уровней пути завершены.';

    const remaining = [];
    const events = Math.max(0, eventTarget - Number(family.completed_events || 0));
    const weeks = Math.max(0, weekTarget - Number(family.active_weeks || 0));
    if (events) {
      remaining.push(`${events} ${achievementWord(events, 'завершение', 'завершения', 'завершений')}`);
    }
    if (weeks) {
      remaining.push(`${weeks} ${achievementWord(weeks, 'активная неделя', 'активные недели', 'активных недель')}`);
    }
    const requirement = remaining.length ? `ещё ${remaining.join(' и ')}` : 'условия выполнены';
    return `До уровня ${family.next.level}: ${requirement}.`;
  }

  function achievementMilestones(family) {
    return (family.milestones || []).map((milestone) => {
      const marker = milestone.status === 'claimed'
        ? '✓'
        : (milestone.status === 'reached' ? '•' : '○');
      const events = achievementWord(
        milestone.events_required,
        'завершение',
        'завершения',
        'завершений',
      );
      return `<li class="achievement-milestone is-${esc(milestone.status)}">
        <span>${marker}</span>
        <b>${milestone.level} ур.</b>
        <small>${fmt(milestone.events_required)} ${events} · ${milestone.weeks_required} нед.</small>
        <em>+${fmt(milestone.reward_mora)} 🪙</em>
      </li>`;
    }).join('');
  }

  function achievementFamilyCard(family) {
    const next = family.next;
    const maxActiveWeeks = Number(_achievementsV1Data?.max_active_weeks) || 156;
    const finalMilestone = (family.milestones || []).find(
      (milestone) => Number(milestone.level) === Number(family.max_level),
    );
    const eventTarget = Number(next?.events_required)
      || Number(finalMilestone?.events_required)
      || 1;
    const weekTarget = Number(next?.weeks_required) || maxActiveWeeks;
    const eventValue = Number(family.completed_events || 0);
    const weekValue = Number(family.active_weeks || 0);
    const category = family.category === 'games' ? 'Игры' : 'Приключения';
    const action = ACHIEVEMENT_ACTIONS[family.id] || "goTo('activities')";
    const nextTitle = next
      ? `Следующий уровень · +${fmt(next.reward_mora)} Моры`
      : 'Путь завершён';

    return `<article class="achievement-card" data-category="${esc(family.category)}">
      <header class="achievement-card-head">
        <span class="achievement-icon" aria-hidden="true">${esc(family.icon)}</span>
        <div><small>${category}</small><h2>${esc(family.title)}</h2><p>${esc(family.help)}</p></div>
        <strong>${family.level}<small>/ ${family.max_level}</small></strong>
      </header>
      <div class="achievement-next">
        <b>${nextTitle}</b>
        <span>${esc(achievementNextCopy(family, eventTarget, weekTarget))}</span>
      </div>
      <div class="achievement-meter">
        <label><span>Завершения</span><b>${achievementProgressCopy(eventValue, eventTarget)}</b></label>
        <div role="progressbar" aria-label="${esc(family.title)}: завершения" aria-valuemin="0" aria-valuemax="${eventTarget}" aria-valuenow="${Math.min(eventValue, eventTarget)}"><i style="width:${achievementPct(eventValue, eventTarget)}%"></i></div>
      </div>
      <div class="achievement-meter">
        <label><span>Активные недели</span><b>${achievementProgressCopy(weekValue, weekTarget)}</b></label>
        <div role="progressbar" aria-label="${esc(family.title)}: активные недели" aria-valuemin="0" aria-valuemax="${weekTarget}" aria-valuenow="${Math.min(weekValue, weekTarget)}"><i style="width:${achievementPct(weekValue, weekTarget)}%"></i></div>
      </div>
      <div class="achievement-card-actions">
        <button type="button" onclick="${action}">${esc(family.action_label || 'К активности')}</button>
        <details>
          <summary aria-label="Вехи: ${esc(family.title)}">Вехи</summary>
          <p>Мора указана за достижение самого уровня.</p>
          <ul>${achievementMilestones(family)}</ul>
        </details>
      </div>
    </article>`;
  }

  function achievementFilterButtons(families) {
    const filters = [
      ['all', 'Все', families.length],
      ['games', 'Игры', families.filter((family) => family.category === 'games').length],
      ['collection', 'Приключения', families.filter((family) => family.category === 'collection').length],
    ];
    return filters.map(([id, label, count]) => (
      `<button type="button" data-achievement-filter="${id}"`
      + ` class="${_achievementsV1Filter === id ? 'is-active' : ''}"`
      + ` aria-pressed="${_achievementsV1Filter === id}"`
      + ` onclick="achievementsV1Filter('${id}')">${label}<span>${count}</span></button>`
    )).join('');
  }

  function renderAchievementsV1() {
    const root = el('pg-achievements-v1');
    if (!root || !_achievementsV1Data) return;

    const families = _achievementsV1Data.families || [];
    const shown = _achievementsV1Filter === 'all'
      ? families
      : families.filter((family) => family.category === _achievementsV1Filter);
    const summary = _achievementsV1Data.summary || {};
    const cards = shown.map(achievementFamilyCard).join('')
      || '<p class="empty">В этой категории пока нет путей.</p>';

    root.innerHTML = `<div class="looks-head achievement-head">
        <button class="looks-back" onclick="goTo('profile')" aria-label="Назад">‹</button>
        <h1 class="looks-htitle">🏅 Достижения</h1>
      </div>
      <section class="achievement-hero">
        <div><span>Общий путь</span><strong>${fmt(summary.total_levels || 0)} <small>/ ${fmt((summary.families || 5) * 40)} уровней</small></strong></div>
        <div><span>Получено за уровни</span><strong>${fmt(summary.claimed_mora || 0)} 🪙</strong></div>
        <p>Засчитываются только подтверждённые завершения. Награда — Мора, без скрытой косметики.</p>
      </section>
      <nav class="achievement-filters" aria-label="Категории достижений">${achievementFilterButtons(families)}</nav>
      <p class="sr-only" role="status" aria-live="polite">Показано путей: ${shown.length}</p>
      <section class="achievement-list">${cards}</section>`;
  }

  window.achievementsV1Filter = function (category) {
    _achievementsV1Filter = ACHIEVEMENT_FILTERS.includes(category) ? category : 'all';
    renderAchievementsV1();
    requestAnimationFrame(() => {
      el('pg-achievements-v1')
        ?.querySelector(`[data-achievement-filter="${_achievementsV1Filter}"]`)
        ?.focus();
    });
  };
  window.openAchievementsV1 = async function () {
    switchPage('achievements-v1');
    const root = el('pg-achievements-v1');
    root.innerHTML = '<div class="loader" style="margin-top:44px">Загрузка достижений…</div>';
    try {
      _achievementsV1Data = await api('/achievements-v1/me');
      _achievementsV1Filter = 'all';
      renderAchievementsV1();
    } catch (error) {
      root.innerHTML = `<div class="v3-err quest-load-error" role="alert">
        <b>Достижения не загрузились</b><span>${esc(error)}</span>
        <button type="button" onclick="openAchievementsV1()">Повторить</button>
      </div>`;
    }
  };
})();
