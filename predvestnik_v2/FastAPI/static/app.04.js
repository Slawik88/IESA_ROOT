// ── Центр активностей: единственный игровой вход релизной версии ──────────────
// Старые гача, аукцион, квесты, инвентарь и боевые режимы вынесены из
// доставляемого JavaScript. Их архивные данные остаются только для компенсации.

// Kept empty for the legacy public-profile renderer in app.06.js.  That
// renderer is not a player-facing route in the release, but this declaration
// makes a stale admin modal fail visually neutral instead of with ReferenceError.
const PET_SPECIES_EMOJI={};

const _ARENA_TABS=['game'];

function openRhythmV2Game(){ location.href=BASE+'/rhythm-v2'; }
function openMinesweeperGame(){ location.href=BASE+'/minesweeper'; }

// «Как играть» for people who have never played Mafia: plain steps + one line per role.
// Keep the markup semantic (details/ol/dl); styling hooks are listed in docs/MAFIA_DESIGN_HANDOFF.md.
const MAFIA_HOWTO_STEPS=[
  ['Напиши в группе «бот мафия»','Появится лобби. Все, кто хочет играть, нажимают «Войти». Нужно от 4 игроков.'],
  ['Получи роль в личке с ботом','Бот пришлёт её сам. Если не пишет — открой бота и нажми Start.'],
  ['Играй: ночь, обсуждение, голосование','Ночью роли с действиями жмут кнопки в личке. Днём все спорят в чате и голосуют кнопкой.'],
  ['Победа','Мирные побеждают, когда мафии не осталось. Мафия — когда её не меньше, чем остальных.']
];
const MAFIA_HOWTO_ROLES=[
  ['🧑','Мирный житель','Днём ищет мафию и голосует.'],
  ['🔫','Мафия','Ночью выбирает, кого убрать.'],
  ['🎩','Дон','Главный в мафии: решает, если мафиози спорят.'],
  ['💉','Доктор','Ночью лечит одного игрока.'],
  ['🔎','Детектив','Ночью проверяет, мафия ли игрок.']
];
const MAFIA_ART_ROLES=['citizen','mafia','don','doctor','detective'];
function mafiaArt(role,cls='',loading='lazy'){
  if(role!=='city'&&!MAFIA_ART_ROLES.includes(role))return '';
  return `<img class="${cls}" src="${BASE}/static/mafia-art/${role}.webp" alt="" width="${role==='city'?800:64}" height="${role==='city'?400:64}" loading="${loading}" decoding="async">`;
}
function mafiaHowTo(){
  const steps=MAFIA_HOWTO_STEPS.map(x=>`<li class="mafia-howto-step"><b>${esc(x[0])}</b><span>${esc(x[1])}</span></li>`).join('');
  const roles=MAFIA_HOWTO_ROLES.map((x,i)=>`<div class="mafia-howto-role"><dt>${mafiaArt(MAFIA_ART_ROLES[i],'mafia-role-art')}${x[0]} ${esc(x[1])}</dt><dd>${esc(x[2])}</dd></div>`).join('');
  return `<details class="mafia-howto"><summary class="mafia-howto-title">Как играть в Мафию</summary><ol class="mafia-howto-steps">${steps}</ol><dl class="mafia-howto-roles">${roles}</dl></details>`;
}

