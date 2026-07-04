// ── Auction: поиск + фильтры + сортировка (ШАГ2, клиентская сторона) ───────────
let _allLots=[];
let _aucSearch='', _aucRarity='', _aucCat='', _aucSort='ending';
const _AUC_KNOWN_CATS=['food','booster','material','utility','theme','spin_token','pet'];
function filterAuction(q){ _aucSearch=(q||'').toLowerCase(); _applyAucFilters(); }
function setAucFilter(kind,val){ if(kind==='rarity')_aucRarity=val; else if(kind==='cat')_aucCat=val; else if(kind==='sort')_aucSort=val; _applyAucFilters(); }
function _aucOpt(kind,opts){ const cur=kind==='sort'?_aucSort:kind==='rarity'?_aucRarity:_aucCat;
  return opts.map(([v,l])=>`<option value="${v}"${v===cur?' selected':''}>${l}</option>`).join(''); }
function _lotPrice(l){ return l.current_bid || l.min_bid || 0; }
function _lotEnds(l){ return new Date((l.ends_at+'').includes('T')?l.ends_at:l.ends_at+'Z').getTime(); }
function _lotCat(l){ const c=l.item_category||''; return c || (l.item_id_ref?'other':'pet'); }
function _applyAucFilters(){
  let lots=_allLots.slice();
  if(_aucSearch) lots=lots.filter(l=>((l.item_name_display||l.item_name||'').split('||')[0].toLowerCase()).includes(_aucSearch));
  if(_aucRarity) lots=lots.filter(l=>(l.item_rarity||'')===_aucRarity);
  if(_aucCat){ lots=lots.filter(l=>{ const c=_lotCat(l); return _aucCat==='other' ? !_AUC_KNOWN_CATS.includes(c) : c===_aucCat; }); }
  if(_aucSort==='cheap')          lots.sort((a,b)=>_lotPrice(a)-_lotPrice(b));
  else if(_aucSort==='expensive') lots.sort((a,b)=>_lotPrice(b)-_lotPrice(a));
  else if(_aucSort==='new')       lots.sort((a,b)=>(b.id||0)-(a.id||0));
  else                            lots.sort((a,b)=>_lotEnds(a)-_lotEnds(b)); // ending soon
  renderLots(lots, _aucSearch);
}
// Category → icon emoji for auction lot cards
const LOT_CAT_ICON={food:'🍖',spin_token:'🎟',booster:'⚡',material:'💠',utility:'🏡',theme:'🎨',pet:'🐾'};
// Цвет/название редкости — общая таблица RARITY_META (app.01.js), не дублируем здесь.

function renderLots(lots, searchQuery) {
  if (!el('lot-list')) return;
  if(!lots.length) {
    el('lot-list').innerHTML = searchQuery
      ? `<div style="text-align:center;padding:24px;color:var(--muted)"><div style="font-size:24px;margin-bottom:6px">🔍</div><div style="font-size:12px">Ничего не найдено по «${searchQuery}»</div></div>`
      : `<div style="text-align:center;padding:32px 16px;color:var(--muted)"><div style="font-size:32px;margin-bottom:8px">🏛️</div><div style="font-size:13px;font-weight:600;margin-bottom:4px">Аукцион пуст</div><div style="font-size:11px">Выставь свой лот — нажми «+ Выставить»!</div></div>`;
    return;
  }
  el('lot-list').innerHTML = lots.map(l => {
    const ends = new Date((l.ends_at+'').includes('T') ? l.ends_at : l.ends_at+'Z');
    const totalSec = 24*3600;
    const diffSec  = Math.max(0, Math.floor((ends - Date.now())/1000));
    const pctLeft  = Math.min(100, Math.round(diffSec/totalSec*100));
    const tl = diffSec > 3600
      ? Math.floor(diffSec/3600)+'ч '+Math.floor((diffSec%3600)/60)+'м'
      : Math.floor(diffSec/60)+'м';
    const isUrgent = diffSec < 3600;

    const hasBids = !!l.has_bids;
    const curBid  = l.current_bid || l.min_bid;
    const minNext = l.min_next_bid || (hasBids ? Math.ceil(curBid*1.05)+1 : Math.ceil(l.min_bid));
    const buyout  = l.buyout || 0;

    const displayName = l.item_name_display || (l.item_name||'?').split('||')[0] || '?';
    const desc   = l.item_description || '';
    const cat    = l.item_category || '';
    const icon   = LOT_CAT_ICON[cat] || (displayName.match(/^\p{Emoji}/u)?.[0] || '📦');
    const qty    = l.quantity > 1 ? ` ×${l.quantity}` : '';
    const bidArgs = `${l.id},'${displayName.replace(/'/g,"\\'")}',${curBid},${minNext},${hasBids},${buyout},${l.remaining_sec||diffSec}`;

    const hotCls     = hasBids ? ' hot' : '';
    const buyoutCls  = buyout ? ' buyout-avail' : '';
    const rar        = l.item_rarity || '';
    const rarCol     = rar ? rarColor(rar) : '';

    return `<div class="lot-card${hotCls}${buyoutCls}"${rarCol?` style="border-left:3px solid ${rarCol}"`:''}>
      <!-- Timer bar -->
      <div class="lot-timer-bar">
        <div class="lot-timer-fill" style="width:${pctLeft}%;${isUrgent?'background:var(--red)':''}"></div>
      </div>
      <!-- Top row: icon + info -->
      <div class="lot-card-top">
        <div class="lot-icon">${icon}</div>
        <div class="lot-info">
          <div class="lot-name">${displayName}${qty}</div>
          ${desc?`<div class="lot-desc">${desc}</div>`:''}
          <div class="lot-badges">
            ${rar?`<span class="lot-badge" style="color:${rarCol};border-color:${rarCol}">${rarLabel(rar)}</span>`:''}
            <span class="lot-badge seller" onclick="openGlobalProfile(${l.seller_id})" style="cursor:pointer">👤 ${vipName(l.seller_name||'Игрок', l.seller_is_vip)}</span>
            <span class="lot-badge timer${isUrgent?' hot':''}">⏳ ${tl}</span>
            ${hasBids
              ? '<span class="lot-badge hot">🔥 Есть ставки</span>'
              : '<span class="lot-badge first">Первая ставка</span>'}
          </div>
        </div>
      </div>
      <!-- Footer: bid + button -->
      <div class="lot-footer">
        <div class="lot-price-wrap">
          <div class="lot-bid-label">${hasBids?'Текущая ставка':'Старт'}</div>
          <div class="lot-bid">${fmt(curBid)} 🪙</div>
          ${buyout?`<div class="lot-buyout">⚡ Выкуп: ${fmt(buyout)} 🪙</div>`:''}
        </div>
        <button class="btn btn-sm btn-gold" onclick="openBidModal(${bidArgs})" style="padding:8px 14px">
          💰 Ставка
        </button>
      </div>
    </div>`;
  }).join('');
}

// ── Крипто-Биржа (ШАГ4): лорные монеты, свечи, купить/продать с ползунком % ──────
let _cxData=null, _cxSel=null, _cxAction='buy', _cxPct=50, _cxHost='mb', _cxView='list';
// Инлайн-вкладка «📈 Биржа» (под-вкладка страницы Аукцион·Обменник·Биржа).
function loadCrypto(){
  _cxHost='mkt-crypto'; _cxSel=null; _cxAction='buy'; _cxPct=50; _cxView='list';
  const h=el('mkt-crypto'); if(h) h.innerHTML='<div class="loader">Загрузка рынка...</div>';
  _cxLoad();
}
function _cxLoad(){ api('/exchange/crypto').then(d=>{_cxData=d; renderCrypto();})
  .catch(e=>{const b=el(_cxHost); if(b)b.innerHTML=`<div class="err">${e}</div>`;}); }
