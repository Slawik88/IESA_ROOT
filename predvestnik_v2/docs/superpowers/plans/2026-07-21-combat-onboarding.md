# Онбординг боя — план реализации

> **Для исполнителя:** реализуется задача за задачей. Проверки — по конвенции проекта:
> assert-скрипты `python tools/test_*.py`, `node --check` для JS, `preview_server.mjs`+puppeteer
> для UI на 390px. НЕ pytest (в проекте его нет для боёвки). Шаги — чекбоксы `- [ ]`.

**Goal:** Сделать боёвку 4.0 понятной и «живой» для новичка: пошаговая анимация хода врага,
читаемая карта, скриптованный обучающий «Первый бой» и дофаминовый экран победы с кликабельными
наградами.

**Architecture:** Всё на существующем движке `combat2`/`services/battle3.py`/`app.11.js`. Сервер
дописывает транзиентную «ленту битов» хода врага в ответ действия; клиент проигрывает её пошагово.
Туториал — реальный серверный бой на `mode="tutorial"` с синтетическим отрядом, анти-фейлом и
data-driven коуч-слоем на клиенте. Экран победы и переиспользуемый лист-описание — новые UI-модули.

**Tech Stack:** Python 3.11 (прод!) / FastAPI / asyncpg+PGAdapter / aiogram; классический JS
(app.NN.js, склейка в main.py), app.css.

## Global Constraints (из спеки, копировать в каждую задачу)

- `services/` НЕ импортирует `bot.*` / `FastAPI.*`. Логика боя — только `services/battle3.py`.
- JS — классический script: `let/const` только вверху функций (TDZ), `${}` только в backtick,
  проверять `node --check`, дубли функций недопустимы.
- Прод **Python 3.11** — f-strings проверять визуально (локальный 3.12 пропускает PEP 701).
- Все анимации имеют мгновенную ветку для `body.no-fx` и `prefers-reduced-motion: reduce`.
- DESIGN: тёмная тема, золото — «валюта внимания», НЕ «дешёвый кликер» (без постоянного мигания),
  свечение blur ≤10px на жирном тексте. Тач-цель ≥ ~40px.
- `timeline` транзиентен (в БД не пишем); старые режимы abyss/war/gates не должны сломаться.
- Числа/лимиты — в `core/constants.py`, не в коде.

---

## Task 1 — Backend: лента битов хода врага (A1)

**Files:**
- Modify: `services/battle3.py` (`_enemy_phase`, `_execute_enemy_plan`, `_enemy_attack`,
  `_enemy_aoe`, ульта врага; helper `_beat()`; `apply_action`/`end_player_turn` — прокинуть)
- Modify: `core/constants.py` (тайминги битов)
- Modify: `FastAPI/routers/battle.py` (`_respond` — прокинуть `turn.timeline` как есть; уже
  прокидывается через `extra={"turn": res}`, проверить)
- Test: `tools/test_battle_timeline.py` (новый)

**Interfaces (Produces):**
- `res["timeline"]: list[dict]` в ответе `end_turn`. Бит:
  `{"actor": {"side": "enemy", "i": int}, "kind": "intent"|"move"|"attack"|"defend"|"aoe"|"ult"|"skip",
    "from": {"x","y"}|None, "to": {"x","y"}|None, "target": {"side": "ally", "i": int}|None,
    "dmg": int|None, "crit": bool, "elem": str|None, "text": str}`

**Constants (`core/constants.py`):**
```python
B4_BEAT_INTENT_MS = 350
B4_BEAT_MOVE_MS = 300
B4_BEAT_HIT_MS = 220
B4_BEAT_GAP_MS = 180
```

**Steps:**
- [ ] 1. В `battle3.py` добавить сборщик ленты: во время `_enemy_phase` копить биты в
  `state.setdefault("timeline_round", [])`. Helper `_beat(state, **kw)` аппендит нормализованный бит.
- [ ] 2. `_execute_enemy_plan`: перед движением — бит `intent`; при смене клетки — бит `move`
  (`from`=старый pos, `to`=новый); `attack`/`defend`/`aoe`/`ult` — соответствующие биты с `dmg/crit/elem`.
  `_enemy_attack` возвращает нанесённый урон/крит/стихию, чтобы бит был точным.
- [ ] 3. `_end_round`: `timeline = state.pop("timeline_round", [])`; вернуть в dict результата
  рядом с `hits`. `end_player_turn` пробрасывает.
- [ ] 4. Тест `tools/test_battle_timeline.py`: создать бой, сделать `end_turn` (через `apply_action`),
  проверить что `res["timeline"]` непустой,每 бит валиден (kind в допустимых, move имеет from/to,
  attack имеет target+dmg), и что финальное состояние согласовано с последним `to` каждого врага.
