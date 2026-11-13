// Current profile support only. Retired game/economy interfaces are not shipped.
// «Моя семья»: предложения, брак, семейный кошелёк — разделами .v3-sec и строками .v3-row, валюты рисованные (v3Cur, app.50.js)
const _FAM_CUR = [['mora', 'family_balance', 'Мора'], ['diamonds', 'family_balance_diamonds', 'Алмазы'], ['essence', 'family_balance_essence', 'Эссенция'], ['zarniki', 'family_balance_zarniki', 'Зарники']];
const _famName = (look, name, vip) => apName(apFromLook(look), esc(vipName(name, vip)));
function loadMarriageCard(){
  const host=el('pro-marriage-card'); if(!host)return;
  Promise.all([api('/marriage/'),api('/marriage/proposals')]).then(([m,p])=>{
    const proposals=p.proposals||[];
    const inbox=proposals.length?`<div class="v3-sec"><span class="v3-eyebrow">Предложения руки и сердца · ${proposals.length}</span></div>${proposals.map(x=>`<div class="v3-row fam-offer"><span><b>${_famName(x.look,x.proposer_name||`ID${x.proposer_id}`,x.proposer_is_vip)}</b><small>Предлагает брак</small></span><span class="v3-end"><button type="button" class="v3-pill v3-pill--sm" onclick="acceptProposal(${x.id},this)">Принять</button><button type="button" class="v3-pill v3-pill--sm v3-pill--ghost" onclick="declineProposal(${x.id},this)">Отклонить</button></span></div>`).join('')}`:'';
    if(!m.married){host.innerHTML=`${inbox}<div class="v3-sec"><span class="v3-eyebrow">Брак</span></div><div class="v3-row"><span><b>Брак не заключён</b><small>В группе с ботом напиши: <code>бот брак, @username</code></small></span></div>`;return;}
    const rows=_FAM_CUR.map(([k,f,n])=>`<div class="v3-row"><span class="v3-row-ic">${v3Cur(k)}</span><span>${n}</span><span class="v3-end">${fmt(m[f]||0)}</span></div>`).join('');
    const gifts=(m.received_gifts||[]).map(g=>`<div class="v3-row"><span><b>${esc(g.name)}</b><small>${(g.sent_at||'').slice(0,10)}</small></span></div>`).join('');
    host.innerHTML=`${inbox}<div class="v3-sec"><span class="v3-eyebrow">Брак</span></div>
      <div class="v3-row"><span><b>${_famName(m.partner_look,m.partner_name||'Партнёр',m.partner_is_vip)}</b><small>Вместе ${fmt(m.days||0)} дн.</small></span><span class="v3-end"><button type="button" class="v3-pill v3-pill--sm v3-pill--ghost" onclick="openPartnerGifts()">Подарить</button></span></div>
      <div class="v3-sec"><span class="v3-eyebrow">Семейный кошелёк</span></div>${rows}
      <div class="fam-bank"><input id="bank-amt" class="v3-field" aria-label="Сумма перевода" type="number" min="0.000001" step="any" placeholder="Сумма"><select id="bank-cur" class="v3-field" aria-label="Валюта перевода">${_FAM_CUR.map(([k,,n])=>`<option value="${k}">${n}</option>`).join('')}</select><button type="button" class="v3-pill v3-pill--sm" onclick="familyBank('deposit')">Внести</button><button type="button" class="v3-pill v3-pill--sm v3-pill--ghost" onclick="familyBank('withdraw')">Вывести</button></div>
      <p id="bank-status" class="v3-head-s" role="status">Все переводы сохраняются в истории.</p>
      ${gifts?`<div class="v3-sec"><span class="v3-eyebrow">Недавние подарки</span></div>${gifts}`:''}
      <button type="button" class="v3-pill v3-pill--sm v3-pill--danger fam-divorce" onclick="confirmDivorce()">Развестись</button>`;
    familyBankPending();
  }).catch(()=>{host.innerHTML='<div class="v3-empty" role="alert"><b>Семейный кошелёк не загрузился</b><button type="button" class="v3-link" onclick="loadMarriageCard()">Повторить</button></div>';});
}
let _familyBankMutation=null;
function familyBankStorageKey(){return 'pv-family-bank:'+String(_uid||localStorage.getItem(UK)||'');}
function familyBankPending(){
  let pending=null;try{pending=JSON.parse(localStorage.getItem(familyBankStorageKey())||'null');}catch(_){}
  if(pending){
    if(el('bank-amt')){el('bank-amt').value=pending.body.amount;el('bank-amt').disabled=true;}
    if(el('bank-cur')){el('bank-cur').value=pending.body.currency;el('bank-cur').disabled=true;}
    if(el('bank-status'))el('bank-status').textContent='Перевод ожидает ответа. Нажми «Внести» или «Вывести», чтобы проверить ту же операцию.';
  }
  return pending;
}
async function familyBank(action){
  if(_familyBankMutation)return;const storageKey=familyBankStorageKey();
  let pending=familyBankPending();
  if(!pending){
    const amount=Number(el('bank-amt')?.value||0),currency=el('bank-cur')?.value||'mora';
    if(!Number.isFinite(amount)||amount<=0)return toast('Введите сумму.',false);
    if(['zarniki','essence'].includes(currency)&&!Number.isInteger(amount))return toast('Эта валюта переводится целым числом.',false);
    if(!['deposit','withdraw'].includes(action))return;
    pending={key:crypto.randomUUID(),body:{amount,action,currency}};
    try{localStorage.setItem(storageKey,JSON.stringify(pending));}catch(_){return toast('Не удалось сохранить номер перевода. Проверь свободное место и повтори.',false);}
  }
  _familyBankMutation=pending;familyBankPending();
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
  try{
    const response=await fetch(BASE+'/marriage/bank',{method:'POST',signal:controller.signal,headers:{...hdrs(),'Idempotency-Key':pending.key},body:JSON.stringify(pending.body)});
    const result=await response.json();
    if(!response.ok){
      // Explicit validation/conflict replies prove that this attempt did not
      // commit. Network failures and 5xx leave the original key for recovery.
      if([400,409,422].includes(response.status))localStorage.removeItem(storageKey);
      throw new Error(typeof result.detail==='string'?result.detail:'Перевод пока не подтверждён.');
    }
    localStorage.removeItem(storageKey);toast(result.message);refreshCurrBar();
  }catch(error){toast(error.message||'Ответ потерян. Повтори: номер перевода сохранён.',false);}
  finally{clearTimeout(timeout);_familyBankMutation=null;loadMarriageCard();}
}
let _divorceIntent=null;
function confirmDivorce(){api('/marriage/divorce/intent',{method:'POST'}).then(r=>{_divorceIntent=r.intent_id;const body=r.needs_allocation?`<div class="v3-dim" style="padding:10px 0;line-height:1.5"><b>Это действие необратимо.</b> Средства будут разделены поровну, неделимый остаток получит партнёр с меньшим ID. ${r.family_pet_count||0} питомц. будут переданы обоим по очереди, после чего брак сразу завершится. Ничего не удаляется.</div>`:'<div class="v3-dim" style="padding:10px 0">Имущество уже распределено. Подтвердите развод отдельным нажатием.</div>';OM('💔 Развод',body,r.needs_allocation?[{l:'⚖️ Разделить и развестись',c:'danger',f:'allocateDivorce()'},{l:'Отмена',c:'ghost',f:'CM()'}]:[{l:'Развестись',c:'danger',f:'doDivorce()'},{l:'Отмена',c:'ghost',f:'CM()'}]);}).catch(e=>toast(e,false));}
function allocateDivorce(){if(!_divorceIntent)return;api(`/marriage/divorce/${encodeURIComponent(_divorceIntent)}/allocate`,{method:'POST'}).then(r=>{toast('💔 Имущество распределено, брак завершён.');_divorceIntent=null;CM();refreshCurrBar();loadMarriageCard();}).catch(e=>toast(e,false));}
function doDivorce(){if(!_divorceIntent)return;api(`/marriage/divorce/${encodeURIComponent(_divorceIntent)}/confirm`,{method:'POST'}).then(()=>{toast('💔 Развод оформлен.');_divorceIntent=null;CM();loadMarriageCard();}).catch(e=>toast(e,false));}
function acceptProposal(id,b){b.disabled=true;api('/marriage/proposals/accept',{method:'POST',body:JSON.stringify({proposal_id:id})}).then(()=>{toast('💍 Брак заключён!');loadMarriageCard();}).catch(e=>{toast(e,false);b.disabled=false;});}
function declineProposal(id,b){b.disabled=true;api('/marriage/proposals/decline',{method:'POST',body:JSON.stringify({proposal_id:id})}).then(()=>{toast('Предложение отклонено.');loadMarriageCard();}).catch(e=>{toast(e,false);b.disabled=false;});}
function openPartnerGifts(){
  OM('Подарок партнёру',v3Skel('Загружаем подарки…'),[{l:'Закрыть',c:'ghost',f:'CM()'}]);
  api('/marriage/gifts').then(r=>{const gs=r.gifts||[];el('mb').innerHTML=v3CurIn(gs.length?`<p class="v3-head-s">Подарок остаётся в семейной истории и не меняет игровую силу.</p>${gs.map(g=>`<div class="v3-row"><span><b>${esc(g.name)}</b></span><span class="v3-end"><button type="button" class="v3-pill v3-pill--sm v3-pill--ghost" onclick="buyPartnerGift('${g.id}',this)" data-name="${esc(g.name)}" data-price="${Number(g.price)||0}" data-cur="${esc(g.currency||'')}">${fmt(g.price)} ${{mora:'🪙',diamonds:'💎',zarniki:'✨'}[g.currency]||''}</button></span></div>`).join('')}`:'<div class="v3-empty">Подарков пока нет.</div>');}).catch(e=>{el('mb').innerHTML=`<div class="v3-err">${esc(String(e))}</div>`;});
}
async function buyPartnerGift(id,b){const icon={mora:'🪙',diamonds:'💎',zarniki:'✨'}[b.dataset.cur]||'';if(b.dataset.name&&!(await v3Confirm({title:'Подарок партнёру',visual:'🎁',name:b.dataset.name,sub:'Остаётся в семейной истории и не меняет игровую силу',price:Number(b.dataset.price),icon,cta:`Подарить за ${fmt(Number(b.dataset.price))} ${icon}`})))return;b.disabled=true;const key=b.dataset.requestKey||economyRequestKey(`partner-gift-${id}`);b.dataset.requestKey=key;api('/marriage/gift',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({gift_id:id})}).then(r=>{toast(`🎁 ${r.gift_name} вручён партнёру!`);refreshCurrBar();CM();loadMarriageCard();}).catch(e=>{toast(e,false);b.disabled=false;});}
function showPartnerGift(payloads){const p=(payloads&&payloads[0])||{};OM('💖 Подарок от супруга!',`<div style="text-align:center;font-size:42px">🎁</div><div style="text-align:center;font-weight:700">${esc(p.gift_name||'Подарок')}</div><div class="v3-dim" style="text-align:center;margin-top:5px">${esc(p.msg||'Вам сделали подарок')}</div>`,[{l:'Спасибо!',c:'primary',f:'CM();_nextModal()'}]);}