function mafiaDate(v){ if(!v) return ''; const d=new Date(v); return isNaN(d)?'':d.toLocaleDateString('ru-RU',{day:'numeric',month:'short'}); }
function openMafiaStats(){
  OM('🕵️ Мафия — моя история','<div class="loader">Загружаем историю…</div>',[{l:'Закрыть',f:'CM()'}]);
  api('/mafia-v1/me').then(d=>{
    const s=d.stats||{}, played=Number(s.played||0), wins=Number(s.wins||0);
    const role={citizen:['🧑','Мирный житель'],mafia:['🔫','Мафия'],don:['🎩','Дон'],doctor:['💉','Доктор'],detective:['🔎','Детектив']};
    const phase={lobby:'Набор игроков',night:'Ночь',discussion:'Обсуждение',voting:'Голосование',paused:'На паузе'};
    const r=m=>role[m.role]||['❔','Роль ещё не выдана'];
    const live=(d.live||[]).map(m=>`<div class="v3-line mafia-live"><span>${mafiaArt(m.role,'mafia-role-mini')}<b>${r(m)[0]} ${esc(r(m)[1])}</b><br><small>Идёт сейчас · ${esc(phase[m.phase]||m.phase)}</small></span></div>`).join('');
    const rows=(d.matches||[]).map(m=>{ const when=mafiaDate(m.finished_at||m.started_at), side=m.winner==='town'?'победили мирные':m.winner==='mafia'?'победила мафия':'';
      return `<div class="v3-line mafia-row"><span><b>${r(m)[0]} ${esc(r(m)[1])}</b><br><small>${esc([when,side].filter(Boolean).join(' · '))}</small></span><em class="mafia-res ${m.won===true?'win':''}">${m.won===true?'Победа':m.won===false?'Поражение':''}</em><button type="button" class="v3-link" onclick="openMafiaReview(${Number(m.match_id)})">Разбор ›</button></div>`; }).join('');
    const summary=played?`<div class="mafia-sum"><div><b>${played}</b><span>сыграно</span></div><div><b>${wins}</b><span>побед</span></div><div><b>${Math.round(wins*100/played)}%</b><span>успех</span></div></div>${s.favorite_role&&role[s.favorite_role]&&played>=3?`<p class="v3-stat-line">Чаще всего: ${esc(role[s.favorite_role][1])}</p>`:''}${Number(s.win_streak||0)>=2?`<p class="v3-stat-line">Серия побед: ${Number(s.win_streak)}${Number(s.win_streak)>=50?'+':''}</p>`:''}`:'';
    const hidden='';
    const empty='<div class="v3-empty">🕵️<b>Партий пока нет</b>В нужной Telegram-группе напиши: «бот мафия». Игра начнётся прямо там.</div>';
    el('mb').innerHTML=`${mafiaArt('city','mafia-city-art','eager')}${mafiaHowTo()}<div class="v3-eyebrow">Моя статистика</div>${summary}${live}${rows||(live?'':empty)}${hidden}`;
  }).catch(e=>{ el('mb').innerHTML=`<div class="v3-err">${esc(String(e))}</div>`; });
}

// Каждый режим показывается только при включённом серверном флаге (по умолчанию все выключены).
const _V3_GAMES = [
  {flag:'game_rhythm_v2', name:'Ритм', desc:'Бесконечный забег. Жми руны точно, скорость растёт.', hint:'Бесконечный забег, рейтинг подтверждённых результатов', cta:'Играть', open:'openRhythmV2Game()'},
  {flag:'game_minesweeper_v2', name:'Сапёр', desc:'Открывай клетки и ставь флаги. В рейтинг попадают только победы.', hint:'Логика, победы попадают в топ', cta:'Играть', open:'openMinesweeperGame()'},
  {flag:'game_casino_v1', name:'Казино', desc:'Руны удачи, колесо и кости на жетоны. Подарок жетонов каждый день.', hint:'Слоты, колесо и кости · подарок дня', cta:'Играть', open:'openCasino()'},
  {flag:'game_mafia_v1', name:'Мафия', desc:'Играется в групповом чате: напиши «бот мафия». Здесь история ваших партий.', hint:'Играется в чате, здесь ваши партии', cta:'Мои партии', open:'openMafiaStats()'}
];
// Личный результат в строке игры: из таблицы сезона (`personal`). Только Ритм и Сапёр; топ Мафии по победам живёт на экране «Топ».
const _V3_GAME_BOARDS={game_rhythm_v2:'/rhythm-v2/leaderboard/normal', game_minesweeper_v2:'/minesweeper-v2/leaderboard/normal'};
let _hubSeq=0, _hubScore={}, _hubAt={};   // _hubAt: когда пришёл результат (таблица пересчитывает сезон на сервере, не дёргаем чаще раза в минуту)   // _hubScore[flag]: undefined = грузится, null = нет данных, {place,best_score} = есть
function _hubLine(g){
  if(!_V3_GAME_BOARDS[g.flag])return g.hint;
  const r=_hubScore[g.flag];
  if(r===undefined)return 'Загружаем результат…';
  if(r===null)return 'Результат пока недоступен';
  const pr=r.personal, tag=g.flag==='game_minesweeper_v2'?'Обычный · ':'';   // у Сапёра берётся одна сложность
  if(!pr)return tag+'Ещё не играл';
  const best=g.flag==='game_minesweeper_v2'?_hubTime(pr.best_elapsed_ms):fmt(pr.best_score);
  return `${tag}Лучший ${best} · место #${Number(pr.place)}`;
}
function _hubTime(ms){ const t=Math.max(0,Math.round(Number(ms)/1000)||0); return `${Math.floor(t/60)}:${String(t%60).padStart(2,'0')}`; }
function _hubRow(g,chev){
  return `<button type="button" class="v3-game" data-game="${g.flag}" onclick="${g.open}"><span>${g.flag==='game_mafia_v1'?mafiaArt('city','mafia-hub-art'):''}<b>${g.name}</b><small>${_hubLine(g)}</small></span><span class="v3-game-go">${g.cta}</span>${chev}</button>`;
}
function loadActivitiesHub(){
  const host=el('game-hub'); if(!host)return;
  const chev='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';
  const open=_V3_GAMES.filter(g=>_sysFlags[g.flag]===true);
  const mine=++_hubSeq;
  if(!open.length){
    host.innerHTML=`<div class="v3-eyebrow">Играть</div><section class="v3-lead" aria-label="Игры закрыты"><div class="v3-gname" style="font-size:34px">Игры временно недоступны${v3GlintMark('Игры временно недоступны')}</div>
      <p class="v3-gdesc">Прогресс не потеряется. Пока можно заняться питомцами и образами.</p>
      <button type="button" class="v3-pill" onclick="openPetsV1()">К питомцам</button></section>`;
    return;
  }
  const draw=()=>{
    host.innerHTML=`<div class="v3-eyebrow">Играть</div>
      <section class="v3-games v3-games--hub" aria-label="Игры">${open.map(g=>_hubRow(g,chev)).join('')}</section>`;
    if(typeof passHubRow==='function')passHubRow(host);   // строка «Пропуск сезона», пока включён флаг season_pass_v1 (app.43.js)
    leagueHubRow(host,chev);   // «Лига сезона» всем с сезона 2; до него — только с ранним доступом
    if(typeof v3EnterSync==='function')v3EnterSync(host);   // перерисовка не перезапускает каскад
  };
  draw();
  // Каждая игра грузится отдельно: сбой одной не трогает остальных, ответ устаревшей отрисовки отбрасывается.
  open.filter(g=>_V3_GAME_BOARDS[g.flag]).forEach(g=>{
    if(_hubScore[g.flag]&&Date.now()-(_hubAt[g.flag]||0)<60000)return;   // свежий ответ уже есть
    if(!_hubScore[g.flag])_hubScore[g.flag]=undefined;   // прошлый результат остаётся на экране, пока идёт новый запрос
    api(_V3_GAME_BOARDS[g.flag]).then(r=>({personal:r&&r.personal||null})).catch(()=>null).then(v=>{
      if(mine!==_hubSeq)return;
      if(v||_hubScore[g.flag]===undefined)_hubScore[g.flag]=v;
      if(v)_hubAt[g.flag]=Date.now();
      const small=host.querySelector(`.v3-game[data-game="${g.flag}"] small`);
      if(small)small.textContent=_hubLine(g);
    });
  });
}