- [ ] 5. Прогнать: `python tools/test_battle_timeline.py` + `python tools/test_battle_state.py`
  (регресс). Ожидание: OK.
- [ ] 6. Commit: `feat(combat4): лента битов хода врага (сервер отдаёт таймлайн)`.

---

## Task 2 — Backend: режим туториала (C1/C2/C3)

**Files:**
- Modify: `services/battle3.py` (`tutorial_squad()`, `tutorial_enemy_squad()`, анти-фейл в
  `_apply_damage`, детерминизм ИИ при `state.get("tutorial")`, простое поле)
- Modify: `FastAPI/routers/battle.py` (эндпоинт `POST /combat2/tutorial/start`; `_finalize_if_over`
  — tutorial без награды; отдать `tutorial_done` в `/combat2/gates`)
- Modify: `infrastructure/repositories/users.py` (`ensure_account_columns` +
  `combat_tutorial_done`; хелперы `get_combat_tutorial_done`, `set_combat_tutorial_done`)
- Modify: `core/constants.py` (конфиг туториал-отряда/врагов/поля)
- Test: `tools/test_battle_tutorial.py` (новый)

**Interfaces (Produces):**
- `POST /combat2/tutorial/start` → `public_state` с `mode="tutorial"`, `tutorial=True`.
- `GET /combat2/gates` ответ содержит `tutorial_done: bool`.
- `battle3.tutorial_squad() -> list[ally_row]`, `battle3.tutorial_enemy_squad() -> list[enemy]`.
- `users.get_combat_tutorial_done(db, uid) -> bool`, `users.set_combat_tutorial_done(db, uid)`.

**Steps:**
- [ ] 1. `users.py`: в `ensure_account_columns` добавить
  `"ALTER TABLE users ADD COLUMN IF NOT EXISTS combat_tutorial_done BOOLEAN DEFAULT FALSE"`.
  Хелперы get/set (set — идемпотентный UPDATE ... = TRUE).
- [ ] 2. `battle3.py`: `tutorial_squad()` — 2 фиксированных ally_row (DD + танк из UNITS, level 1);
  `tutorial_enemy_squad()` — 2 слабых врага (низкие hp/atk) через `_mk_enemy`.
- [ ] 3. `battle3.py`: `public_state` — добавить `"tutorial": bool(state.get("tutorial"))`.
- [ ] 4. Анти-фейл: в `_apply_damage` если `state.get("tutorial")` и цель — ally, кламп итогового
  hp ≥ 1. Урон врага символический (через слабых врагов из шага 2 — доп. кламп не обязателен, но
  оставить hp≥1 как страховку).
- [ ] 5. Детерминизм: при `state.get("tutorial")` `_roll_telegraph`/`_best_enemy_plan` не используют
  RNG (фиксированные намерения) — чтобы коуч совпадал. Минимально: seed фиксирован + ветки без random.
- [ ] 6. Роутер: `POST /combat2/tutorial/start` — если есть активный бой → 400; создать бой
  `new_battle_state(tutorial_squad(), tutorial_enemy_squad(), "tutorial", {"tutorial": True, "seed": 777})`;
  `bt_repo.create(..., mode="tutorial", ...)`; вернуть `public_state`. НЕ проверять вход дня.
- [ ] 7. Роутер: `_finalize_if_over` — для `mode=="tutorial"` при победе `reward=None` +
  `await users.set_combat_tutorial_done(db, uid)`. `/combat2/gates` отдаёт `tutorial_done`.
- [ ] 8. Тест `tools/test_battle_tutorial.py`: собрать tutorial-бой, прогнать несколько ходов до
  победы, проверить: ally hp никогда < 1; при победе цикл завершается; враги слабые.
- [ ] 9. Прогнать тест + import-тест роутера (`python -c "import FastAPI.routers.battle"`). OK.
- [ ] 10. Commit: `feat(combat4): режим туториала — синтетический отряд, анти-фейл, флаг завершения`.

---

## Task 3 — Frontend: проигрыватель ленты + слайд токенов (A1/A2/A4)

**Files:**
- Modify: `FastAPI/static/app.11.js` (`_b3PlayTimeline`, интеграция в `_b3Api`/`_btRender`;
  залок `_b3Playing`; скип по тапу; слайд-позиционирование токенов)
- Modify: `FastAPI/static/app.css` (transition позиции токена, пульс активного врага)
- Modify: `core/constants.py` — уже сделано в Task 1 (тайминги отдаются? нет — тайминги в JS
  константах `B4_BEAT_*`, зеркалят backend; или отдать в `public_state`). Решение: JS-константы.

