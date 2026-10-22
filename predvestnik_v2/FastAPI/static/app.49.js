// Pet equipment and the short outing. All odds, prices and item effects come from the server.
const _TR_SPECIALITY={navigation:'навигация',crossing:'переправы',search:'поиск',stealth:'скрытность',camp:'привалы'};
function trailEquipment(pet, slot) { trailGo('equipment',pet,slot); }
function trailGearSlot(slot) {
  if (!_tr.me.equipment?.slots?.[slot]) return;
  _tr.gearSlot = slot; _trRender(); el('pg-pets')?.querySelector(`[data-f="gear-${slot}"]`)?.focus({preventScroll:true});
}
_TR_VIEWS.equipment = me => {
  const p = _trPet(_tr.pet); if (!p || !me.equipment) return _TR_VIEWS.hub(me);
  const r = me.equipment, g = p.equipment || {items:{},equipped:{}}, out = _trOut(p);
  const selected = r.slots[_tr.gearSlot] ? _tr.gearSlot : Object.keys(r.slots)[0];
  _tr.gearSlot = selected;
  const slots = `<div class="tr-loadout tr-loadout--select" role="group" aria-label="Слот экипировки">${Object.entries(r.slots).map(([slot,name])=>{
    const item = r.catalog.find(i=>i.id===g.equipped[slot]);
    return `<button type="button" aria-pressed="${slot===selected}" data-f="gear-${slot}" onclick="trailGearSlot('${slot}')"><span aria-hidden="true">${item?.icon || '＋'}</span><small>${_trE(slot === 'tool' ? 'Инструм.' : name)}</small><b>${item ? _TR_TIER[g.items[item.id]] : '—'}</b></button>`;
  }).join('')}</div>`;
  const starter = g.starter_claimed ? '' : `<section class="tr-starter"><span><b>Первый набор — бесплатно</b><small>Все пять слотов: предметы I уровня для ${_trE(p.name)}.</small></span><button class="v3-pill" type="button" data-f="gear-starter" onclick="trailGear(this,'starter','')"${out?' disabled':''}>Получить и надеть</button></section>`;
  const equippedItem = r.catalog.find(i=>i.id===g.equipped[selected]);
  const items = r.catalog.filter(i=>i.slot===selected).map(i=>{
    const tier = g.items[i.id] || 0, equipped = g.equipped[selected]===i.id, cost = tier ? r.upgrade_cost[tier] : r.craft_cost;
    const shortage = cost ? Math.max(0,cost-r.parts) : 0;
    const other = !equipped && equippedItem ? `<p class="tr-note">Заменит: ${_trE(equippedItem.name)} ${_TR_TIER[g.items[equippedItem.id]]} · ${_trTxt(equippedItem.effects[g.items[equippedItem.id]-1])}</p>` : '';
    return `<article class="tr-gear-card${equipped?' is-equipped':''}"><div class="tr-gear-heading"><span class="tr-ic" aria-hidden="true">${i.icon}</span><span><small>${equipped?'Надето':tier?'Есть у питомца':'Ещё не изготовлено'}</small><h3>${_trE(i.name)}${tier?' '+_TR_TIER[tier]:''}</h3></span></div><p class="tr-gear-effect">${_trTxt(i.effects[Math.max(0,tier-1)])}</p><p class="tr-note">Вылазка: ${_trE(_TR_SPECIALITY[i.speciality])} · повышает шанс на подходящих развилках.</p>${other}${tier && tier<3?`<div class="tr-next-effect"><small>После улучшения до ${_TR_TIER[tier+1]}</small><b>${_trTxt(i.effects[tier])}</b></div>`:''}<div class="tr-gear-actions">${tier?`<button class="v3-pill v3-pill--ghost" type="button" data-f="gear-equip-${i.id}" onclick="trailGear(this,'${equipped?'unequip':'equip'}','${i.id}')"${out?' disabled':''}>${equipped?'Снять':'Надеть'}</button>`:''}${cost?`<button class="v3-pill" type="button" data-f="gear-buy-${i.id}" onclick="trailGear(this,'${tier?'upgrade':'craft'}','${i.id}')"${out || shortage?' disabled':''}>${tier?'Улучшить':'Изготовить'} · ${cost} дет.</button>`:'<span class="tr-note">Высший уровень</span>'}</div>${shortage?`<p class="tr-note">Не хватает ${shortage} дет. Их можно добыть в Вылазке.</p>`:''}${!tier?'<p class="tr-note">Изготовленный предмет нужно надеть в этот слот.</p>':''}</article>`;
  }).join('');
  return `${v3Head('Экипировка',{back:'trailBack()',sub:p.name})}<div class="tr-gear-balance"><span>Детали <b>${r.parts}</b></span><button type="button" class="v3-link" data-f="gear-outing" onclick="trailGo('outing',${p.id})">Добыть детали ›</button></div>${out?'<p role="status" class="tr-note">Питомец в пути. Можно сравнить вещи; менять их — после возвращения.</p>':''}${starter}${slots}<section class="tr-sec"><h2 class="tr-section-title">${_trE(r.slots[selected])}</h2><div class="tr-gear-options">${items}</div></section><details class="tr-details" data-detail="gear-rules"><summary data-f="detail-gear-rules">Как работают предметы и талисманы</summary><p class="tr-note">Пять предметов принадлежат этому питомцу. Бонусы работают в Походах, Экспедициях и Дозоре, а специальности — в Вылазке. Общая дневная норма Следов сохраняется. Бонус Следов учитывается у ведущего; Спутник получает свою долю. Склонности находок меняют их доли, а не добавляют отдельную награду.</p><p class="tr-note">Два талисмана — отдельная часть сборки: они усиливают один маршрут и ослабляют другой. Они не занимают эти пять слотов.</p><button type="button" class="v3-link" onclick="trailPet(${p.id})">К сборке питомца ›</button></details>`;
};
function trailGear(button,operation,item) {
  const p=_trPet(_tr.pet); if(!p)return;
  const tier=p.equipment?.items?.[item]||0;
  return _trRun(button,async()=>{
    try {
      const r=await _trPost('equipment',{pet_id:p.id,operation,item:item||null,expected_tier:tier},'gear',p.id,operation,item,tier,p.equipment?.revision||0);
      p.equipment=r.equipment; _tr.me.equipment.parts=r.parts; p.energy=r.energy;
      toast(r.spent?`Готово · потрачено ${r.spent} деталей`:'Экипировка обновлена',true);
      _trRender();
      await _trRefresh();
    }catch(e){_trFail(e);}
  });
}
const _TR_OUTCOME={returned:'Вернулся с добычей',completed:'Тропа пройдена',rescued:'Лагерь пришёл на помощь'};
function _trOutingDelta(x) {
  return [x.gain?'+'+x.gain+' дет.':'',x.damage?'−'+x.damage+' здоровья':'',x.heal?'+'+x.heal+' здоровья':'',x.supplies?'+'+x.supplies+' '+_trWord(x.supplies,'припас','припаса','припасов'):'',x.spent_parts?'−'+x.spent_parts+' дет.':'',x.spent_supplies?'−'+x.spent_supplies+' '+_trWord(x.spent_supplies,'припас','припаса','припасов'):''].filter(Boolean).map(t=>' · '+t).join('');
}
function _trOutingLog(o) {
  return `<ol class="tr-outing-log">${o.log.map(x=>`<li><b>${_trE(x.event)}</b><span>${_trE(x.action)} · ${x.success?'удачно':'неудача'}${_trOutingDelta(x)}</span></li>`).join('')}</ol>`;
}
_TR_VIEWS.outing = me => {
  const r=me.equipment; if(!r)return _TR_VIEWS.hub(me);
  const o=r.open||(r.last?.id!==_tr.outingDismissed?r.last:null);
  let body='';
  if(o && o.status!=='active') {
    body=`<section class="tr-sec" role="status"><h2 tabindex="-1" id="tr-outing-event">${_TR_OUTCOME[o.status]||'Вылазка завершена'}</h2><p>В лагерь доставлено: <b>${o.reward} ${_trWord(o.reward,'деталь','детали','деталей')}</b>.</p><p class="tr-note">${o.status==='rescued'?'Сохранена половина добычи. Питомец вернулся целым.':o.status==='completed'?`Бонус за полный маршрут: ${Math.max(0,o.reward-o.cargo)} дет. (учтён в награде).`:'Добыча сохранена полностью. Если остались попытки, можно отправиться снова.'}</p><button class="v3-pill" type="button" onclick="_tr.outingDismissed='${_trE(o.id)}';_trRender();_trFocusHead()">К следующей Вылазке</button><details class="tr-details" data-detail="outing-receipt"><summary data-f="detail-outing-receipt">История Вылазки · ${o.log.length} ${_trWord(o.log.length,'развилка','развилки','развилок')}</summary>${_trOutingLog(o)}</details></section>`;
  }else if(o) {
    const last=o.log[o.log.length-1];
    body=`<section class="tr-sec"><p class="tr-outing-stats" aria-label="Запасы Вылазки"><span><small>Здоровье</small><b>♥ ${o.hp}/4</b></span><span><small>Припасы</small><b>${o.supplies}/5</b></span><span><small>Добыча</small><b>${o.cargo} дет.</b></span></p><p class="tr-note">Развилка ${o.step+1} из ${o.steps} · ${_trE(_trPet(o.pet_id)?.name||'Питомец')}</p>${_trMeter(o.step/o.steps,{label:`Пройдено развилок: ${o.step} из ${o.steps}`})}<h2 tabindex="-1" id="tr-outing-event">${_trE(o.event)}</h2>${last?`<p role="status" class="tr-note">${_trE(last.action)}: ${last.success?'удачно':'неудача'}${_trOutingDelta(last)}.</p>`:''}${o.hp<=1?'<p class="tr-note" role="status">Осталось одно здоровье. Можно вернуться с добычей; при спасении сохранится половина.</p>':''}<div class="tr-outing-choices">${o.choices.map(c=>`<button type="button" class="tr-outing-choice" onclick="trailOutingChoose(this,${c.id})"${c.enabled?'':' disabled'}><b>${_trE(c.label)}</b><span>${c.chance}% успеха${c.gear_bonus?' · экипировка +'+c.gear_bonus+' п.п.':''}</span><small>Успех: ${[c.gain?'+'+c.gain+' '+_trWord(c.gain,'деталь','детали','деталей'):'',c.heal?'+'+c.heal+' здоровья':'',c.supplies?'+'+c.supplies+' '+_trWord(c.supplies,'припас','припаса','припасов'):''].filter(Boolean).join(', ')||'без добычи'}${c.chance<100?` · Неудача: −${c.damage} здоровья`:''}</small><small>${[c.supply_cost?'Цена: '+c.supply_cost+' '+_trWord(c.supply_cost,'припас','припаса','припасов'):'',c.cargo_cost?'Цена: '+c.cargo_cost+' '+_trWord(c.cargo_cost,'деталь','детали','деталей'):''].filter(Boolean).join(' · ')||'Без расхода припасов'}${c.enabled?'':' · '+_trE(c.disabled_reason)}</small></button>`).join('')}</div><button class="v3-pill v3-pill--ghost" type="button" onclick="trailOutingChoose(this,'leave')">Вернуться · сохранить ${o.cargo} дет.</button><p class="tr-note">При нуле здоровья лагерь спасёт питомца, но сохранится только половина добычи. За все семь развилок — ещё 3 детали; за забег не больше 32.</p><details class="tr-details" data-detail="outing-history"><summary data-f="detail-outing-history">Пройденные развилки</summary>${_trOutingLog(o)}</details></section>`;
  } else {
    const available=me.pets.slice().sort((a,b)=>Number(b.id===_tr.pet)-Number(a.id===_tr.pet) || Number(_trOut(a))-Number(_trOut(b)) || b.energy-a.energy);
    body=`<section class="tr-sec"><h3>Семь развилок, один рюкзак</h3><p class="tr-note">Короткий забег без ожидания: решай, на что потратить припасы, когда рискнуть и когда вернуться. Выборы сохраняются после выхода. Экипировка повышает шансы на подходящих препятствиях.</p><p>Попыток: ${r.attempts_left} из ${r.daily} · вход ${r.energy} энергии · детали ${r.parts}</p><p class="tr-note">Детали нужны только для экипировки. Мора, Алмазы и Эссенция здесь не разыгрываются.</p><ul class="tr-list">${available.map(p=>`<li class="tr-row tr-outing-pet"><span class="tr-ic">${_trE(p.icon)}</span><span class="tr-nm"><b>${_trE(p.name)}</b><small>${Math.round(p.energy)} сил · ${Object.keys(p.equipment?.equipped||{}).length}/5 предметов</small><small>${_trOut(p)?'Сначала забери награду за занятие':!r.attempts_left?'Попытки закончились · новые завтра (UTC)':p.energy<r.energy?`Не хватает ${Math.ceil(r.energy-p.energy)} сил`:r.energy+' сил за вход'}</small><button type="button" class="v3-link" data-f="outing-gear-${p.id}" onclick="trailEquipment(${p.id},'tool')">Подготовить экипировку ›</button></span><button type="button" class="v3-pill" onclick="trailOutingStart(this,${p.id})"${!_trOut(p)&&r.attempts_left&&p.energy>=r.energy?'':' disabled'}>В путь</button></li>`).join('')||'<li class="tr-note">Свободных питомцев пока нет. Забери награды за занятия.</li>'}</ul></section>`;
  }
  return `${_trSubHead('Вылазка')}${body}`;
};
function trailOutingStart(button,pet_id) {
  const navigation = _tr.nav || 0;
  return _trRun(button,async()=>{
    try{
      const r=await _trPost('outing/start',{pet_id},'outing-start',pet_id,String(_tr.me.now).slice(0,10),_tr.me.equipment.attempts_left);
       _tr.me.equipment.open=r.outing;
      const p=_trPet(pet_id);if(p){p.outing=true;p.energy=r.energy;}
      _tr.me.equipment.attempts_left=Math.max(0,_tr.me.equipment.attempts_left-1);
      _tr.needsRefresh=false; _trRender();
      if (typeof _activePage !== 'undefined' && _activePage === 'pets' && _tr.view === 'outing' && navigation === (_tr.nav || 0)) {
        try { window.scrollTo(0,0); } catch (_) { /* no viewport in rule tests */ }
        document.getElementById('tr-outing-event')?.focus({preventScroll:true});
      }
    }catch(e){_trFail(e);}
  });
}
function trailOutingChoose(button,choice) {
  const navigation = _tr.nav || 0;
  const o=_tr.me.equipment.open;if(!o)return;
  return _trRun(button,async()=>{
    try{
      const r=await _trPost('outing/choose',{outing_id:o.id,step:o.step,choice},'outing-choice',o.id,o.step,choice);
      _tr.me.equipment.parts=r.parts;
      if(r.outing.status==='active')_tr.me.equipment.open=r.outing;
      else { _tr.me.equipment.open=null;_tr.me.equipment.last=r.outing;const p=_trPet(o.pet_id);if(p)p.outing=false; }
      _tr.needsRefresh=false; _trRender();
      if (typeof _activePage !== 'undefined' && _activePage === 'pets' && _tr.view === 'outing' && navigation === (_tr.nav || 0)) {
        try { window.scrollTo(0,0); } catch (_) { /* no viewport in rule tests */ }
        document.getElementById('tr-outing-event')?.focus({preventScroll:true});
      }
    }catch(e){_trFail(e);}
  });
}