// Лига (рейтинг уровнями + Пропуск сезона): до сезона 2 — только с правом «Ранний доступ к контенту», с сезона 2 — всем.
// Карточка-герой: мини-созвездие, текущие уровни обеих игр и сколько наград Пропуска ждёт (точка). Ответы сервера запоминаются на минуту.
let _league=null,_leagueAt=0;
const _LEAGUE_SKY='<svg class="v3-league-sky" viewBox="0 0 160 90" aria-hidden="true"><path d="M30 24L64 14L96 34L128 20M96 34L88 66L124 78M64 14L52 50L88 66" fill="none" stroke="currentColor" stroke-opacity=".28" stroke-width=".8"/><g fill="currentColor"><circle cx="30" cy="24" r="1.3"/><circle cx="64" cy="14" r="2"/><circle cx="96" cy="34" r="1.5"/><circle cx="128" cy="20" r="1.2"/><circle cx="88" cy="66" r="2.2"/><circle cx="124" cy="78" r="1.2"/><circle cx="52" cy="50" r="1.1"/><circle cx="150" cy="54" r=".9" opacity=".5"/><circle cx="12" cy="70" r=".8" opacity=".4"/></g></svg>';
function _leagueCard(chev){
  const r=_league, me=r.me, ps=r.pass, cur=ps&&ps.active&&ps.seasons.find(x=>x.current);
  const ready=ps&&ps.active&&ps.account&&ps.account.eligible?ps.seasons.reduce((n,x)=>n+x.track.filter(t=>t.free.state==='ready').length+x.track.filter(t=>t.vip.state==='ready').length,0):0;
  const days=cur?Math.max(0,Math.ceil((Date.parse(cur.ends_at)-Date.now())/864e5)):null;
  const top=r.public?`Сезон ${me?String(me.season).replace(/^s/,''):''}${days!==null?` · ${days} дн.`:''}`:'Ранний доступ · демо';
  const lv=me?`<span class="v3-league-lv"><span>Сапёр <i>ур. ${Number(me.games.minesweeper.unlocked)}</i></span><span>Ритм <i>ур. ${Number(me.games.rhythm.unlocked)}</i></span></span>`:'<small>Рейтинг уровнями и Пропуск сезона</small>';
  const go=ready?`<span class="v3-league-ready"><i class="v3-league-dot" aria-hidden="true"></i>К получению: ${ready}</span>`:'';
  return `<button type="button" class="v3-game v3-league" data-game="league" onclick="location.href=BASE+'/league'${ready?"+'#pass'":''}" aria-label="Лига сезона${ready?`, наград к получению: ${ready}`:''}">${_LEAGUE_SKY}<span class="v3-league-t"><small>${top}</small><b>Лига сезона</b>${lv}${go}</span>${ready?'':'<span class="v3-league-go">Открыть</span>'}${chev}</button>`;
}
function leagueHubRow(host,chev){
  const paint=()=>{
    const list=host.querySelector('.v3-games--hub');
    if(!_league||!_league.allowed||!list)return;
    const old=host.querySelector('.v3-game[data-game="league"]');
    if(old)old.outerHTML=_leagueCard(chev); else list.insertAdjacentHTML('afterbegin',_leagueCard(chev));
  };
  if(Date.now()-_leagueAt<60000){paint();return;}
  api('/league-demo/api/access').then(async r=>{
    if(!r||!r.allowed){_league=r||null;_leagueAt=Date.now();return;}
    const [me,pass]=await Promise.all([api('/league-demo/api/me').catch(()=>null),r.public?api('/league-demo/api/pass').catch(()=>null):null]);
    _league={...r,me,pass};_leagueAt=Date.now();paint();
  }).catch(()=>{});
}