function _cxCur(){ return (_cxData&&_cxData.coins||[]).find(c=>c.id===_cxSel); }
function _cxAmt(a){ return (Number(a)||0).toLocaleString('ru',{maximumFractionDigits:4}); }
function renderCrypto(){
  const b=el(_cxHost); if(!b||!_cxData) return;
  if(_cxView==='top'){ b.innerHTML='<div class="loader">Загрузка...</div>'; _cxTopLoad(); return; }
  if(_cxSel){ b.innerHTML=_cxDetailHtml(); return; }
  var pnl=_cxData.portfolio_pnl||0, pnlCls=pnl>=0?'cx-pnl-up':'cx-pnl-dn', pnlSign=pnl>=0?'+':'';
  var pnlTxt=_cxData.portfolio_value>0?' <span class="'+pnlCls+'">'+pnlSign+fmt(Math.round(pnl))+' P&L</span>':'';
  var head='<div class="cx-head">'
    +'<div><div class="cx-h-l">💼 Портфель</div><div class="cx-h-v">'+fmt(_cxData.portfolio_value)+' 🪙'+pnlTxt+'</div></div>'
    +'<div style="text-align:right"><div class="cx-h-l">Баланс · <button class="cx-star" onclick="_cxView=\'top\';renderCrypto()" title="Топ трейдеров">🏆</button></div>'
    +'<div class="cx-h-v">'+fmt(_cxData.mora)+' 🪙</div></div></div>';
  b.innerHTML=head+'<div class="cx-list">'+_cxData.coins.map(_cxRow).join('')+'</div>';
}
function _cxRow(c){
  var up=c.change_24h>=0;
  var pnlBadge='';
  if(c.holding>0 && c.avg_buy){
    var pCls=c.pnl_abs>=0?'cx-pnl-up':'cx-pnl-dn', pSign=c.pnl_abs>=0?'+':'';
    pnlBadge=' <span class="'+pCls+'">'+pSign+fmt(Math.round(c.pnl_abs))+'</span>';
  }
  var holdLine=c.holding>0
    ?'<div class="cx-rhold">'+_cxAmt(c.holding)+' · '+fmt(c.value)+'🪙'+pnlBadge+'</div>'
    :'<div class="cx-rhold cx-dim">—</div>';
  var starCls='cx-star'+(c.starred?' on':'');
  return '<div class="cx-row" onclick="_cxOpen(\''+c.id+'\')">'
    +'<div class="cx-ico">'+c.emoji+'</div>'
    +'<div class="cx-rinfo"><div class="cx-rname">'+esc(c.name)
    +' <button class="'+starCls+'" onclick="event.stopPropagation();_cxWatch(\''+c.id+'\')" title="Избранное">'+( c.starred?'★':'☆')+'</button></div>'
    +holdLine+'</div>'
    +_cxSpark(c.candles,up)
    +'<div class="cx-rprice"><div class="cx-rp">'+fmt(c.price)+'🪙</div>'
    +'<div class="cx-rchg '+(up?'up':'down')+'">'+(up?'▲':'▼')+Math.abs(c.change_24h)+'%</div></div></div>';
}
function _cxSpark(cd,up){
  const cl=(cd||[]).map(x=>x.c), W=52,H=24;
  if(cl.length<2) return `<svg class="cx-spark" width="${W}" height="${H}"></svg>`;
  const mn=Math.min(...cl), mx=Math.max(...cl), rng=(mx-mn)||1;
  const pts=cl.map((v,i)=>`${(i/(cl.length-1)*W).toFixed(1)},${(H-(v-mn)/rng*H).toFixed(1)}`).join(' ');
  return `<svg class="cx-spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><polyline points="${pts}" fill="none" stroke="${up?'#5fd38a':'#e0556b'}" stroke-width="1.5"/></svg>`;
}
function _cxOpen(id){ _cxSel=id; _cxAction='buy'; _cxPct=50; renderCrypto(); }
function _cxBack(){ _cxSel=null; renderCrypto(); }
function _cxSetAction(a){ _cxAction=a; _cxPct=50; renderCrypto(); }
// Комиссия CRYPTO_TRADE_FEE берётся на ОБЕ стороны → учитываем и в maxAmt (на покупке
// 1 монета стоит price×(1+fee), иначе ползунок 100% ушёл бы за баланс), и в сумме сделки.
function _cxMaxAmt(c){ const fee=_cxData.fee||0; if(_cxAction==='buy'){ const u=c.price*(1+fee); return u>0?_cxData.mora/u:0; } return c.holding; }
function _cxCost(c,amt){ const fee=_cxData.fee||0; return _cxAction==='buy'?amt*c.price*(1+fee):amt*c.price*(1-fee); }
function _cxDetailHtml(){
  const c=_cxCur(); if(!c) return '';
  const up=c.change_24h>=0, price=c.price, fee=_cxData.fee||0;
  const maxAmt=_cxMaxAmt(c);
  const amt=maxAmt*_cxPct/100;
  const cost=_cxCost(c,amt);
  const noFunds=maxAmt<=0;
  return `<button class="btn btn-sm btn-ghost" style="margin-bottom:8px" onclick="_cxBack()">← Все монеты</button>
    <div class="cx-det-head"><span class="cx-ico" style="font-size:26px">${c.emoji}</span>
      <div><div class="cx-rname" style="font-size:16px">${c.name}</div>
      <div class="cx-rchg ${up?'up':'down'}">${fmt(price)} 🪙 · ${up?'▲':'▼'} ${Math.abs(c.change_24h)}% (24ч)</div></div></div>
    ${_cxChart(c.candles)}
    <div class="cx-hold">В портфеле: <b>${_cxAmt(c.holding)}</b> ${c.emoji} <span class="cx-dim">(${fmt(c.value)} 🪙)</span></div>
    ${c.holding&&c.avg_buy?`<div class="cx-pnl ${c.pnl_abs>=0?'up':'down'}">P&L: ${c.pnl_abs>=0?'+':''}${fmt(Math.round(c.pnl_abs))} 🪙 (${c.pnl_pct>=0?'+':''}${c.pnl_pct}%) · ср. цена ${fmt(Math.round(c.avg_buy))} 🪙</div>`:''}
    <div class="cx-tabs"><button class="cx-tab ${_cxAction==='buy'?'on':''}" onclick="_cxSetAction('buy')">Купить</button>
      <button class="cx-tab ${_cxAction==='sell'?'on':''}" onclick="_cxSetAction('sell')">Продать</button></div>
    <div class="cx-slider-row"><input id="cx-slider" type="range" min="0" max="100" value="${_cxPct}" oninput="_cxSlide(this.value)"/>
      <span id="cx-pct" class="cx-pct">${_cxPct}%</span></div>
    <div class="cx-quote"><div>Кол-во: <b id="cx-amt">${_cxAmt(amt)}</b> ${c.emoji}</div>
      <div>${_cxAction==='buy'?'Потратишь':'Получишь'}: <b id="cx-cost">${fmt(Math.round(cost))}</b> 🪙</div></div>
    ${fee?`<div class="cx-dim" style="font-size:10px;margin:-4px 0 8px">↳ комиссия биржи −${Math.round(fee*100)}% (и при покупке, и при продаже)</div>`:''}
    ${noFunds?`<div class="cx-dim" style="font-size:11px;text-align:center;margin-bottom:6px">${_cxAction==='buy'?'Недостаточно 🪙 для покупки':'Нет '+esc(c.name)+' в портфеле'}</div>`:''}
    <button class="btn btn-full ${_cxAction==='buy'?'btn-gold':'btn-ghost'}" ${noFunds?'disabled':''} onclick="_cxTrade()">${_cxAction==='buy'?'📈 Купить':'📉 Продать'} ${esc(c.name)}</button>
    <button class="btn btn-sm btn-ghost" style="margin-top:8px;width:100%" onclick="_cxHistLoad('${c.id}')">📋 История сделок</button>
    <div id="cx-hist-box" style="margin-top:6px"></div>`;
}
function _cxChart(cd){
  if(!cd||!cd.length) return '';
  const W=300,H=110,pad=5, lo=Math.min(...cd.map(x=>x.l)), hi=Math.max(...cd.map(x=>x.h)), rng=(hi-lo)||1, cw=W/cd.length;
  const y=v=>pad+(H-2*pad)*(1-(v-lo)/rng);
  const bars=cd.map((k,i)=>{const x=i*cw+cw/2, up=k.c>=k.o, col=up?'#5fd38a':'#e0556b';
    const bt=y(Math.max(k.o,k.c)), bb=y(Math.min(k.o,k.c)), bh=Math.max(1,bb-bt), bw=Math.max(2,cw*0.6);
    return `<line x1="${x}" y1="${y(k.h)}" x2="${x}" y2="${y(k.l)}" stroke="${col}" stroke-width="1"/><rect x="${(x-bw/2).toFixed(1)}" y="${bt.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" fill="${col}"/>`;
  }).join('');
  return `<svg class="cx-chart" width="100%" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${bars}</svg>`;
}
function _cxSlide(v){
  _cxPct=parseInt(v)||0; const c=_cxCur(); if(!c) return;
  const maxAmt=_cxMaxAmt(c);
  const amt=maxAmt*_cxPct/100, cost=_cxCost(c,amt);
  const e1=el('cx-pct'),e2=el('cx-amt'),e3=el('cx-cost');
  if(e1)e1.textContent=_cxPct+'%'; if(e2)e2.textContent=_cxAmt(amt); if(e3)e3.textContent=fmt(Math.round(cost));
}
function _cxTrade(){
  const c=_cxCur(); if(!c) return;
  const maxAmt=_cxMaxAmt(c);
  const amt=maxAmt*_cxPct/100;
  if(amt<=0){ toast('Выбери количество ползунком',false); return; }
  api('/exchange/crypto/trade',{method:'POST',body:JSON.stringify({coin_id:c.id,action:_cxAction,amount:amt})})
    .then(r=>{toast('✅ '+r.message); refreshCurrBar(); _cxLoad();})
    .catch(e=>toast(e,false));
}
// ── БЛОК22: Вотчлист / история / топ трейдеров ───────────────────────────────────
function _cxWatch(coinId){
  api('/exchange/crypto/watchlist/'+coinId,{method:'POST'})
    .then(function(r){
      var c=(_cxData&&_cxData.coins||[]).find(function(x){return x.id===coinId;});
      if(c) c.starred=r.starred;
      renderCrypto();
    }).catch(function(e){toast(e,false);});
}
function _cxHistLoad(coinId){
  var box=el('cx-hist-box'); if(!box) return;
  box.innerHTML='<div class="cx-dim" style="font-size:11px;text-align:center;padding:4px">Загрузка...</div>';
  api('/exchange/crypto/history?coin_id='+coinId)
    .then(function(rows){
      if(!rows||!rows.length){box.innerHTML='<div class="cx-dim" style="font-size:11px;text-align:center;padding:4px">Сделок нет</div>'; return;}
      var coin=(_cxData&&_cxData.coins||[]).find(function(x){return x.id===coinId;});
      var emoji=coin?coin.emoji:'';
      box.innerHTML=rows.map(function(r){
        var isBuy=r.action==='buy';
        var amtFmt=(Number(r.amount)||0).toLocaleString('ru',{maximumFractionDigits:4});
        return '<div class="cx-hist-row">'
          +'<span class="cx-hist-act '+(isBuy?'buy':'sell')+'">'+(isBuy?'▲ Куп':'▼ Прод')+'</span>'
          +' '+emoji+' '+amtFmt
          +'<span class="cx-dim" style="margin:0 auto 0 6px">'+fmt(Math.round(r.price))+'🪙</span>'
          +'<span style="font-weight:700;color:var(--gold2)">'+fmt(Math.round(r.total_mora))+'🪙</span>'
          +'<span class="cx-dim" style="font-size:10px;margin-left:6px">'+r.traded_at+'</span>'
          +'</div>';
      }).join('');
    }).catch(function(e){if(box)box.innerHTML='<div class="err">'+e+'</div>';});
}
function _cxTopLoad(){
  var b=el(_cxHost); if(!b) return;
  api('/exchange/crypto/top')
    .then(function(rows){
      var html='<button class="btn btn-sm btn-ghost" style="margin-bottom:10px" onclick="_cxView=\'list\';renderCrypto()">← Биржа</button>'
        +'<div style="font-size:14px;font-weight:800;color:var(--bright);margin-bottom:8px">🏆 Топ трейдеров</div>';
      if(!rows||!rows.length){html+='<div class="cx-dim" style="font-size:12px;text-align:center;padding:12px">Ещё никто не торговал</div>'; b.innerHTML=html; return;}
      html+=rows.map(function(r){
        return '<div class="cx-top-row">'
          +'<span class="cx-top-rank">#'+r.rank+'</span>'
          +'<span>@'+esc(r.username||('id'+r.user_id))+'</span>'
          +'<span class="cx-top-val">'+fmt(Math.round(r.value))+' 🪙</span>'
          +'</div>';
      }).join('');
      b.innerHTML=html;
    }).catch(function(e){var b2=el(_cxHost); if(b2)b2.innerHTML='<div class="err">'+e+'</div>';});
}
// ── Глобальный профиль (БЛОК19 Часть3): клик по нику → витрина игрока ────────────
function unameLink(userId,name,vip,glow){ if(!userId) return esc('@'+(name||'?')); return `<span class="uname-link${glow?' '+glow:''}" onclick="openGlobalProfile(${userId})">${vip?'👑':''}@${esc(name||('id'+userId))}</span>`; }
function openGlobalProfile(userId){
  if(!userId) return;
  OM('👤 Профиль игрока','<div class="loader">Загрузка...</div>',[{l:'Закрыть',c:'btn-gold',f:'CM()'}]);
  api('/profile/u/'+userId).then(d=>renderGlobalProfile(d, userId)).catch(e=>{const b=el('mb');if(b)b.innerHTML=`<div class="err">${e}</div>`;});
}
function renderGlobalProfile(d, recipientId){
  const b=el('mb'); if(!b) return;
  const co=d.cosmetics||{}, cls=s=>(co[s]&&co[s].css)||'';
  const emap=(typeof PET_SPECIES_EMOJI!=='undefined')?PET_SPECIES_EMOJI:{};
  const pets=(d.pets||[]).map(p=>`<div class="gp-pet"><span class="gp-pe">${emap[p.species_id]||'🐾'}</span>
    <span class="gp-pn">${esc(p.name||p.species_id)}</span>
    <span class="gp-pl">Ур.${p.pet_level}${p.placement==='active'?' ·⚔️':''}</span></div>`).join('')
    ||'<div class="cx-dim" style="font-size:11px;padding:4px">Питомцев нет</div>';
  const clan=d.clan?`<div class="gp-clan">${d.clan.emblem||'🛡'} <b>${esc(d.clan.name)}</b> <span class="clan-tag">[${esc(d.clan.tag)}]</span> · ${d.clan.role==='leader'?'👑 Лидер':'Участник'}</div>`:'';
  const s=d.sanction;
  const sanctionHtml = s ? `<div class="gp-sanction gp-sanction-${s.type}">
      ${s.type==='ban'?'🔨 ГЛОБАЛЬНЫЙ БАН':'⚠️ Ограничение'}${s.reason?': '+esc(s.reason):''}
      ${s.expires_at?`<span class="gp-sanction-exp">до ${new Date(s.expires_at).toLocaleDateString('ru')}</span>`:'<span class="gp-sanction-exp">бессрочно</span>'}
    </div>` : '';
  const chatSancBits=[];
  if(d.chat_warnings>0) chatSancBits.push(`⚠️ ${d.chat_warnings} варн(ов) в чатах`);
  if(d.muted_until) chatSancBits.push(`🔇 в муте до ${new Date(d.muted_until).toLocaleString('ru')}`);
  const chatSanctionHtml = chatSancBits.length ? `<div class="gp-sanction gp-sanction-restrict">${chatSancBits.join(' · ')}</div>` : '';
  b.innerHTML=`<div class="looks-preview ${cls('profile_bg')}" style="text-align:left;padding:14px">
      ${cls('card_fx')?`<div class="card-fx ${cls('card_fx')}"></div>`:''}
      <div style="display:flex;align-items:center;gap:12px;position:relative;z-index:3">
        <div class="ava ${cls('avatar_frame')} ${cls('avatar_halo')}" style="width:58px;height:58px;font-size:30px;flex:none">${d.is_vip?'👑':'🔮'}</div>
        <div style="min-width:0">
          <div class="pname ${cls('name_glow')}" style="font-size:18px">@${esc(d.username)}</div>
          <div class="prank">${d.rank}</div>
          ${co.title?`<div class="ptitle${co.title_css?' '+co.title_css:''}">${esc(co.title)}</div>`:''}
        </div>
      </div>
    </div>
    ${sanctionHtml}
    ${chatSanctionHtml}
    ${clan}
    <div class="gp-stats">
      <div class="gp-st"><div class="gp-sv">${d.level}</div><div class="gp-sl">Уровень</div></div>
      ${typeof d.combat_power==='number'?`<div class="gp-st"><div class="gp-sv" style="color:var(--gold2)">⚡${fmt(d.combat_power)}</div><div class="gp-sl">Сила</div></div>`:''}
      <div class="gp-st"><div class="gp-sv">🔥${d.streak}</div><div class="gp-sl">Стрик</div></div>
      <div class="gp-st"><div class="gp-sv">🏆${d.achievements}</div><div class="gp-sl">Ачивки</div></div>
      <div class="gp-st"><div class="gp-sv">${fmt(d.messages)}</div><div class="gp-sl">Сообщений</div></div>
    </div>
    <div class="looks-slot-t" style="margin-top:12px">🐾 Питомцы (${(d.pets||[]).length})</div>
    <div class="gp-pets">${pets}</div>
    ${(recipientId && String(recipientId)!==String(typeof _uid!=='undefined'?_uid:''))?`<button class="btn btn-gold btn-full" style="margin-top:12px" onclick="_openGiftModal(${recipientId})">🎁 Подарить косметику</button>`:''}`;
}
// ── БЛОК21: подарок косметики за Stars (виральность) ─────────────────────────────
function _openGiftModal(rid){
  OM('🎁 Подарить косметику','<div class="loader">Загрузка...</div>',[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
  api('/cosmetics/gift/catalog?recipient_id='+rid).then(d=>{
    const items=(d.items||[]); const b=el('mb'); if(!b) return;
    if(!items.length){ b.innerHTML='<div class="cx-dim" style="padding:12px;text-align:center">Нет косметики для подарка.</div>'; return; }
    const cards=items.map(it=>{
      const foot = it.owned ? '<span class="lc-on">✓ есть</span>'
        : `<button class="btn btn-sm btn-gold" onclick="_giftBuy(${rid},'${it.id}',this)">${it.zarniki} ✨</button>`;
      return `<div class="looks-card r-${it.rarity}${it.owned?' lc-dim':''}">
        ${_looksSwatch(it.slot, it)}<div class="lc-name">${esc(it.name)}</div>
        <div class="lc-foot"><span class="lc-rar">${_rarLabel(it.rarity)}</span>${foot}</div></div>`;
    }).join('');
    b.innerHTML=`<div class="looks-hint">🎁 Списываются твои ✨ Зарники — подарок прилетит игроку, а в его профиле/топах засветится статус. Серые — у него уже есть.</div>
      <div class="looks-cards">${cards}</div>`;
  }).catch(e=>{const b=el('mb');if(b)b.innerHTML=`<div class="err">${e}</div>`;});
}
function _giftBuy(rid, cid, btn){
  if(btn) btn.disabled=true;
  api('/cosmetics/gift',{method:'POST',body:JSON.stringify({recipient_id:rid,cosmetic_id:cid,chat_id:(_initChatId||_cid||0)})})
    .then(r=>{ toast(r.message||'🎁 Подарок отправлен! 💜'); refreshCurrBar(); CM(); })
    .catch(e=>{toast(e,false); if(btn) btn.disabled=false;});
}
// ── R2 Врата 2.0: PvE-лестница с Боем 2.0 (замена пассивного дрейна) ──────────
let _g2Data=null, _btState=null, _btQteStart=0, _btLock=false;
function openShadowGates(){ OM('🌑 Врата 2.0','<div class="loader">Загрузка...</div>',[{l:'Закрыть',c:'btn-gold',f:'CM()'}]); _g2Load(); }
function _g2Load(){
  api('/combat2/gates').then(d=>{
    _g2Data=d;
    if(d.active_battle){ _btRender(d.active_battle); return; }
    _g2RenderLobby();
  }).catch(e=>{const b=el('mb');if(b)b.innerHTML=`<div class="err">${e}</div>`;});
}
function _g2RenderLobby(){
  const b=el('mb'); if(!b||!_g2Data) return;
  const d=_g2Data;
  const emap=(typeof PET_SPECIES_EMOJI!=='undefined')?PET_SPECIES_EMOJI:{};
  const floors=(d.floors||[]).map(f=>`<div class="g2-floor${f.open?'':' locked'}">
      <span class="g2-fn">Этаж ${f.floor} <span class="cx-dim">· волн: ${f.waves}</span></span>
      <span class="g2-fr">+${f.reward_dark} 🌑</span>
      ${f.open
        ? `<button class="btn btn-sm btn-gold" ${d.entries_left<=0?'disabled':''} onclick="_g2PickPet(${f.floor})">Войти</button>`
        : `<span class="g2-lock">🔒 ⚡${fmt(f.cp_gate)}</span>`}
    </div>`).join('');
  const heal=(d.pets||[]).filter(p=>p.hp<p.hp_max).map(p=>`<div class="gt-pet">
      <span class="gt-pe">${emap[p.species_id]||'🐾'}</span>
      <span class="gt-pn">${esc(p.name||p.species_id)}</span>
      <span class="gt-php">HP ${Math.floor(p.hp)}/${p.hp_max}</span>
      <button class="btn btn-sm btn-ghost" onclick="_g2Heal(${p.id})">💊 ${fmt(Math.ceil((p.hp_max-p.hp)*(d.heal_price_per_hp||2)))} 🪙</button>
    </div>`).join('');
  b.innerHTML=`<div class="looks-hint">⚔️ Врата 2.0 — живой бой: выбирай стойку и жми в момент сжатия кольца.
    Победа: Тёмная Мора + шанс 💠 Осколков Бездны. Входов сегодня: <b>${d.entries_left}</b>. Твоя Сила: ⚡ ${fmt(d.cp)}.
    Стамина тратится в бою и сама восстанавливается — 10% от максимума в час (точное время до полной — на карточке питомца).</div>
    <div class="looks-slot-t">🗼 Этажи</div>${floors}
    ${heal?`<div class="looks-slot-t" style="margin-top:12px">💊 Подлечить (${(d.heal_price_per_hp||2)} 🪙/HP)</div>${heal}`:''}`;
}
function _g2PickPet(floor){
  const b=el('mb'); if(!b||!_g2Data) return;
  const emap=(typeof PET_SPECIES_EMOJI!=='undefined')?PET_SPECIES_EMOJI:{};
  const pets=(_g2Data.pets||[]).filter(p=>p.alive).map(p=>`<div class="gt-pet">
      <span class="gt-pe">${emap[p.species_id]||'🐾'}</span>
      <span class="gt-pn">${esc(p.name||p.species_id)} <span class="cx-dim">${rarLabel(p.rarity)} Ур.${p.pet_level}</span></span>
      <span class="gt-php">HP ${Math.floor(p.hp)}/${p.hp_max} · ⚡${Math.floor(p.stamina)}/${p.stamina_max}</span>
      <button class="btn btn-sm btn-gold" onclick="_g2Enter(${floor},${p.id},this)">⚔️ Войти</button>
    </div>`).join('')||'<div class="cx-dim" style="padding:8px">Все питомцы без сил — подлечи.</div>';
  b.innerHTML=`<div class="looks-slot-t">Этаж ${floor} — кем идём?</div>${pets}
    <button class="btn btn-ghost btn-full" style="margin-top:8px" onclick="_g2RenderLobby()">↩ Назад</button>`;
}
function _g2Enter(floor, petId, btn){
  if(btn)btn.disabled=true;
  _btBackFn=_g2Load;
  api('/combat2/gates/enter',{method:'POST',body:JSON.stringify({floor, pet_id:petId})})
    .then(st=>{_haptic('medium'); _btRender(st);})
    .catch(e=>{toast(e,false); if(btn)btn.disabled=false;});
}
let _btBackFn=null;   // куда возвращаться после боя (Врата/Бездна/Война)
function _btBack(){ (_btBackFn||_g2Load)(); }
function _g2Heal(petId){
  api('/combat2/heal',{method:'POST',body:JSON.stringify({pet_id:petId})})
    .then(r=>{toast(`💊 +${r.healed} HP за ${fmt(r.price)} 🪙`); refreshCurrBar(); _g2Load();})
    .catch(e=>toast(e,false));
}
// ── Экран Боя 2.0 (общий для gates/abyss/war) ─────────────────────────────────
function _btRender(st, turn, reward){
  const b=el('mb'); if(!b) return;
  _btState=st; _btLock=false;
  const pet=st.pet, en=st.enemy;
  const bar=(v,m,cls)=>`<div class="bt-bar"><div class="bt-fill ${cls}" style="width:${Math.max(0,Math.min(100,m?v/m*100:0)).toFixed(0)}%"></div></div>`;
  const finished = st.status==='won'||st.status==='lost';
  let head='';
  if(st.status==='won'){
    let rw='';
    if(reward){
      if(reward.dark_mora!==undefined) rw=` +${reward.dark_mora} 🌑${reward.shards?` +${reward.shards} 💠`:''}`;
      else if(reward.split) rw=` +${reward.shards} 💠 (${reward.split.treasury} в казну${reward.boss_key?' · 🗝 ключ этажа':''})`;
      else if(reward.damage!==undefined) rw=` урон стене: ${fmt(reward.damage)}${reward.breached?' · 🏰 УЗЕЛ ЗАХВАЧЕН!':` (${fmt(reward.wall_total)}/${fmt(reward.wall_hp_max)})`}`;
    }
    head=`<div class="skg-head skg-won">🏆 ПОБЕДА!${rw}</div>`;
  } else if(st.status==='lost'){
    head=`<div class="skg-head skg-lost">☠️ Поражение. Питомца можно подлечить за 🪙.</div>`;
  }
  b.innerHTML=`
    ${head}
    <div class="bt-arena">
      <div class="bt-side">
        <div class="bt-name">${esc(pet.name||'Питомец')}</div>
        ${bar(pet.hp,pet.hp_max,'hp')}<div class="bt-num">${pet.hp}/${pet.hp_max} HP</div>
        ${bar(pet.st,pet.st_max,'st')}<div class="bt-num">${pet.st}/${pet.st_max} ⚡</div>
      </div>
      <div class="bt-vs">⚔️<div class="bt-wave">волна ${st.wave}/${st.waves_total}</div></div>
      <div class="bt-side">
        <div class="bt-name">${en.emoji||'👹'} ${esc(en.name||'Враг')}</div>
        ${bar(en.hp,en.hp_max,'hp en')}<div class="bt-num">${en.hp}/${en.hp_max} HP</div>
      </div>
    </div>
    ${finished?'':`<div class="bt-qte">${turn&&turn.grade?`<div class="bt-flash bt-flash-${turn.grade}"></div>`:''}<div class="bt-ring" id="bt-ring"></div><div class="bt-ring-core">🎯</div></div>`}
    <div class="bt-log">${(st.log||[]).slice(-5).map(l=>`<div>${esc(l)}</div>`).join('')}</div>
    ${finished
      ? `<button class="btn btn-gold btn-full" onclick="_btBack()">↩ Назад</button>`
      : `<div class="bt-stances">
          <button class="btn btn-red"   onclick="_btAct('attack',this)">⚔️ Атака</button>
          <button class="btn btn-teal"  onclick="_btAct('block',this)">🛡 Блок</button>
          <button class="btn btn-ghost" onclick="_btAct('focus',this)">🧘 Дух</button>
        </div>`}`;
  if(!finished) _btStartQte(st.qte);
}
function _btStartQte(q){
  const ring=el('bt-ring'); if(!ring||!q) return;
  ring.style.animation='none'; void ring.offsetWidth;
  ring.style.animation=`btRing ${q.ring_ms}ms linear forwards`;
  _btQteStart=Date.now();
  _btState._ringMs=q.ring_ms;
}
function _btAct(stance, btn){
  if(_btLock||!_btState) return;
  _btLock=true;
  // Сырой тайминг: |прошло − полное сжатие|; сервер сам грейдит (анти-чит там же)
  const elapsed=Date.now()-_btQteStart;
  const off=Math.abs(elapsed-(_btState._ringMs||1400));
  api('/combat2/battle/action',{method:'POST',body:JSON.stringify({battle_id:_btState.battle_id, stance, tap_offset_ms:off})})
    .then(r=>{
      const g=r.turn&&r.turn.grade;
      _haptic(g==='perfect'?'success':(g==='good'?'medium':'error'));
      if(r.status==='won'){_haptic('success'); refreshCurrBar();}
      if(r.status==='lost') _haptic('error');
      _btRender(r, r.turn, r.reward);
    })
    .catch(e=>{toast(e,false); _btLock=false;});
}
// ── Клановые Рейды (БЛОК19 Ч.6, замена PvP) ─────────────────────────────────────
let _raidData=null;
function loadRaid(){
  const host=el('rc'); if(host)host.innerHTML='<div class="loader">Загрузка...</div>';
  api('/combat/raid').then(d=>{_raidData=d;renderRaid();}).catch(e=>{if(el('rc'))el('rc').innerHTML=`<div class="err">${e}</div>`;});
}
function renderRaid(){
  const host=el('rc'); if(!host||!_raidData) return;
  if(!_raidData.in_clan){ host.innerHTML=`<div class="empty-state"><div class="es-icon">🛡</div><div class="es-title">Рейды — для кланов</div><div class="es-sub">Вступи в клан, чтобы бить боссов вместе.</div><button class="btn btn-gold btn-sm" style="margin-top:10px" onclick="openClansModal()">🛡 К кланам</button></div>`; return; }
  const raid=_raidData.raid;
  if(!raid){
    host.innerHTML=`<div class="card"><div class="card-title">👹 Клановый рейд</div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:10px">Сейчас рейда нет. Босс масштабируется по числу участников; награды — по вкладу урона.</div>
      ${_raidData.is_leader?`<button class="btn btn-gold btn-full" onclick="_raidStart()">👹 Запустить рейд</button>`:'<div class="cx-dim" style="font-size:11px">Рейд запускает лидер клана.</div>'}</div>`;
    return;
  }
  const pct=Math.max(0,Math.min(100,raid.hp_max?raid.hp/raid.hp_max*100:0));
  const pets=_raidData.pets||[];
  const petOpts=pets.map(p=>`<option value="${p.pet_id}">${esc(p.name||p.species_id)} · Ур.${p.level} · HP ${p.hp.toFixed(0)} · ⚔️${p.attack}</option>`).join('');
  const contribs=(_raidData.contribs||[]).map((c,i)=>`<div class="rd-crow"><span>${i+1}. ${unameLink(c.user_id,c.username,false)}</span><span class="rd-dmg">${fmt(Math.round(c.damage))} dmg</span></div>`).join('')||'<div class="cx-dim" style="font-size:11px">Пока никто не бил.</div>';
  const h=Math.floor((_raidData.ends_in||0)/3600), m=Math.floor(((_raidData.ends_in||0)%3600)/60);
  host.innerHTML=`<div class="rd-boss">
      <div class="rd-emoji">${raid.boss_emoji||'👹'}</div>
      <div class="rd-name">${esc(raid.boss_name)}</div>
      <div class="rd-hpbar"><div class="rd-hpfill" style="width:${pct.toFixed(1)}%"></div></div>
      <div class="rd-hplbl">${fmt(Math.round(raid.hp))} / ${fmt(Math.round(raid.hp_max))} HP · ${pct.toFixed(0)}% · ⏳ ${h}ч ${m}м</div>
    </div>
    ${pets.length?`<div class="rd-attack">
      <select id="raid-pet" class="num-input" style="margin:0;flex:1">${petOpts}</select>
      <button class="btn btn-gold btn-sm" onclick="_raidAttack()">⚔️ Атаковать</button>
    </div><div class="cx-dim" style="font-size:10px;margin:4px 0 8px">Питомец бьёт боссом и получает контр-урон (теряет HP). HP восстанавливается регеном/во Вратах.</div>`:'<div class="cx-dim" style="font-size:11px;padding:6px">Нет свободных боевых питомцев (заняты/0 HP).</div>'}
    <div class="looks-slot-t">🏅 Вклад клана</div><div class="rd-contribs">${contribs}</div>`;
}
function _raidStart(){ api('/combat/raid/start',{method:'POST',body:JSON.stringify({})}).then(r=>{toast(r.message);loadRaid();}).catch(e=>toast(e,false)); }
function _raidAttack(){ const id=parseInt((el('raid-pet')||{}).value)||0; if(!id){toast('Выбери питомца',false);return;} api('/combat/raid/attack',{method:'POST',body:JSON.stringify({pet_id:id})}).then(r=>{toast(r.message);refreshCurrBar();loadRaid();}).catch(e=>toast(e,false)); }
// openDuelChallenge / submitDuelChallenge — defined above in the loadDuels section

// doSpin and closeSpinResult defined above (no loadGacha to avoid overwriting result)

// ── Browser Notifications ─────────────────────────────────────────────────────
function requestBrowserNotif() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission().then(p => { if(p==='granted') toast('✅ Уведомления включены!'); });
  }
}
function browserNotif(title, body) {
  if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
    new Notification(title, {body, icon: './favicon.ico'});
  }
}
// Request permission when user first connects WS
// Override connectWS with browser notification support
function connectWS() {
  if (!_uid) return;
  requestBrowserNotif();
  // H6: WS требует аутентификации — WebApp шлёт initData, браузер — session-token
  const auth = INIT_DATA ? ('init='+encodeURIComponent(INIT_DATA))
                         : ('token='+encodeURIComponent(sess()||''));
  const wsUrl = BASE.replace('https://','wss://').replace('http://','ws://') + '/ws/'+_uid+'?'+auth;
  _ws = new WebSocket(wsUrl);
  _ws.onmessage = e => {
    const ev = JSON.parse(e.data);
    if(ev.type && ev.type.startsWith('lot_')){ _lotLiveOnEvent(ev); return; }  // R5: live-комната
    if(ev.type!=='pong') showWsNotif(ev);
  };
  _ws.onclose = () => { setTimeout(connectWS, 4000); };
  _ws.onerror = () => {};
}

