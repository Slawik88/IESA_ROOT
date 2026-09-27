// Player-created exchange v1. The entry remains hidden while the server flag is
// off, except for players who already have recoverable exchange state.
let _pxState=null, _pxCoins=[], _pxMarket=null, _pxSide='buy', _pxPendingOrder=null, _pxPendingBid=null;

function syncPlayerExchangeEntry(){
  const entry=el('cc-exchange-v1'); if(!entry)return;
  if(_isFeatureEnabled('economy_player_exchange_v1')){ entry.hidden=false; return; }
  api('/player-exchange/v1/me?limit=1').then(()=>{entry.hidden=false;}).catch(()=>{entry.hidden=true;});
}
function openPlayerExchangeV1(){ switchPage('exchange-v1'); }
function _pxNum(v,scale=1){ if(v===null||v===undefined||v==='')return '—';const n=Number(v)/scale; return Number.isFinite(n)?n.toLocaleString('ru-RU',{maximumFractionDigits:6}):'—'; }
function _pxPrice(v){ return _pxNum(v,1000000); }
function _pxStatus(v){ return ({auction:'Сбор заявок',active:'Торги идут',halted:'Торги остановлены',failed:'Запуск не состоялся',archived:'Закрыта'})[v]||v; }
function _pxEmpty(text){ return `<p class="px-empty">${esc(text)}</p>`; }
function _pxError(message){ const host=el('pg-exchange-v1'); if(host)host.innerHTML=`<section class="px-shell"><button class="px-back" type="button" onclick="navBack()">‹ Назад</button><h1>Биржа недоступна</h1>${_pxEmpty(message)}</section>`; }

