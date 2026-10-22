// Exercise the shipped renderers and navigation, including asynchronous preparation.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const root={dataset:{},innerHTML:'',querySelectorAll:()=>[],querySelector:()=>null,contains:()=>false,insertAdjacentHTML(_,s){this.innerHTML+=s;}};
const nodes={'pg-pets':root,'tr-send-forecast':{innerHTML:''},'tr-send-quote':{textContent:''}};
let timers=[],reads=0,sheets=[],forecasts=0;
const box={window:{openPetsV1(){},scrollY:130,scrollTo(){}},document:{activeElement:{dataset:{f:'pet-1'}},hidden:false,getElementById:id=>nodes[id]||null,querySelector:()=>null},_V3_PATHS:{},_backHooks:[],_activePage:'pets',_sysFlags:{pets_v2:true},_profileEsc:esc,_profileData:null,fmt:n=>String(n),rarLabel:()=> 'Редкий',v3Head:(s)=>`<h1>${esc(s)}</h1>`,v3GuideBtn:()=>'',v3EnterSync(){},_v3Icon:()=>'',_v3Row:(i,t,a,h)=>`<button onclick="${a}">${t} ${h}</button>`,_haptic(){},toast(){},el:id=>nodes[id]||null,setInterval(){},setTimeout(f){timers.push(f);return timers.length;},clearTimeout(){},crypto:{randomUUID:()=>String(Math.random())}};
vm.createContext(box);
for(const file of ['app.40.js','app.41.js','app.49.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../FastAPI/static',file),'utf8'),box);
const run=s=>vm.runInContext(s,box);
const rules={max_level:30,daily_soft_from:500,daily_soft_rate:.25,energy:{run:{3:15,6:30,9:45},watch:{9:10},pair:10},xp:{run:{3:70,6:150,9:250},watch:{9:100},expedition:1.2},calling_min_level:10,trait_slot_levels:[10,15,20],talisman_slots:2,talisman:{kinds:{},plus:{}},track:{daily:2},affinity_bonus:.2,swap:{}};
const pet={id:1,name:'Сова <тест>',icon:'🦉',rarity:'rare',species_id:'mirror_owl',energy:60,energy_max:100,level:13,ceiling:15,next_cost:1000,xp:500,bond_days:20,next_gate_days:50,stars:2,resilience:33,traits:[],talismans:[],trait_slots:1,track_points:5,favorite_route:'ruins',trial:{matches:1},equipment:{items:{compass:1},equipped:{tool:'compass'},starter_claimed:true}};
const gear={slots:{tool:'Инструмент',boots:'Обувь',guard:'Защита',charm:'Оберег',pack:'Сумка'},parts:2,energy:10,daily:3,attempts_left:2,craft_cost:8,upgrade_cost:{1:12,2:24},catalog:[{id:'compass',slot:'tool',name:'Компас',icon:'🧭',effects:['+4% Следов','+8% Следов','+12% Следов'],speciality:'navigation'},{id:'lens',slot:'tool',name:'Линза',icon:'🔎',effects:['Поиск I','Поиск II','Поиск III'],speciality:'search'},{id:'boots',slot:'boots',name:'Сапоги',icon:'🥾',effects:['Силы I','Силы II','Силы III'],speciality:'crossing'}]};
box.fixture={pets:[pet,{...pet,id:2,name:'Спутник',equipment:{items:{},equipped:{}}}],activities:[],slots:3,daily:{credited:625,max:625},rules,equipment:gear,durations:{run:[3,6,9],watch:[9]},routes:['forest','ruins'],pair:{unlocked:true},camp:{levels:{}},track:{attempts_left:2},trial:{}};
run('_tr.me=fixture;_tr.tab="collection";_tr.filter="free";');
run("trailPet(1);trailEquipment(1,'boots');trailGo('outing',1);trailEquipment(1,'pack');trailBack()");
assert.equal(run('_tr.view'),'outing');assert.equal(run('_tr.pet'),1);
run('trailBack()');assert.equal(run('_tr.view'),'equipment');assert.equal(run('_tr.gearSlot'),'boots');
run('trailBack();trailBack()');assert.equal(run('_tr.view'),'hub');assert.equal(run('_tr.tab'),'collection');assert.equal(run('_tr.filter'),'free');
run("trailGo('trial',1);trailPet(1);trailGo('trial',1);trailTrialPick(2);trailBack();trailBack()");assert.equal(run('_tr.trial.pet'),1,'nested trial selection restores the original candidate');
run('trailTab("overview")');let html=run('_TR_VIEWS.hub(_tr.me)');
assert.match(html,/Вылазка/);assert.match(html,/Выслеживание/);assert.match(html,/Испытание недели/);assert.match(html,/Отправить в путь/,'daily cap does not block activities');
run('_tr.me.activities=[{id:"a",pet_id:1,kind:"trek",hours:3,ready:true},{id:"b",pet_id:2,kind:"trek",hours:3,ready:true}]');html=run('_trSlots(_tr.me)');assert.equal((html.match(/<button[^>]*class="[^"]*v3-pill[^"]*"[^>]*>/g)||[]).filter(tag=>!tag.includes('v3-pill--ghost')).length,1,'ready work has one primary filled action');run('_tr.me.activities=[]');
run('_tr.pet=1');html=run('_TR_VIEWS.pet(_tr.me)');
assert.ok(html.indexOf('Пять слотов')<html.indexOf('Развитие'));assert.ok(html.includes('Сова &lt;тест&gt;'));assert.ok(!html.includes('Сова <тест>'));
run('_tr.me.activities=[{id:"run",pet_id:1,hours:3,kind:"trek",ends_at:"2099-01-01T00:00:00Z"}];_tr.me.pets[0].run_id="run"');
html=run('_TR_VIEWS.pet(_tr.me)');assert.match(html,/onclick="trailFeed\(1\)">/);assert.match(html,/onclick="trailGo\('track',1\)">/);assert.match(html,/onclick="trailGo\('trial',1\)">/);assert.match(html,/onclick="trailBuild\(1\)" disabled/);
run('_tr.me.pets[0].run_id=null;_tr.me.activities=[];_tr.gearSlot="tool"');html=run('_TR_VIEWS.equipment(_tr.me)');
assert.match(html,/Компас/);assert.match(html,/Линза/);assert.ok(!html.includes('Сапоги'));assert.match(html,/Не хватает 10 дет/);assert.match(html,/Заменит: Компас/);
run('_tr.me.equipment.open={pet_id:2};_tr.me.pets[1].outing=true');
assert.equal(run('_trPetMatches(_tr.me.pets[1],"busy")'),true);assert.equal(run('_trPetMatches(_tr.me.pets[1],"free")'),false);
run('_tr.me.equipment.open=null;_tr.me.pets[1].outing=false;_tr.view="pet";_tr.pet=1;_tr.send={pet:1,kind:"expedition",hours:6,route:"forest",routeSet:true,fitted:true,comp:2}');
run('_trSheet=html=>{};trailClose=()=>{};');run('trailPrepareSend()');assert.equal(run('_tr.sendDraft.hours'),6);assert.equal(run('_tr.sendDraft.route'),'forest');
run('_trLoad=async()=>{_tr.me.pets[0].energy=25;_tr.me.pets[1].outing=true;return true};_trSheet=html=>{savedHtml=html};_trForecastSchedule=()=>{forecastCount++};');
box.forecastCount=0;
(async()=>{
 await box.trailResumeSend(null);
 assert.equal(run('_tr.send.kind'),'expedition');assert.equal(run('_tr.send.hours'),6);assert.equal(run('_tr.send.route'),'forest');assert.equal(run('_tr.send.comp'),0,'unavailable companion removed after fresh read');
 assert.match(run('savedHtml'),/Не хватает сил: нужно 30/);assert.equal(box.forecastCount,1);
 // A slow /me must not open a send dialog after the player leaves preparation.
 let resolve;box.deferred=new Promise(r=>resolve=r);run('_tr.sendDraft={pet:1};_trLoad=()=>deferred;_trSheet=()=>{unexpectedSheet=true};unexpectedSheet=false;');
 const pending=box.trailResumeSend(null);run('trailTab("collection");trailPet(1)');resolve(true);await pending;assert.equal(run('unexpectedSheet'),false,'leaving and returning to the same pet invalidates an old resume request');
 let resolveAgain;box.deferred=new Promise(r=>resolveAgain=r);const once=box.trailResumeSend(null);await box.trailResumeSend(null);assert.ok(run('_tr.resumeRequest'));run('_tr.busy=true');resolveAgain(true);await once;assert.equal(run('unexpectedSheet'),false,'resume cannot open while a writer is active');run('_tr.busy=false');
 // A newly opened and closed preparation sheet also retires the old resume intent.
 let resolveDialog;box.deferred=new Promise(r=>resolveDialog=r);run('_tr.sendDraft={pet:1};');const staleDialog=box.trailResumeSend(null);run('_tr.dialog=(_tr.dialog||0)+1');resolveDialog(true);await staleDialog;assert.equal(run('unexpectedSheet'),false);
 // A replaced writer button reconnects focus after /me; navigation must not steal it back.
 const originalQuery=root.querySelector, originalActive=box.document.activeElement;let focused=0;box.document.body={};box.document.activeElement=box.document.body;root.querySelector=()=>({focus(){focused++}});
 await box._trRun({dataset:{f:'gear-equip-compass'},isConnected:false},async()=>{});assert.equal(focused,1);
 await box._trRun({dataset:{f:'gear-equip-compass'},isConnected:false},async()=>{run('_tr.nav++')});assert.equal(focused,1);
 root.querySelector=originalQuery;box.document.activeElement=originalActive;
 // Execute the real forecast scheduler with out-of-order replies.
 const src=fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.40.js'),'utf8');
 vm.runInContext(src.match(/^function _trForecastSchedule\([\s\S]*?^\}/m)[0],box);
 const replies=[];box.api=()=>new Promise(r=>replies.push(r));
 run('_tr.send={pet:1,kind:"trek",hours:3,route:"forest"}');box._trForecastSchedule();const first=timers.pop()();
 run('_tr.send.hours=6');box._trForecastSchedule();const second=timers.pop()();
 const q=n=>({min:{credited:n,raw:n},max:{credited:n,raw:n},factors:{build:1},paths:{},notice:'',reasons:[]});
 replies[1](q(60));await second;replies[0](q(30));await first;assert.equal(nodes['tr-send-quote'].textContent,'Прогноз: 60 Следов');
 // Outing replies still apply canonical state after Back, but cannot move the new screen.
 let finishOuting;box.api=()=>new Promise(r=>finishOuting=r);let scrollCalls=0;box.window.scrollTo=()=>{scrollCalls++};
 run('_tr.view="outing";_tr.me.equipment.open=null;_tr.needsRefresh=false');const starting=box.trailOutingStart(null,1);run('trailTab("collection")');const beforeStartReply=scrollCalls;
 finishOuting({outing:{id:'late-outing',pet_id:1,step:0,status:'active',log:[]},energy:15});await starting;assert.equal(scrollCalls,beforeStartReply);assert.equal(run('_tr.me.equipment.open.id'),'late-outing');
 run('_tr.view="outing";_tr.needsRefresh=false');const choosing=box.trailOutingChoose(null,0);run('trailTab("collection")');const beforeChoiceReply=scrollCalls;
 finishOuting({outing:{id:'late-outing',pet_id:1,step:1,status:'active',log:[]},parts:4});await choosing;assert.equal(scrollCalls,beforeChoiceReply);assert.equal(run('_tr.me.equipment.open.step'),1);
 console.log('PASS: contextual back stack, distinct readiness, busy eligibility, capped rewards, slot comparisons, fresh draft/companion, navigation and forecast races');
})().catch(e=>{console.error(e);process.exitCode=1});
