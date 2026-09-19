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

function loadActivitiesHub(){
  const host=el('game-hub'); if(!host)return;
  host.innerHTML=`<section class="recon-entry-card">
    <div class="recon-entry-mark">ᚱ</div><div class="recon-entry-copy"><span class="recon-entry-kicker">БЕСКОНЕЧНЫЙ ЗАБЕГ</span><h2>Ритм</h2><p>Нажимай руны точно. Скорость растёт плавно, а каждый режим имеет собственную таблицу лидеров.</p><div class="recon-entry-facts"><span>реакция</span><span>2 режима</span><span>топ игроков</span></div></div>
    <button class="btn btn-gold recon-entry-action" onclick="openRhythmV2Game()">Играть <b>›</b></button></section>
  <section class="recon-entry-card" style="margin-top:10px">
    <div class="recon-entry-mark">⚑</div><div class="recon-entry-copy"><span class="recon-entry-kicker">ЛОГИЧЕСКАЯ ИГРА</span><h2>Сапёр</h2><p>Открывай безопасные клетки, ставь флаги и проходи три уровня сложности. Победы попадают в таблицу лидеров.</p><div class="recon-entry-facts"><span>6×6 · 9×9</span><span>3 сложности</span><span>топ игроков</span></div></div>
    <button class="btn btn-gold recon-entry-action" onclick="openMinesweeperGame()">Играть <b>›</b></button></section>
  <section class="recon-entry-card" style="margin-top:10px">
    <div class="recon-entry-mark">🕵️</div><div class="recon-entry-copy"><span class="recon-entry-kicker">ГРУППОВАЯ ИГРА В ЧАТЕ</span><h2>Мафия</h2><p>Партия идёт в Telegram-группе: напиши там «бот мафия». Здесь — только твоя история и статистика.</p><div class="recon-entry-facts"><span>группа</span><span>роли в личке</span><span>история</span></div></div>
    <button class="btn btn-gold recon-entry-action" onclick="openMafiaStats()">История <b>›</b></button></section>`;
}

function loadArena(){ swArena('game'); }
function swArena(tab){
  _arenaTab='game';
  _trackSubtab('arena/game');
  loadActivitiesHub();
}
