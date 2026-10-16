// Client-only practice. No economic or long-job quest writers.

(() => {
 const root=document.getElementById('pv-lighthouse'),el=id=>root.querySelector('#'+id);
 const rock=new Set([1,7,8,13,16,19,28,38,40]);
 const water=new Set([3,9,15,27,33,39]);
 let rescueCell=35;const rulesVersion='practice-1',scanNames={all:'Вокруг',up:'Север',right:'Восток',down:'Юг',left:'Запад'};
 const objectAt={0:['Сундук смотрителя','archive'],6:['Камень с письменами','scroll-text'],12:['Корни старого дерева','tree-deciduous'],17:['Склон над рекой','mountain'],5:['Лесной маяк','tower-control'],36:['Лагерь','tent']};
 const contracts={beacon:{title:'Лесной маяк',brief:'Найдите линзу и зажгите маяк.'},rescue:{title:'Следы в зарослях',brief:'Верните зверька в лагерь. С ним рывки недоступны.'},survey:{title:'Голоса древних камней',brief:'Три камня меняют условия вылазки. Затем — в лагерь.'}};
 const terrains=[['Старый мост','Прямой путь охраняет страж. Чутьё поможет найти обход.'],['Южный брод','На юге открыт новый переход. Можно пройти в обход моста.'],['После паводка','Мост разрушен. Его можно починить за ход или найти лаз.']];
 const stories=['Смотритель уходил последним. Он оставил свет для тех, кто ещё в пути.','Под старым деревом звери годами прокладывали дорогу на другой берег.','Знаки на камнях — не заклинание. Так путники передавали друг другу безопасный маршрут.','Каменный страж помнит приказ охранять мост, хотя караван давно прошёл.','Лесной родник появляется там, где корни находят старые подземные каналы.'];
 function objects(){const result={...objectAt};if(state.contract==='rescue'){result[rescueCell]=[state.carrying?'Место спасения':'Раненый зверёк','paw-print'];}if(state.contract==='survey')for(const n of [0,24,35])result[n]=[n===0?'Камень пути':n===24?'Камень движения':'Камень защиты',n===0?'door-open':n===24?'zap':'shield'];result[state.eventPos]=[state.seed%2?'Лесной родник':'Камень эха',state.seed%2?'droplets':'audio-lines'];result[state.cachePos]=['Забытый дневник','book-open'];if(state.layout===2&&!state.repaired)result[21]=['Разрушенный мост','construction'];return result;}
 const xy=i=>[i%6,Math.floor(i/6)],dist=(a,b)=>Math.abs(a%6-b%6)+Math.abs(Math.floor(a/6)-Math.floor(b/6));
 const neighbors=i=>Array.from({length:42},(_,n)=>n).filter(n=>dist(i,n)===1);
 const sealKeys=['leaf','moon','spark'],sealLabels=['Лист','Луна','Искра'],sealIcons=['leaf','moon','flame'];
 const base=(memory={played:0,stories:[],records:[]},seed=1,contract='beacon')=>({
  v:4,memory,seed,contract,approach:'any',rescueAt:35,layout:(seed+Math.floor(seed/3))%3,
  eventPos:[18,34,11][seed%3],cachePos:[2,37,4][seed%3],eventDone:false,cacheDone:false,carrying:false,stones:[],repaired:false,lure:null,ward:0,recorded:false,
  pos:30,hp:6,charges:2,cooldown:0,turn:0,status:'prep',lens:false,lensSource:'',secret:false,secretUsed:false,clue:false,chest:false,rested:false,
  seals:initialSeals(seed),sealHint:null,sealLast:null,seen:[],journal:[],enemies:[{id:'guard',name:'Каменный страж',pos:20,hp:4,patrol:0},{id:'prowler',name:'Лесной хищник',pos:23,hp:3,patrol:0}],
  message:'Соседняя тропа — шаг. Объект — бесплатный осмотр.'});
 let state=base(),mode='walk',selected=null,panel='',busy=false,epoch=0,playback=[],travel=null,travelSerial=0,scanAim='all';
 const publicationId=globalThis.crypto?.randomUUID?.()||('pv-'+Math.random().toString(36).slice(2));let publicationSeq=0;
 const reduced=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 const sleep=ms=>new Promise(r=>setTimeout(r,reduced()?0:ms));
 const safe=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function note(text){if(!state.journal.includes(text))state.journal.push(text);}
 function reveal(radius=2){for(let i=0;i<42;i++)if(dist(state.pos,i)<=radius&&!state.seen.includes(i))state.seen.push(i);if(state.seen.includes(6)&&!state.clue){state.clue=true;note('На камне: '+codeText()+'. Это порядок печатей сундука.');}}
 function occupied(i,except=''){return state.enemies.some(e=>e.hp>0&&e.id!==except&&e.pos===i);}
 function ground(i,layout=state.layout,repaired=state.repaired){if(!Number.isInteger(i)||i<0||i>=42)return false;if(layout===1&&[38,39,40].includes(i))return true;if(i===21&&layout===2&&!repaired)return false;return !rock.has(i)&&!water.has(i);}
 function code(seed=state.seed){return [['leaf','moon','spark'],['moon','spark','leaf'],['spark','leaf','moon'],['leaf','spark','moon'],['moon','leaf','spark'],['spark','moon','leaf']][(seed-1)%6];}
 function codeText(){return code().map(x=>({leaf:'лист',moon:'луна',spark:'искра'}[x])).join(' → ');}
 function rotateSeals(values,index){const result=values.slice();result[index]=(result[index]+1)%3;const next=(index+1)%3;result[next]=(result[next]+1)%3;return result;}
 function solveSeals(values,target){
  const wanted=target.join(','),queue=[{values:values.slice(),steps:[]}],seen=new Set([values.join(',')]);
  while(queue.length){const current=queue.shift();if(current.values.join(',')===wanted)return current.steps;for(let i=0;i<3;i++){const next=rotateSeals(current.values,i),key=next.join(',');if(!seen.has(key)){seen.add(key);queue.push({values:next,steps:[...current.steps,i]});}}}
  return null;
 }
 function initialSeals(seed){const target=code(seed).map(x=>sealKeys.indexOf(x)),eligible=[];for(let n=0;n<27;n++){const values=[Math.floor(n/9),Math.floor(n/3)%3,n%3],steps=solveSeals(values,target);if(steps&&steps.length>=2&&steps.length<=5)eligible.push(values);}return eligible[(seed-1)%eligible.length].slice();}
 function sealsMatch(){return state.seals.every((value,i)=>sealKeys[value]===code()[i]);}
 function recordKey(){return rulesVersion+':'+state.contract+':'+state.seed+':'+state.layout+':'+rescueCell+':'+(state.approach||'any')+':'+(state.contract==='beacon'?state.lensSource:'');}
 function record(){if(state.recorded)return;state.recorded=true;const records=(state.memory.records||[]).slice(),key=recordKey();if(state.status==='won'){const old=records.find(r=>r.key===key),entry={key,turn:Math.min(old?.turn??state.turn,state.turn),hp:Math.max(old?.hp??state.hp,state.hp)};state.memory.records=[entry,...records.filter(r=>r.key!==key)].slice(0,24);}state.memory.played++;}
 function path(from,to,except='',avoid=[]){const queue=[[from]],seen=new Set([from]);while(queue.length){const p=queue.shift(),last=p[p.length-1];if(last===to)return p;for(const n of neighbors(last))if(ground(n)&&!avoid.includes(n)&&!occupied(n,except)&&!seen.has(n)){seen.add(n);queue.push([...p,n]);}}return null;}
 function routeStepReason(from,to){
  if(!state.seen.includes(to))return 'Дальше туман — выберите шаг вручную.';
  if(dist(from,to)!==1||!ground(to)||occupied(to))return 'Проход изменился или занят.';
  if(state.enemies.some(e=>e.hp>0&&state.seen.includes(e.pos)&&(dist(from,e.pos)<=3||dist(to,e.pos)<=3)))return 'Рядом противник — управление возвращено вам.';
  const f=forecast({type:'move',to});if(f.hp<state.hp||f.ward<state.ward)return 'Впереди зона удара — выберите действие вручную.';
  return '';
 }
 function pendingRouteObject(i){return i===state.eventPos&&!state.eventDone||i===state.cachePos&&!state.cacheDone||state.contract==='rescue'&&i===rescueCell&&!state.carrying||state.contract==='survey'&&[0,24,35].includes(i)&&!state.stones.includes(i)||state.contract==='beacon'&&(i===0&&!state.chest||i===5&&state.lens)||i===36&&((state.contract==='rescue'&&state.carrying)||(state.contract==='survey'&&state.stones.length===3));}
 function routePlan(target){
  if(state.status!=='playing'||mode!=='walk'||!state.seen.includes(target)||dist(state.pos,target)<=1||!ground(target)||occupied(target))return null;
  const q=[[state.pos]],seen=new Set([state.pos]);let found=null;
  while(q.length){const p=q.shift(),last=p[p.length-1];if(last===target){found=p;break;}
   for(const n of neighbors(last))if(!seen.has(n)&&!routeStepReason(last,n)){seen.add(n);q.push([...p,n]);}}
  if(!found)return null;
  const stop=found.findIndex((n,i)=>i>0&&pendingRouteObject(n));if(stop>0&&stop<found.length-1)return {cells:found.slice(0,stop+1),reason:'Остановка у объекта: '+objects()[found[stop]][0],objectStop:true};
  return {cells:found,reason:'Остановка при новой находке или опасности.'};
 }
 async function followRoute(target){
  if(busy||travel||state.status!=='playing')return;const planned=routePlan(target);if(!planned)return;
  const token=++travelSerial,ownerEpoch=epoch;travel={token,cells:planned.cells.slice(1),total:planned.cells.length-1,done:0,stopRequested:false};mode='walk';selected=null;panel='';render();
  let reason=planned.objectStop?planned.reason:'Маршрут завершён. Взаимодействия выполняются вручную.';
  for(const next of planned.cells.slice(1)){
   if(epoch!==ownerEpoch||travel?.token!==token)return;
   if(travel.stopRequested){reason='Движение остановлено. Все начатые ходы завершены.';break;}
   const unsafe=routeStepReason(state.pos,next);if(unsafe){reason=unsafe;break;}
   const knownFoes=new Set(state.enemies.filter(e=>e.hp>0&&state.seen.includes(e.pos)).map(e=>e.id)),knownObjects=new Set(Object.keys(objects()).map(Number).filter(i=>state.seen.includes(i))),oldTurn=state.turn;
   await commit({type:'move',to:next,routeToken:token});
   if(epoch!==ownerEpoch||travel?.token!==token)return;
   if(state.turn!==oldTurn+1||state.pos!==next){reason='Маршрут изменился. Выберите путь заново.';break;}
   travel.done++;travel.cells.shift();
   if(state.status!=='playing')break;
   if(state.enemies.some(e=>e.hp>0&&state.seen.includes(e.pos)&&(!knownFoes.has(e.id)||dist(state.pos,e.pos)<=3))){reason='Обнаружен противник — движение остановлено.';break;}
   if(Object.keys(objects()).map(Number).some(i=>state.seen.includes(i)&&!knownObjects.has(i))){reason='Новая находка рядом — движение остановлено.';break;}
   if(travel.stopRequested){reason='Движение остановлено. Все начатые ходы завершены.';break;}
   render();await sleep(100);
  }
  if(epoch!==ownerEpoch||travel?.token!==token)return;travel=null;if(state.status==='playing'){state.message=reason;selected=objects()[state.pos]?state.pos:null;}render();save();
 }
 function intents(){return state.enemies.filter(e=>e.hp>0).map(e=>{
  if((e.recovery||0)>0)return {id:e.id,type:'recover',remaining:e.recovery,cells:[]};
  if(e.id==='guard'){
   const [x,y]=xy(e.pos),[u,v]=xy(state.pos);if(dist(e.pos,state.pos)>2||!(x===u||y===v))return {id:e.id,type:'wait',cells:[]};
   const dx=Math.sign(u-x),dy=Math.sign(v-y),cells=[];for(let step=1;step<=2;step++){const nx=x+dx*step,ny=y+dy*step;if(nx<0||nx>5||ny<0||ny>6)break;const n=ny*6+nx;if(!ground(n))break;cells.push(n);}return {id:e.id,type:cells.includes(state.pos)?'attack':'wait',cells:cells.includes(state.pos)?cells:[],damage:2};
  }
  if(state.lure&&state.lure.remaining>0){const route=path(e.pos,state.lure.pos,e.id,[state.pos]);return route&&route.length>1?{id:e.id,type:'move',to:route[1],cells:[route[1]]}:{id:e.id,type:'wait',cells:[]};}
  if(dist(e.pos,state.pos)===1)return {id:e.id,type:'attack',cells:[state.pos],damage:1};
  const patrol=state.seed%2?[35,29,23,29]:[23,29,35,29];let target=dist(e.pos,state.pos)<=4?state.pos:patrol[e.patrol%4];if(target===e.pos)target=patrol[(e.patrol+1)%4];const route=path(e.pos,target,e.id);return route&&route.length>1?{id:e.id,type:'move',to:route[1],cells:[route[1]]}:{id:e.id,type:'wait',cells:[]};
 });}
 function direction(from,to){return to%6>from%6?'→':to%6<from%6?'←':to>from?'↓':'↑';}
 function planText(e,p){return p.type==='attack'?e.name+': удар '+p.damage:p.type==='recover'?e.name+': восстановление '+p.remaining+' х.':p.type==='move'?e.name+': шаг '+direction(e.pos,p.to):e.name+': выжидает';}
 function hitResult(hp,ward,damage){const absorbed=Math.min(ward,damage);return {hp:Math.max(0,hp-(damage-absorbed)),ward:ward-absorbed,absorbed};}
 function forecast(action){
  let pos=['move','dash','tunnel'].includes(action.type)?action.to:state.pos,hp=state.hp,ward=state.ward;
  if(['beacon','deliver'].includes(action.type))return {hp,ward};
  if(action.type==='heal'||action.type==='rest')hp=Math.min(6,hp+2);
  if(action.type==='stone'&&action.at===35)ward=2;
  const killed=action.type==='attack'&&state.enemies.find(e=>e.id===action.id)?.hp<=2?action.id:null;
  for(const p of intents())if(p.id!==killed&&p.type==='attack'&&p.cells.includes(pos)){const hit=hitResult(hp,ward,p.damage);hp=hit.hp;ward=hit.ward;if(hp===0)break;}
  return {hp,ward};
 }
 function forecastText(action,label='После ответа'){const f=forecast(action);return label+': здоровье '+f.hp+'/'+6+(state.ward||f.ward?' · защита '+f.ward:'')+(f.hp===0?' · отступление':'');}
 function moveCost(action){const f=forecast(action),health=state.hp-f.hp,ward=state.ward-f.ward;return {label:health?(f.hp===0?'!':'')+'−'+health+(ward?' щ'+ward:''):ward?'щ'+ward:'',description:health?'потеря здоровья '+health+(ward?', расход защиты '+ward:'')+(f.hp===0?', отступление':''):ward?'защита поглотит '+ward+' урона':''};}
 function scanCells(direction='all'){return Array.from({length:42},(_,i)=>i).filter(i=>{if(direction==='all')return dist(state.pos,i)<=4;const dx=i%6-state.pos%6,dy=Math.floor(i/6)-Math.floor(state.pos/6),along=direction==='up'?-dy:direction==='down'?dy:direction==='left'?-dx:dx,across=['up','down'].includes(direction)?Math.abs(dx):Math.abs(dy);return along>0&&across<=along&&dist(state.pos,i)<=6;});}
 function sniffBenefit(direction='all'){return {cells:scanCells(direction).filter(i=>!state.seen.includes(i)).length,secret:!state.secret&&dist(state.pos,12)<=2};}
 function objectiveTargets(){return state.contract==='rescue'?[[state.carrying?36:rescueCell,state.carrying?'К лагерю':'К зверьку']]:state.contract==='survey'?(state.stones.length===3?[[36,'К лагерю']]:[[0,'Путь'],[24,'Движение'],[35,'Защита']].filter(([i])=>!state.stones.includes(i))):state.lens?[[5,'К маяку']]:[[0,'К сундуку'],[20,'К стражу']].filter(([i])=>state.seen.includes(i)&&(state.approach==='any'||i===(state.approach==='guard'?20:0)));}
 function trailHint(){
  const targets=state.contract==='rescue'?[state.carrying?36:rescueCell]:state.contract==='survey'?(state.stones.length===3?[36]:[0,24,35].filter(i=>!state.stones.includes(i))):state.lens?[5]:[0,20];
  const target=targets.slice().sort((a,b)=>dist(state.pos,a)-dist(state.pos,b))[0],known=i=>state.seen.includes(i)||(state.secret&&[12,17].includes(i));
  const q=[[state.pos]],seen=new Set([state.pos]);let best=[state.pos],score=dist(state.pos,target)*10;
  while(q.length){const p=q.shift(),last=p[p.length-1],rank=dist(last,target)*10+p.length;if(rank<score){best=p;score=rank;}if(dist(last,target)<=1){best=p;break;}
   const next=neighbors(last);if(state.secret&&[12,17].includes(last))next.push(last===12?17:12);
   for(const n of next)if(known(n)&&ground(n)&&!occupied(n)&&!seen.has(n)){seen.add(n);q.push([...p,n]);}}
  if(dist(state.pos,target)<=1)return 'Цель рядом — осмотрите объект.';
  if(best.length<2)return 'Дальше след скрывается в тумане.';
  return dist(best[0],best[1])>1?'К цели ведёт открытый лаз.':'Первый шаг по известной тропе: '+({ '↑':'вверх','↓':'вниз','←':'влево','→':'вправо'}[direction(best[0],best[1])])+'.';
 }
 function save(){if(window.PetPractice?.setWidgetState){const snapshot=globalThis.structuredClone?structuredClone(state):JSON.parse(JSON.stringify(state));window.PetPractice.setWidgetState({modelContent:{concept:'Разные вылазки питомца',contract:state.contract,terrain:terrains[state.layout][0],seed:state.seed,turn:state.turn,status:state.status,eventDone:state.eventDone,discoveries:state.memory.stories.length,lensRoute:state.lensSource,secretUsed:state.secretUsed,defeated:state.enemies.filter(e=>e.hp===0).map(e=>e.name)},privateContent:{...snapshot,_pvPublication:{id:publicationId,seq:++publicationSeq}}}).catch(()=>{});}}
 function restore(snapshot){
  epoch++;travelSerial++;travel=null;busy=false;mode='walk';selected=null;panel='';scanAim='all';rescueCell=35;
  let p=snapshot?.privateContent;
  if(p&&typeof p==='object'){const {_pvPublication,...snapshotState}=p;p=snapshotState;}
  if(p?.v===3)p={...base(),...p,v:4,layout:0,eventDone:true,cacheDone:true};
  if(!p||p.v!==4||!contracts[p.contract]||!Number.isInteger(p.seed)||p.seed<1||p.seed>1000000||![0,1,2].includes(p.layout)||!ground(p.pos,p.layout,p.repaired)||!Number.isInteger(p.hp)||p.hp<0||p.hp>6||!Number.isInteger(p.charges)||p.charges<0||p.charges>2||!Number.isInteger(p.cooldown)||p.cooldown<0||p.cooldown>3||!Number.isInteger(p.turn)||p.turn<0||p.turn>10000||!['prep','playing','won','lost','returned'].includes(p.status)||!Array.isArray(p.seen)||!Array.isArray(p.journal)||!Array.isArray(p.enemies)||p.enemies.length!==2){state=base();reveal();return;}
  const enemies=[];for(const model of base().enemies){const e=p.enemies.find(x=>x.id===model.id);if(!e||!ground(e.pos,p.layout,p.repaired)||!Number.isInteger(e.hp)||e.hp<0||e.hp>model.hp||!Number.isInteger(e.patrol)||e.patrol<0||e.patrol>10000){state=base();reveal();return;}enemies.push({...model,pos:e.pos,hp:e.hp,patrol:e.patrol,recovery:Number.isInteger(e.recovery)?Math.max(0,Math.min(2,e.recovery)):0});}
  state={...base(),...p,enemies,seen:[...new Set(p.seen.filter(i=>Number.isInteger(i)&&i>=0&&i<42))],journal:p.journal.filter(t=>typeof t==='string').slice(-40).map(t=>t.slice(0,180)),message:typeof p.message==='string'?p.message.slice(0,350):''};
  for(const key of ['lens','secret','secretUsed','clue','chest','rested','eventDone','cacheDone','carrying','repaired','recorded'])state[key]=p[key]===true;
  state.memory={played:Number.isInteger(p.memory?.played)?Math.max(0,p.memory.played):0,stories:[...new Set((Array.isArray(p.memory?.stories)?p.memory.stories:[]).filter(n=>Number.isInteger(n)&&n>=0&&n<5))],records:(Array.isArray(p.memory?.records)?p.memory.records:[]).filter(r=>r&&typeof r.key==='string'&&r.key.length<80&&Number.isInteger(r.turn)&&r.turn>0&&r.turn<=10000&&Number.isInteger(r.hp)&&r.hp>0&&r.hp<=6).slice(0,24).map(r=>({key:r.key,turn:r.turn,hp:r.hp}))};
  state.stones=[...new Set((Array.isArray(p.stones)?p.stones:[]).filter(n=>[0,24,35].includes(n)))];state.ward=Number.isInteger(p.ward)?Math.max(0,Math.min(2,p.ward)):0;
  state.seals=Array.isArray(p.seals)&&p.seals.length===3&&p.seals.every(n=>Number.isInteger(n)&&n>=0&&n<3)?p.seals.slice():initialSeals(state.seed);
  state.sealHint=[0,1,2].includes(p.sealHint)?p.sealHint:null;state.sealLast=[0,1,2].includes(p.sealLast)?p.sealLast:null;
  state.eventPos=[18,34,11][state.seed%3];state.cachePos=[2,37,4][state.seed%3];
  state.lure=p.lure&&ground(p.lure.pos,p.layout,p.repaired)&&Number.isInteger(p.lure.remaining)&&p.lure.remaining>0&&p.lure.remaining<=4?{pos:p.lure.pos,remaining:p.lure.remaining}:null;
  state.lensSource=['guard','ruins'].includes(p.lensSource)?p.lensSource:'';reveal();
  state.rescueAt=p.rescueAt===35?35:17;rescueCell=state.rescueAt;state.approach=['guard','ruins'].includes(p.approach)?p.approach:'any';
 }
 function canMove(i){if(!ground(i)||occupied(i)||state.status!=='playing')return false;if(mode!=='dash')return dist(state.pos,i)===1;const [x,y]=xy(state.pos),[u,v]=xy(i),middle=(state.pos+i)/2;return !state.carrying&&state.charges>0&&dist(state.pos,i)===2&&(x===u||y===v)&&ground(middle)&&!occupied(middle);}
 const icons=()=>{if(globalThis.lucide)lucide.createIcons({attrs:{width:16,height:16}});};
 for(let i=0;i<42;i++){const button=document.createElement('button');button.type='button';button.className='lh-cell cursor-interaction';button.dataset.cell=i;el('lh-board').append(button);}
 for(const [id,icon,kind] of [['hero','cat','lh-hero'],['guard','shield','lh-enemy'],['prowler','dog','lh-enemy']]){const a=document.createElement('div');a.id='lh-actor-'+id;a.className='lh-actor '+kind;a.innerHTML=`<div class="lh-sprite"><i data-lucide="${icon}"></i></div>${id==='hero'?'<span class="lh-cargo"><i data-lucide="paw-print"></i></span>':'<small></small>'}`;el('lh-actors').append(a);}
 function sprite(id,pos,visible,hp){const a=el('lh-actor-'+id),[x,y]=xy(pos);a.style.left=(x*100/6)+'%';a.style.top=(y*100/7)+'%';a.hidden=!visible;if(id!=='hero')a.querySelector('small').textContent=hp;}
 function hit(id){const a=el('lh-actor-'+id);a.classList.remove('lh-hit');void a.offsetWidth;a.classList.add('lh-hit');}
 function nearbyObject(i){return dist(state.pos,i)<=1;}
 function actionFor(i){
  if(!nearbyObject(i))return null;
  if(i===state.eventPos&&!state.eventDone)return ['event','Исследовать встречу · выбор бесплатный'];
  if(i===state.cachePos&&!state.cacheDone)return ['cache','Прочесть дневник · 1 ход'];
  if(state.contract==='rescue'&&i===rescueCell&&!state.carrying&&!occupied(rescueCell))return ['rescue','Взять зверька на руки · 1 ход'];
  if(state.contract==='survey'&&[0,24,35].includes(i)&&!state.stones.includes(i))return ['stone','Пробудить камень · 1 ход'];
  if(i===36&&((state.contract==='rescue'&&state.carrying)||(state.contract==='survey'&&state.stones.length===3)))return ['deliver','Завершить задание в лагере'];
  if(i===21&&state.layout===2&&!state.repaired&&!occupied(21))return ['repair','Починить мост · 1 ход, без припасов'];
  if(i===5&&state.contract==='beacon'&&state.lens)return ['beacon','Зажечь маяк · завершить вылазку'];
  if(i===0&&state.contract==='beacon'&&state.approach!=='guard'&&!state.chest)return ['chest','Открыть печати'];
  if((i===12||i===17)&&nearbyObject(i)&&state.secret&&!occupied(i))return ['tunnel','Пройти через лаз · 1 ход'];
  if(i===36&&nearbyObject(36)&&!state.rested&&state.hp<6)return ['rest','Перевязка: +2 здоровья · 1 ход'];
  return null;
 }
 function description(i){
  const foe=state.enemies.find(e=>e.hp>0&&e.pos===i);if(foe)return [foe.name+' · '+foe.hp+' здоровья',(foe.id==='guard'?'Тяжёлый удар: 2. После него — 2 хода восстановления.':'Удар: 1. После него — 1 ход восстановления.')+(objects()[i]?' Здесь также: '+objects()[i][0]+'.':'')];
  if(i===state.eventPos)return [state.seed%2?'Лесной родник':'Камень эха',state.eventDone?'Встреча уже завершена.':state.seed%2?'Вода восстановит здоровье или заряд рывка. Выберите, что сейчас нужнее.':'Шум отвлечёт хищника на четыре следующих хода. Или прочтите следы, чтобы открыть лаз.'];
  if(i===state.cachePos)return ['Забытый дневник',state.cacheDone?'Запись сохранена в коллекции историй.':'Необязательная находка. Можно потратить ход и узнать историю долины.'];
  if(state.contract==='rescue'&&i===rescueCell)return ['Раненый зверёк',state.carrying?'Зверёк у вас на руках. Рывок недоступен; ходить и пользоваться лазом можно.':'Сначала подготовьте обратный путь. При переноске рывок недоступен.'];
  if(state.contract==='survey'&&[0,24,35].includes(i))return [objects()[i][0],state.stones.includes(i)?'Камень уже пробуждён.':i===0?'Откроет скрытый лаз между берегами.':i===24?'Рывки: '+state.charges+' → '+Math.min(2,state.charges+1)+'. '+(state.charges===2?'Сейчас бонус пропадёт: можно вернуться после рывка.':'Восстановит один заряд.'):'Защита: '+state.ward+' → 2. Можно получить её до опасного участка.'];
  if(i===21&&state.layout===2&&!state.repaired)return ['Разрушенный мост','Для ремонта достаточно одного хода. Можно также найти лаз на западном берегу.'];
  if(i===0)return ['Сундук смотрителя',state.contract==='beacon'&&state.approach==='guard'?'В этом забеге линзу нужно получить у стража.':state.contract!=='beacon'?'Сегодня задание ведёт в другое место.':state.chest?'Печати открыты.':state.clue?'Порядок печатей: '+codeText()+'.':'Три печати. Подсказка вырезана на камне рядом.'];
  if(i===6)return ['Письмена на камне',codeText()+'. Порядок печатей сундука.'];
  if(i===12||i===17)return [state.secret?'Скрытый лаз':'Старые корни',state.secret?'Лаз соединяет два берега. Проход в обе стороны.': 'Питомец чувствует движение воздуха. Попробуйте чутьё рядом с корнями.'];
  if(i===5)return ['Лесной маяк',state.contract!=='beacon'?'Сегодня у вас другая цель: '+contracts[state.contract].brief:state.lens?'Линза у вас. Зажечь маяк можно с соседней клетки; это сразу завершит вылазку.':'Нужна одна линза. Найдите её в руинах или победите стража.'];
  if(i===36)return ['Лагерь',state.contract==='rescue'&&state.carrying?'Зверёк в безопасности. Можно завершить задание.':state.contract==='survey'?`Камней пробуждено: ${state.stones.length}/3. После всех трёх вернитесь сюда.`:state.rested?'Перевязка уже использована.':'Одна перевязка восстановит до 2 здоровья.'];
  return [!ground(i)&&water.has(i)?'Река':!ground(i)&&rock.has(i)?'Заросли и камни':'Тропа',!ground(i)&&water.has(i)?'Ищите мост или скрытый проход.':!ground(i)&&rock.has(i)?'Пройти здесь нельзя.':'Нажмите соседнюю клетку для движения.'];
 }
 function render(){
  const prep=state.status==='prep';el('lh-prep').hidden=!prep;el('lh-play').hidden=prep;el('lh-title').textContent=prep?'Выберите цель':contracts[state.contract].title;
  if(prep){el('lh-phase').textContent='Подготовка';el('lh-prep').innerHTML=`<div class="lh-contracts">${Object.entries(contracts).map(([key,c])=>`<button type="button" data-contract="${key}" class="lh-contract cursor-interaction" aria-label="${c.title}" aria-pressed="${state.contract===key}"><strong>${({beacon:'Маяк',rescue:'Спасение',survey:'Камни'})[key]}</strong></button>`).join('')}</div><p class="lh-brief">${contracts[state.contract].brief}</p><button type="button" data-depart class="lh-confirm cursor-interaction">Отправиться</button><details class="lh-conditions"><summary>Условия вылазки · ${terrains[state.layout][0]}</summary>${terrains[state.layout][1]}<br>Следы ведут к ${state.seed%2?'лесному роднику':'камню эха'}.</details><button type="button" data-album class="lh-text cursor-interaction">Истории долины: ${state.memory.stories.length}/5</button><div id="lh-album" hidden></div>`;if(state.contract==='beacon')el('lh-prep').querySelector('.lh-contracts').insertAdjacentHTML('afterend',`<label class="lh-approach">Цель маршрута<select data-approach><option value="any" ${state.approach==='any'?'selected':''}>Любой путь к линзе</option><option value="guard" ${state.approach==='guard'?'selected':''}>Через бой со стражем</option><option value="ruins" ${state.approach==='ruins'?'selected':''}>Через печати сундука</option></select></label>`);return;}
  const ended=state.status!=='playing',plans=ended?[]:busy?playback:intents();
  el('lh-targets').hidden=ended||busy||!!travel||mode==='lure';el('lh-targets').innerHTML=objectiveTargets().map(([i,label])=>`<button type="button" data-pin="${i}" class="cursor-interaction" aria-label="Отметить: ${label}. Без движения">${label} ⌖</button>`).join('');el('lh-actor-hero').dataset.carrying=String(state.carrying);
  const lureCells=mode==='lure'?lureTargets():[],noiseAt=mode==='lure'?selected:state.lure?.pos;
  const routePreview=!busy&&!travel&&selected!==null?routePlan(selected):null,routeCells=travel?travel.cells:routePreview?.cells.slice(1)||[];
  el('lh-phase').textContent=ended?'Завершено':busy?'Ход врагов':travel?'Идём по тропе':mode==='lure'?'Выбор приманки':'Ваш ход';el('lh-lure-controls').hidden=mode!=='lure';
  el('lh-travel').hidden=!travel;el('lh-travel-progress').textContent=travel?'Пройдено: '+travel.done+'/'+travel.total+' · каждый шаг — ход':'';el('lh-travel-stop').disabled=!!travel?.stopRequested;el('lh-travel-stop').textContent=travel?.stopRequested?'Завершаем ход…':'Стоп';el('lh-journal').disabled=!!travel;
  el('lh-hp').textContent=state.hp+'/6';el('lh-charges').textContent=state.charges+' рывка';el('lh-turn').textContent=state.turn;el('lh-ward').hidden=state.ward===0;el('lh-ward').textContent='Защита '+state.ward;
  el('lh-goal').textContent=state.contract==='rescue'?(state.carrying?'Зверёк на руках · вернитесь в лагерь':'Найдите раненого зверька на востоке'):state.contract==='survey'?`Пробудите камни: ${state.stones.length}/3${state.stones.length===3?' · в лагерь':''}`:state.lens?'Линза найдена · зажгите маяк':state.approach==='guard'?'Получите линзу у стража':state.approach==='ruins'?'Получите линзу из сундука':'Найдите линзу для маяка';
  for(let i=0;i<42;i++){
   const b=el('lh-board').children[i],known=state.seen.includes(i)||i===5||(state.contract==='rescue'&&i===rescueCell)||(state.contract==='survey'&&[0,24,35].includes(i)),enemy=state.enemies.find(e=>e.hp>0&&e.pos===i),obj=objects()[i];
   const threat=plans.some(p=>p.type==='attack'&&p.cells.includes(i)&&state.seen.includes(state.enemies.find(e=>e.id===p.id).pos)),step=state.seen.includes(i)&&plans.some(p=>p.type==='move'&&p.to===i&&state.seen.includes(state.enemies.find(e=>e.id===p.id).pos));
   b.dataset.terrain=state.layout===1&&[38,39,40].includes(i)?'path':i===21&&state.layout===2&&!state.repaired?'water':water.has(i)?'water':rock.has(i)?'stone':i===21?'bridge':[30,31,32,26,20,22,23,17,11,5].includes(i)?'path':'grass';
   const routeIndex=routeCells.indexOf(i);b.dataset.routeOrder=routeIndex>=0?String(routeIndex+1+(travel?.done||0)):'';
   b.className='lh-cell cursor-interaction'+(!known?' lh-fog':'')+(!busy&&!travel&&!ended&&(mode==='attack'?enemy&&dist(state.pos,i)===1:canMove(i))?' lh-reach':'')+(known&&threat?' lh-danger':'')+(step?' lh-enemystep':'')+(selected===i?' lh-selected':'')+(routeIndex>=0?' lh-route':'');
   if(mode==='lure')b.classList.toggle('lh-reach',lureCells.includes(i));if(noiseAt===i&&!ended)b.classList.add('lh-noise');
   if(panel==='scan'&&!busy&&!travel&&!ended&&scanCells(scanAim).includes(i))b.classList.add('lh-scan-area');
   const mover=state.seen.includes(i)&&plans.find(p=>p.type==='move'&&p.to===i&&state.seen.includes(state.enemies.find(e=>e.id===p.id).pos));b.dataset.direction=mover?direction(state.enemies.find(e=>e.id===mover.id).pos,i):'';
   let icon=known?(obj?obj[1]:rock.has(i)&&!ground(i)?'tree-pine':null):null;if(i===12&&state.secret)icon='door-open';if(i===0&&state.chest)icon='archive-restore';if(i===5&&state.status==='won'&&state.contract==='beacon')icon='sun';if(i===rescueCell&&state.contract==='rescue'&&state.carrying)icon='check';
   b.innerHTML=icon?`<i data-lucide="${icon}" aria-hidden="true"></i>`:'';
   if(panel==='scan'&&!busy&&!travel&&!ended&&scanCells(scanAim).includes(i))b.innerHTML+='<span class="lh-scan-mark" aria-hidden="true"></span>';
   if(known&&threat||step)b.innerHTML+=`<span class="lh-marks" aria-hidden="true">${known&&threat?'<span class="lh-strike">×</span>':''}${step?'<span>'+b.dataset.direction+'</span>':''}</span>`;
   if(noiseAt===i&&!ended)b.innerHTML+=`<span class="lh-noise-mark" aria-hidden="true">♪${mode==='lure'?'':state.lure.remaining}</span>`;
   const cost=!busy&&!travel&&!ended&&state.seen.includes(i)&&['walk','dash'].includes(mode)&&canMove(i)?moveCost({type:mode==='dash'?'dash':'move',to:i}):null;
   if(cost?.label)b.innerHTML+=`<span class="lh-cost" aria-hidden="true">${cost.label}</span>`;
   const [x,y]=xy(i);b.setAttribute('aria-label',(known?(enemy?enemy.name:obj?obj[0]:description(i)[0]):'Туман')+`, столбец ${x+1}, ряд ${y+1}`+(known&&threat?', клетка следующего удара':'')+(step?', сюда шагнёт хищник':'')+(routeIndex>=0?', шаг маршрута '+b.dataset.routeOrder:''));b.disabled=busy||!!travel;
   if(cost?.description)b.setAttribute('aria-label',b.getAttribute('aria-label')+', '+cost.description+'. '+forecastText({type:mode==='dash'?'dash':'move',to:i}));
   if(panel==='scan'&&scanCells(scanAim).includes(i))b.setAttribute('aria-label',b.getAttribute('aria-label')+', в выбранной области чутья');
   if(mode==='lure')b.setAttribute('aria-label',b.getAttribute('aria-label')+(lureCells.includes(i)?', можно направить эхо':', недоступно для эха'));if(noiseAt===i&&!ended)b.setAttribute('aria-label',b.getAttribute('aria-label')+(mode==='lure'?', выбранное место шума':', шум: ещё '+state.lure.remaining+' следующих ходов'));
  }
  sprite('hero',state.pos,true);for(const e of state.enemies)sprite(e.id,e.pos,e.hp>0&&state.seen.includes(e.pos),e.hp);
  const visiblePlans=plans.filter(p=>state.seen.includes(state.enemies.find(e=>e.id===p.id).pos));el('lh-intentions').hidden=ended||visiblePlans.length===0;el('lh-intentions').textContent=visiblePlans.map(p=>planText(state.enemies.find(e=>e.id===p.id),p)).join(' · ');
  const waiting=forecast({type:'wait'}),hasCosts=!!root.querySelector('.lh-cost');el('lh-risk').hidden=busy||!!travel||ended||!hasCosts&&waiting.hp===state.hp&&waiting.ward===state.ward;el('lh-risk').textContent=(hasCosts?'На клетках: − здоровье, щ — расход защиты. ':'')+(waiting.hp<state.hp||waiting.ward<state.ward?'Если ждать: '+waiting.hp+'/6 здоровья'+(state.ward?' · защита '+waiting.ward:'')+(waiting.hp===0?' · отступление':''):'');
  if(mode==='lure')el('lh-risk').hidden=true;
  const pickedFoe=state.enemies.find(e=>e.hp>0&&e.pos===selected&&dist(state.pos,e.pos)===1);el('lh-bite').querySelector('strong').textContent=pickedFoe?'Атаковать':'Укус';
  el('lh-message').textContent=mode==='dash'?'Выберите точку рывка и проверьте прогноз. Выбор цели бесплатный.':mode==='attack'?pickedFoe?'Цель: '+pickedFoe.name+'. Можно атаковать или сменить цель.':'Выберите соседнего противника. Выбор цели бесплатный.':state.message+(state.lure?' Приманка: ещё '+state.lure.remaining+' х.':'');
  for(const id of ['lh-bite','lh-dash','lh-sniff','lh-wait','lh-return','lh-walk'])el(id).disabled=busy||!!travel;
  el('lh-bite').setAttribute('aria-pressed',String(mode==='attack'));el('lh-dash').setAttribute('aria-pressed',String(mode==='dash'));
  const benefit={cells:Math.max(...Object.keys(scanNames).map(d=>sniffBenefit(d).cells)),secret:sniffBenefit().secret};el('lh-dash').disabled=busy||!!travel||state.charges===0||state.carrying;el('lh-dash').querySelector('small').textContent=state.carrying?'Зверёк на руках':'2 клетки · 1 ход';el('lh-sniff').disabled=busy||!!travel||state.cooldown>0||(!benefit.cells&&!benefit.secret);el('lh-sniff-label').textContent=state.cooldown?'Через '+state.cooldown+' х.':benefit.cells||benefit.secret?'Выбрать область':'Нет новых следов';el('lh-walk').hidden=mode==='walk';
  el('lh-controls').hidden=ended||mode==='lure';el('lh-result').hidden=!ended;
  const detail=el('lh-detail');detail.hidden=selected===null||ended||!!travel;
  if(selected!==null&&!ended){const aimingDash=mode==='dash'&&canMove(selected),[title,body]=aimingDash?['Цель рывка','Два шага по прямой · расход 1 заряда.']:description(selected),action=aimingDash?null:actionFor(selected),foe=state.enemies.find(e=>e.hp>0&&e.pos===selected);const canBite=foe&&dist(state.pos,selected)===1;detail.innerHTML=`<strong>${safe(title)}</strong><p>${safe(body)}</p>${aimingDash?`<p>${forecastText({type:'dash',to:selected})}</p><button type="button" data-dash-to="${selected}" class="cursor-interaction" ${busy?'disabled':''}>Выполнить рывок · 1 ход</button>`:''}${foe?`<button type="button" data-quickbite="${foe.id}" class="cursor-interaction" ${busy||!canBite?'disabled':''}>Здоровье врага: ${foe.hp} → ${Math.max(0,foe.hp-2)} · укус за 1 ход</button>${canBite?'<p>'+forecastText({type:'attack',id:foe.id})+'</p>':''}`:''}${action?`<button type="button" data-context="${action[0]}" data-object="${selected}" class="cursor-interaction" ${busy?'disabled':''}>${action[1]}</button>`:''}${mode==='walk'&&dist(state.pos,selected)===1&&ground(selected)&&!occupied(selected)?`<button type="button" data-step-to="${selected}" class="cursor-interaction" ${busy?'disabled':''}>Шаг на эту клетку · 1 ход</button>`:''}`;}
  if(mode==='lure'){el('lh-message').textContent='Выберите подсвеченную клетку для шума. Выбор бесплатный.';detail.hidden=selected===null;detail.innerHTML=selected===null?'':`<strong>Шум: столбец ${selected%6+1}, ряд ${Math.floor(selected/6)+1}</strong><p>♪ — место приманки. Сейчас враг выполнит прежнее намерение; затем будет отвлечён на 4 хода. Укус снимет отвлечение.</p><p>${forecastText({type:'lure',to:selected})}</p><button type="button" data-place-lure="${selected}" class="cursor-interaction">Направить эхо сюда · 1 ход</button>`;}
  if(selected!==null&&!ended&&!busy&&!travel&&detail.querySelector('[data-context]')){const action=actionFor(selected);if(action&&!['event','chest'].includes(action[0])){const f={type:action[0],at:selected,to:selected===12?17:12};detail.innerHTML+=`<p data-context-forecast>${forecastText(f,'Итог взаимодействия')}</p>`;}}
  if(routePreview)detail.innerHTML+=`<p>Маршрут: ходов ${routePreview.cells.length-1}. ${safe(routePreview.reason)}</p><button type="button" data-follow-route="${selected}" class="cursor-interaction">Идти по маршруту · ходов ${routePreview.cells.length-1}</button>`;
  if(detail.hidden)detail.innerHTML='';
  if(ended){const best=state.memory.records?.find(r=>r.key===recordKey());el('lh-result').innerHTML=`<h3>${state.status==='won'?(state.contract==='rescue'?'Зверёк спасён':state.contract==='survey'?'Камни заговорили':'Маяк снова горит'):state.status==='lost'?'Питомец отступил':'Вы вернулись'}</h3><p>Ходов: ${state.turn} · Здоровье: ${state.hp}/6 · Истории: ${state.memory.stories.length}/5</p>${best?`<p>Лучшее в этих условиях и пути: ${best.turn} ходов. Самое бережное: ${best.hp}/6 здоровья.</p>`:''}<button type="button" data-retry class="cursor-interaction">Повторить те же условия</button><button type="button" data-restart class="cursor-interaction">Другие условия</button><small>Повторы тренировочные, без реальных наград.</small>`;}
  el('lh-message').hidden=!el('lh-message').textContent.trim();
  if(mode==='lure')el('lh-journal').disabled=true;renderPanel();icons();
 }
 function renderPanel(){const p=el('lh-panel');p.hidden=!panel;if(!panel)return;
  if(panel==='scan'){const gain=sniffBenefit(scanAim);p.innerHTML=`<h3>Куда направить чутьё?</h3><p>Вокруг — радиус 4. Сектор — до 6 клеток. Корни рядом проверяются в любом направлении.</p><div class="lh-scan-options">${Object.entries(scanNames).map(([d,label])=>`<button type="button" data-scan-dir="${d}" class="cursor-interaction" aria-pressed="${scanAim===d}">${label} · +${sniffBenefit(d).cells}</button>`).join('')}</div><p role="status" aria-live="polite">Новых клеток: ${gain.cells}.${gain.secret?' Можно найти лаз у корней.':''}</p><p>${forecastText({type:'sniff'})}</p><button type="button" data-scan-cast class="lh-confirm cursor-interaction" ${state.cooldown||!gain.cells&&!gain.secret?'disabled':''}>Исследовать область · 1 ход</button><button type="button" data-close class="lh-text cursor-interaction">Отмена · без хода</button>`;return;}
  if(panel==='journal')p.innerHTML=`<h3>Журнал вылазки</h3><p>Управление: шаг по соседней клетке. Дальние объекты можно осматривать бесплатно. Укус и рывок требуют выбора цели.</p><ul>${state.journal.map(t=>`<li>${safe(t)}</li>`).join('')||'<li>Долина ждёт своих открытий.</li>'}</ul><button type="button" data-close class="lh-text cursor-interaction">Закрыть · без хода</button>`;
  else if(panel==='chest'){
   const matches=state.seals.filter((value,i)=>sealKeys[value]===code()[i]).length,solved=matches===3;
   p.innerHTML=`<h3>Связанные печати</h3><p><strong>${state.clue?'Цель: '+codeText():'Цель начертана на камне рядом'}</strong></p><p>Поворот меняет эту печать и следующую. Третья связана с первой.</p><div class="lh-seals">${state.seals.map((value,i)=>`<button type="button" data-seal="${i}" class="cursor-interaction ${state.sealLast!==null&&[state.sealLast,(state.sealLast+1)%3].includes(i)?'lh-linked':''} ${state.sealHint===i?'lh-hinted':''}" aria-label="Печать ${i+1}: ${sealLabels[value]}. Поворот изменит печати ${i+1} и ${(i+1)%3+1}" ${busy?'disabled':''}><small>${i+1} ↻ ${(i+1)%3+1}</small><i data-lucide="${sealIcons[value]}" aria-hidden="true"></i><strong>${sealLabels[value]}</strong><small>${state.sealHint===i?'Подсказка':state.clue&&sealKeys[value]===code()[i]?'✓ совпала':'повернуть'}</small></button>`).join('')}</div><p id="lh-seal-feedback" role="status" aria-live="polite">${state.clue?(solved?'Узор совпал. Можно открыть сундук.':'Совпало: '+matches+'/3.'+(state.sealHint!==null?' Подсказка: поверните печать '+(state.sealHint+1)+'.':'')):'Осмотрите камень, чтобы узнать цель.'}</p><div class="lh-seal-tools"><button type="button" data-seal-hint class="lh-text cursor-interaction" ${!state.clue||busy?'disabled':''}>Подсказать поворот</button><button type="button" data-clear class="lh-text cursor-interaction" ${busy?'disabled':''}>Исходный узор</button></div><button type="button" data-submit class="lh-confirm cursor-interaction" ${busy?'disabled':''}>${solved?'Открыть сундук':'Проверить печати'} · 1 ход</button><p>Повороты и подсказка бесплатны. Проверка всегда занимает ход.</p><button type="button" data-close class="lh-text cursor-interaction">Закрыть · узор сохранится</button>`;
  }
  else if(panel==='event'){
   const spring=state.seed%2,heal=Math.min(2,6-state.hp),charge=state.carrying?0:Math.min(1,2-state.charges),targets=lureTargets(),e=state.enemies.find(e=>e.id==='prowler');
   p.innerHTML=`<h3>${spring?'Лесной родник':'Камень эха'}</h3><p>Одно решение на вылазку. Ход тратится при подтверждении.</p>`;
   if(spring)p.innerHTML+=`<button type="button" data-encounter="heal" class="lh-choice cursor-interaction" ${heal?'':'disabled'}><strong>Напиться · +${heal} здоровья · 1 ход</strong><small>${heal?'Восстановление сразу':'Здоровье уже полное'}</small></button><button type="button" data-encounter="charge" class="lh-choice cursor-interaction" ${charge?'':'disabled'}><strong>Наполнить флягу · +${charge} рывок · 1 ход</strong><small>${state.carrying?'При переноске рывок недоступен':charge?'Заряд можно использовать в этой вылазке':'Заряды уже полные'}</small></button>`;
   else p.innerHTML+=`<button type="button" data-encounter="lure" class="lh-choice cursor-interaction" ${targets.length?'':'disabled'}><strong>Выбрать место шума · без хода</strong><small>${targets.length?'Затем подтвердите приманку на 4 следующих хода':e.hp===0?'Хищник повержен':!state.seen.includes(e.pos)?'Сначала обнаружьте хищника':'Нет открытого свободного пути для приманки'}</small></button><button type="button" data-encounter="trail" class="lh-choice cursor-interaction" ${state.secret?'disabled':''}><strong>Прочесть следы · открыть лаз · 1 ход</strong><small>${state.secret?'Лаз уже открыт':'Можно обойти мост без поиска у корней'}</small></button>`;
   p.innerHTML+='<button type="button" data-close class="lh-text cursor-interaction">Пройти мимо · без хода</button>';
  }
 }
 function lureTargets(){
  const e=state.enemies.find(e=>e.id==='prowler');if(state.status!=='playing'||state.seed%2||state.eventDone||!nearbyObject(state.eventPos)||!e||e.hp===0||!state.seen.includes(e.pos))return [];
  const queue=[e.pos],seen=new Set(queue);while(queue.length){const last=queue.shift();for(const n of neighbors(last))if(state.seen.includes(n)&&ground(n)&&n!==state.pos&&!occupied(n,e.id)&&!seen.has(n)){seen.add(n);queue.push(n);}}
  return [...seen].filter(n=>n!==e.pos);
 }
 function refreshSeals(button){const focused=document.activeElement===button;const selector=button.dataset.seal!==undefined?'[data-seal="'+button.dataset.seal+'"]':button.hasAttribute('data-seal-hint')?'[data-seal-hint]':'[data-clear]';renderPanel();icons();if(focused)root.querySelector(selector)?.focus({preventScroll:true});save();}
 async function commit(action){
  if(busy||state.status!=='playing'||travel&&action.routeToken!==travel.token)return;const frozen=intents(),currentEpoch=epoch,focused=action.type==='attack'?action.id:null,hadFocus=root.contains(document.activeElement)&&document.activeElement.tagName==='BUTTON';busy=true;playback=frozen.slice();mode='walk';panel='';selected=null;
  if(action.type!=='sniff')state.cooldown=Math.max(0,state.cooldown-1);
  let message='';
  if(action.type==='move'||action.type==='dash'){if(action.type==='dash')state.charges--;state.pos=action.to;message=action.type==='dash'?'Рывок: −1 заряд.':'';}
  if(action.type==='attack'){const enemy=state.enemies.find(e=>e.id===action.id);enemy.hp=Math.max(0,enemy.hp-2);hit(enemy.id);message=enemy.hp?'Укус: −2 здоровья противнику.':enemy.name+' повержен.';if(enemy.id==='prowler'&&state.lure){state.lure=null;message+=' Приманка больше не отвлекает хищника.';}if(enemy.hp===0){note(enemy.name+' повержен.');if(enemy.id==='guard'&&!state.lens&&state.contract==='beacon'&&state.approach!=='ruins'){state.lens=true;state.lensSource='guard';message+=' Линза найдена!';note('Линза получена у стража моста.');}}}
  if(action.type==='sniff'){const benefit=sniffBenefit(action.direction);state.cooldown=3;state.seen=[...new Set([...state.seen,...scanCells(action.direction)])];reveal();message='Чутьё: +'+benefit.cells+' клеток. ';if(benefit.secret){state.secret=true;message+='Найден лаз. ';note('Чутьё открыло лаз у корней: оба берега соединены.');}message+=trailHint();}
  if(action.type==='tunnel'){state.pos=action.to;state.secretUsed=true;message='Питомец пробрался на другой берег.';note('Скрытый лаз исследован.');}
  if(action.type==='chest'){if(action.correct&&state.approach!=='guard'){state.chest=true;if(!state.lens){state.lens=true;state.lensSource='ruins';}message='Печати открылись. Линза у вас!';note('Печати сундука открыты: '+codeText()+'.');}else message='Печати не открылись. Проверьте порядок на камне.';}
  if(action.type==='rest'){state.hp=Math.min(6,state.hp+2);state.rested=true;message='Перевязка восстановила здоровье.';note('Перевязка в лагере использована.');}
  if(action.type==='rescue'){state.carrying=true;message='Зверёк у вас на руках. Дойдите до лагеря; рывок недоступен.';note('Раненый зверёк найден. Нужно вернуться в лагерь.');}
  if(action.type==='repair'){state.repaired=true;message='Мост восстановлен. Путь открыт.';note('Разрушенный мост восстановлен.');}
  if(action.type==='stone'){state.stones.push(action.at);if(action.at===0){state.secret=true;message='Камень указал скрытый лаз между берегами.';}else if(action.at===24){const recovered=Math.min(1,2-state.charges);state.charges+=recovered;message=recovered?'Камень восстановил заряд рывка.':'Камень пробуждён. Заряды уже полные.';}else{state.ward=2;message='Камень дал защиту от 2 единиц урона.';}note('Пробуждён камень: '+(action.at===0?'путь':action.at===24?'движение':'защита')+'.');}
  if(action.type==='heal'){state.eventDone=true;const n=Math.min(2,6-state.hp);state.hp+=n;message='Родник восстановил '+n+' здоровья.';note('У родника выбрано восстановление здоровья.');}
  if(action.type==='charge'){state.eventDone=true;state.charges=Math.min(2,state.charges+1);message='Фляга восстановила заряд рывка.';note('У родника выбрано восстановление рывка.');}
  if(action.type==='trail'){state.eventDone=true;state.secret=true;message='Следы у камня эха открыли лаз.';note('Следы открыли лаз без применения чутья.');}
  if(action.type==='lure'){state.eventDone=true;state.lure={pos:action.to,remaining:4};message='Шум отвлечёт хищника на четыре следующих хода. Сейчас он выполнит прежнее намерение.';note('Камень эха отвлекает хищника.');}
  if(action.type==='cache'){state.cacheDone=true;const id=(state.seed-1)%stories.length;state.memory.stories=[...new Set([...state.memory.stories,id])];message=stories[id];note('Найден дневник: '+stories[id]);}
  if(action.type==='wait')message='';
  state.turn++;reveal();state.message=message;
  if(action.type==='beacon'||action.type==='deliver'){state.status='won';state.message=action.type==='beacon'?'Маяк зажжён. Вы в безопасности.':state.contract==='rescue'?'Зверёк доставлен в лагерь. Он в безопасности.':'Все камни исследованы. Вы вернулись в лагерь.';busy=false;note(state.message);record();render();if(hadFocus)root.querySelector('[data-retry]')?.focus({preventScroll:true});save();return;}
  render();await sleep(180);if(currentEpoch!==epoch)return;
  for(const intent of frozen){const e=state.enemies.find(e=>e.id===intent.id);if(e.hp===0)continue;
   if(intent.type==='attack'){e.recovery=e.id==='guard'?2:1;if(intent.cells.includes(state.pos)){const previous=state.hp,hitState=hitResult(state.hp,state.ward,intent.damage);state.ward=hitState.ward;state.hp=hitState.hp;hit('hero');message+=' '+e.name+': −'+(previous-state.hp)+' здоровья'+(hitState.absorbed?', защита поглотила '+hitState.absorbed:'')+'.';}else message+=' '+e.name+' промахнулся.';}
   if(intent.type==='recover')e.recovery=Math.max(0,(e.recovery||0)-1);
   if(intent.type==='move'){if(intent.to!==state.pos&&!occupied(intent.to,e.id)&&ground(intent.to)){e.pos=intent.to;e.patrol++;}}
   playback=playback.filter(p=>p.id!==intent.id);state.message=message;reveal();render();await sleep(180);if(currentEpoch!==epoch)return;if(state.hp===0)break;
  }
  if(state.lure&&action.type!=='lure'){state.lure.remaining--;if(state.lure.remaining<=0)state.lure=null;}
  if(state.hp===0){state.status='lost';state.message='Питомец отступил в лагерь. Реальных потерь нет.';record();}
  busy=false;state.message=state.status==='lost'?state.message:message;reveal();
  if(state.status==='playing'){const target=focused?state.enemies.find(e=>e.id===focused&&e.hp>0):null;selected=target?target.pos:actionFor(36)?.[0]==='deliver'?36:state.contract==='beacon'&&state.lens&&nearbyObject(5)?5:objects()[state.pos]?state.pos:null;}
  render();if(hadFocus&&!root.contains(document.activeElement)){if(state.status==='playing')(focused&&state.enemies.some(e=>e.id===focused&&e.hp>0)?el('lh-bite'):el('lh-board').children[state.pos]).focus({preventScroll:true});else root.querySelector('[data-retry]')?.focus({preventScroll:true});}save();
 }
 root.addEventListener('change',e=>{if(e.target.matches('[data-approach]')&&state.status==='prep'&&['any','guard','ruins'].includes(e.target.value)){state.approach=e.target.value;render();root.querySelector('[data-approach]')?.focus({preventScroll:true});save();}});
 root.addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b||b.disabled)return;
  if(b.id==='lh-travel-stop'&&travel){travel.stopRequested=true;render();return;}
  if(travel)return;
  if(mode==='lure'){
   if(busy||state.status!=='playing')return;
   if(b.id==='lh-lure-cancel'){mode='walk';selected=state.eventPos;panel='event';render();el('lh-panel').querySelector('[data-encounter="lure"]')?.focus({preventScroll:true});return;}
   if(b.dataset.cell!==undefined){const to=Number(b.dataset.cell);if(lureTargets().includes(to)){selected=to;render();}else{el('lh-message').textContent='Выберите открытую свободную клетку, до которой есть открытый путь от хищника.';}return;}
   if(b.dataset.placeLure!==undefined){const to=Number(b.dataset.placeLure);if(to===selected&&lureTargets().includes(to))commit({type:'lure',to});return;}
   return;
  }
  if(b.dataset.contract&&state.status==='prep'&&contracts[b.dataset.contract]){state.contract=b.dataset.contract;render();root.querySelector(`[data-contract="${state.contract}"]`)?.focus({preventScroll:true});save();return;}
  if(b.hasAttribute('data-depart')&&state.status==='prep'){state.status='playing';state.message=state.memory.played?'':'Соседняя тропа — шаг. Объект — бесплатный осмотр. Враги отвечают после вашего действия.';reveal();render();save();return;}
  if(b.hasAttribute('data-album')&&state.status==='prep'){const a=el('lh-album');a.hidden=!a.hidden;a.innerHTML=state.memory.stories.length?state.memory.stories.map(n=>`<p>${safe(stories[n])}</p>`).join(''):'<p>В пути можно найти забытые дневники. Они сохраняются только в этом пробном режиме.</p>';return;}
  if(b.id==='lh-journal'){panel=panel==='journal'?'':'journal';render();return;}
  if(b.hasAttribute('data-close')){const closed=panel;panel='';render();(closed==='scan'?el('lh-sniff'):closed==='journal'?el('lh-journal'):root.querySelector(`[data-context="${closed==='chest'?'chest':'event'}"]`)||el('lh-board').children[state.pos]).focus({preventScroll:true});return;}
  if(b.hasAttribute('data-restart')||b.hasAttribute('data-retry')){if(state.status==='playing'||state.status==='prep')return;epoch++;const retry=b.hasAttribute('data-retry'),keys=Object.keys(contracts),oldLayout=state.layout,oldRescue=rescueCell,oldApproach=state.approach;state=base(state.memory,retry?state.seed:state.seed%1000000+1,retry?state.contract:keys[(keys.indexOf(state.contract)+1)%keys.length]);if(retry){state.layout=oldLayout;state.rescueAt=oldRescue;state.approach=oldApproach;}rescueCell=state.rescueAt;busy=false;mode='walk';panel='';selected=null;scanAim='all';reveal();render();root.querySelector('[data-depart]')?.focus({preventScroll:true});save();return;}
  if(busy||state.status!=='playing')return;
  if(b.dataset.pin!==undefined){const to=Number(b.dataset.pin);if(objectiveTargets().some(([i])=>i===to)){selected=to;mode='walk';panel='';render();root.querySelector(`[data-pin="${to}"]`)?.focus({preventScroll:true});}return;}
  if(b.dataset.scanDir&&panel==='scan'&&Object.hasOwn(scanNames,b.dataset.scanDir)){scanAim=b.dataset.scanDir;render();root.querySelector(`[data-scan-dir="${scanAim}"]`)?.focus({preventScroll:true});return;}
  if(b.hasAttribute('data-scan-cast')&&panel==='scan'){const gain=sniffBenefit(scanAim);if(!state.cooldown&&(gain.cells||gain.secret))commit({type:'sniff',direction:scanAim});return;}
  if(b.dataset.followRoute!==undefined){followRoute(Number(b.dataset.followRoute));return;}
  if(b.dataset.seal!==undefined&&panel==='chest'&&nearbyObject(0)&&!state.chest){const index=Number(b.dataset.seal);if([0,1,2].includes(index)){state.seals=rotateSeals(state.seals,index);state.sealHint=null;state.sealLast=index;refreshSeals(b);}return;}
  if(b.hasAttribute('data-seal-hint')&&panel==='chest'&&nearbyObject(0)&&!state.chest&&state.clue){const steps=solveSeals(state.seals,code().map(x=>sealKeys.indexOf(x)));state.sealHint=steps?.[0]??null;refreshSeals(b);return;}
  if(b.dataset.quickbite){const enemy=state.enemies.find(e=>e.id===b.dataset.quickbite&&e.hp>0);if(enemy&&dist(state.pos,enemy.pos)===1)commit({type:'attack',id:enemy.id});return;}
  if(b.dataset.dashTo!==undefined){const to=Number(b.dataset.dashTo);if(mode==='dash'&&canMove(to))commit({type:'dash',to});return;}
  if(b.dataset.stepTo!==undefined){const to=Number(b.dataset.stepTo);if(mode==='walk'&&canMove(to))commit({type:'move',to});return;}
  if(b.hasAttribute('data-clear')&&panel==='chest'&&nearbyObject(0)&&!state.chest){state.seals=initialSeals(state.seed);state.sealHint=null;state.sealLast=null;refreshSeals(b);return;}
  if(b.hasAttribute('data-submit')){if(panel==='chest'&&nearbyObject(0)&&!state.chest)commit({type:'chest',correct:sealsMatch()});return;}
  if(b.dataset.encounter&&panel==='event'&&nearbyObject(state.eventPos)&&!state.eventDone){const type=b.dataset.encounter;if(type==='lure'){if(lureTargets().length){mode='lure';selected=null;panel='';render();}return;}if(type==='heal'&&state.seed%2&&state.hp<6||type==='charge'&&state.seed%2&&!state.carrying&&state.charges<2||type==='trail'&&state.seed%2===0&&!state.secret)commit({type});return;}
  if(b.dataset.context){const i=Number(b.dataset.object),type=b.dataset.context;if(!actionFor(i)||actionFor(i)[0]!==type)return;
   if(type==='chest'){panel='chest';renderPanel();icons();return;}
   if(type==='event'){panel='event';renderPanel();icons();return;}
   if(type==='tunnel'){const to=i===12?17:12;if(occupied(to)){state.message='Выход из лаза занят. Ход не потрачен.';render();return;}commit({type,to});return;}
   commit({type,at:i});return;
  }
  if(b.id==='lh-walk'){mode='walk';selected=null;render();return;}
  if(b.id==='lh-bite'){const foe=state.enemies.find(e=>e.hp>0&&e.pos===selected&&dist(state.pos,e.pos)===1);if(foe){commit({type:'attack',id:foe.id});return;}mode='attack';const adjacent=state.enemies.filter(e=>e.hp>0&&dist(state.pos,e.pos)===1);selected=adjacent.length===1?adjacent[0].pos:null;panel='';render();return;}
  if(b.id==='lh-dash'){mode=mode==='dash'?'walk':'dash';selected=null;panel='';render();return;}
  if(b.id==='lh-sniff'){if(state.cooldown===0&&Object.keys(scanNames).some(d=>{const gain=sniffBenefit(d);return gain.cells||gain.secret;})){scanAim='all';panel='scan';mode='walk';selected=null;render();}return;}
  if(b.id==='lh-wait'){commit({type:'wait'});return;}
  if(b.id==='lh-return'){state.status='returned';record();mode='walk';panel='';selected=null;state.message='Питомец вернулся в лагерь. Реальных потерь нет.';render();save();return;}
  if(b.dataset.cell!==undefined){const i=Number(b.dataset.cell);if(mode==='attack'){const enemy=state.enemies.find(e=>e.hp>0&&e.pos===i);if(enemy){selected=i;render();return;}state.message='Для укуса нужен противник на соседней клетке.';mode='walk';}
   else if(canMove(i)){if(mode==='dash'||actionFor(i)){selected=i;render();return;}commit({type:'move',to:i});return;}
   if(state.seen.includes(i)||i===5||(state.contract==='rescue'&&i===rescueCell)||(state.contract==='survey'&&[0,24,35].includes(i))){selected=i;render();}else{state.message='Сначала подойдите ближе. Ход не потрачен.';render();}
  }
 });
 restore(window.PetPractice?.widgetState);render();
 window.addEventListener('pet-practice:restore',e=>{if(e.detail?.globals&&Object.hasOwn(e.detail.globals,'widgetState')){const snapshot=e.detail.globals.widgetState;if(snapshot?.privateContent?._pvPublication?.id===publicationId)return;restore(snapshot);render();}});
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&travel){travel.stopRequested=true;render();}});
})();