// ── WS ping/pong — prevents Cloudflare 100s idle timeout ─────────────────────
setInterval(() => { if (_ws?.readyState === WebSocket.OPEN) _ws.send('ping'); }, 25000);

// ── R5 «Молот Аукциона»: live-комната финала лота ─────────────────────────────
// Открывается из openBidModal при remaining ≤ 10 мин: sub_lot по WS, тикающий
// таймер (дедлайн двигается на анти-снайп-продлениях), лента ставок/жаб, зрители.
// Ставки из БОТА в комнату не прилетают (WS-хаб в веб-процессе) — «Текущая
// ставка» в модалке гарантированно свежая только по site-ставкам.
let _lotLive = null;   // {lotId, deadline, timer}
function _wsSend(obj){ try{ if(_ws && _ws.readyState===WebSocket.OPEN) _ws.send(JSON.stringify(obj)); }catch(e){} }
function lotLiveJoin(lotId, remSec){
  lotLiveLeave();
  _lotLive = {lotId, deadline: Date.now()+remSec*1000, timer: setInterval(_lotLiveTick, 500)};
  _wsSend({type:'sub_lot', lot_id: lotId});
  _lotLiveTick();
}
function lotLiveLeave(){
  if(!_lotLive) return;
  clearInterval(_lotLive.timer);
  _wsSend({type:'unsub_lot', lot_id:_lotLive.lotId});
  _lotLive = null;
}
function _lotLiveTick(){
  if(!_lotLive) return;
  const t = el('lot-live-timer');
  if(!t){ lotLiveLeave(); return; }   // модалку закрыли мимо CM — самоочистка
  const s = Math.max(0, Math.floor((_lotLive.deadline - Date.now())/1000));
  t.textContent = Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
  t.style.color = s<=60 ? 'var(--red)' : '';
  if(s<=0){ t.textContent='ФИНИШ'; clearInterval(_lotLive.timer); }
}
// EPIC3: анти-снайп продлил лот — вспышка на таймере, чтобы это было заметно
// без необходимости следить за секундами глазами.
function _lotLiveFlashTimer(){
  const t = el('lot-live-timer');
  if(!t) return;
  t.classList.remove('flash-gold'); void t.offsetWidth;   // рестарт анимации, если уже шла
  t.classList.add('flash-gold');
  setTimeout(()=>t.classList.remove('flash-gold'), 650);
}
// EPIC3: летящий вверх эмодзи-реакция — своя (оптимистично, сразу по клику) и
// чужие (по приходу lot_react из WS). Элемент убирается из DOM после анимации.
function _lotLiveSpawnFly(emoji){
  const host = el('lot-live-fly');
  if(!host) return;
  const s = document.createElement('span');
  s.className = 'fly-emoji';
  s.textContent = emoji || '🐸';
  s.style.left = (10 + Math.random()*70) + '%';
  host.appendChild(s);
  s.addEventListener('animationend', () => s.remove());
  setTimeout(() => s.remove(), 2000);   // страховка, если animationend не пришёл
}
function _lotLiveFeedAdd(html){
  const f = el('lot-live-feed');
  if(!f) return;
  const d = document.createElement('div');
  d.className = 'lot-live-row';
  d.innerHTML = html;
  f.prepend(d);
  while(f.children.length > 8) f.removeChild(f.lastChild);
}
function _lotLiveOnEvent(ev){
  if(!_lotLive || ev.lot_id !== _lotLive.lotId) return;
  if(ev.type === 'lot_bid'){
    if(typeof ev.remaining_sec === 'number') _lotLive.deadline = Date.now()+ev.remaining_sec*1000;
    const cur = el('lot-live-cur');
    if(cur) cur.textContent = fmt(ev.amount)+' 🪙';
    const inp = el('bid-val');
    if(inp){ const mn = Math.ceil(ev.amount*1.05)+1; inp.min = mn; if(parseFloat(inp.value||0) < mn) inp.value = mn; }
    _lotLiveFeedAdd(`💰 <b>@${esc(ev.bidder_name||'Игрок')}</b> — ${fmt(ev.amount)} 🪙${ev.extended?' <span style="color:var(--gold2)">+60с ⏱</span>':''}${ev.is_buyout?' <span style="color:var(--red)">⚡ ВЫКУП</span>':''}`);
    if(typeof ev.viewers === 'number'){ const v = el('lot-live-viewers'); if(v) v.textContent = '👁 '+ev.viewers; }
    if(ev.extended) _lotLiveFlashTimer();
    _haptic('medium');
    _lotLiveTick();
  } else if(ev.type === 'lot_viewers'){
    const v = el('lot-live-viewers');
    if(v) v.textContent = '👁 '+ev.viewers;
  } else if(ev.type === 'lot_react'){
    _lotLiveFeedAdd(`<span class="lot-live-frog">${esc(ev.emoji||'🐸')}</span> зритель квакает`);
    if(ev.from !== _uid) _lotLiveSpawnFly(ev.emoji);   // своя уже улетела оптимистично
  }
}
function lotLiveReact(){
  if(!_lotLive) return;
  _wsSend({type:'lot_react', lot_id:_lotLive.lotId, emoji:'🐸'});
  _lotLiveSpawnFly('🐸');
  _haptic('light');
}

