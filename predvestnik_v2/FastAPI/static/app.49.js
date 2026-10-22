// Pet equipment and the short outing. All odds, prices and item effects come from the server.
const _TR_SPECIALITY={navigation:'навигация',crossing:'переправы',search:'поиск',stealth:'скрытность',camp:'привалы'};
function _trEquipmentLink(p) {
  const n = Object.keys(p.equipment?.equipped || {}).length;
  return `<section class="tr-sec">${_v3Row('bag', 'Экипировка', `trailGo('equipment',${p.id})`, `${n} из 5 слотов · инструменты, обувь, защита, оберег и сумка`)}</section>`;
}
_TR_VIEWS.equipment = me => {
  const p = _trPet(_tr.pet); if (!p || !me.equipment) return _TR_VIEWS.hub(me);
  const r = me.equipment, g = p.equipment || {items:{},equipped:{}}, out = _trOut(p);
  const starter = g.starter_claimed ? '' : `<section class="tr-sec"><b>Первый набор бесплатно</b><p class="tr-note">Пять предметов I уровня для этого питомца. Детали для новых предметов и улучшений добываются в Вылазке.</p><button class="v3-pill" type="button" onclick="trailGear(this,'starter','')"${out?' disabled':''}>Получить и надеть</button></section>`;
  const slots = Object.entries(r.slots).map(([slot,name]) => `<section class="tr-sec"><h3>${_trE(name)}</h3><ul class="tr-list">${r.catalog.filter(i=>i.slot===slot).map(i=>{
    const tier=g.items[i.id]||0, equipped=g.equipped[slot]===i.id, cost=tier?r.upgrade_cost[tier]:r.craft_cost;
    const disabled=out?' disabled':'';
    return `<li class="tr-row tr-gear-item"><span class="tr-ic" aria-hidden="true">${i.icon}</span><span class="tr-nm"><b>${_trE(i.name)} ${tier?_TR_TIER[tier]:''}${equipped?' · надето':''}</b><small>${_trTxt(i.effects[Math.max(0,tier-1)])}</small>${tier&&tier<3?`<small>Далее: ${_trTxt(i.effects[tier])}</small>`:''}<small>Вылазка: ${_trE(_TR_SPECIALITY[i.speciality])} · лучше шанс</small><span class="tr-gear-actions">${tier?`<button class="v3-pill v3-pill--ghost" type="button" onclick="trailGear(this,'${equipped?'unequip':'equip'}','${i.id}')"${disabled}>${equipped?'Снять':'Надеть'}</button>`:''}${cost?`<button class="v3-pill" type="button" onclick="trailGear(this,'${tier?'upgrade':'craft'}','${i.id}')"${out||r.parts<cost?' disabled':''}>${tier?'Улучшить':'Изготовить'} · ${cost} дет.</button>`:'<small>Высший уровень</small>'}</span></span></li>`;
  }).join('')}</ul></section>`).join('');
  return `${_trSubHead('Экипировка')}<p class="tr-note">Детали: <b>${r.parts}</b>. Предметы принадлежат этому питомцу. Бонусы действуют в походах, экспедициях и дозоре; общая дневная норма Следов сохраняется. Бонус Следов учитывается у ведущего; Спутник получает свою долю. Склонности находок меняют их доли, а не добавляют отдельную награду.</p>${out?'<p role="status" class="tr-note">Сначала верни питомца из пути или Вылазки.</p>':''}${starter}${slots}<button type="button" class="v3-link" onclick="trailGo('outing')">За деталями в Вылазку ›</button>`;
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
  return [x.gain?'+'+x.gain+' дет.':'',x.damage?'−'+x.damage+' здоровья':'',x.heal?'+'+x.heal+' здоровья':'',x.supplies?'+'+x.supplies+' припасов':'',x.spent_parts?'−'+x.spent_parts+' дет.':'',x.spent_supplies?'−'+x.spent_supplies+' припасов':''].filter(Boolean).map(t=>' · '+t).join('');
}
function _trOutingLog(o) {
  return `<ol class="tr-outing-log">${o.log.map(x=>`<li><b>${_trE(x.event)}</b><span>${_trE(x.action)} · ${x.success?'удачно':'неудача'}${_trOutingDelta(x)}</span></li>`).join('')}</ol>`;
}
_TR_VIEWS.outing = me => {
  const r=me.equipment; if(!r)return _TR_VIEWS.hub(me);
  const o=r.open||(r.last?.id!==_tr.outingDismissed?r.last:null);
  let body='';
  if(o && o.status!=='active') {
    body=`<section class="tr-sec" role="status"><h3>${_TR_OUTCOME[o.status]||'Вылазка завершена'}</h3><p>В лагерь доставлено: <b>${o.reward} деталей</b>.</p><p class="tr-note">${o.status==='rescued'?'Сохранена половина добычи. Питомец вернулся целым.':o.status==='completed'?`Бонус за полный маршрут: ${Math.max(0,o.reward-o.cargo)} дет. (учтён в награде).`:'Можно было уйти раньше, чтобы сохранить добычу.'}</p>${_trOutingLog(o)}<button class="v3-pill" type="button" onclick="_tr.outingDismissed='${_trE(o.id)}';_trRender()">К следующей Вылазке</button></section>`;
  }else if(o) {
    const last=o.log[o.log.length-1];
    body=`<section class="tr-sec"><p class="tr-outing-stats" aria-label="Запасы Вылазки"><span>♥ ${o.hp}/4</span><span>🎒 ${o.supplies}/5</span><span>⚙ ${o.cargo} дет.</span></p><p class="tr-note">Развилка ${o.step+1} из ${o.steps} · ${_trE(_trPet(o.pet_id)?.name||'Питомец')}</p><h3 tabindex="-1" id="tr-outing-event">${_trE(o.event)}</h3>${last?`<p role="status" class="tr-note">${_trE(last.action)}: ${last.success?'удачно':'неудача'}${_trOutingDelta(last)}.</p>`:''}<div class="tr-outing-choices">${o.choices.map(c=>`<button type="button" class="tr-outing-choice" onclick="trailOutingChoose(this,${c.id})"${c.enabled?'':' disabled'}><b>${_trE(c.label)}</b><span>${c.chance}% успеха${c.gear_bonus?' · экипировка +'+c.gear_bonus+' п.п.':''}</span><small>Успех: ${[c.gain?'+'+c.gain+' деталей':'',c.heal?'+'+c.heal+' здоровья':'',c.supplies?'+'+c.supplies+' припасов':''].filter(Boolean).join(', ')||'без добычи'}${c.chance<100?` · Неудача: −${c.damage} здоровья`:''}</small><small>${[c.supply_cost?'Цена: '+c.supply_cost+' припас':'',c.cargo_cost?'Цена: '+c.cargo_cost+' детали':''].filter(Boolean).join(' · ')||'Без расхода припасов'}${c.enabled?'':' · '+_trE(c.disabled_reason)}</small></button>`).join('')}</div><button class="v3-pill v3-pill--ghost" type="button" onclick="trailOutingChoose(this,'leave')">Вернуться · сохранить ${o.cargo} дет.</button><p class="tr-note">При нуле здоровья лагерь спасёт питомца, но сохранится только половина добычи. За все семь развилок — ещё 3 детали; за забег не больше 32.</p><details><summary>Пройденные развилки</summary>${_trOutingLog(o)}</details></section>`;
  } else {
    const available=me.pets.filter(p=>!_trOut(p));
    body=`<section class="tr-sec"><h3>Семь развилок, один рюкзак</h3><p class="tr-note">Короткий забег без ожидания: решай, на что потратить припасы, когда рискнуть и когда вернуться. Выборы сохраняются после выхода. Экипировка повышает шансы на подходящих препятствиях.</p><p>Попыток: ${r.attempts_left} из ${r.daily} · вход ${r.energy} энергии · детали ${r.parts}</p><p class="tr-note">Детали нужны только для экипировки. Мора, Алмазы и Эссенция здесь не разыгрываются.</p><ul class="tr-list">${available.map(p=>`<li class="tr-row"><span class="tr-ic">${_trE(p.icon)}</span><span class="tr-nm"><b>${_trE(p.name)}</b><small>${p.energy} энергии · ${Object.keys(p.equipment?.equipped||{}).length}/5 предметов</small></span><button type="button" class="v3-pill" onclick="trailOutingStart(this,${p.id})"${r.attempts_left&&p.energy>=r.energy?'':' disabled'}>В путь</button></li>`).join('')||'<li class="tr-note">Свободных питомцев пока нет. Забери награды за занятия.</li>'}</ul></section>`;
  }
  return `${_trSubHead('Вылазка')}${body}`;
};
function trailOutingStart(button,pet_id) {
  return _trRun(button,async()=>{
    try{
      const r=await _trPost('outing/start',{pet_id},'outing-start',pet_id,String(_tr.me.now).slice(0,10),_tr.me.equipment.attempts_left);
       _tr.me.equipment.open=r.outing;
      const p=_trPet(pet_id);if(p){p.outing=true;p.energy=r.energy;}
      _tr.me.equipment.attempts_left=Math.max(0,_tr.me.equipment.attempts_left-1);
      _tr.needsRefresh=false; _trRender();
    }catch(e){_trFail(e);}
  });
}
function trailOutingChoose(button,choice) {
  const o=_tr.me.equipment.open;if(!o)return;
  return _trRun(button,async()=>{
    try{
      const r=await _trPost('outing/choose',{outing_id:o.id,step:o.step,choice},'outing-choice',o.id,o.step,choice);
      _tr.me.equipment.parts=r.parts;
      if(r.outing.status==='active')_tr.me.equipment.open=r.outing;
      else { _tr.me.equipment.open=null;_tr.me.equipment.last=r.outing;const p=_trPet(o.pet_id);if(p)p.outing=false; }
      _tr.needsRefresh=false; _trRender();
      document.getElementById('tr-outing-event')?.focus({preventScroll:true});
    }catch(e){_trFail(e);}
  });
}