**Interfaces (Consumes):** `res.turn.timeline` (Task 1).

**Steps:**
- [ ] 1. JS-константы `B4_BEAT_INTENT_MS/MOVE_MS/HIT_MS/GAP_MS` (зеркало backend) вверху app.11.js.
- [ ] 2. `_b3PlayTimeline(timeline, finalState, turn)`: async-очередь битов. `_b3Playing=true` на
  время; по каждому биту — подсветить актора (класс пульса), для `move` — проставить токену целевую
  клетку (CSS transition сам анимирует), для `attack/aoe/ult` — `_b3OneHitFx`. Между битами — `gap`.
  По завершении — `_b3Playing=false; _btRender(finalState, turn)`.
- [ ] 3. `_b3Api`: если `r.turn && r.turn.timeline && r.turn.timeline.length` и не no-fx →
  `_b3PlayTimeline(r.turn.timeline, r, r.turn)` вместо прямого `_btRender`. Иначе — как сейчас.
- [ ] 4. Токены рендерить по позиции клетки с `transition: transform .3s` (no-fx → none). Слайд
  своего хода (`_b3Move`) — тот же механизм.
- [ ] 5. Залок ввода: `_b3TapCell`/кнопки проверяют `_b3Playing`; тап по доске во время
  проигрывания → доиграть мгновенно (`_b3SkipTimeline()`).
- [ ] 6. **Фикс «конец хода со 2-го тапа»** (systematic-debugging): воспроизвести в preview,
  найти причину (гипотеза: `_b3Lock`/ре-рендер), починить. Критерий: одиночный тап всегда срабатывает.
- [ ] 7. `node --check FastAPI/static/app.11.js`. Прогон preview_server: враг двигается пошагово,
  конец хода с 1 тапа. Скриншоты 390px.
- [ ] 8. Commit: `feat(combat4): пошаговая анимация хода врага + слайд токенов + фикс конца хода`.

---

## Task 4 — Frontend: читаемые клетки + мини-легенда (B)

**Files:**
- Modify: `FastAPI/static/app.css` (клетки-состояния: точки-следы хода, кольцо-прицел, опасная,
  укрытие-щит, препятствие; линия намерения врага)
- Modify: `FastAPI/static/app.11.js` (легенда: расширить кнопку «?» → сворачиваемая панель значков;
  усилить рендер намерения врага)

**Steps:**
- [ ] 1. CSS: `.b4-reach` → точки-следы (radial-gradient точка по центру, не заливка);
  `.b4-atk` → кольцо-прицел вокруг врага; `.b4-danger` → красная штриховка/пульс;
  `.b4-cover` → бейдж-щит; `.b4-obstacle` → глухая. Reduced-motion — без пульса.
- [ ] 2. JS: функция `_b3Legend()` — HTML-панель «что значит значок» (клетки, `B4_THREAT_ICO`,
  `B3_FX_ICO`, ярость). Кнопка «?» в арене открывает её (боттом-шит `OM`).
- [ ] 3. Намерение врага: увеличить `.b4-threat-l`, добавить связь с целью (подсветка `.b4-threat`
  уже есть — усилить визуально).
- [ ] 4. `node --check`. Preview 390px: клетки читаются, легенда открывается, тач-цели ≥40px.
- [ ] 5. Commit: `feat(combat4): читаемые клетки поля + постоянная мини-легенда`.

---

## Task 5 — Frontend: коуч-слой туториала (C4)

**Files:**
- Modify: `FastAPI/static/app.11.js` (`TUTORIAL_STEPS`, драйвер `_b3Coach(state)`, пузырь-подсказка,
  автозапуск, повтор через «?»)
- Modify: `FastAPI/static/app.css` (пузырь коуч-марки, затемнение-подсветка)
- Modify: `FastAPI/static/app.01.js` или Врата-рендер — автозапуск при `tutorial_done=false`

**Interfaces (Consumes):** `st.mode==='tutorial'`, `st.tutorial`; `POST /combat2/tutorial/start`;
`gates.tutorial_done`.

**Steps:**
- [ ] 1. `TUTORIAL_STEPS` — массив из 8 шагов (см. спека §4.C4). Каждый:
  `{id, when(st), text, highlight(st), advanceOn(st)}`. `when/advanceOn` — чистые предикаты по state.
- [ ] 2. `_b3Coach(st)`: если `st.mode!=='tutorial'` → скрыть пузырь, выход. Иначе найти первый
  незавершённый шаг с истинным `when`, показать пузырь снизу + подсветку `highlight`, затемнить фон.
  Хранить пройденные шаги в `_b3CoachDone` (Set). Вызвать в конце `_btRender`.