function loadPlayerExchangeV1(){
  const host=el('pg-exchange-v1'); if(!host)return;
  host.innerHTML='<section class="px-shell"><div class="loader">Загрузка биржи…</div></section>';
  api('/player-exchange/v1/me?limit=100').then(state=>{
    _pxState=state;
    return api('/player-exchange/v1/coins').then(coins=>{_pxCoins=coins.items||[];}).catch(()=>{_pxCoins=_pxRecoveryCoins(state);});
  }).then(_pxRenderHome).catch(e=>_pxError(String(e)));
}
function _pxRecoveryCoins(state){
  const out=new Map();
  ['holdings','orders','auction_bids','owned_coins'].forEach(key=>(state[key]?.items||[]).forEach(row=>{
    const id=row.coin_id||row.id;if(!id)return;
    const prev=out.get(id)||{};out.set(id,{...prev,...row,id,coin_id:id});
  }));
  return [...out.values()];
}
function _pxRenderHome(){
  const host=el('pg-exchange-v1'); if(!host||!_pxState)return;
  const holdings=_pxState.holdings?.items||[], orders=_pxState.orders?.items||[], bids=_pxState.auction_bids?.items||[], owned=_pxState.owned_coins?.items||[];
  const openOrders=orders.filter(o=>o.status==='open');
  const markets=_pxState.trading_enabled?_pxCoins.map(c=>`<button type="button" class="px-market-row" data-px-coin="${esc(c.id)}"><span><b>${esc(c.ticker)}</b><small>${esc(c.name)}</small></span><span><em>${esc(_pxStatus(c.status))}</em><i>›</i></span></button>`).join(''):'';
  const assets=holdings.map(h=>`<div class="px-asset"><span><b>${esc(h.ticker)}</b><small>${esc(h.name)}</small></span><strong>${_pxNum(h.available_units,1000)}<small>${Number(h.reserved_units)>0?` · ${_pxNum(h.reserved_units,1000)} в заявках`:''}</small></strong></div>`).join('');
  const orderRows=openOrders.map(o=>`<div class="px-order"><span><b>${o.side==='buy'?'Покупка':'Продажа'} ${esc(o.ticker)}</b><small>${_pxNum(o.remaining_units,1000)} по ${_pxPrice(o.limit_price_micromora)} моры</small></span><button type="button" data-px-cancel="${esc(o.id)}">Отменить</button></div>`).join('');
  const bidRows=bids.map(b=>`<div class="px-asset"><span><b>${esc(b.ticker)} · ${b.status==='open'?'Активная заявка':'Завершено'}</b><small>Макс. цена ${_pxPrice(b.max_price_micromora)} моры</small></span><strong>${_pxNum(b.escrow_mora)}<small>моры в резерве</small></strong></div>`).join('');
  const ownedRows=owned.map(c=>`<div class="px-asset"><span><b>${esc(c.ticker)}</b><small>${esc(c.name)}</small></span><strong>${esc(_pxStatus(c.status))}</strong></div>`).join('');
  host.innerHTML=`<section class="px-shell">
    <header class="px-head"><div><small>Игровой рынок</small><h1>Биржа монет</h1></div><button type="button" class="px-refresh" onclick="loadPlayerExchangeV1()" aria-label="Обновить">↻</button></header>
    <aside class="px-risk"><b>Это внутриигровые активы.</b><span>Их нельзя вывести в реальные деньги. Цена может резко вырасти или упасть.</span></aside>
    <div class="px-summary"><span><small>В портфеле</small><b>${holdings.length}</b></span><span><small>Открытых заявок</small><b>${openOrders.length}</b></span><span><small>Своих монет</small><b>${owned.length}</b></span></div>
    ${_pxState.trading_enabled?`<button type="button" class="px-primary" onclick="_pxOpenCreate()">Создать свою монету</button>`:'<p class="px-halt">Новые сделки временно закрыты. Активы и отмена заявок доступны.</p>'}
    <section class="px-flow"><h2>Портфель</h2>${assets||_pxEmpty('Монет пока нет. Купленные активы появятся здесь.')}</section>
    <section class="px-flow"><h2>Открытые заявки</h2>${orderRows||_pxEmpty('Открытых заявок нет.')}${_pxState.orders?.next_cursor?'<button type="button" class="px-link" onclick="_pxLoadMoreOrders()">Показать ещё</button>':''}</section>
    ${bidRows?`<section class="px-flow"><h2>Аукционные заявки</h2>${bidRows}</section>`:''}
    ${ownedRows?`<section class="px-flow"><h2>Ваши монеты</h2>${ownedRows}</section>`:''}
    ${_pxState.trading_enabled?`<section class="px-flow"><h2>Рынки</h2>${markets||_pxEmpty('Доступных монет пока нет.')}</section>`:''}
  </section>`;
  host.querySelectorAll('[data-px-coin]').forEach(b=>b.addEventListener('click',()=>_pxOpenCoin(b.dataset.pxCoin)));
  host.querySelectorAll('[data-px-cancel]').forEach(b=>b.addEventListener('click',()=>_pxCancel(b.dataset.pxCancel,b)));
}
function _pxReload(){ _loaded.delete('exchange-v1'); loadPlayerExchangeV1(); }
function _pxCancel(id,button){
  if(button)button.disabled=true;
  api(`/player-exchange/v1/orders/${encodeURIComponent(id)}/cancel`,{method:'POST'})
    .then(()=>{toast('Заявка отменена. Резерв возвращён.');_pxReload();}).catch(e=>{toast(e,false);if(button)button.disabled=false;});
}
function _pxLoadMoreOrders(){
  const cursor=_pxState?.orders?.next_cursor;if(!cursor)return;
  api('/player-exchange/v1/me?limit=100&orders_cursor='+encodeURIComponent(cursor)).then(next=>{
    const known=new Set((_pxState.orders.items||[]).map(x=>x.id));
    _pxState.orders.items.push(...(next.orders.items||[]).filter(x=>!known.has(x.id)));
    _pxState.orders.next_cursor=next.orders.next_cursor;_pxRenderHome();
  }).catch(e=>toast(e,false));
}
function _pxOpenCreate(){
  OM('Создать монету',`<div class="px-form"><p>Создание стоит <b>2 000 ✨</b>. Ещё 10 000–1 000 000 моры становятся стартовой ликвидностью монеты.</p><label>Название<input id="px-name" maxlength="24" placeholder="Например, Полярная"></label><label>Тикер<input id="px-ticker" maxlength="6" autocapitalize="characters" placeholder="POL"></label><label>Стартовая ликвидность<input id="px-liquidity" type="number" min="10000" max="1000000" step="1" value="10000"></label><small>После подтверждения списание необратимо. Сначала монета проходит 24-часовой аукцион.</small></div>`,[{l:'Отмена',c:'btn-ghost',f:'CM()'},{l:'Создать за 2 000 ✨',c:'btn-gold',f:'_pxCreate()'}]);
}
function _pxCreate(){
  const payload={name:(el('px-name')?.value||'').trim(),ticker:(el('px-ticker')?.value||'').trim().toUpperCase(),initial_mora:Number(el('px-liquidity')?.value||0),action_id:economyRequestKey('coin-create')};
  api('/player-exchange/v1/coins',{method:'POST',body:JSON.stringify(payload)}).then(r=>{CM();toast('Монета создана. Аукцион начался.');_pxReload();setTimeout(()=>_pxOpenCoin(r.coin.id),250);}).catch(e=>toast(e,false));
}
function _pxOpenCoin(id){
  const coin=_pxCoins.find(c=>c.id===id);if(!coin)return;
  if(!_pxState?.trading_enabled){toast('Новые сделки временно закрыты.',false);return;}
  if(coin.status==='auction'){_pxRenderAuction(coin);return;}
  api(`/player-exchange/v1/coins/${encodeURIComponent(id)}/market?levels=12&trades=20`).then(m=>{_pxMarket=m;_pxRenderMarket();}).catch(e=>toast(e,false));
}
function _pxRenderAuction(coin){
  const host=el('pg-exchange-v1');const end=coin.auction_ends_at?new Date(coin.auction_ends_at).toLocaleString('ru-RU'):'—';
  host.innerHTML=`<section class="px-shell"><button class="px-back" type="button" onclick="_pxRenderHome()">‹ Все монеты</button><header class="px-coin-title"><div><small>${esc(coin.ticker)}</small><h1>${esc(coin.name)}</h1></div><span>Аукцион</span></header><p class="px-lead">Игроки называют максимальную цену и резервируют Мору. После ${esc(end)} все победители купят монету по одной итоговой цене.</p><div class="px-form px-inline"><label>Максимум за 1 монету<input id="px-bid-price" inputmode="decimal" placeholder="0,50"></label><label>Сколько Моры зарезервировать<input id="px-bid-escrow" type="number" min="1" step="1" placeholder="1000"></label><button type="button" class="px-primary" onclick="_pxBid('${esc(coin.id)}')">Подать заявку</button></div><aside class="px-risk"><b>Мора будет недоступна до расчёта.</b><span>Неиспользованный остаток вернётся автоматически.</span></aside></section>`;
}
function _pxBid(id){
  const coin=_pxCoins.find(c=>c.id===id)||{},price=(el('px-bid-price')?.value||'').replace(',','.'),escrow=Number(el('px-bid-escrow')?.value||0);
  if(!(Number(price)>0&&escrow>0)){toast('Укажите цену и сумму резерва.',false);return;}
  _pxPendingBid={path:`/player-exchange/v1/coins/${encodeURIComponent(id)}/auction-bids`,payload:{max_price_mora:price,escrow_mora:escrow,action_id:economyRequestKey('coin-bid')}};
  const end=coin.auction_ends_at?new Date(coin.auction_ends_at).toLocaleString('ru-RU'):'конца аукциона';
  OM('Проверьте заявку',`<div class="px-confirm"><b>${esc(coin.ticker||'Монета')} · ${_pxNum(escrow)} моры</b><span>Максимум ${esc(price)} моры за монету</span><small>Мора будет заблокирована до ${esc(end)}. Отменить заявку нельзя; неиспользованный остаток вернётся.</small></div>`,[{l:'Назад',c:'btn-ghost',f:'CM()'},{l:'Зарезервировать',c:'btn-gold',f:'_pxConfirmBid()'}]);
}
function _pxConfirmBid(){
  const pending=_pxPendingBid;if(!pending)return;_pxPendingBid=null;
  api(pending.path,{method:'POST',body:JSON.stringify(pending.payload)}).then(()=>{CM();toast('Заявка принята. Мора зарезервирована.');_pxReload();}).catch(e=>{_pxPendingBid=pending;toast(e,false);});
}
function _pxRenderMarket(){
  const m=_pxMarket,coin=m.coin,stats=m.stats_24h||{},book=m.order_book||{},trades=m.recent_trades||[];const halted=coin.status==='halted'||stats.halt?.active;
  const asks=(book.asks||[]).slice(0,5),bids=(book.bids||[]).slice(0,5);
  const rows=[...asks.reverse().map(x=>({...x,t:'ask'})),...bids.map(x=>({...x,t:'bid'}))].map(x=>`<div class="px-book-row ${x.t}"><span>${_pxPrice(x.price_micromora)}</span><span>${_pxNum(x.units,1000)}</span></div>`).join('');
  const tradeRows=trades.slice(0,8).map(t=>`<div class="px-trade"><span>${_pxPrice(t.price_micromora)}</span><span>${_pxNum(t.units,1000)}</span><time>${new Date(t.created_at).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}</time></div>`).join('');
  const host=el('pg-exchange-v1');host.innerHTML=`<section class="px-shell"><button class="px-back" type="button" onclick="_pxRenderHome()">‹ Все монеты</button><header class="px-coin-title"><div><small>${esc(coin.ticker)} / МОРА</small><h1>${esc(coin.name)}</h1></div><span class="${halted?'is-halted':''}">${halted?'Пауза':_pxPrice(stats.reference_price_micromora||stats.last_price_micromora)}</span></header>${halted?`<p class="px-halt">${esc(stats.halt?.public_reason||'Торги временно остановлены. Открытые заявки можно отменить.')}</p>`:''}<div class="px-market-stats"><span><small>Лучшая покупка</small><b>${_pxPrice(stats.best_bid_micromora)}</b></span><span><small>Лучшая продажа</small><b>${_pxPrice(stats.best_ask_micromora)}</b></span><span><small>Объём 24 ч</small><b>${_pxNum(stats.volume_mora)}</b></span></div><div class="px-segment" role="group" aria-label="Направление сделки"><button type="button" aria-pressed="${_pxSide==='buy'}" onclick="_pxSetSide('buy')">Купить</button><button type="button" aria-pressed="${_pxSide==='sell'}" onclick="_pxSetSide('sell')">Продать</button></div><div class="px-form px-trade-form"><label>Количество ${esc(coin.ticker)}<input id="px-amount" inputmode="decimal" placeholder="10"></label><label>Цена за монету в Море<input id="px-limit" inputmode="decimal" placeholder="0,50"></label><button type="button" class="px-primary ${_pxSide==='sell'?'is-sell':''}" ${halted?'disabled':''} onclick="_pxSubmitOrder('${esc(coin.id)}')">${_pxSide==='buy'?'Купить':'Продать'} ${esc(coin.ticker)}</button><small>Цена фиксирует ваш максимум для покупки или минимум для продажи. Заявка может исполниться частично.</small></div><section class="px-flow"><h2>Стакан</h2><div class="px-book-head"><span>Цена</span><span>Количество</span></div>${rows||_pxEmpty('Заявок пока нет.')}</section><section class="px-flow"><h2>Последние сделки</h2><div class="px-trade-head"><span>Цена</span><span>Количество</span><span>Время</span></div>${tradeRows||_pxEmpty('Сделок пока нет.')}</section><p class="px-disclosure">Игровой актив без вывода в деньги. Доход не гарантирован.</p></section>`;
}
function _pxSetSide(side){_pxSide=side;_pxRenderMarket();}
function _pxSubmitOrder(id){
  const amount=(el('px-amount')?.value||'').replace(',','.');
  if(!(Number(amount)>0)){toast('Укажите количество монет.',false);return;}
  const common={side:_pxSide,amount,action_id:economyRequestKey('coin-order')};
  const path=`/player-exchange/v1/coins/${encodeURIComponent(id)}/orders`;
  const payload={...common,limit_price_mora:(el('px-limit')?.value||'').replace(',','.'),time_in_force:'gtc'};
  const coin=_pxCoins.find(c=>c.id===id)||{};
  const rawPrice=Number(payload.limit_price_mora)*1000000;
  if(!(Number(rawPrice)>0)){toast('Укажите корректную цену.',false);return;}
  const protectedPrice=rawPrice;
  const notional=Number(amount)*protectedPrice/1000000,feeFloor=notional<10?0:Math.max(1,notional*.0025),reserve=notional<10?notional:notional*1.1;
  _pxPendingOrder={path,payload};
  const bound=`Лимит: ${esc(payload.limit_price_mora)} моры`;
  const commitment=_pxSide==='buy'?`В резерв уйдёт не более ${_pxNum(reserve)} моры. Неиспользованное вернётся после сделки или отмены.`:`Оценка минимума к получению: ${_pxNum(Math.max(0,notional-Math.max(feeFloor,notional*.1)))} моры.`;
  OM(`Подтвердите ${_pxSide==='buy'?'покупку':'продажу'}`,`<div class="px-confirm"><b>${esc(amount)} ${esc(coin.ticker||'монет')}</b><span>${bound}</span><span>${commitment}</span><small>Комиссия: maker 0,10%, taker 0,25%; минимум 1 мора для исполнения от 10 моры. Заявка может исполниться частично.</small></div>`,[{l:'Назад',c:'btn-ghost',f:'CM()'},{l:'Подтвердить',c:_pxSide==='sell'?'btn-danger':'btn-gold',f:'_pxConfirmOrder()'}]);
}
function _pxConfirmOrder(){
  const pending=_pxPendingOrder;if(!pending)return;
  _pxPendingOrder=null;
  api(pending.path,{method:'POST',body:JSON.stringify(pending.payload)}).then(()=>{CM();toast('Заявка размещена.');_pxReload();}).catch(e=>{_pxPendingOrder=pending;toast(e,false);});
}
