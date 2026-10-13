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
function mafiaHowTo(){
  const steps=MAFIA_HOWTO_STEPS.map(x=>`<li class="mafia-howto-step"><b>${esc(x[0])}</b><span>${esc(x[1])}</span></li>`).join('');
  const roles=MAFIA_HOWTO_ROLES.map(x=>`<div class="mafia-howto-role"><dt>${x[0]} ${esc(x[1])}</dt><dd>${esc(x[2])}</dd></div>`).join('');
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
    const live=(d.live||[]).map(m=>`<div class="v3-line mafia-live"><span><b>${r(m)[0]} ${esc(r(m)[1])}</b><br><small>Идёт сейчас · ${esc(phase[m.phase]||m.phase)}</small></span></div>`).join('');
    const rows=(d.matches||[]).map(m=>{ const when=mafiaDate(m.finished_at||m.started_at), side=m.winner==='town'?'победили мирные':m.winner==='mafia'?'победила мафия':'';
      return `<div class="v3-line mafia-row"><span><b>${r(m)[0]} ${esc(r(m)[1])}</b><br><small>${esc([when,side].filter(Boolean).join(' · '))}</small></span><em class="mafia-res ${m.won===true?'win':''}">${m.won===true?'Победа':m.won===false?'Поражение':''}</em></div>`; }).join('');
    const summary=played?`<div class="mafia-sum"><div><b>${played}</b><span>сыграно</span></div><div><b>${wins}</b><span>побед</span></div><div><b>${Math.round(wins*100/played)}%</b><span>успех</span></div></div>${s.favorite_role&&role[s.favorite_role]&&played>=3?`<p class="v3-stat-line">Чаще всего: ${esc(role[s.favorite_role][1])}</p>`:''}${Number(s.win_streak||0)>=2?`<p class="v3-stat-line">Серия побед: ${Number(s.win_streak)}${Number(s.win_streak)>=50?'+':''}</p>`:''}`:'';
    const hidden='';
    const empty='<div class="v3-empty">🕵️<b>Партий пока нет</b>В нужной Telegram-группе напиши: «бот мафия». Игра начнётся прямо там.</div>';
    el('mb').innerHTML=`${mafiaHowTo()}<div class="v3-eyebrow">Моя статистика</div>${summary}${live}${rows||(live?'':empty)}${hidden}`;
  }).catch(e=>{ el('mb').innerHTML=`<div class="v3-err">${esc(String(e))}</div>`; });
}

// Каждый режим показывается только при включённом серверном флаге (по умолчанию все выключены).
const _V3_GAMES = [
  {flag:'game_rhythm_v2', name:'Ритм', desc:'Бесконечный забег. Жми руны точно, скорость растёт.', hint:'Бесконечный забег, рейтинг подтверждённых результатов', cta:'Играть', open:'openRhythmV2Game()'},
  {flag:'game_minesweeper_v2', name:'Сапёр', desc:'Открывай клетки и ставь флаги. В рейтинг попадают только победы.', hint:'Логика, победы попадают в топ', cta:'Играть', open:'openMinesweeperGame()'},
  {flag:'game_mafia_v1', name:'Мафия', desc:'Играется в групповом чате: напиши «бот мафия». Здесь история ваших партий.', hint:'Играется в чате, здесь ваши партии', cta:'Мои партии', open:'openMafiaStats()'}
];
// Личный результат в строке игры: из таблицы сезона (`personal`). Только Ритм и Сапёр; у Мафии таблицы нет.
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
  return `<button type="button" class="v3-game" data-game="${g.flag}" onclick="${g.open}"><span><b>${g.name}</b><small>${_hubLine(g)}</small></span><span class="v3-game-go">${g.cta}</span>${chev}</button>`;
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

function loadArena(){ swArena('game'); }
function swArena(tab){
  _arenaTab='game';
  _trackSubtab('arena/game');
  loadActivitiesHub();
}