- [ ] 3. Пузырь: снизу над панелью действий, стрелка к цели, кнопка «Пропустить обучение»
  (→ подтверждение → долистать / выйти). Reduced-motion — без анимации появления.
- [ ] 4. Автозапуск: в `loadGates`, если `d.tutorial_done===false` и нет активного боя — предложить
  «▶ Первый бой» заметной кнопкой (не форс-модалка); отдельно кнопка «?» → «Пройти обучение заново»
  → `POST /combat2/tutorial/start` → `_btRender`.
- [ ] 5. `node --check`. Preview: прогнать туториал от старта до победы, проверить что подсказки
  идут по порядку и не ломаются при «неправильном» действии.
- [ ] 6. Commit: `feat(combat4): скриптованный «Первый бой» — коуч-слой из 8 шагов + автозапуск`.

---

## Task 6 — Frontend: экран победы + лист-описание (D)

**Files:**
- Modify: `FastAPI/static/app.11.js` (`_b3Victory(st, reward)`, `_b3Defeat(st)`, замена `headHtml`;
  `showItemDetail(key)`, реестр `ITEM_INFO`; счётчик-роллап `_b3CountUp`)
- Modify: `FastAPI/static/app.css` (штамп победы, карточки наград, confetti-lite, боттом-шит описания)

**Interfaces (Consumes):** `st.status`, `_b3LastReward` (dark_mora/shards/unit_shards/reward_mult/
split/boss_key/damage/breached). **Produces:** `showItemDetail(key)` — переиспользуемый (для #4).

**Steps:**
- [ ] 1. `ITEM_INFO` — реестр `{key: {emoji, name, type, rarity, what, why, where_get, where_use}}`
  для `dark_mora`, `abyss_shard`, `unit_shard` (+ generic fallback). Тексты по DESIGN, без вопросов
  после прочтения.
- [ ] 2. `showItemDetail(key)`: боттом-шит `OM` с секциями Что это / Зачем / Где взять / Где применить.
- [ ] 3. `_b3Victory`: полноэкранный оверлей — штамп «🏆 ПОБЕДА» (scale+glow, haptic) → карточки
  наград по одной с `_b3CountUp` → бейдж мастерства при `reward_mult>1` → confetti-lite (сдержанно) →
  кнопки «⚔️ Ещё бой»/«↩ Назад». Карточки кликабельны → `showItemDetail`. Пустая награда (туториал) →
  поздравление без карточек.
- [ ] 4. `_b3Defeat`: экран «☠️ Отряд пал» + «восстановятся» + «⚔️ Ещё раз»/«↩ Назад».
- [ ] 5. Встроить в `_btRender`: при `finished` вызывать `_b3Victory`/`_b3Defeat` вместо строки.
  Учесть проигрывание ленты перед экраном (victory после settle).
- [ ] 6. `node --check`. Preview 390px: победа/поражение/клик по награде → описание. Reduced-motion.
- [ ] 7. Commit: `feat(combat4): дофаминовый экран победы + кликабельные награды с описанием`.

---

## Task 7 — Полировка, проверка, чейнджлог

**Files:**
- Modify: `PLAYER_CHANGELOG.md` (новая запись в начало)
- Проверка целостности

**Steps:**
- [ ] 1. `node --check` на всех тронутых app.NN.js. `python tools/test_battle_*.py` — все зелёные.
- [ ] 2. `python -c "import services.battle3; import FastAPI.routers.battle"` — импорт ок.
- [ ] 3. Полный прогон preview_server 390px: туториал целиком, реальный бой (лента врага), легенда,
  победа, описание награды. Скриншоты, сверка с DESIGN.
- [ ] 4. Проверить регресс abyss/war (timeline не ломает; экран победы рендерит их ветки reward).
- [ ] 5. `PLAYER_CHANGELOG.md` — запись простым языком (обучение, живой ход врага, экран победы).
- [ ] 6. Commit + push всего.

## Self-review (покрытие спеки)

- A1 лента врага → Task 1 + Task 3 ✓ · A2 слайд → Task 3 ✓ · A4 фикс ввода → Task 3.6 ✓
- B карта+легенда → Task 4 ✓
- C туториал (режим/анти-фейл/детерминизм/поле/коуч/флаг/автозапуск) → Task 2 + Task 5 ✓
- D экран победы+поражения+лист-описание → Task 6 ✓
- Тест-план/выкладка → Task 7 ✓
- Границы (#4 site-wide, #5 changelog-страница) — не входят, компонент `showItemDetail` — задел ✓
