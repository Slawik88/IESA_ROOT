// Player-created exchange v1. The entry remains hidden while the server flag is
// off, except for players who already have recoverable exchange state.
let _pxState=null, _pxShortState=null, _pxCoins=[], _pxMarket=null, _pxSide='buy', _pxPendingOrder=null, _pxPendingBid=null, _pxPendingEmission=null, _pxPendingTreasury=null, _pxPendingLiquidity=null, _pxPendingCollateral=null, _pxPendingShortAction=null, _pxEmissionCancelActions={}, _pxLiquidityCancelActions={}, _pxOwnerActionIds={}, _pxVestingSubmitting=false;

async function _pxRecoveryRequest(path){
  const response=await fetch(BASE+path,{headers:hdrs()});
  if(response.status===401)return api(path);
  const data=await response.json().catch(()=>({}));
  if(response.status===404&&[
    'Биржа монет пока закрыта для игроков.',
    'Шорты пока закрыты для игроков.'
  ].includes(data.detail))return null;
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Не удалось загрузить финансовое состояние.');
  return data;
}

function syncPlayerExchangeEntry(){
  const entry=el('cc-exchange-v1'); if(!entry)return;
  if(_isFeatureEnabled('economy_player_exchange_v1')){ entry.hidden=false; return; }
  Promise.all([
    _pxRecoveryRequest('/player-exchange/v1/me?limit=1'),
    _pxRecoveryRequest('/player-exchange/v1/shorts/me?limit=1')
  ]).then(([spot,shorts])=>{entry.hidden=!(spot||shorts);}).catch(()=>{
    entry.hidden=false;entry.title='Состояние биржи временно недоступно. Откройте для повторной проверки.';
  });
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
  Promise.all([
    _pxRecoveryRequest('/player-exchange/v1/me?limit=100'),
    _pxRecoveryRequest('/player-exchange/v1/shorts/me?limit=100')
  ]).then(([state,shortState])=>{
    if(!state&&!shortState)throw new Error('Биржа пока закрыта для игроков.');
    _pxState=state||{holdings:{items:[]},orders:{items:[]},auction_bids:{items:[]},owned_coins:{items:[]},trading_enabled:false};
    _pxShortState=shortState;
    if(!_pxState.trading_enabled){_pxCoins=_pxRecoveryCoins(_pxState);return;}
    return api('/player-exchange/v1/coins').then(coins=>{_pxCoins=coins.items||[];});
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
function _pxShortRecoveryBlock(){
  const s=_pxShortState;if(!s)return '';
  const lending=(s.lending?.items||[]).map(x=>`<div class="px-asset"><span><b>${esc(x.ticker)}</b><small>${esc(x.name)}</small></span><strong>${_pxNum(x.available_units,1000)} свободно<small>${_pxNum(x.loaned_units,1000)} в займе · ${_pxNum(x.frozen_units,1000)} временно заблокировано</small></strong>${Number(x.available_units)>0?`<button type="button" data-px-short-withdraw="${esc(x.coin_id)}">Забрать свободные</button>`:''}</div>`).join('');
  const positions=(s.positions?.items||[]).map(x=>`<div class="px-asset"><span><b>${esc(x.ticker)} · ${x.status==='open'||x.status==='closing'?'Открытый шорт':x.status==='frozen'?'Долг заморожен':'Закрытый шорт'}</b><small>Долг: ${_pxNum(x.outstanding_debt_units,1000)} монет · ставка ${_pxNum(Number(x.open_apr_bps||0)/100)}% годовых</small></span><strong>${_pxNum(x.cash_escrow_mora)} моры<small>заблокировано в позиции</small></strong>${x.status==='open'?`<button type="button" data-px-short-topup="${esc(x.id)}">Добавить залог</button><button type="button" data-px-short-reduce="${esc(x.id)}">Уменьшить</button><button type="button" data-px-short-close="${esc(x.id)}">Закрыть</button>`:''}</div>`).join('');
  const principal=(s.principal_claims?.items||[]).map(x=>`<div class="px-asset"><span><b>${esc(x.ticker)} · возврат монет</b><small>${x.status==='open'?'Ожидает резерв':'Возвращено'}</small></span><strong>${_pxNum(x.remaining_units,1000)}<small>из ${_pxNum(x.principal_units,1000)} монет</small></strong></div>`).join('');
  const interest=(s.interest_claims?.items||[]).map(x=>`<div class="px-asset"><span><b>${esc(x.ticker)} · проценты</b><small>${x.status==='open'?'Ожидают резерв':'Выплачены'}</small></span><strong>${_pxNum(x.remaining_mora)}<small>из ${_pxNum(x.principal_mora)} моры</small></strong></div>`).join('');
  const more=[['lending','lending_cursor'],['positions','positions_cursor'],['principal_claims','principal_cursor'],['interest_claims','interest_cursor']].map(([kind])=>s[kind]?.next_cursor?`<button type="button" class="px-link" data-px-short-more="${kind}">Показать ещё</button>`:'');
  return `<section class="px-flow"><h2>Займы и шорты</h2><p class="px-disclosure">${esc(s.notice||'Монеты в займе могут быть временно заблокированы.')}</p>${s.shorts_enabled?'':'<p class="px-halt">Новые операции Shorts закрыты. Ваши позиции и требования остаются видны.</p>'}<h3>Пул займа</h3>${lending||_pxEmpty('Монет в пуле нет.')}${more[0]}<h3>Позиции</h3>${positions||_pxEmpty('Позиций нет.')}${more[1]}<h3>Возврат монет</h3>${principal||_pxEmpty('Требований нет.')}${more[2]}<h3>Проценты</h3>${interest||_pxEmpty('Требований нет.')}${more[3]}</section>`;
}
function _pxLoadMoreShorts(kind){
  const cursors={lending:'lending_cursor',positions:'positions_cursor',principal_claims:'principal_cursor',interest_claims:'interest_cursor'};
  const param=cursors[kind],cursor=param&&_pxShortState?.[kind]?.next_cursor;if(!cursor)return;
  api('/player-exchange/v1/shorts/me?limit=100&'+param+'='+encodeURIComponent(cursor)).then(next=>{
    const current=_pxShortState[kind],known=new Set(current.items.map(x=>x.id||x.coin_id));
    current.items.push(...(next[kind].items||[]).filter(x=>!known.has(x.id||x.coin_id)));
    current.next_cursor=next[kind].next_cursor;_pxRenderHome();
  }).catch(e=>toast(e,false));
}
function _pxOpenShortTopup(positionId){
  const position=(_pxShortState?.positions?.items||[]).find(x=>x.id===positionId);if(!position||position.status!=='open')return;
  OM('Добавить залог',`<div class="px-form"><p>${esc(position.ticker)} · сейчас заблокировано ${_pxNum(position.cash_escrow_mora)} моры.</p><label>Дополнительный залог в Море<input id="px-short-collateral" inputmode="decimal" placeholder="100"></label><small>Мора перейдёт из кошелька в позицию. Пополнение доступно и во время остановки торгов.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Проверить',c:'primary',f:`_pxReviewShortTopup('${esc(positionId)}')`}]);
}
function _pxReviewShortTopup(positionId){
  const amount=(el('px-short-collateral')?.value||'').replace(',','.');if(!(Number(amount)>=1)){toast('Укажите не меньше 1 моры.',false);return;}
  _pxPendingCollateral={positionId,amount,action_id:economyRequestKey('short-collateral')};
  OM('Подтвердите залог',`<div class="px-confirm"><b>+${esc(amount)} моры в шорт</b><span>Средства будут заблокированы в позиции.</span><small>При штатном закрытии неиспользованный остаток вернётся в кошелёк. Пополнение необратимо до закрытия позиции.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Добавить',c:'primary',f:'_pxConfirmShortTopup()'}]);
}
function _pxConfirmShortTopup(){
  const pending=_pxPendingCollateral;if(!pending)return;_pxPendingCollateral=null;
  api(`/player-exchange/v1/shorts/positions/${encodeURIComponent(pending.positionId)}/collateral`,{method:'POST',body:JSON.stringify({amount_mora:pending.amount,action_id:pending.action_id})})
    .then(()=>{CM();toast('Залог добавлен.');_pxReload();}).catch(e=>{_pxPendingCollateral=pending;toast(e,false);});
}
function _pxOpenShortWithdraw(coinId){
  const row=(_pxShortState?.lending?.items||[]).find(x=>x.coin_id===coinId);if(!row||Number(row.available_units)<=0)return;
  OM('Забрать монеты из пула',`<div class="px-form"><p>${esc(row.ticker)} · свободно ${_pxNum(row.available_units,1000)} монет.</p><label>Количество<input id="px-short-withdraw" inputmode="decimal" placeholder="1"></label><small>Монеты, выданные в заём или ожидающие возврата из резерва, вывести нельзя.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Проверить',c:'primary',f:`_pxReviewShortWithdraw('${esc(coinId)}')`}]);
}
function _pxReviewShortWithdraw(coinId){
  const amount=(el('px-short-withdraw')?.value||'').replace(',','.'),row=(_pxShortState?.lending?.items||[]).find(x=>x.coin_id===coinId);
  if(!(Number(amount)>0&&Number(amount)*1000<=Number(row?.available_units||0))){toast('Укажите количество свободных монет.',false);return;}
  _pxPendingShortAction={kind:'withdraw',coinId,amount,action_id:economyRequestKey('short-lending-withdraw')};
  OM('Подтвердите вывод',`<div class="px-confirm"><b>${esc(amount)} ${esc(row.ticker)}</b><span>Свободные монеты вернутся на ваш биржевой баланс.</span><small>Выданные в заём и frozen-claim останутся в пуле до расчёта.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Забрать',c:'primary',f:'_pxConfirmShortAction()'}]);
}
function _pxOpenShortClose(positionId,partial){
  const row=(_pxShortState?.positions?.items||[]).find(x=>x.id===positionId);if(!row||row.status!=='open')return;
  if(!partial){_pxReviewShortClose(positionId,null);return;}
  OM('Уменьшить шорт',`<div class="px-form"><p>${esc(row.ticker)} · долг ${_pxNum(row.outstanding_debt_units,1000)} монет.</p><label>Сколько монет выкупить<input id="px-short-reduce" inputmode="decimal" placeholder="1"></label><small>Сначала покажем оценку по допустимым заявкам. Исполнение проверяется повторно.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Рассчитать',c:'primary',f:`_pxReviewShortClose('${esc(positionId)}','partial')`}]);
}
function _pxReviewShortClose(positionId,kind){
  const row=(_pxShortState?.positions?.items||[]).find(x=>x.id===positionId),amount=kind==='partial'?(el('px-short-reduce')?.value||'').replace(',','.'):null;
  if(!row||(kind==='partial'&&!(Number(amount)>0&&Number(amount)*1000<Number(row.outstanding_debt_units)))){toast('Укажите часть долга меньше полного объёма.',false);return;}
  const query=amount?'?amount='+encodeURIComponent(amount):'';
  api(`/player-exchange/v1/shorts/positions/${encodeURIComponent(positionId)}/close-quote${query}`).then(q=>{
    if(!q.available){toast(q.reason||'Выкуп сейчас недоступен.',false);return;}
    _pxPendingShortAction={kind:amount?'reduce':'close',positionId,amount,action_id:economyRequestKey('short-close'),max_buyback_price_micromora:q.max_price_micromora,max_escrow_debit_mora:q.estimated_escrow_debit_mora};
    OM(amount?'Подтвердите уменьшение':'Подтвердите закрытие',`<div class="px-confirm"><b>${_pxNum(q.units,1000)} ${esc(row.ticker)}</b><span>Предел списания из позиции: ${_pxNum(q.estimated_escrow_debit_mora)} моры, включая до ${_pxNum(q.estimated_fee_mora)} комиссии и начисленные проценты</span><span>Сейчас в позиции: ${_pxNum(q.cash_escrow_mora)} моры</span><span>Максимальная цена выкупа: ${_pxPrice(q.max_price_micromora)} моры</span><small>Если цена или полный расход превысят подтверждённый предел, операция отменится. ${esc(q.notice)}</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:amount?'Уменьшить':'Закрыть',c:'primary',f:'_pxConfirmShortAction()'}]);
  }).catch(e=>toast(e,false));
}
function _pxConfirmShortAction(){
  const p=_pxPendingShortAction;if(!p)return;_pxPendingShortAction=null;
  const path=p.kind==='withdraw'||p.kind==='deposit'?`/player-exchange/v1/shorts/coins/${encodeURIComponent(p.coinId)}/lending/${p.kind}`:p.kind==='open'?`/player-exchange/v1/shorts/coins/${encodeURIComponent(p.coinId)}/positions`:`/player-exchange/v1/shorts/positions/${encodeURIComponent(p.positionId)}/${p.kind}`;
  const payload={action_id:p.action_id};if(p.amount)payload.amount=p.amount;
  if(p.kind==='open'){payload.max_collateral_mora=p.max_collateral_mora;payload.min_sale_price_micromora=p.min_sale_price_micromora;payload.max_apr_bps=p.max_apr_bps;}
  if(p.kind==='reduce'||p.kind==='close'){payload.max_buyback_price_micromora=p.max_buyback_price_micromora;payload.max_escrow_debit_mora=p.max_escrow_debit_mora;}
  api(path,{method:'POST',body:JSON.stringify(payload)}).then(result=>{CM();toast(p.kind==='liquidate'?(result.decision==='short_liquidated'?'Шорт ликвидирован.':result.decision==='short_frozen'?'Долг переведён в защищённые требования.':'Риск больше не требует ликвидации.'):'Операция выполнена.');_pxReload();}).catch(e=>{_pxPendingShortAction=p;toast(e,false);});
}
function _pxShortTradingBlock(coin){
  if(!_pxShortState?.shorts_enabled)return '';
  return `<section class="px-flow"><h2>Займы и шорты</h2><p class="px-disclosure">Монеты можно добровольно передать в пул. Занятую долю нельзя вывести до возврата. Для шорта нужен залог Моры; долг и проценты могут превысить выручку. При дефиците возврат кредитору не имеет гарантированной даты.</p><div class="px-owner-grid"><button type="button" onclick="_pxOpenShortDeposit('${esc(coin.id)}')">Передать в пул</button><button type="button" onclick="_pxOpenShortPosition('${esc(coin.id)}')">Открыть шорт</button><button type="button" onclick="_pxShowShortLiquidations('${esc(coin.id)}')">Проверить ликвидации</button></div><small>Шорт доступен только после 7 дней торгов, 100 сделок, 20 участников, недельного объёма 50 000 моры и достаточной глубины стакана.</small></section>`;
}
function _pxShowShortLiquidations(coinId){
  api(`/player-exchange/v1/shorts/coins/${encodeURIComponent(coinId)}/liquidations`).then(data=>{
    const items=data.items||[];
    const rows=items.map(row=>`<div class="px-order"><span><b>${esc(row.ticker)} · риск ${_pxNum(Number(row.marked_margin_bps)/100)}%</b><small>Оценка от ${new Date(row.marked_at).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}; сервер проверит риск заново.</small></span><button type="button" onclick="_pxReviewShortLiquidation('${esc(row.position_id)}')">Проверить</button></div>`).join('');
    OM('Риск шортов',`<div class="px-form">${rows||_pxEmpty('Позиций для ликвидации сейчас нет.')}<small>За исполнение положена доля штрафа до 5% залога. Награда зависит от оставшихся средств позиции; при заморозке долга выплаты может не быть.</small></div>`,[{l:'Закрыть',c:'ghost',f:'CM()'}]);
  }).catch(e=>toast(e,false));
}
function _pxReviewShortLiquidation(positionId){
  _pxPendingShortAction={kind:'liquidate',positionId,action_id:economyRequestKey('short-liquidation')};
  OM('Подтвердите ликвидацию',`<div class="px-confirm"><b>Проверить и исполнить рискованный шорт</b><span>Сервер заново проверит рынок, стакан и размер долга. Если риск уже снят, сделки не будет.</span><small>Залог и Мора исполнителя не расходуются. При исполнении вознаграждение поступит в кошелёк; при заморозке долга его может не быть.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Исполнить',c:'primary',f:'_pxConfirmShortAction()'}]);
}
function _pxOpenShortDeposit(coinId){
  const coin=_pxMarket?.coin;if(!coin||coin.id!==coinId)return;
  OM('Передать монеты в пул',`<div class="px-form"><p>${esc(coin.ticker)} · монеты из вашего свободного биржевого остатка станут доступны для займа.</p><label>Количество<input id="px-short-deposit" inputmode="decimal" placeholder="1"></label><small>Свободную долю можно забрать. Выданная в заём и frozen-доля будут заблокированы до возврата; дата возврата не гарантирована.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Проверить',c:'primary',f:`_pxReviewShortDeposit('${esc(coinId)}')`}]);
}
function _pxReviewShortDeposit(coinId){
  const coin=_pxMarket?.coin,amount=(el('px-short-deposit')?.value||'').replace(',','.');if(!coin||!(Number(amount)>0)){toast('Укажите количество монет.',false);return;}
  _pxPendingShortAction={kind:'deposit',coinId,amount,action_id:economyRequestKey('short-lending-deposit')};
  OM('Подтвердите передачу',`<div class="px-confirm"><b>${esc(amount)} ${esc(coin.ticker)} в пул займа</b><span>Свободную долю можно вывести; занятую и frozen-долю — только после возврата.</span><small>Монеты не списываются, но срок возврата занятой доли не гарантирован.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Передать',c:'primary',f:'_pxConfirmShortAction()'}]);
}
function _pxOpenShortPosition(coinId){
  const coin=_pxMarket?.coin;if(!coin||coin.id!==coinId)return;
  OM('Открыть шорт',`<div class="px-form"><p>${esc(coin.ticker)} · заёмные монеты будут проданы целиком одной атомарной операцией.</p><label>Количество для займа<input id="px-short-open" inputmode="decimal" placeholder="1"></label><small>Сначала покажем расчёт залога, ставки и допустимых цен. Выручка от продажи остаётся заблокированной.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Рассчитать',c:'primary',f:`_pxReviewShortOpen('${esc(coinId)}')`}]);
}
function _pxReviewShortOpen(coinId){
  const coin=_pxMarket?.coin,amount=(el('px-short-open')?.value||'').replace(',','.');if(!coin||!(Number(amount)>0)){toast('Укажите количество монет.',false);return;}
  api(`/player-exchange/v1/shorts/coins/${encodeURIComponent(coinId)}/open-quote?amount=${encodeURIComponent(amount)}`).then(q=>{
    _pxPendingShortAction={kind:'open',coinId,amount,action_id:economyRequestKey('short-open'),max_collateral_mora:q.collateral_mora,min_sale_price_micromora:q.sale_limit_price_micromora,max_apr_bps:q.open_apr_bps};
    OM('Подтвердите шорт',`<div class="px-confirm"><b>${esc(amount)} ${esc(coin.ticker)} · максимальный залог ${_pxNum(q.collateral_mora)} моры</b><span>Оценка долга: ${_pxPrice(q.mark_price_micromora)} моры за монету · ставка не выше ${_pxNum(Number(q.open_apr_bps)/100)}% годовых</span><span>Продажа не дешевле ${_pxPrice(q.sale_limit_price_micromora)} моры; текущая цена выкупа ${_pxPrice(q.buyback_limit_price_micromora)} моры</span><small>При изменении пределов операция отменится. Залог и выручка заблокируются; возможна ликвидация и потеря залога. ${esc(q.notice)}</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Открыть',c:'btn-danger',f:'_pxConfirmShortAction()'}]);
  }).catch(e=>toast(e,false));
}
function _pxRenderHome(){
  const host=el('pg-exchange-v1'); if(!host||!_pxState)return;
  const holdings=_pxState.holdings?.items||[], orders=_pxState.orders?.items||[], bids=_pxState.auction_bids?.items||[], owned=_pxState.owned_coins?.items||[];
  const openOrders=orders.filter(o=>o.status==='open');
  const markets=_pxState.trading_enabled?_pxCoins.map(c=>`<button type="button" class="px-market-row" data-px-coin="${esc(c.id)}"><span><b>${esc(c.ticker)}</b><small>${esc(c.name)}</small></span><span><em>${esc(_pxStatus(c.status))}</em><i>›</i></span></button>`).join(''):'';
  const assets=holdings.map(h=>`<div class="px-asset"><span><b>${esc(h.ticker)}</b><small>${esc(h.name)}</small></span><strong>${_pxNum(h.available_units,1000)}<small>${Number(h.reserved_units)>0?` · ${_pxNum(h.reserved_units,1000)} в заявках`:''}</small></strong></div>`).join('');
  const orderRows=openOrders.map(o=>{const emissionLocked=o.actor_kind==='treasury'&&o.side==='buy'&&owned.some(c=>c.coin_id===o.coin_id&&c.pending_emission_id);return `<div class="px-order"><span><b>${o.actor_kind==='treasury'?'Казна · ':''}${o.side==='buy'?'Покупка':'Продажа'} ${esc(o.ticker)}</b><small>${_pxNum(o.remaining_units,1000)} по ${_pxPrice(o.limit_price_micromora)} моры</small></span><button type="button" ${emissionLocked?'disabled':''} ${o.actor_kind==='treasury'?`data-px-treasury-cancel="${esc(o.id)}" data-px-treasury-coin="${esc(o.coin_id)}"`:`data-px-cancel="${esc(o.id)}"`}>${emissionLocked?'Защищает эмиссию':'Отменить'}</button></div>`;}).join('');
  const bidRows=bids.map(b=>`<div class="px-asset"><span><b>${esc(b.ticker)} · ${b.status==='open'?'Активная заявка':'Завершено'}</b><small>Макс. цена ${_pxPrice(b.max_price_micromora)} моры</small></span><strong>${_pxNum(b.escrow_mora)}<small>моры в резерве</small></strong></div>`).join('');
  const ownedRows=owned.map(c=>{const cancelOpen=c.emission_can_cancel===true,liquidityCancelOpen=c.liquidity_withdrawal_can_cancel===true;return `<div class="px-asset px-owned"><span><b>${esc(c.ticker)}</b><small>${esc(c.name)}</small>${c.pending_emission_id?`<small>Эмиссия +${_pxNum(c.pending_emission_units,1000)} · ${new Date(c.emission_executes_at).toLocaleString('ru-RU')}</small>`:''}${c.pending_liquidity_withdrawal_id?`<small>Вывод ${_pxNum(c.pending_liquidity_withdrawal_mora)} моры · ${new Date(c.liquidity_withdrawal_executes_at).toLocaleString('ru-RU')}</small>`:''}</span><strong>${esc(_pxStatus(c.status))}</strong>${c.pending_emission_id?`<button type="button" ${cancelOpen?'':'disabled'} data-px-emission-cancel="${esc(c.pending_emission_id)}" data-px-emission-coin="${esc(c.coin_id)}">${cancelOpen?'Отменить эмиссию':'Отмена закрыта'}</button>`:''}${c.pending_liquidity_withdrawal_id?`<button type="button" ${liquidityCancelOpen?'':'disabled'} data-px-liquidity-cancel="${esc(c.pending_liquidity_withdrawal_id)}" data-px-liquidity-coin="${esc(c.coin_id)}">${liquidityCancelOpen?'Отменить вывод ликвидности':'Вывод уже исполнен'}</button>`:''}</div>`;}).join('');
  host.innerHTML=`<section class="px-shell">
    <header class="px-head"><div><small>Игровой рынок</small><h1>Биржа монет</h1></div><button type="button" class="px-refresh" onclick="loadPlayerExchangeV1()" aria-label="Обновить">↻</button></header>
    <aside class="px-risk"><b>Это внутриигровые активы.</b><span>Их нельзя вывести в реальные деньги. Цена может резко вырасти или упасть.</span></aside>
    <div class="px-summary"><span><small>В портфеле</small><b>${holdings.length}</b></span><span><small>Открытых заявок</small><b>${openOrders.length}</b></span><span><small>Своих монет</small><b>${owned.length}</b></span></div>
    ${_pxState.trading_enabled?`<button type="button" class="px-primary" onclick="_pxOpenCreate()">Создать свою монету</button>`:'<p class="px-halt">Новые сделки временно закрыты. Активы и отмена заявок доступны.</p>'}
    <section class="px-flow"><h2>Портфель</h2>${assets||_pxEmpty('Монет пока нет. Купленные активы появятся здесь.')}</section>
    <section class="px-flow"><h2>Открытые заявки</h2>${orderRows||_pxEmpty('Открытых заявок нет.')}${_pxState.orders?.next_cursor?'<button type="button" class="px-link" onclick="_pxLoadMoreOrders()">Показать ещё</button>':''}</section>
    ${bidRows?`<section class="px-flow"><h2>Аукционные заявки</h2>${bidRows}</section>`:''}
    ${ownedRows?`<section class="px-flow"><h2>Ваши монеты</h2>${ownedRows}</section>`:''}
    ${_pxShortRecoveryBlock()}
    ${_pxState.trading_enabled?`<section class="px-flow"><h2>Рынки</h2>${markets||_pxEmpty('Доступных монет пока нет.')}</section>`:''}
  </section>`;
  host.querySelectorAll('[data-px-coin]').forEach(b=>b.addEventListener('click',()=>_pxOpenCoin(b.dataset.pxCoin)));
  host.querySelectorAll('[data-px-cancel]').forEach(b=>b.addEventListener('click',()=>_pxCancel(b.dataset.pxCancel,b)));
  host.querySelectorAll('[data-px-treasury-cancel]').forEach(b=>b.addEventListener('click',()=>_pxCancelTreasury(b.dataset.pxTreasuryCancel,b.dataset.pxTreasuryCoin)));
  host.querySelectorAll('[data-px-emission-cancel]').forEach(b=>b.addEventListener('click',()=>_pxCancelEmission(b.dataset.pxEmissionCancel,b.dataset.pxEmissionCoin)));
  host.querySelectorAll('[data-px-liquidity-cancel]').forEach(b=>b.addEventListener('click',()=>_pxCancelLiquidityWithdrawal(b.dataset.pxLiquidityCancel,b.dataset.pxLiquidityCoin)));
  host.querySelectorAll('[data-px-short-more]').forEach(b=>b.addEventListener('click',()=>_pxLoadMoreShorts(b.dataset.pxShortMore)));
  host.querySelectorAll('[data-px-short-topup]').forEach(b=>b.addEventListener('click',()=>_pxOpenShortTopup(b.dataset.pxShortTopup)));
  host.querySelectorAll('[data-px-short-withdraw]').forEach(b=>b.addEventListener('click',()=>_pxOpenShortWithdraw(b.dataset.pxShortWithdraw)));
  host.querySelectorAll('[data-px-short-reduce]').forEach(b=>b.addEventListener('click',()=>_pxOpenShortClose(b.dataset.pxShortReduce,true)));
  host.querySelectorAll('[data-px-short-close]').forEach(b=>b.addEventListener('click',()=>_pxOpenShortClose(b.dataset.pxShortClose,false)));
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
  OM('Создать монету',`<div class="px-form"><p>Создание стоит <b>2 000 ✨</b>. Ещё 10 000–1 000 000 моры становятся стартовой ликвидностью монеты.</p><label>Название<input id="px-name" maxlength="24" placeholder="Например, Полярная"></label><label>Тикер<input id="px-ticker" maxlength="6" autocapitalize="characters" placeholder="POL"></label><label>Стартовая ликвидность<input id="px-liquidity" type="number" min="10000" max="1000000" step="1" value="10000"></label><small>После подтверждения списание необратимо. Сначала монета проходит 24-часовой аукцион.</small></div>`,[{l:'Отмена',c:'ghost',f:'CM()'},{l:'Создать за 2 000 ✨',c:'primary',f:'_pxCreate()'}]);
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
  OM('Проверьте заявку',`<div class="px-confirm"><b>${esc(coin.ticker||'Монета')} · ${_pxNum(escrow)} моры</b><span>Максимум ${esc(price)} моры за монету</span><small>Мора будет заблокирована до ${esc(end)}. Отменить заявку нельзя; неиспользованный остаток вернётся.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Зарезервировать',c:'primary',f:'_pxConfirmBid()'}]);
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
  const isOwner=(_pxState?.owned_coins?.items||[]).some(x=>(x.coin_id||x.id)===coin.id);
  const emissions=(m.emissions||[]).map(e=>{const pct=Number(e.requested_units)*100/Number(e.circulation_snapshot_units||1),cancelOpen=e.can_cancel===true,eventLabel=e.status==='pending'?'Запланировано':e.status==='executed'?'Исполнено':'Отменено',eventAt=e.status==='executed'?e.executed_at:e.status==='cancelled'?e.cancelled_at:e.executes_at;return `<div class="px-emission"><span><b>+${_pxNum(e.requested_units,1000)} ${esc(coin.ticker)} · ${_pxNum(pct)}%</b><small>${esc(e.reason)}</small><small>База: ${_pxNum(e.circulation_snapshot_units,1000)} · запрос ${new Date(e.requested_at).toLocaleString('ru-RU')}</small></span><strong>${e.status==='pending'?'Ожидает':e.status==='executed'?'Исполнена':'Отменена'}<small>${eventLabel}: ${eventAt?new Date(eventAt).toLocaleString('ru-RU'):'—'}</small><small>Новый объём: ${_pxNum(e.projected_total_supply_units,1000)}</small></strong>${isOwner&&e.status==='pending'?`<button type="button" ${cancelOpen?'':'disabled'} onclick="_pxCancelEmission('${esc(e.id)}','${esc(coin.id)}')">${cancelOpen?'Отменить':'Отмена закрыта'}</button>`:''}</div>`;}).join('');
  const vesting=m.owner_vesting,claimable=Number(vesting?.claimable_units||0),vestingBlock=vesting?`<section class="px-flow"><h2>Доля владельца</h2><div class="px-vesting"><span><b>${_pxNum(vesting.claimed_units,1000)} получено</b><small>${_pxNum(vesting.locked_units,1000)} ещё заблокировано</small><small>30 дней блокировки, затем выдача частями за 180 дней</small></span>${isOwner?`<button type="button" ${claimable>0?'':'disabled'} onclick="_pxOpenVestingClaim('${esc(coin.id)}')">${claimable>0?`Получить ${_pxNum(claimable,1000)}`:'Пока недоступно'}</button>`:''}</div></section>`:'';
  const hasPendingEmission=(m.emissions||[]).some(e=>e.status==='pending'),treasury=m.treasury||{},treasuryOrders=(m.treasury_orders||[]).filter(o=>o.status==='open').map(o=>{const locked=hasPendingEmission&&o.side==='buy';return `<div class="px-order"><span><b>${o.side==='buy'?'Покупка':'Продажа'} казны</b><small>${_pxNum(o.remaining_units,1000)} по ${_pxPrice(o.limit_price_micromora)} моры</small></span>${isOwner?`<button type="button" ${locked?'disabled':''} onclick="_pxCancelTreasury('${esc(o.id)}','${esc(coin.id)}')">${locked?'Защищает эмиссию':'Отменить'}</button>`:''}</div>`;}).join('');
  const withdrawals=(m.liquidity_withdrawals||[]).map(w=>{const state={pending:'Ожидает 24 часа',executed:'Исполнен',cancelled:'Отменён'}[w.status]||w.status,at=w.status==='executed'?w.executed_at:w.status==='cancelled'?w.cancelled_at:w.executes_at;return `<div class="px-emission"><span><b>Вывод ${_pxNum(w.amount_mora)} моры</b><small>База: ${_pxNum(w.treasury_snapshot_mora)} · лимит: ${_pxNum(w.max_amount_mora)}</small><small>Запрос: ${new Date(w.requested_at).toLocaleString('ru-RU')}</small></span><strong>${esc(state)}<small>${w.status==='pending'?'Исполнение':'Статус'}: ${at?new Date(at).toLocaleString('ru-RU'):'—'}</small></strong>${isOwner&&w.status==='pending'?`<button type="button" onclick="_pxCancelLiquidityWithdrawal('${esc(w.id)}','${esc(coin.id)}')">Отменить вывод</button>`:''}</div>`;}).join('');
  const treasuryBlock=`<section class="px-flow"><h2>Публичная казна</h2><div class="px-treasury"><span><small>Мора</small><b>${_pxNum(treasury.treasury_mora)}</b></span><span><small>${esc(coin.ticker)}</small><b>${_pxNum(treasury.treasury_units,1000)}</b></span><span><small>Резерв стакана</small><b>${_pxNum(Number(treasury.market_reserve_units||0)+Number(treasury.market_reserved_units||0),1000)}</b></span></div>${isOwner?`<div class="px-owner-grid"><button type="button" onclick="_pxOpenTreasuryOrder('${esc(coin.id)}','buy')">Выкупить</button><button type="button" onclick="_pxOpenTreasuryOrder('${esc(coin.id)}','sell')">Продать</button><button type="button" onclick="_pxOpenTreasuryBurn('${esc(coin.id)}')">Сжечь</button><button type="button" onclick="_pxOpenLiquidityAdd('${esc(coin.id)}')">Добавить Мору</button><button type="button" onclick="_pxOpenLiquidityWithdrawal('${esc(coin.id)}')">Запросить вывод</button></div>`:''}${treasuryOrders}${withdrawals?`<div class="px-subflow"><h3>Движение ликвидности</h3>${withdrawals}</div>`:''}</section>`;
  const journalLabels={coin_created:'Монета создана',auction_settled:'Аукцион завершён',treasury_ladder_created:'Стартовый стакан',market_halted:'Торги остановлены',market_halted_manual:'Торги остановлены',emission_requested:'Запрошена эмиссия',emission_cancelled:'Эмиссия отменена',emission_executed:'Эмиссия исполнена',owner_vesting_claimed:'Получена доля владельца',treasury_order_placed:'Заявка казны',treasury_order_cancelled:'Заявка казны отменена',treasury_burned:'Монеты сожжены',liquidity_added:'Ликвидность добавлена',liquidity_withdrawal_requested:'Вывод ликвидности запрошен',liquidity_withdrawal_cancelled:'Вывод ликвидности отменён',liquidity_withdrawal_executed:'Вывод ликвидности исполнен'};
  const journal=(m.journal||[]).slice(0,20).map(e=>`<div class="px-journal"><span><b>${esc(journalLabels[e.event_type]||e.event_type)}</b><small>${new Date(e.created_at).toLocaleString('ru-RU')}</small></span><code>${esc(JSON.stringify(e.details||{}))}</code></div>`).join('');
  const host=el('pg-exchange-v1');host.innerHTML=`<section class="px-shell"><button class="px-back" type="button" onclick="_pxRenderHome()">‹ Все монеты</button><header class="px-coin-title"><div><small>${esc(coin.ticker)} / МОРА</small><h1>${esc(coin.name)}</h1></div><span class="${halted?'is-halted':''}">${halted?'Пауза':_pxPrice(stats.reference_price_micromora||stats.last_price_micromora)}</span></header>${halted?`<p class="px-halt">${esc(stats.halt?.public_reason||'Торги временно остановлены. Открытые заявки можно отменить.')}</p>`:''}<div class="px-market-stats"><span><small>Лучшая покупка</small><b>${_pxPrice(stats.best_bid_micromora)}</b></span><span><small>Лучшая продажа</small><b>${_pxPrice(stats.best_ask_micromora)}</b></span><span><small>Объём 24 ч</small><b>${_pxNum(stats.volume_mora)}</b></span></div><div class="px-segment" role="group" aria-label="Направление сделки"><button type="button" aria-pressed="${_pxSide==='buy'}" onclick="_pxSetSide('buy')">Купить</button><button type="button" aria-pressed="${_pxSide==='sell'}" onclick="_pxSetSide('sell')">Продать</button></div><div class="px-form px-trade-form"><label>Количество ${esc(coin.ticker)}<input id="px-amount" inputmode="decimal" placeholder="10"></label><label>Цена за монету в Море<input id="px-limit" inputmode="decimal" placeholder="0,50"></label><button type="button" class="px-primary ${_pxSide==='sell'?'is-sell':''}" ${halted?'disabled':''} onclick="_pxSubmitOrder('${esc(coin.id)}')">${_pxSide==='buy'?'Купить':'Продать'} ${esc(coin.ticker)}</button><small>Цена фиксирует ваш максимум для покупки или минимум для продажи. Заявка может исполниться частично.</small></div><section class="px-flow"><h2>Стакан</h2><div class="px-book-head"><span>Цена</span><span>Количество</span></div>${rows||_pxEmpty('Заявок пока нет.')}</section><section class="px-flow"><h2>Последние сделки</h2><div class="px-trade-head"><span>Цена</span><span>Количество</span><span>Время</span></div>${tradeRows||_pxEmpty('Сделок пока нет.')}</section>${treasuryBlock}${vestingBlock}${isOwner?`<button type="button" class="px-link px-owner-action" onclick="_pxOpenEmission('${esc(coin.id)}')">Запланировать эмиссию</button>`:''}${emissions?`<section class="px-flow"><h2>Эмиссия</h2>${emissions}</section>`:''}${journal?`<section class="px-flow"><h2>Публичный журнал</h2>${journal}</section>`:''}<p class="px-disclosure">Игровой актив без вывода в деньги. Доход не гарантирован.</p></section>`;
  const disclosure=host.querySelector('p.px-disclosure');
  if(disclosure&&_pxShortState?.shorts_enabled)disclosure.insertAdjacentHTML('beforebegin',_pxShortTradingBlock(coin));
}
function _pxOpenTreasuryOrder(id,side){const coin=_pxMarket?.coin||{};OM(side==='buy'?'Выкуп из казны':'Продажа из казны',`<div class="px-form"><label>Количество ${esc(coin.ticker||'')}<input id="px-treasury-amount" inputmode="decimal"></label><label>Лимитная цена в Море<input id="px-treasury-price" inputmode="decimal"></label><small>Заявка будет публичной и попадёт в общий стакан.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Дальше',c:'primary',f:`_pxReviewTreasuryOrder('${esc(id)}','${side}')`}]);}
function _pxReviewTreasuryOrder(id,side){const amount=(el('px-treasury-amount')?.value||'').replace(',','.'),price=(el('px-treasury-price')?.value||'').replace(',','.'),n=Number(amount)*Number(price),coin=_pxMarket?.coin||{};if(!(Number(amount)>0&&Number(price)>0)){toast('Укажите количество и цену.',false);return;}_pxPendingTreasury={kind:'order',id,payload:{side,amount,limit_price_mora:price,action_id:economyRequestKey('coin-treasury-order')}};const reserve=side==='buy'?(n>=10?n*1.1:n):Number(amount);OM('Проверьте заявку казны',`<div class="px-confirm"><b>${side==='buy'?'Выкуп':'Продажа'} ${esc(amount)} ${esc(coin.ticker||'')}</b><span>Цена: ${esc(price)} моры</span><span>${side==='buy'?'Максимальный резерв':'Резерв монет'}: ${_pxNum(reserve)}</span><small>Операция публична. Сделка может исполниться частично.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Опубликовать',c:'primary',f:'_pxConfirmTreasury()'}]);}
function _pxOpenTreasuryBurn(id){const coin=_pxMarket?.coin||{},available=Number(_pxMarket?.treasury?.treasury_units||0)/1000;OM('Сжечь монеты казны',`<div class="px-form"><p>Доступно: <b>${_pxNum(available)} ${esc(coin.ticker||'')}</b></p><label>Количество<input id="px-treasury-burn" inputmode="decimal"></label><small>Сжигание навсегда уменьшает общий выпуск.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Дальше',c:'primary',f:`_pxReviewTreasuryBurn('${esc(id)}')`}]);}
function _pxReviewTreasuryBurn(id){const amount=(el('px-treasury-burn')?.value||'').replace(',','.'),coin=_pxMarket?.coin||{},units=Number(amount)*1000;if(!(Number(amount)>0)){toast('Укажите количество.',false);return;}_pxPendingTreasury={kind:'burn',id,payload:{amount,action_id:economyRequestKey('coin-treasury-burn')}};OM('Подтвердите сжигание',`<div class="px-confirm"><b>Сжечь ${esc(amount)} ${esc(coin.ticker||'')}</b><span>Новый выпуск: ${_pxNum(Number(coin.total_supply_units)-units,1000)}</span><small>Операция публична и необратима.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Сжечь',c:'primary',f:'_pxConfirmTreasury()'}]);}
function _pxConfirmTreasury(){const p=_pxPendingTreasury;if(!p)return;_pxPendingTreasury=null;const path=p.kind==='burn'?`/player-exchange/v1/coins/${encodeURIComponent(p.id)}/treasury/burn`:`/player-exchange/v1/coins/${encodeURIComponent(p.id)}/treasury/orders`;api(path,{method:'POST',body:JSON.stringify(p.payload)}).then(()=>{CM();toast(p.kind==='burn'?'Монеты сожжены.':'Заявка казны опубликована.');_pxOpenCoin(p.id);}).catch(e=>{_pxPendingTreasury=p;toast(e,false);});}
function _pxCancelTreasury(orderId,coinId){const key=`treasury-cancel:${orderId}`,actionId=_pxOwnerActionIds[key]||(_pxOwnerActionIds[key]=economyRequestKey('coin-treasury-cancel'));api(`/player-exchange/v1/treasury/orders/${encodeURIComponent(orderId)}/cancel`,{method:'POST',body:JSON.stringify({action_id:actionId})}).then(()=>{delete _pxOwnerActionIds[key];toast('Заявка казны отменена.');if(_pxState?.trading_enabled)_pxOpenCoin(coinId);else _pxReload();}).catch(e=>toast(e,false));}
function _pxOpenLiquidityAdd(id){const treasury=_pxMarket?.treasury||{};OM('Добавить ликвидность',`<div class="px-form"><p>В казне сейчас: <b>${_pxNum(treasury.treasury_mora)} моры</b>.</p><label>Сколько Моры добавить<input id="px-liquidity-add" inputmode="decimal" placeholder="1000"></label><small>Мора уйдёт из вашего кошелька в публичную казну монеты. Вернуть её можно только отдельным выводом с задержкой и лимитом.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Дальше',c:'primary',f:`_pxReviewLiquidityAdd('${esc(id)}')`}]);}
function _pxReviewLiquidityAdd(id){const amount=(el('px-liquidity-add')?.value||'').replace(',','.');if(!(Number(amount)>=1)){toast('Укажите сумму не меньше 1 моры.',false);return;}_pxPendingLiquidity={kind:'add',id,payload:{amount_mora:amount,action_id:economyRequestKey('coin-liquidity-add')}};OM('Подтвердите пополнение казны',`<div class="px-confirm"><b>+${esc(amount)} моры в казну</b><span>Средства перейдут из вашего кошелька в ликвидность ${esc(_pxMarket?.coin?.ticker||'монеты')}.</span><small>Операция публична. Отменить пополнение после подтверждения нельзя.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Добавить',c:'primary',f:'_pxConfirmLiquidity()'}]);}
function _pxOpenLiquidityWithdrawal(id){const treasury=_pxMarket?.treasury||{},maximum=Math.floor(Number(treasury.treasury_mora||0)*0.1*1000000)/1000000;OM('Запросить вывод ликвидности',`<div class="px-form"><p>За один вывод доступно до <b>${_pxNum(maximum)} моры</b> — 10% текущей казны.</p><label>Сколько вывести<input id="px-liquidity-withdraw" inputmode="decimal" placeholder="${esc(String(maximum||''))}"></label><small>После 30 дней с запуска можно сделать один публичный запрос. Исполнение — через 24 часа; следующий вывод — не раньше чем через 7 дней после исполнения.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Дальше',c:'primary',f:`_pxReviewLiquidityWithdrawal('${esc(id)}')`}]);}
function _pxReviewLiquidityWithdrawal(id){const amount=(el('px-liquidity-withdraw')?.value||'').replace(',','.'),maximum=Number(_pxMarket?.treasury?.treasury_mora||0)*.1;if(!(Number(amount)>=1)){toast('Укажите сумму не меньше 1 моры.',false);return;}if(Number(amount)>maximum){toast('Сумма больше 10% текущей казны.',false);return;}_pxPendingLiquidity={kind:'withdrawal',id,payload:{amount_mora:amount,action_id:economyRequestKey('coin-liquidity-withdraw')}};OM('Проверьте вывод ликвидности',`<div class="px-confirm"><b>${esc(amount)} моры из казны</b><span>Это не моментальный вывод: запрос увидят все, а исполнение будет через 24 часа.</span><small>До исполнения его можно отменить. Сервер повторно проверит возраст монеты, лимит 10% и паузу после прошлого вывода.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Опубликовать запрос',c:'primary',f:'_pxConfirmLiquidity()'}]);}
function _pxConfirmLiquidity(){const pending=_pxPendingLiquidity;if(!pending)return;_pxPendingLiquidity=null;const path=pending.kind==='add'?`/player-exchange/v1/coins/${encodeURIComponent(pending.id)}/liquidity/add`:`/player-exchange/v1/coins/${encodeURIComponent(pending.id)}/liquidity/withdrawals`;api(path,{method:'POST',body:JSON.stringify(pending.payload)}).then(()=>{CM();toast(pending.kind==='add'?'Ликвидность добавлена в казну.':'Вывод опубликован и будет исполнен не раньше чем через 24 часа.');_pxOpenCoin(pending.id);}).catch(e=>{_pxPendingLiquidity=pending;toast(e,false);});}
function _pxCancelLiquidityWithdrawal(id,coinId){const actionId=_pxLiquidityCancelActions[id]||(_pxLiquidityCancelActions[id]=economyRequestKey('coin-liquidity-cancel'));api(`/player-exchange/v1/liquidity/withdrawals/${encodeURIComponent(id)}/cancel`,{method:'POST',body:JSON.stringify({action_id:actionId})}).then(()=>{delete _pxLiquidityCancelActions[id];toast('Вывод ликвидности отменён.');if(_pxState?.trading_enabled&&_pxMarket?.coin?.id===coinId)_pxOpenCoin(coinId);else _pxReload();}).catch(e=>toast(e,false));}
function _pxOpenVestingClaim(id){const vesting=_pxMarket?.owner_vesting,coin=_pxMarket?.coin;if(!vesting||!coin||Number(vesting.claimable_units)<=0)return;const units=Number(vesting.claimable_units),projected=Number(coin.circulating_units)+units,pct=units*100/Math.max(1,Number(coin.circulating_units));OM('Получить долю владельца',`<div class="px-confirm"><b>${_pxNum(units,1000)} ${esc(coin.ticker)}</b><span>Обращение вырастет на ${_pxNum(pct)}%</span><span>После операции: ${_pxNum(projected,1000)} монет в обращении</span><small>Операция публична и необратима. Монеты поступят на ваш биржевой баланс.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Получить',c:'primary',f:`_pxClaimVesting('${esc(id)}',${units})`}]);}
function _pxClaimVesting(id,units){if(_pxVestingSubmitting)return;_pxVestingSubmitting=true;const actionId=_pxOwnerActionIds[`vesting:${id}`]||(_pxOwnerActionIds[`vesting:${id}`]=economyRequestKey('coin-owner-vesting'));api(`/player-exchange/v1/coins/${encodeURIComponent(id)}/owner-vesting/claim`,{method:'POST',body:JSON.stringify({action_id:actionId,units})}).then(r=>{_pxVestingSubmitting=false;delete _pxOwnerActionIds[`vesting:${id}`];CM();toast(`Получено ${_pxNum(r.vesting.units,1000)} монет.`);_pxOpenCoin(id);}).catch(e=>{_pxVestingSubmitting=false;toast(e,false);});}
function _pxOpenEmission(id){
  const coin=_pxMarket?.coin||{};const maximum=Number(coin.circulating_units||0)/10000;
  OM('Публичная эмиссия',`<div class="px-form"><p>Максимум сейчас: <b>${_pxNum(maximum)} ${esc(coin.ticker||'')}</b>. Монеты попадут в казну через 24 часа.</p><label>Количество<input id="px-emission-amount" inputmode="decimal"></label><label>Публичная причина<textarea id="px-emission-reason" maxlength="160" placeholder="Зачем монете нужна эмиссия"></textarea></label><small>Запрос видят все. Отмена закроется за час до исполнения.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Дальше',c:'primary',f:`_pxRequestEmission('${esc(id)}')`}]);
}
function _pxRequestEmission(id){const amount=el('px-emission-amount')?.value||'',reason=(el('px-emission-reason')?.value||'').trim(),coin=_pxMarket?.coin||{},units=Number(amount)*1000,pct=units*100/Number(coin.circulating_units||1),projected=Number(coin.total_supply_units||0)+units;if(!(Number(amount)>0)||reason.length<10){toast('Укажите количество и причину.',false);return;}_pxPendingEmission={id,payload:{amount,reason,action_id:economyRequestKey('coin-emission')}};OM('Проверьте эмиссию',`<div class="px-confirm"><b>+${esc(amount)} ${esc(coin.ticker||'')}</b><span>Размытие: ${_pxNum(pct)}%</span><span>Новый объём: ${_pxNum(projected,1000)}</span><span>${esc(reason)}</span><small>Запрос публичен на 24 часа. Отмена закроется за час до исполнения.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Опубликовать',c:'primary',f:'_pxConfirmEmission()'}]);}
function _pxConfirmEmission(){const pending=_pxPendingEmission;if(!pending)return;_pxPendingEmission=null;api(`/player-exchange/v1/coins/${encodeURIComponent(pending.id)}/emissions`,{method:'POST',body:JSON.stringify(pending.payload)}).then(()=>{CM();toast('Эмиссия опубликована.');_pxOpenCoin(pending.id);}).catch(e=>{_pxPendingEmission=pending;toast(e,false);});}
function _pxCancelEmission(id,coinId){const actionId=_pxEmissionCancelActions[id]||(_pxEmissionCancelActions[id]=economyRequestKey('coin-emission-cancel'));api(`/player-exchange/v1/emissions/${encodeURIComponent(id)}/cancel`,{method:'POST',body:JSON.stringify({action_id:actionId})}).then(()=>{delete _pxEmissionCancelActions[id];toast('Эмиссия отменена.');if(_pxState?.trading_enabled&&_pxMarket?.coin?.id===coinId)_pxOpenCoin(coinId);else _pxReload();}).catch(e=>toast(e,false));}
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
  OM(`Подтвердите ${_pxSide==='buy'?'покупку':'продажу'}`,`<div class="px-confirm"><b>${esc(amount)} ${esc(coin.ticker||'монет')}</b><span>${bound}</span><span>${commitment}</span><small>Комиссия: maker 0,10%, taker 0,25%; минимум 1 мора для исполнения от 10 моры. Заявка может исполниться частично.</small></div>`,[{l:'Назад',c:'ghost',f:'CM()'},{l:'Подтвердить',c:_pxSide==='sell'?'btn-danger':'btn-gold',f:'_pxConfirmOrder()'}]);
}
function _pxConfirmOrder(){
  const pending=_pxPendingOrder;if(!pending)return;
  _pxPendingOrder=null;
  api(pending.path,{method:'POST',body:JSON.stringify(pending.payload)}).then(()=>{CM();toast('Заявка размещена.');_pxReload();}).catch(e=>{_pxPendingOrder=pending;toast(e,false);});
}
