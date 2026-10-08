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

function openMafiaStats(){
  OM('🕵️ Мафия — моя история','<div class="loader">Загружаем историю…</div>',[{l:'Закрыть',f:'CM()'}]);
  api('/mafia-v1/me').then(d=>{
    const s=d.stats||{};
    const role={citizen:'Мирный житель',mafia:'Мафия',don:'Дон',doctor:'Доктор',detective:'Детектив'};
    const state={finished:'Завершена',cancelled:'Отменена',lobby:'Лобби',night:'Ночь',discussion:'Обсуждение',voting:'Голосование',paused:'На паузе'};
    const rows=(d.matches||[]).map(m=>`<div class="pcard"><b>${esc(role[m.role]||'Роль ещё не выдана')}</b><br><small>Партия #${Number(m.match_id)} · ${esc(state[m.phase]||m.phase)}${m.winner?` · победили ${m.winner==='town'?'мирные':'мафия'}`:''}</small></div>`).join('')||'<div class="empty-state"><div class="es-icon">🕵️</div><div class="es-title">Партий пока нет</div><div class="es-sub">В нужной Telegram-группе напиши: «бот мафия». Игра начнётся прямо там.</div></div>';
    el('mb').innerHTML=`<div class="card"><div class="card-title">Моя статистика</div><b>${Number(s.wins||0)}</b> побед · <b>${Number(s.played||0)}</b> завершённых партий</div>${rows}`;
  }).catch(e=>{ el('mb').innerHTML=`<div class="err">${esc(String(e))}</div>`; });
}

// Каждый режим показывается только при включённом серверном флаге (по умолчанию все выключены).
const _V3_GAMES = [
  {flag:'game_rhythm_v2', name:'Ритм', desc:'Бесконечный забег. Жми руны точно, скорость растёт.', hint:'Бесконечный забег, рейтинг подтверждённых результатов', cta:'Играть', open:'openRhythmV2Game()'},
  {flag:'game_minesweeper_v2', name:'Сапёр', desc:'Открывай клетки и ставь флаги. В рейтинг попадают только победы.', hint:'Логика, победы попадают в топ', cta:'Играть', open:'openMinesweeperGame()'},
  {flag:'game_mafia_v1', name:'Мафия', desc:'Играется в групповом чате: напиши «бот мафия». Здесь история ваших партий.', hint:'Играется в чате, здесь ваши партии', cta:'Мои партии', open:'openMafiaStats()'}
];
function loadActivitiesHub(){
  const host=el('game-hub'); if(!host)return;
  const chev='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';
  const open=_V3_GAMES.filter(g=>_sysFlags[g.flag]===true);
  if(!open.length){
    host.innerHTML=`<div class="v3-eyebrow">Играть</div><section class="v3-lead" aria-label="Игры закрыты"><div class="v3-gname" style="font-size:34px">Игры временно недоступны</div>
      <p class="v3-gdesc">Прогресс не потеряется. Пока можно заняться питомцами и образами.</p>
      <button type="button" class="v3-pill" onclick="openPetsV1()">К питомцам</button></section>`;
    return;
  }
  const [lead,...rest]=open;
  host.innerHTML=`<div class="v3-eyebrow">Играть</div>
    <section class="v3-lead" aria-label="${lead.name}"><div class="v3-gname">${lead.name}</div>
      <p class="v3-gdesc">${lead.desc}</p>
      <button type="button" class="v3-pill" onclick="${lead.open}">${_v3Icon('play')}${lead.cta}</button></section>
    ${rest.length?`<section class="v3-games" aria-label="Другие игры">${rest.map(g=>`<button type="button" class="v3-game" onclick="${g.open}"><span><b>${g.name}</b><small>${g.hint}</small></span>${chev}</button>`).join('')}</section>`:''}`;
  if(typeof v3EnterSync==='function')v3EnterSync(host);   // перерисовка не перезапускает каскад
}

function loadArena(){ swArena('game'); }
function swArena(tab){
  _arenaTab='game';
  _trackSubtab('arena/game');
  loadActivitiesHub();
}