// ── Marriage card (в дашборде Обзор) ──────────────────────────────────────────
// Рендерит в #pro-marriage-card. Развод/банк/предложения — прямо внутри карточки
// (Закон близости: действие рядом с объектом).
function loadMarriageCard() {
  const host = el('pro-marriage-card');
  if(!host) return;
  Promise.all([api('/marriage/'), api('/marriage/proposals')]).then(([m, pr])=>{
    const proposals = pr.proposals || [];
    let propHtml = '';
    if(proposals.length) {
      propHtml = `<div class="card" style="border-color:var(--gold)">
        <div class="card-title">💌 Предложения руки и сердца (${proposals.length})</div>
        ${proposals.map(p=>`<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border2)">
          <div>
            <span style="font-weight:600">@${vipName(p.proposer_name||'ID'+p.proposer_id, p.proposer_is_vip)}</span>
            <span style="font-size:10px;color:var(--muted);margin-left:6px">${new Date(p.proposed_at).toLocaleDateString('ru')}</span>
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn btn-sm btn-gold" onclick="acceptProposal(${p.id},this)">✅ Принять</button>
            <button class="btn btn-sm btn-ghost" onclick="declineProposal(${p.id},this)">❌</button>
          </div>
        </div>`).join('')}
      </div>`;
    }
    if(!m.married){
      // Empty state с CTA (заповедь 5)
      host.innerHTML=propHtml+`<div class="card">
        <div class="empty-state">
          <div class="es-icon">💔</div>
          <div class="es-title">Вы не в браке</div>
          <div class="es-sub">Свяжите судьбу с другим игроком — напишите в чате<br><code>бот брак, @username</code></div>
        </div>
      </div>`;
      return;
    }
    const pets=m.family_pets||[];
    host.innerHTML=propHtml+`
      <div class="card card-gold">
        <div class="card-title">💍 Брак</div>
        <div style="text-align:center;padding:4px 0 12px">
          <div style="font-size:28px;margin-bottom:6px">💍</div>
          <div style="font-size:15px;font-weight:700;color:var(--bright)">${vipName(m.partner_name||'Партнёр', m.partner_is_vip)}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:3px">Вместе ${m.days} дней</div>
        </div>
        ${(()=>{
          const fb=[['🪙',m.family_balance,'mora'],['💎',m.family_balance_diamonds,'diamonds'],['🌑',m.family_balance_dark_mora,'dark_mora'],['✨',m.family_balance_zarniki,'zarniki']];
          const shown=fb.filter(([ic,v,cur])=>(v||0)>0||cur==='mora').map(([ic,v])=>`${ic} ${fmt(v||0)}`).join(' · ');
          return `<div class="irow"><span class="ik">Семейный кошелёк</span><span style="color:var(--gold);font-weight:700">${shown}</span></div>`;
        })()}
        <div style="display:flex;gap:6px;margin-top:10px">
          <input id="bank-amt" type="number" class="num-input" style="margin:0;flex:1" placeholder="Сумма" min="1"/>
          <select id="bank-cur" class="num-input" style="margin:0;flex:none;width:64px">
            <option value="mora">🪙</option><option value="diamonds">💎</option>
            <option value="dark_mora">🌑</option><option value="zarniki">✨</option>
          </select>
        </div>
        <div style="display:flex;gap:7px;margin-top:6px">
          <button class="btn btn-sm btn-gold" style="flex:1" onclick="familyBank('deposit')">📥 Вложить</button>
          <button class="btn btn-sm btn-ghost" style="flex:1" onclick="familyBank('withdraw')">📤 Забрать</button>
        </div>
        <button class="btn btn-sm btn-ghost btn-full" style="margin-top:8px" onclick="openPartnerGifts()">🎁 Подарить партнёру</button>
        ${(m.received_gifts&&m.received_gifts.length)?`<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border2)">
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">🎁 Подарки от партнёра</div>
          ${m.received_gifts.map(g=>`<div class="irow"><span class="ik">${esc(g.name)}</span><span class="iv" style="font-size:10px">${(g.sent_at||'').slice(0,10)}</span></div>`).join('')}
        </div>`:''}
        ${pets.length?`<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border2)">
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">🐾 Питомцы семьи (${pets.length})</div>
          ${pets.map(p=>`<div class="irow"><span class="ik">${p.name||p.species_id} ${rc(p.rarity)}</span><span class="iv">Lv${p.pet_level} · ${PL[p.placement]||p.placement}</span></div>`).join('')}
        </div>`:''}
        <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border2)">
          <button class="btn btn-red btn-full" style="margin:0" onclick="confirmDivorce()">💔 Развестись</button>
        </div>
      </div>`;
    host._mid=m.marriage_id;
  }).catch(e=>{host.innerHTML=`<div class="card"><div class="err">${e}</div></div>`;});
}
function familyBank(action) {
  const v=parseFloat(el('bank-amt')?.value||0);
  if(!v||v<=0){toast('Введите сумму.',false);return;}
  const cur=el('bank-cur')?.value||'mora';
  const mid=el('pro-marriage-card')?._mid;
  if(!mid){toast('Нет данных о браке.',false);return;}
  api('/marriage/bank',{method:'POST',body:JSON.stringify({marriage_id:mid,amount:v,action,currency:cur})})
    .then(r=>{toast(`✅ ${r.message}`);refreshCurrBar();loadMarriageCard();})
    .catch(e=>toast(e,false));
}
function confirmDivorce() {
  OM('💔 Развод','<div style="text-align:center;padding:12px 0;color:var(--muted)">Вы уверены? Брак будет расторгнут <b style="color:var(--red)">безвозвратно</b>. Семейный банк будет разделён.</div>',[
    {l:'Да, развестись',c:'btn-red',f:'doDivorce()'},
    {l:'Отмена',c:'btn-ghost',f:'CM()'},
  ]);
}
function doDivorce() {
  api('/marriage/divorce',{method:'POST'})
    .then(()=>{toast('💔 Развод оформлен.');CM();loadMarriageCard();})
    .catch(e=>toast(e,false));
}
function acceptProposal(id,btn) {
  btn.disabled=true;
  api('/marriage/proposals/accept',{method:'POST',body:JSON.stringify({proposal_id:id})})
    .then(()=>{toast('💍 Брак заключён!');loadMarriageCard();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}
function declineProposal(id,btn) {
  btn.disabled=true;
  api('/marriage/proposals/decline',{method:'POST',body:JSON.stringify({proposal_id:id})})
    .then(()=>{toast('Предложение отклонено.');loadMarriageCard();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

// ── Подарки партнёру (Block 5.4 на вебе — паритет с ботом «бот подарки») ───────
const _GIFT_CUR_ICON = {mora:'🪙', diamonds:'💎', zarniki:'✨'};
function openPartnerGifts() {
  OM('🎁 Подарок партнёру','<div style="text-align:center;padding:16px 0;color:var(--muted)">Загрузка…</div>',
     [{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
  api('/marriage/gifts').then(r=>{
    const gifts=r.gifts||[];
    if(!gifts.length){el('mb').innerHTML='<div style="text-align:center;padding:14px 0;color:var(--muted)">Подарков нет.</div>';return;}
    const rows=gifts.map(g=>{
      const ic=_GIFT_CUR_ICON[g.currency]||'';
      const tag=g.kind==='buff'
        ? `<span style="color:var(--gold2)">✨ +${Math.round((g.buff_value||0)*100)}% XP · ${g.buff_hours}ч партнёру</span>`
        : `<span style="color:var(--muted)">🎀 знак внимания</span>`;
      return `<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px solid var(--border2)">
        <div style="min-width:0">
          <div style="font-weight:600">${esc(g.name)}</div>
          <div style="font-size:10px;margin-top:2px">${tag}</div>
        </div>
        <button class="btn btn-sm btn-gold" style="flex:none" onclick="buyPartnerGift('${g.id}',this)">${fmt(g.price)} ${ic}</button>
      </div>`;
    }).join('');
    el('mb').innerHTML=`<div style="font-size:11px;color:var(--muted);margin-bottom:6px">Подарок вручается вашему супругу. Баф-подарки дают партнёру +XP на время.</div>${rows}`;
  }).catch(e=>{el('mb').innerHTML=`<div class="err">${e}</div>`;});
}
function buyPartnerGift(id,btn) {
  if(btn) btn.disabled=true;
  api('/marriage/gift',{method:'POST',body:JSON.stringify({gift_id:id})})
    .then(r=>{toast(`🎁 ${r.gift_name} вручён партнёру! 💖`);refreshCurrBar();CM();loadMarriageCard();})
    .catch(e=>{toast(e,false);if(btn) btn.disabled=false;});
}
// Коробка «подарок от супруга» — получателю (WS онлайн / web_notifications офлайн)
function showPartnerGift(payloads) {
  const p=(payloads&&payloads[0])||{};
  const who=p.from?('@'+esc(p.from)):'Ваш супруг';
  OM('💖 Подарок от супруга!',
    `<div style="text-align:center;font-size:46px;margin:2px 0 10px;animation:floaty 1.6s ease-in-out infinite">${esc(p.gift_name||'🎁')}</div>
     <div style="text-align:center;font-size:14px;font-weight:700;color:var(--bright)">${who}</div>
     <div style="text-align:center;font-size:12px;color:var(--gold2);margin-top:4px">${esc(p.msg||'подарил(а) вам подарок')}</div>`,
    [{l:'💖 Спасибо!', c:'btn-gold', f:'CM();_nextModal()'}]);
}

// ── Wallet mini — свёрнутая история транзакций внизу дашборда Профиля ────────────
let _walletMiniExpanded = false;
let _walletMiniTxs = [];
function loadWalletMini() {
  const host = el('wallet-mini');
  if(!host) return;
  host.innerHTML='<div class="sk" style="height:44px;border-radius:var(--r)"></div>';
  api('/wallet/history').then(txs=>{
    _walletMiniTxs = txs;
    _walletMiniExpanded = false;
    _renderWalletMini();
  }).catch(()=>{ if(el('wallet-mini')) el('wallet-mini').innerHTML=''; });
}
function toggleWalletMini() { _walletMiniExpanded=!_walletMiniExpanded; _renderWalletMini(); }
function _renderWalletMini() {
  const host = el('wallet-mini');
  if(!host) return;
  if(!_walletMiniTxs.length){
    host.innerHTML=`<div class="card"><div class="card-title">💳 История операций</div>
      <div class="cx-dim" style="font-size:11px;padding:6px 0">Пока пусто — здесь появится история, как только пройдёт первая покупка, поход или обмен.</div></div>`;
    return;
  }
  const show = _walletMiniExpanded ? _walletMiniTxs : _walletMiniTxs.slice(0,4);
  // ШАГ1: формат «Было → Изменение → Стало (причина)». Было = Стало − Изменение.
  const fmtTx = t => {
    const line = (delta, after, icon) => {
      if(!delta) return '';
      const before = after - delta, sign = delta>0?'+':'';
      const col = delta>0?'var(--green)':'var(--red)';
      return `<div class="wtx-line">
        <span class="wtx-was">${fmtF(before)} ${icon}</span><span class="wtx-arrow">→</span>
        <span class="wtx-delta" style="color:${col}">${sign}${fmtF(delta)} ${icon}</span><span class="wtx-arrow">→</span>
        <span class="wtx-now">Итог ${fmtF(after)} ${icon}</span></div>`;
    };
    const lines = [line(t.delta_mora,t.mora_after,'🪙'),
                   line(t.delta_diamonds,t.diamonds_after,'💎'),
                   line(t.delta_zarniki,t.zarniki_after,'✨'),
                   line(t.delta_dark_mora,t.dark_mora_after,'🌑')].filter(Boolean).join('');
    return `<div class="wtx">
      <div class="wtx-head"><span class="wtx-label">${t.label}</span><span class="wtx-time">${fmtUTC(t.created_at)}</span></div>
      ${lines}
      ${t.note?`<div class="wtx-note">${esc(t.note)}</div>`:''}
    </div>`;
  };
  host.innerHTML=`<div class="card">
    <div class="card-title">💳 История операций</div>
    ${show.map(fmtTx).join('')}
    ${_walletMiniTxs.length>4?`<button class="btn btn-ghost btn-sm btn-full" style="margin-top:6px" onclick="toggleWalletMini()">${_walletMiniExpanded?'▲ Свернуть':'▼ Показать все ('+_walletMiniTxs.length+')'}</button>`:''}
  </div>`;
}

// ── Daily Deal ────────────────────────────────────────────────────────────────
let _dealRefreshAt = null, _dealTimerInterval = null;
function loadDeal() {
  el('mkt-deal').innerHTML='<div class="loader">Загрузка...</div>';
  api('/daily-deal/').then(d=>{
    _dealRefreshAt = d.refreshes_at;
    const deals = d.deals||[];
    el('mkt-deal').innerHTML=`
      <div style="background:var(--gold-dim);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-bottom:12px;text-align:center">
        <div style="font-size:11px;color:var(--gold);text-transform:uppercase;letter-spacing:1px">Акция обновится через</div>
        <div id="deal-timer" style="font-size:20px;font-weight:700;color:var(--gold2);font-family:monospace">--:--:--</div>
      </div>
      <div class="balrow">
        <div class="bal"><div class="bv">🪙 ${fmt(d.mora)}</div><div class="bl">Мора</div></div>
        <div class="bal"><div class="bv">💎 ${d.diamonds.toFixed(1)}</div><div class="bl">Алмазы</div></div>
      </div>
      ${deals.length?'<div class="card"><div class="card-title">🏷 Предложения сегодня</div>'+
        deals.map(deal=>{
          const priceVal = deal.price_mora?deal.price_mora:deal.price_diamonds?deal.price_diamonds:0;
          const priceIcon = deal.price_mora?'🪙':deal.price_diamonds?'💎':'';
          const price = priceVal?`${fmt(priceVal)} ${priceIcon}`:'—';
          const purchased=deal.purchased===true;
          const haveVal = deal.price_mora?d.mora:deal.price_diamonds?d.diamonds:0;
          const afford = purchased || haveVal >= priceVal;
          return `<div class="shop-row">
            <div class="shop-icon">${(deal.item_name||'?').split(' ')[0]}</div>
            <div class="shop-info">
              <div class="shop-name">${deal.item_name||'?'} ${deal.quantity>1?'×'+deal.quantity:''}</div>
              <div class="shop-price">${price}</div>
              <div class="shop-desc">${deal.item_description||''}</div>
            </div>
            <button class="btn btn-sm ${purchased?'btn-ghost':(afford?'btn-gold':'btn-ghost')}" ${purchased?'disabled':''} onclick="buyDeal(${deal.slot},this)">
              ${purchased?'✓ Куплено':(afford?`Купить за ${price}`:`Нужно ${price}`)}
            </button>
          </div>`;
        }).join('')+'</div>'
      :'<div class="loader">Акций нет.</div>'}
      <div id="mkt-showcase"></div>`;
    startDealTimer();
    loadShowcase();
  }).catch(e=>{el('mkt-deal').innerHTML=`<div class="err">${e}</div>`;});
}
// ── R4.2: Витрина недели — 5 тёмных карточек косметики со скидкой 10–30% ───────
// Тайна до тапа: слот+цвет редкости видны, предмет и цена — после reveal (сервер).
function loadShowcase(){
  const box=el('mkt-showcase'); if(!box) return;
  api('/showcase/').then(d=>{
    const slots=d.slots||[];
    if(!slots.length){box.innerHTML='';return;}
    const days=Math.floor((d.rotates_in_sec||0)/86400), hrs=Math.floor(((d.rotates_in_sec||0)%86400)/3600);
    box.innerHTML=`<div class="card">
      <div class="card-title">🃏 Витрина недели <span style="float:right;font-size:10px;font-weight:400;color:var(--muted)">обновится через ${days}д ${hrs}ч</span></div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:8px">5 случайных предметов косметики со скидкой 10–30%. Нажми на карту, чтобы узнать, что внутри. Одна покупка каждой карты в неделю.</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
        ${slots.map(s=>_showcaseCard(s)).join('')}
      </div>
    </div>`;
  }).catch(()=>{box.innerHTML='';});
}
function _showcaseCard(s){
  const slotIcons={name_glow:'✨',avatar_frame:'🖼',title:'🏷',avatar_halo:'🌟',profile_bg:'🖌',card_fx:'❄️'};
  const icon=slotIcons[s.slot]||'🎁';
  if(!s.revealed){
    return `<div class="looks-card r-${s.rarity}" onclick="_showcaseReveal(${s.slot_idx},this)"
      style="cursor:pointer;text-align:center;padding:14px 6px;background:linear-gradient(135deg,var(--bg2),var(--dim))">
      <div style="font-size:26px;filter:grayscale(1) brightness(.6)">${icon}</div>
      <div style="font-size:16px;margin:4px 0;color:var(--muted)">❓</div>
      <div class="lc-rar" style="font-size:9px">${rarLabel(s.rarity)}</div>
    </div>`;
  }
  const bought=s.purchased;
  const afford = bought || (_profileData?.zarniki||0) >= s.price;
  return `<div class="looks-card r-${s.rarity}" style="text-align:center;padding:10px 6px">
    <div style="font-size:20px">${icon}</div>
    <div style="font-size:10.5px;font-weight:600;margin:3px 0;line-height:1.25">${esc(s.name||'')}</div>
    <div style="font-size:10px"><s style="color:var(--muted)">${s.price_base}✨</s>
      <b style="color:var(--gold2)">${s.price}✨</b>
      <span style="color:var(--green)">−${s.discount_pct}%</span></div>
    <button class="btn btn-sm ${bought?'btn-ghost':(afford?'btn-gold':'btn-ghost')}" style="margin-top:5px;width:100%" ${bought?'disabled':''}
      onclick="_showcaseBuy(${s.slot_idx},this)">${bought?'✓ Куплено':(afford?`Купить за ${s.price}✨`:`Нужно ${s.price}✨`)}</button>
  </div>`;
}
function _showcaseReveal(idx,card){
  if(card) card.style.opacity='.5';
  api('/showcase/reveal',{method:'POST',body:JSON.stringify({slot_idx:idx})})
    .then(()=>loadShowcase())
    .catch(e=>{toast(e,false);if(card)card.style.opacity='1';});
}
function _showcaseBuy(idx,btn){
  if(btn){btn.disabled=true;btn.textContent='...';}
  api('/showcase/buy',{method:'POST',body:JSON.stringify({slot_idx:idx})})
    .then(r=>{toast(r.message||'🎨 Куплено!');loadShowcase();})
    .catch(e=>{toast(e,false);loadShowcase();});
}
function startDealTimer() {
  if(_dealTimerInterval) clearInterval(_dealTimerInterval);
  if(!_dealRefreshAt) return;
  const tick=()=>{
    const t=el('deal-timer');if(!t){clearInterval(_dealTimerInterval);return;}
    const diff=Math.max(0,Math.floor((new Date(_dealRefreshAt)-Date.now())/1000));
    if(diff<=0){t.textContent='Скоро обновится...';clearInterval(_dealTimerInterval);return;}
    const h=Math.floor(diff/3600),m=Math.floor((diff%3600)/60),s=diff%60;
    t.textContent=`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  };
  tick();
  _dealTimerInterval=setInterval(tick,1000);
}
function buyDeal(dealId,btn) {
  btn.disabled=true;
  btn.textContent='...';
  api('/daily-deal/buy',{method:'POST',body:JSON.stringify({deal_id:dealId})})
    .then(r=>{
      btn.textContent='✓ Куплено';
      btn.className='btn btn-ghost btn-sm';
      toast(`✅ Куплено +${r.qty}× предмет!`);
      refreshCurrBar();
    })
    .catch(e=>{toast(e,false);btn.disabled=false;btn.textContent='Купить';});
}

// ── Promo code (модалка из шапки Магазина) ────────────────────────────────────
function openPromoModal() {
  OM('🎫 Промокод', `
    <div style="font-size:12px;color:var(--muted);margin-bottom:10px;line-height:1.5">
      Введите промокод. Каждый код — одноразовый.<br>
      <span style="color:var(--gold);font-size:11px">💡 Коды публикуются в официальных чатах и анонсах бота.</span>
    </div>
    <input id="promo-input" type="text" class="num-input"
           placeholder="ПРОМОКОД" style="text-transform:uppercase;margin:0"
           oninput="this.value=this.value.toUpperCase()"/>
    <div id="promo-result" style="margin-top:8px"></div>
  `, [
    {l:'🎫 Активировать', c:'btn-gold', f:'redeemPromo(this)'},
    {l:'Закрыть', c:'btn-ghost', f:'CM()'},
  ]);
}
function redeemPromo(btn) {
  const code=el('promo-input')?.value?.trim();
  if(!code){toast('Введите промокод.',false);return;}
  btn.disabled=true;
  api('/promo/redeem',{method:'POST',body:JSON.stringify({code})})
    .then(r=>{
      el('promo-input').value='';
      const rw=r.reward||{};
      const rewards=[];
      if(rw.mora>0)    rewards.push(`<span style="color:var(--gold);font-size:22px;font-weight:800">+${fmt(rw.mora)} 🪙</span>`);
      if(rw.diamonds>0)rewards.push(`<span style="color:var(--blue);font-size:22px;font-weight:800">+${rw.diamonds} 💎</span>`);
      if(rw.dark_mora>0)rewards.push(`<span style="color:var(--muted);font-size:22px;font-weight:800">+${fmt(rw.dark_mora)} 🌑</span>`);
      if(rw.zarniki>0) rewards.push(`<span style="color:var(--bright);font-size:22px;font-weight:800">+${rw.zarniki} ✨</span>`);
      if(rw.items&&Object.keys(rw.items).length){
        for(const[id,q] of Object.entries(rw.items)) rewards.push(`<span style="font-size:16px">+${q}× ${id}</span>`);
      }
      const desc=rw.description?`<div style="font-size:11px;color:var(--muted);margin-top:6px">${rw.description}</div>`:'';
      el('promo-result').innerHTML=`
        <div style="background:var(--s);border:1px solid var(--border);border-radius:var(--r);padding:16px;text-align:center;animation:fadeIn .4s ease">
          <div style="font-size:24px;margin-bottom:6px">🎉</div>
          <div style="font-size:13px;font-weight:700;color:var(--green);margin-bottom:10px">Промокод активирован!</div>
          <div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-bottom:8px">${rewards.join('')}</div>
          ${desc}
          <div style="font-size:10px;color:var(--dim);margin-top:8px">Код: <code>${rw.code||code}</code></div>
        </div>`;
      refreshCurrBar();
    })
    .catch(e=>{
      el('promo-result').innerHTML=`<div class="err">${e}</div>`;
    })
    .finally(()=>{btn.disabled=false;});
}

// ── Exchange Zarniki → Mora/Diamonds (Implementation Block 1.3) ───────────────
function openExchangeZarnikiModal() {
  const zar = Math.floor(_profileData?.zarniki || 0);
  OM('🔄 Обмен Зарников', `
    <div style="font-size:12px;color:var(--muted);margin-bottom:10px;line-height:1.5">
      Баланс: <b style="color:var(--bright)">${zar} ✨</b><br>
      Курс: 1✨ = 150 🪙  ·  1✨ = 0.05 💎 (20✨ = 1💎)<br>
      <span style="color:var(--gold);font-size:11px">⚠️ Обмен необратим.</span>
    </div>
    <input id="exch-zar-amount" type="number" class="num-input" min="1" max="${zar}" step="1"
           placeholder="Сколько ✨ обменять" style="margin:0"/>
    <div style="display:flex;gap:8px;margin-top:8px">
      <button class="btn btn-sm btn-gold" style="flex:1" onclick="doExchangeZarniki('mora')">→ 🪙 Мора</button>
      <button class="btn btn-sm btn-gold" style="flex:1" onclick="doExchangeZarniki('diamonds')">→ 💎 Алмазы</button>
    </div>
    <div id="exch-zar-result" style="margin-top:8px"></div>
  `, [
    {l:'Закрыть', c:'btn-ghost', f:'CM()'},
  ]);
}
function doExchangeZarniki(to) {
  const amount = parseFloat(el('exch-zar-amount')?.value);
  if(!amount || amount<=0){ toast('Укажи количество ✨', false); return; }
  api('/wallet/exchange-zarniki', {method:'POST', body:JSON.stringify({amount, to})})
    .then(r=>{
      el('exch-zar-result').innerHTML = `<div style="color:var(--green);font-size:12px">${r.message}</div>`;
      loadProfile();
    })
    .catch(e=>{
      el('exch-zar-result').innerHTML = `<div class="err">${e}</div>`;
    });
}

// ── switchPro — Профиль: Обзор / Инвентарь / Темы / Квесты / Ачивки / Топ ───────
// Брак и Ник — карточки в Обзоре. История кошелька — свёрнутая секция внизу Обзора.
let _invSubTab = 'items';
function switchPro(tab, btn) {
  _proTab = tab;
  document.querySelectorAll('#pg-profile > .tabs > .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  ['main','inv','themes','quests','ach','hof'].forEach(t=>{ const d=el('pro-'+t); if(d) d.style.display=t===tab?'':'none'; });
  // inv/quests/hof делегируют трекинг своим дочерним функциям (swInv/swQuests/switchTop)
  if(tab==='main'||tab==='themes'||tab==='ach') _trackSubtab('profile/'+tab);
  if(tab==='main') loadProfile();
  else if(tab==='inv') swInv(_invSubTab, document.querySelector('#pro-inv .tab-inner .tb'));
  else if(tab==='themes') loadThemes();
  else if(tab==='quests') swQuests(_questsTab, document.querySelector(`#pro-quests .tab-inner .tb[onclick*="'${_questsTab}'"]`) || document.querySelector('#pro-quests .tab-inner .tb'));
  else if(tab==='ach') loadAch();
  else if(tab==='hof') switchTop('local', document.querySelector('#pro-hof .tab-inner .tb'));
}
function swInv(sub, btn) {
  _invSubTab = sub;
  document.querySelectorAll('#pro-inv .tab-inner .tb').forEach(b=>b.classList.remove('active'));
  const safeBtn = btn || document.querySelector(`#pro-inv .tab-inner .tb[onclick*="'${sub}'"]`) || document.querySelector('#pro-inv .tab-inner .tb');
  if(safeBtn) safeBtn.classList.add('active');
  el('inv-items').style.display = sub==='items' ? '' : 'none';
  el('inv-craft').style.display = sub==='craft' ? '' : 'none';
  _trackSubtab('profile/inv/'+sub);
  if(sub==='items') loadInventory(); else loadCraft();
}

// ── swMkt — Магазин: Гача / Премиум / Расходники / Акции дня ─────────────────────
// Промокод — модалка (кнопка в шапке Магазина). Аукцион/Обмен → pg-auction.
function swMkt(tab, _btn) {
  const btn = _btn || document.querySelector(`#pg-market > .tabs > .tb[onclick*="'${tab}'"]`) || document.querySelector('#pg-market > .tabs > .tb');
  _mktTab = tab;
  document.querySelectorAll('#pg-market > .tabs > .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const bd = el('balrow'); if(bd) bd.style.display = (tab === 'goods') ? 'flex' : 'none';
  ['vip','gacha','goods','deal'].forEach(t=>{ const d=el(t==='goods'?'mkt-goods':'mkt-'+t); if(d) d.style.display=t===tab?'':'none'; });
  _trackSubtab('market/'+tab);
  ({vip:loadVip, gacha:loadGacha, goods:loadMarketGoods, deal:loadDeal}[tab]||loadGacha)();
}

// ── swGoods — Расходники: 🛒 Обычный (Магазин) / 🌑 Тёмный (Чёрный Рынок) ────────
let _goodsTab='shop';
function swGoods(sub, btn) {
  _goodsTab = sub;
  document.querySelectorAll('#mkt-goods .tabs .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  el('mkt-shop').style.display = sub==='shop' ? '' : 'none';
  el('mkt-dark').style.display = sub==='dark' ? '' : 'none';
  el('balrow').style.display='flex';
  _trackSubtab('market/goods/'+sub);
  if(sub==='shop') loadShopCatalog(); else loadDarkMora();
}
function loadMarketGoods() {
  swGoods(_goodsTab, document.querySelector(`#mkt-goods .tabs .tb[onclick*="'${_goodsTab}'"]`));
}
// Шорткат "Чёрный Рынок" из карточек предметов — открыть Расходники сразу на Тёмном
function goToDarkMora() { _goodsTab='dark'; goTo('market','goods'); }

// ── swAuction — Аукцион & Обменник ──────────────────────────────────────────────
let _aucTab='auc';
function swAuction(tab, btn) {
  _aucTab = tab;
  document.querySelectorAll('#pg-auction .tb').forEach(b=>b.classList.remove('active'));
  btn = btn || document.querySelector(`#pg-auction .tb[onclick*="'${tab}'"]`);
  if(btn) btn.classList.add('active');
  el('mkt-auc').style.display = tab==='auc' ? '' : 'none';
  el('mkt-exch').style.display = tab==='exch' ? '' : 'none';
  const cx=el('mkt-crypto'); if(cx) cx.style.display = tab==='crypto' ? '' : 'none';
  _trackSubtab('auction/'+tab);
  if(tab==='auc') loadAuction(0); else if(tab==='exch') loadExchange(); else loadCrypto();
}
function loadAuctionPage() { swAuction(_aucTab, document.querySelector(`#pg-auction .tb[onclick*="'${_aucTab}'"]`)); }

// ── swQuests — Квесты & Стрик (под-вкладки внутри про-квесты в Профиле) ─────────
let _questsTab='quests';
function swQuests(tab, btn) {
  _questsTab = tab;
  document.querySelectorAll('#pro-quests .tab-inner .tb').forEach(b=>b.classList.remove('active'));
  const safeBtn = btn || document.querySelector(`#pro-quests .tab-inner .tb[onclick*="'${tab}'"]`) || document.querySelector('#pro-quests .tab-inner .tb');
  if(safeBtn) safeBtn.classList.add('active');
  el('quests-content').style.display = tab==='quests' ? '' : 'none';
  el('pro-streak').style.display = tab==='streak' ? '' : 'none';
  _trackSubtab('profile/quests/'+tab);
  if(tab==='quests') loadQuests(); else loadStreak();
}

// ── Auto-refresh ──────────────────────────────────────────────────────────────
setInterval(()=>{if(_loaded.has('profile'))loadProfile();},300000);
setInterval(()=>{if(_loaded.has('zoo'))api('/zoo/expeditions').then(d=>renderExps(d)).catch(()=>{});},30000);

// ── Dust modal ────────────────────────────────────────────────────────────────
function _showDustModal(did) {
  if(!_zooData?.pets?.length){toast('У вас нет питомцев.',false);return;}
  const dusts={'star_dust_s':'+1 дубл.','star_dust_l':'+5 дубл.'};
  OM('✨ Применить '+dusts[did],
    _zooData.pets.map(p=>`<div class="fopt" onclick="doApplyDust('${did}',${p.id},this)">
      <span class="fn">${p.name||p.species_id}</span>
      <span style="font-size:11px;color:var(--muted)">${rc(p.rarity)} Lv${p.pet_level||1} · ${p.placement==='storage'?'📦':p.placement==='active'?'⚔️':'🛡'}</span>
    </div>`).join(''),
    [{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}

// ── Pet modal: applicable items section ───────────────────────────────────────
function renderPetItems(petId, petData) {
  const dustItems = (_invData||[]).filter(i=>i.item_id.startsWith('star_dust') && i.quantity>0);
  if(!dustItems.length) return '';
  return `<div class="card-title" style="margin-top:14px">📦 Применить предмет</div>
    ${dustItems.map(i=>`<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border2)">
      <div>
        <span style="font-size:13px;font-weight:600">${i.name}</span>
        <span style="font-size:10px;color:var(--muted);margin-left:6px">×${i.quantity}</span>
      </div>
      <button class="btn btn-sm btn-gold" onclick="doApplyDustFromPetModal('${i.item_id}',${petId},this)">Применить</button>
    </div>`).join('')}`;
}
function doApplyDustFromPetModal(did,pid,btn) {
  btn.disabled=true;
  api('/inventory/apply-dust',{method:'POST',body:JSON.stringify({dust_id:did,pet_id:pid,chat_id:_cid})})
    .then(r=>{toast(`✅ +${r.duplicates_added} дубл. добавлено!`);CM();_zooData=null;loadInventory();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

// ── Profile Settings ──────────────────────────────────────────────────────────
// ── Nickname card (в дашборде Обзор) ──────────────────────────────────────────
// Рендерит в #pro-nick-card. Без активного чата карточка просто не показывается.
function loadNickCard() {
  const c=el('pro-nick-card');
  if(!c) return;
  // Prefer the chat mini-app was opened from (_initChatId); fall back to first chat from API
  const chatId=_initChatId||_cid||0;
  if(!chatId){ c.innerHTML=''; return; }
  api(`/profile/nickname?chat_id=${chatId}`).then(r=>{
    const nick=(r.nickname||'').replace(/"/g,'&quot;');
    c.innerHTML=`<div class="card">
      <div class="card-title">🏷 Ник в чате</div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:8px">Отображается вместо @username в статистике чата</div>
      <div style="display:flex;gap:8px;align-items:center">
        <input id="nick-inp" type="text" class="num-input" style="flex:1;margin:0"
               value="${nick}" placeholder="Ваш ник" maxlength="32"/>
        <button class="btn btn-sm btn-gold" onclick="saveNick()">Сохранить</button>
      </div>
      <div id="nick-status" style="font-size:11px;margin-top:6px;color:var(--muted)">1–32 символа, буквы/цифры/пробел/- .</div>
    </div>`;
  }).catch(()=>{c.innerHTML='';});
}
function saveNick() {
  const v=(el('nick-inp')?.value||'').trim();
  if(!v){toast('Введите ник.',false);return;}
  if(v.length>32){toast('Ник слишком длинный.',false);return;}
  el('nick-status').textContent='Сохраняем...';
  api('/profile/set-nickname',{method:'POST',body:JSON.stringify({chat_id:_initChatId||_cid,nickname:v})})
    .then(r=>{
      el('nick-status').textContent=`✅ Ник установлен: ${r.nickname}`;
      el('nick-status').style.color='var(--green)';
    })
    .catch(e=>{
      el('nick-status').textContent='❌ '+e;
      el('nick-status').style.color='var(--red)';
    });
}

// ── Events ────────────────────────────────────────────────────────────────────
function loadEvents() {
  el('evc').innerHTML='<div class="loader">Загрузка...</div>';
  api('/events/').then(ev=>{
    let html='';

    // Exchange event
    if(ev.exchange_active) {
      const ea=ev.exchange_active;
      const ends=ea.ends_at?new Date(ea.ends_at):null;
      const msLeft=ends?Math.max(0,ends-Date.now()):0;
      html+=`<div class="card card-gold">
        <div class="card-title">💱 Обмен Мора → Алмазы <span style="color:var(--green);text-transform:none">АКТИВЕН</span></div>
        <div class="irow"><span class="ik">Курс</span><span>${fmt(ev.exchange_rate)} 🪙 = 1 💎</span></div>
        <div class="irow"><span class="ik">Лимит</span><span>${fmt(ev.exchange_cap)} 💎/день</span></div>
        ${msLeft>0?`<div class="irow"><span class="ik">До конца</span><span style="color:var(--gold)">${fmtTime(msLeft)}</span></div>`:''}
        <button class="btn btn-sm btn-gold" style="margin-top:8px;width:100%" onclick="goTo('auction','exch')">Перейти к обмену</button>
      </div>`;
    } else if(ev.exchange_next) {
      const en=ev.exchange_next;
      const starts=en.starts_at?new Date(en.starts_at):null;
      const startsStr=starts?starts.toLocaleString('ru-RU'):'-';
      html+=`<div class="card">
        <div class="card-title">💱 Следующий обмен</div>
        <div class="irow"><span class="ik">Начало</span><span>${startsStr}</span></div>
        <div class="irow"><span class="ik">Курс</span><span>${fmt(ev.exchange_rate)} 🪙 = 1 💎</span></div>
      </div>`;
    } else {
      html+=`<div class="card"><div class="card-title">💱 Обмен</div>
        <div style="color:var(--muted);font-size:12px">Ивент скоро будет запланирован. Заходите позже!</div>
      </div>`;
    }

    // Daily deals
    if(ev.daily_deals?.length) {
      html+=`<div class="card">
        <div class="card-title">🏷 Акция дня</div>
        ${ev.daily_deals.map(d=>`<div class="irow">
          <span class="ik">${d.name}${d.qty>1?` ×${d.qty}`:''}</span>
          <span>
            <span style="color:var(--gold);font-weight:700">${fmt(d.price)} 🪙</span>
            ${d.original&&d.original>d.price?`<s style="color:var(--muted);font-size:10px;margin-left:4px">${fmt(d.original)}</s>`:''}
          </span>
        </div>`).join('')}
        <button class="btn btn-sm btn-teal" style="margin-top:8px;width:100%" onclick="goTo('market','deal')">К акции дня</button>
      </div>`;
    }

    // Gacha overview УДАЛЁН (БЛОК19 Ч.2): честные шансы крутки — во вкладке Гача (ℹ️ Шансы).

    el('evc').innerHTML=html||'<div class="card" style="text-align:center;padding:20px;color:var(--muted)">Нет активных ивентов.</div>';
  }).catch(e=>{el('evc').innerHTML=`<div class="err">${e}</div>`;});
}
// Nav helpers for events page (avoids complex inline onclick in template literals)
// nav-хелперы заменены на единый goTo()
function fmtTime(ms) {
  const s=Math.floor(ms/1000),h=Math.floor(s/3600),m=Math.floor((s%3600)/60);
  if(h>24) return `${Math.floor(h/24)}д ${h%24}ч`;
  return `${h}ч ${m}м`;
}

// ── Species data (общий кэш для Бестиария) ────────────────────────────────────
// Витрина переехала в Зоопарк → Бестиарий (_renderBestiary). Здесь только кэш
// видов и модалка деталей вида, которую вызывает Бестиарий.
let _showcaseData=null;
function showSpeciesDetail(sid) {
  const p=(_showcaseData||[]).find(x=>x.species_id===sid);
  if(!p) return;
  const tiers=p.bonus_tiers||{};
  let bonusHtml='';
  for(const [lv,b] of Object.entries(tiers)){
    const lines=bonusLines(sid,b);
    if(lines.length) bonusHtml+=`<div style="margin-bottom:8px"><div style="font-size:10px;color:var(--gold);font-weight:600;margin-bottom:3px">Уровень ${lv}</div>${lines.map(l=>`<div style="font-size:11px;color:var(--text)">• ${l}</div>`).join('')}</div>`;
  }
  OM(p.name,`<div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px">${p.desc||''}</div>
    <div class="irow"><span class="ik">Редкость</span><span class="${RC[p.rarity]}">${p.rarity}</span></div>
    <div class="irow"><span class="ik">Роль</span><span>${p.role==='active'?'⚔️ Активный':'🛡 Пассивный'}</span></div>
    <div style="margin-top:10px">${bonusHtml||'<div style="color:var(--muted);font-size:11px">Нет данных о бонусах</div>'}</div>
  </div>`,[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}

