// Current profile support only. Retired game/economy interfaces are not shipped.
function loadMarriageCard(){
  const host=el('pro-marriage-card'); if(!host)return;
  const treeEntry='<button type="button" class="v3-pill v3-pill--full v3-pill--ghost" onclick="openFamilyTree()">Моя семья · родословная ›</button>';
  Promise.all([api('/marriage/'),api('/marriage/proposals')]).then(([m,p])=>{
    const proposals=p.proposals||[];
    const inbox=proposals.length?`<details class="profile-fold profile-fold--gold" open><summary><span class="profile-fold-title">💌 Предложения руки и сердца</span><span class="profile-fold-meta">${proposals.length}</span><span class="profile-fold-arrow">›</span></summary><div class="profile-fold-body">${proposals.map(x=>`<div class="v3-line"><span class="">${apName(apFromLook(x.look), esc(vipName(x.proposer_name||`ID${x.proposer_id}`,x.proposer_is_vip)))}</span><span><button class="v3-pill v3-pill--sm" onclick="acceptProposal(${x.id},this)">Принять</button> <button class="v3-pill v3-pill--sm v3-pill--ghost" onclick="declineProposal(${x.id},this)">Отклонить</button></span></div>`).join('')}</div></details>`:'';
    if(!m.married){host.innerHTML=treeEntry+inbox+`<details class="profile-fold"><summary><span class="profile-fold-title">💔 Брак</span><span class="profile-fold-meta">Не заключён</span><span class="profile-fold-arrow">›</span></summary><div class="profile-fold-body"><div class="v3-dim" style="font-size:11px">В группе с ботом напишите: <code>бот брак, @username</code>.</div></div></details>`;return;}
    const rows=[['🪙',m.family_balance,'Мора'],['💎',m.family_balance_diamonds,'Алмазы'],['✨',m.family_balance_zarniki,'Зарники']].map(([i,v,n])=>`<div class="family-balance"><span>${i}</span><b>${fmt(v||0)}</b><small>${n}</small></div>`).join('');
    const gifts=(m.received_gifts||[]).map(g=>`<div class="family-gift"><span>🎁</span><b>${esc(g.name)}</b><small>${(g.sent_at||'').slice(0,10)}</small></div>`).join('');
    host.innerHTML=treeEntry+inbox+`<details class="profile-fold profile-fold--gold family-fold"><summary><span class="profile-fold-title">💍 ${apName(apFromLook(m.partner_look), esc(vipName(m.partner_name||'Партнёр',m.partner_is_vip)))}</span><span class="profile-fold-meta">вместе ${m.days} дн.</span><span class="profile-fold-arrow">›</span></summary><div class="profile-fold-body"><div class="family-wallet-head"><span>Семейный кошелёк</span><small>Все операции сохраняются в истории</small></div><div class="family-balances">${rows}</div><div class="family-bank-form"><input id="bank-amt" class="v3-field" type="number" min="0.000001" step="any" placeholder="Сумма"><select id="bank-cur" class="v3-field"><option value="mora">🪙 Мора</option><option value="diamonds">💎 Алмазы</option><option value="zarniki">✨ Зарники</option></select><button class="v3-pill v3-pill--sm" onclick="familyBank('deposit')">Внести</button><button class="v3-pill v3-pill--sm v3-pill--ghost" onclick="familyBank('withdraw')">Вывести</button></div><button class="v3-pill v3-pill--sm v3-pill--full v3-pill--ghost" style="margin-top:8px" onclick="openPartnerGifts()">🎁 Подарить партнёру</button>${gifts?`<div class="family-gifts"><small>Недавние подарки</small>${gifts}</div>`:''}<button class="v3-pill v3-pill--full v3-pill--danger" style="margin-top:10px" onclick="confirmDivorce()">💔 Развестись</button></div></details>`;
  }).catch(()=>{host.innerHTML='';});
}
let _familyBankMutation=null;
function familyBank(action){if(_familyBankMutation)return;const amount=parseFloat(el('bank-amt')?.value||0);if(!amount||amount<=0)return toast('Введите сумму.',false);const currency=el('bank-cur')?.value||'mora',requestKey=globalThis.crypto?.randomUUID?.()||`family-${Date.now()}`;_familyBankMutation=api('/marriage/bank',{method:'POST',headers:{'Idempotency-Key':requestKey},body:JSON.stringify({amount,action,currency})}).then(r=>{toast(`✅ ${r.message}`);refreshCurrBar();loadMarriageCard();}).catch(e=>toast(e,false)).finally(()=>{_familyBankMutation=null;});}
let _divorceIntent=null;
function confirmDivorce(){api('/marriage/divorce/intent',{method:'POST'}).then(r=>{_divorceIntent=r.intent_id;const body=r.needs_allocation?`<div class="v3-dim" style="padding:10px 0;line-height:1.5"><b>Это действие необратимо.</b> Средства будут разделены поровну, неделимый остаток получит партнёр с меньшим ID. ${r.family_pet_count||0} питомц. будут переданы обоим по очереди, после чего брак сразу завершится. Ничего не удаляется.</div>`:'<div class="v3-dim" style="padding:10px 0">Имущество уже распределено. Подтвердите развод отдельным нажатием.</div>';OM('💔 Развод',body,r.needs_allocation?[{l:'⚖️ Разделить и развестись',c:'danger',f:'allocateDivorce()'},{l:'Отмена',c:'ghost',f:'CM()'}]:[{l:'Развестись',c:'danger',f:'doDivorce()'},{l:'Отмена',c:'ghost',f:'CM()'}]);}).catch(e=>toast(e,false));}
function allocateDivorce(){if(!_divorceIntent)return;api(`/marriage/divorce/${encodeURIComponent(_divorceIntent)}/allocate`,{method:'POST'}).then(r=>{toast('💔 Имущество распределено, брак завершён.');_divorceIntent=null;CM();refreshCurrBar();loadMarriageCard();}).catch(e=>toast(e,false));}
function doDivorce(){if(!_divorceIntent)return;api(`/marriage/divorce/${encodeURIComponent(_divorceIntent)}/confirm`,{method:'POST'}).then(()=>{toast('💔 Развод оформлен.');_divorceIntent=null;CM();loadMarriageCard();}).catch(e=>toast(e,false));}
function acceptProposal(id,b){b.disabled=true;api('/marriage/proposals/accept',{method:'POST',body:JSON.stringify({proposal_id:id})}).then(()=>{toast('💍 Брак заключён!');loadMarriageCard();}).catch(e=>{toast(e,false);b.disabled=false;});}
function declineProposal(id,b){b.disabled=true;api('/marriage/proposals/decline',{method:'POST',body:JSON.stringify({proposal_id:id})}).then(()=>{toast('Предложение отклонено.');loadMarriageCard();}).catch(e=>{toast(e,false);b.disabled=false;});}
function openPartnerGifts(){OM('🎁 Подарок партнёру','<div class="v3-dim" style="padding:12px 0">Загрузка…</div>',[{l:'Закрыть',c:'ghost',f:'CM()'}]);api('/marriage/gifts').then(r=>{const gs=r.gifts||[];el('mb').innerHTML=gs.length?`<div class="v3-dim" style="font-size:11px;margin-bottom:7px">Подарок остаётся в семейной истории и не меняет игровую силу.</div>${gs.map(g=>`<div class="v3-line"><span class="">${esc(g.name)}</span><button class="v3-pill v3-pill--sm" onclick="buyPartnerGift('${g.id}',this)" data-name="${esc(g.name)}" data-price="${Number(g.price)||0}" data-cur="${esc(g.currency||'')}">${fmt(g.price)} ${{mora:'🪙',diamonds:'💎',zarniki:'✨'}[g.currency]||''}</button></div>`).join('')}`:'<div class="v3-dim" style="padding:12px 0">Подарков пока нет.</div>';}).catch(e=>{el('mb').innerHTML=`<div class="v3-err">${e}</div>`;});}
async function buyPartnerGift(id,b){const icon={mora:'🪙',diamonds:'💎',zarniki:'✨'}[b.dataset.cur]||'';if(b.dataset.name&&!(await v3Confirm({title:'Подарок партнёру',visual:'🎁',name:b.dataset.name,sub:'Остаётся в семейной истории и не меняет игровую силу',price:Number(b.dataset.price),icon,cta:`Подарить за ${fmt(Number(b.dataset.price))} ${icon}`})))return;b.disabled=true;const key=b.dataset.requestKey||economyRequestKey(`partner-gift-${id}`);b.dataset.requestKey=key;api('/marriage/gift',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({gift_id:id})}).then(r=>{toast(`🎁 ${r.gift_name} вручён партнёру!`);refreshCurrBar();CM();loadMarriageCard();}).catch(e=>{toast(e,false);b.disabled=false;});}
function showPartnerGift(payloads){const p=(payloads&&payloads[0])||{};OM('💖 Подарок от супруга!',`<div style="text-align:center;font-size:42px">🎁</div><div style="text-align:center;font-weight:700">${esc(p.gift_name||'Подарок')}</div><div class="v3-dim" style="text-align:center;margin-top:5px">${esc(p.msg||'Вам сделали подарок')}</div>`,[{l:'Спасибо!',c:'primary',f:'CM();_nextModal()'}]);}
let _walletMiniExpanded=false,_walletMiniTxs=[];
function loadWalletMini(){const h=el('wallet-mini');if(!h)return;h.innerHTML='<div class="sk" style="height:44px;border-radius:var(--r)"></div>';api('/wallet/history').then(t=>{_walletMiniTxs=(t||[]).filter(x=>!(x.delta_dark_mora&&!x.delta_mora&&!x.delta_diamonds&&!x.delta_zarniki));_walletMiniExpanded=false;_renderWalletMini();}).catch(()=>{if(el('wallet-mini'))el('wallet-mini').innerHTML='';});}
function toggleWalletMini(){_walletMiniExpanded=!_walletMiniExpanded;_renderWalletMini();}
function _renderWalletMini(){const h=el('wallet-mini');if(!h)return;if(!_walletMiniTxs.length){h.innerHTML='<details class="profile-fold wallet-fold"><summary><span class="profile-fold-title">💳 История операций</span><span class="profile-fold-meta">Пока пусто</span><span class="profile-fold-arrow">›</span></summary></details>';return;}const txs=_walletMiniExpanded?_walletMiniTxs:_walletMiniTxs.slice(0,4),one=t=>{const deltas=[['delta_mora','🪙'],['delta_diamonds','💎'],['delta_zarniki','✨']].filter(([k])=>t[k]);const hasGain=deltas.some(([k])=>t[k]>0),hasSpend=deltas.some(([k])=>t[k]<0),tone=hasGain&&hasSpend?'is-exchange':hasGain?'is-income':'is-expense';return `<article class="wtx ${tone}"><span class="wtx-mark">${tone==='is-exchange'?'↔':hasGain?'↗':'↘'}</span><div><div class="wtx-head"><span class="wtx-label">${esc(t.label||'Операция')}</span><span class="wtx-time">${fmtUTC(t.created_at)}</span></div><div class="wtx-values">${deltas.map(([k,i])=>`<span class="wtx-line ${t[k]>0?'is-gain':'is-spend'}">${t[k]>0?'+':''}${fmtF(t[k])} ${i}</span>`).join('')}</div></div></article>`;};h.innerHTML=`<details class="profile-fold wallet-fold"><summary><span class="profile-fold-title">💳 История операций</span><span class="profile-fold-meta">${_walletMiniTxs.length} записей</span><span class="profile-fold-arrow">›</span></summary><div class="profile-fold-body">${txs.map(one).join('')}${_walletMiniTxs.length>4?`<button class="v3-pill v3-pill--sm v3-pill--full v3-pill--ghost" style="margin-top:6px" onclick="toggleWalletMini()">${_walletMiniExpanded?'Свернуть':`Показать все (${_walletMiniTxs.length})`}</button>`:''}</div></details>`;}
function loadNickCard(){const c=el('pro-nick-card');if(!c)return;const chatId=_initChatId||_cid||0;if(!chatId){c.innerHTML='';return;}api(`/profile/nickname?chat_id=${chatId}`).then(r=>{const n=esc(r.nickname||'');c.innerHTML=`<details class="profile-fold"><summary><span class="profile-fold-title">🏷 Ник в чате</span><span class="profile-fold-meta">${n||'Не задан'}</span><span class="profile-fold-arrow">›</span></summary><div class="profile-fold-body"><div style="display:flex;gap:8px"><input id="nick-inp" type="text" class="v3-field" style="flex:1;margin:0" value="${n}" placeholder="Ваш ник" maxlength="32"><button class="v3-pill v3-pill--sm" onclick="saveNick()">Сохранить</button></div><div id="nick-status" class="v3-dim" style="font-size:11px;margin-top:6px">До 32 символов.</div></div></details>`;}).catch(()=>{c.innerHTML='';});}
function saveNick(){const nickname=(el('nick-inp')?.value||'').trim();if(!nickname)return toast('Введите ник.',false);api('/profile/set-nickname',{method:'POST',body:JSON.stringify({chat_id:_initChatId||_cid,nickname})}).then(r=>{el('nick-status').textContent=`✅ Ник установлен: ${r.nickname}`;}).catch(e=>{el('nick-status').textContent=`❌ ${e}`;});}

let _familyTree = null;
function openFamilyTree() {
  OM('Моя родословная', '<div id="family-tree-host" class="v3-empty" role="status">Загружаем родственные связи…</div>', [{l:'Закрыть',f:'CM()'}]);
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