function loadArena(){ swArena('game'); }
function swArena(tab){
  _arenaTab='game';
  _trackSubtab('arena/game');
  loadActivitiesHub();
}

// Only the authenticated finished-match projection is used here; no audit payload reaches the UI.
let _mafiaReviewSeq = 0;
function openMafiaReview(id, page = 0) {
  const seq = ++_mafiaReviewSeq;
  OM('Разбор Мафии', '<div id="mafia-review-host" class="v3-empty" role="status">Загружаем завершённую партию…</div>', [{l:'К истории',f:'openMafiaStats()'},{l:'Закрыть',f:'CM()'}]);
  const host = el('mafia-review-host');
  api(`/mafia-v1/matches/${Number(id)}/review?page=${Number(page)}`).then(d => {
    if (seq !== _mafiaReviewSeq || !host?.isConnected) return;
    const names = Object.fromEntries(d.players.map(p => [p.ref, p.name]));
    const name = ref => esc(names[ref] || 'Воздержались');
    const roles = {citizen:'Мирный',mafia:'Мафия',don:'Дон',doctor:'Доктор',detective:'Детектив'};
    const phase = {night:'Ночь',discussion:'Обсуждение',voting:'Голосование'};
    const timeline = d.timeline.map(r => `<li class="v3-line"><div><b>Раунд ${r.round} · ${phase[r.phase]}</b><p>${r.phase === 'discussion' ? 'Началось голосование.' : r.eliminated ? `Выбыл: ${name(r.eliminated)}.` : 'Никто не выбыл.'}</p>${r.phase === 'voting' ? `<p>Подано голосов: ${r.participated}</p><ul>${r.votes.map(v => `<li>${name(v.target)}: ${v.count}</li>`).join('') || '<li>Голосов нет.</li>'}</ul>${d.vote_mode === 'open' && r.ballots.length ? `<details><summary>Кто как голосовал</summary><ul>${r.ballots.map(v => `<li>${name(v.voter)} → ${name(v.target)}</li>`).join('')}</ul></details>` : ''}` : ''}</div></li>`).join('');
    host.className = '';
    host.innerHTML = `<p class="v3-stat-line">${mafiaArt(d.winner==='town'?'citizen':d.winner==='mafia'?'mafia':null,'mafia-result-art')}${d.winner === 'town' ? 'Победили мирные' : d.winner === 'mafia' ? 'Победила мафия' : 'Партия завершена'} · ${mafiaDate(d.finished_at)}</p><p class="tr-note">${esc(d.disclosure)}</p><details><summary>Участники и раскрытые роли · ${d.players.length}</summary><ul>${d.players.map(p => `<li class="mafia-review-player">${mafiaArt(p.role,'mafia-role-mini')}${esc(p.name)} · ${esc(roles[p.role] || 'Роль не сохранена')}${p.survived ? ' · в игре до финала' : ''}</li>`).join('')}</ul></details><ol class="mafia-review-timeline">${timeline || '<li>Подробные этапы этой партии не сохранились. Итог показан по архивным данным.</li>'}</ol><div class="tr-chips">${page ? `<button class="v3-pill v3-pill--ghost" onclick="openMafiaReview(${Number(id)},${page-1})">Предыдущие этапы</button>` : ''}${d.has_more ? `<button class="v3-pill" onclick="openMafiaReview(${Number(id)},${page+1})">Следующие этапы</button>` : ''}</div>`;
  }).catch(e => { if (seq === _mafiaReviewSeq && host?.isConnected) host.innerHTML = `<p class="v3-err" role="alert">${esc(String(e))}</p><button class="v3-link" onclick="openMafiaReview(${Number(id)},${page})">Повторить</button>`; });
}