let _familyTree = null;
function openFamilyTree() {
  OM('Моя семья', `<div class="v3-guide-row">${v3GuideIcon('family')}</div><div id="pro-marriage-card" role="region" aria-label="Брак и семейный кошелёк">${v3Skel('Загружаем семейный кошелёк…', 4)}</div><section id="family-tree-section"><div class="v3-sec"><span class="v3-eyebrow">Родословная</span></div><div id="family-tree-host" role="status">${v3Skel('Загружаем родственные связи…', 2)}</div></section>`, [{l:'Закрыть',f:'CM()'}]);
  loadMarriageCard();
  const host = el('family-tree-host');
  api('/marriage/tree').then(d => {
    if (!host?.isConnected) return;
    _familyTree = d; familyTreeFocus(d.root);
  }).catch(e => { if (host?.isConnected) host.innerHTML = `<p class="v3-err" role="alert">${esc(String(e))}</p><button type="button" class="v3-link" onclick="openFamilyTree()">Повторить</button>`; });
}
// Дерево — в языке остального сайта: карточка человека с созвездием (.v3-id),
// ряды родственников (.v3-row) и фолды (.profile-fold). Данные и приватность те же:
// видны только связи, кошельки и личные данные родственников не раскрываются.
function familyTreeFocus(id) {
  const d = _familyTree, host = el('family-tree-host'), focus = d?.nodes.find(p => p.id === id);
  if (!host || !focus) return;
  const node = uid => d.nodes.find(n => n.id === uid);
  const parents = d.edges.filter(e => e.kind === 'parent' && e.target === id).map(e => e.source);
  const spouses = d.edges.filter(e => e.kind === 'spouse' && (e.source === id || e.target === id)).map(e => e.source === id ? e.target : e.source);
  const children = d.edges.filter(e => e.kind === 'parent' && e.source === id).map(e => e.target);
  const siblings = [...new Set(d.edges.filter(e => e.kind === 'parent' && parents.includes(e.source) && e.target !== id).map(e => e.target))];
  const childRole = uid => (d.edges.find(e => e.kind === 'parent' && e.source === id && e.target === uid) || {}).role || '';
  const ava = (p, big) => `<span class="fam-ava${big ? ' fam-ava--lg' : ''}" aria-hidden="true">${_v3Constellation(p.name || p.id, 1, false)}</span>`;
  const person = uid => {
    const p = node(uid); if (!p) return '';
    const hint = p.self ? 'Вы' : childRole(uid);
    return `<button type="button" class="v3-row fam-person" onclick="familyTreeFocus('${p.id}')" aria-label="Родственные связи: ${esc(p.name)}">${ava(p)}<span><b>${apName(apFromLook(p.look), esc(p.name))}</b>${hint ? `<small>${esc(hint)}</small>` : ''}</span><span class="v3-end">${_v3Icon('chev')}</span></button>`;
  };
  const section = (title, ids) => {
    const uniq = [...new Set(ids)].filter(uid => node(uid));
    return uniq.length ? `<section class="fam-sec"><div class="fam-sec-head"><span class="v3-eyebrow">${title}</span><small>${uniq.length}</small></div><div class="fam-list">${uniq.map(person).join('')}</div></section>` : '';
  };
  // Подпись родства к владельцу дерева — только то, что честно следует из рёбер.
  const relToRoot = () => {
    if (focus.id === d.root) return 'Это вы';
    if (d.edges.some(e => e.kind === 'spouse' && ((e.source === focus.id && e.target === d.root) || (e.target === focus.id && e.source === d.root)))) return 'Ваш супруг или супруга';
    const kid = d.edges.find(e => e.kind === 'parent' && e.source === d.root && e.target === focus.id);
    if (kid) return kid.role === 'сын' ? 'Ваш сын' : kid.role === 'дочь' ? 'Ваша дочь' : 'Ваш ребёнок';
    if (d.edges.some(e => e.kind === 'parent' && e.target === d.root && e.source === focus.id)) return 'Ваш родитель';
    const rootParents = d.edges.filter(e => e.kind === 'parent' && e.target === d.root).map(e => e.source);
    if (d.edges.some(e => e.kind === 'parent' && rootParents.includes(e.source) && e.target === focus.id)) return 'Брат или сестра';
    return '';
  };
  const ref = /^[A-Za-z0-9_-]{16,64}$/.test(focus.profile_ref || '') ? focus.profile_ref : null;
  const back = id !== d.root ? `<button type="button" class="v3-pill v3-pill--sm v3-pill--ghost" onclick="familyTreeFocus('${d.root}')">Вернуться ко мне</button>` : '';
  const prof = ref ? `<button type="button" class="v3-pill v3-pill--sm" onclick="CM();openPublicCardV3('${ref}')">Публичный профиль</button>` : '';
  const rel = relToRoot();
  host.className = 'family-tree';
  host.innerHTML = `<section class="v3-id fam-hero">${ava(focus, true)}<div><span class="v3-eyebrow">${id === d.root ? 'В центре дерева' : 'Родственные связи'}</span><div class="v3-name">${apName(apFromLook(focus.look), esc(focus.name))}</div>${rel ? `<div class="v3-sub">${esc(rel)}</div>` : ''}</div></section>
    ${(prof || back) ? `<div class="fam-acts">${prof}${back}</div>` : ''}
    ${section('Родители', parents)}${section('Братья и сёстры', siblings)}${section('Супруг / супруга', spouses)}${section('Дети', children)}
    ${d.nodes.length === 1 ? '<div class="v3-empty"><b>Родственных связей пока нет</b>Создать семью или принять приглашение можно в Telegram-чате с ботом.</div>' : ''}
    ${d.truncated ? `<p class="v3-dim fam-note" role="status">Семья большая: показаны первые ${d.max_nodes ?? 60} участников. Часть связей скрыта ограничением размера.</p>` : ''}
    <details class="profile-fold fam-fold"><summary><span class="profile-fold-title">Все в этом дереве</span><span class="profile-fold-meta">${d.nodes.length}</span><span class="profile-fold-arrow">›</span></summary><div class="profile-fold-body"><div class="fam-all">${d.nodes.map(p => `<button type="button" class="fam-mini" onclick="familyTreeFocus('${p.id}')" aria-label="Показать связи: ${esc(p.name)}">${ava(p)}<span>${apName(apFromLook(p.look), esc(p.name))}${p.self ? ' · Вы' : ''}</span></button>`).join('')}</div></div></details>
    <details class="profile-fold fam-fold"><summary><span class="profile-fold-title">О дереве и доступности данных</span><span class="profile-fold-meta"></span><span class="profile-fold-arrow">›</span></summary><div class="profile-fold-body"><p class="v3-dim">${esc(d.notice)} Показан круг до ${d.max_depth} переходов от вас.</p></div></details>`;
}
