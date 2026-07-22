# Остаток работы + косметика + редизайн «Внешний вид» — план на утверждение

**Статус:** пункты 1 (баг), 3 (косметика), 7 (редизайн «Внешний вид») сделаны — по
прямому указанию владельца, ждут деплоя. Пункт 5 (цены) явно пропущен по команде
владельца — НЕ трогать. Всё остальное ЖДЁТ ОТДЕЛЬНОГО «ДЕЛАЕМ» — кода по этим пунктам
нет и не будет.

**Вне плана, сделано по прямому указанию (2026-07-23):** поле боя увеличено с 7×5 до
9×7. Правки: `core/constants.py` (GRID_W/GRID_H), `services/battle3.py::spawn_positions()`
(была захардкожена на старую ширину/высоту — колонки врагов 6/5 и список рядов из 5
значений; теперь считается от GRID_W/GRID_H, иначе враги оказались бы в центре поля,
а не у правого края), `app.css::.b4-grid` (repeat(7→9)). Проверено: все существующие
тесты боя проходят на новом размере, расстановка юнитов реально на новых границах (не
центре), визуально на 390px клетки уменьшились (~52px→39px), но остаются читаемыми —
проверено скриншотом. **Баланс не трогал**: дальность атак/AP/скорость ИИ остались
прежними — это значит юнитам относительно дольше сближаться на большем поле (не
рефакторил без отдельного запроса, но держи в уме при первых боях после деплоя).

**Порядок ниже — рекомендованный порядок реализации** (когда будет дана команда по
конкретному пункту), не хронология обсуждения.

---

## 1. 🔴 БАГ: бой теряет состояние посреди партии — ✅ **ПОФИКШЕН, ждёт деплоя**

**Root cause (подтверждён кодом):** `_finalize_if_over()` в `FastAPI/routers/battle.py`
вызывает `bt_repo.finish(id, 'won')` — эта запись автокоммитится МГНОВЕННО (в проекте
`db.commit()` — no-op без явного `BEGIN`, см. `infrastructure/pg_adapter.py`), статус боя
необратимо становится `won` ДО того, как посчитаны награды режима. В инциденте владельца
награда для `mode='tutorial'` (`set_combat_tutorial_done`) падала на колонке
`combat_tutorial_done`, которой ещё нет на проде (уже пофикшено в 9c0329d3, но не
задеплоено) → исключение улетало наружу необработанным → клиент получал голый 500, а бой
на сервере уже навсегда завершён → любое следующее действие (атака/«Сдаться»/«Выйти») →
404 «бой не найден», хотя клиент ещё рисовал живого врага. Это структурная уязвимость
(любой будущий сбой в начислении награды воспроизвёл бы тот же класс бага), не только
про эту одну колонку — поэтому фикс защитный, а не просто «подождать деплоя».

**Фикс:** начисление наград обёрнуто в `try/except` — `finish()` остаётся вне try (бой
завершается всегда корректно), сбой награды логируется и не роняет весь запрос.
Клиент теперь всегда получает валидный `won`/`lost`, даже если конкретная награда сама
сломалась. Failing-тест до фикса → проходящий после: `tools/test_battle_finalize_resilience.py`.
Регрессия проверена (`tools/test_battle_tutorial.py`). Детали:
`C:\Users\makss\.claude\projects\g--IESA-ROOT\memory\project_bug_combat_state_lost_mid_battle_2026-07-23.md`

**Осталось:** деплой (см. пункт 2) + смоук «Первого боя» до победы на телефоне.

---

## 2. ⛔ Деплой + смоук (сразу после того как баг №1 пофикшен)
Всё, что накопилось за 2 сессии (шапка, «Что нового», «Внешний вид» v1, авто-refresh,
фиксы боя, миграция БД, + фикс бага №1) едет в прод одним рестартом DO. Смоук на
телефоне обязателен для боевых модалок (баг был именно в Telegram-webview).

---

## 3. 🎨 Косметика: проработка эффектов по редкости — ✅ **СДЕЛАНО**

**Аудит показал:** 5 из 6 слотов (ореол/рамка/гало/фон/частицы) уже были тщательно
проработаны в прошлых сессиях — реальная эскалация по редкости (common статичный
акцент → rare лёгкая анимация → epic характерный паттерн → legendary многослойный
эффект → mythic самый сильный/живой), с соблюдением правил DESIGN.md (блюр свечения
≤10px, градиент-текст только как доп. слой через `@supports`, не основной эффект).
Переделывать не стал — было бы порчей уже хорошей работы.

**Реальный пробел нашёл в 6-м слоте (титулы):** 6 из 12 титулов — **на всех
редкостях, от common до mythic** — не имели поля `css` в реестре вообще и
рендерились голым текстом без единого визуального отличия от бесплатного стартового
титула: `wanderer`(common), `novice`(common), `patron`(rare, «Меценат»),
`abysswalker`(epic), `legend`(legendary), `omen`(mythic, «Предвестник» — совпадает
с именем самой игры). Самый дорогой титул (1000 ✨) визуально ничем не отличался от
бесплатного.

**Фикс:** добавил 6 CSS-классов в `app.css` (тот же контракт: common/rare статичны,
epic — анимация, legendary — платиновый gradient-блик, mythic — золото-белый
пульс-glow для «Предвестника» — самый сильный эффект, раз титул назван как игра) +
прописал `"css"` в `core/cosmetics.py` для всех 6 записей. Проверено: все 77
css-ссылок в реестре теперь резолвятся в реальные классы (0 пропущенных), визуально
проверено скриншотом — все 6 различимы и анимации реально идут (не заморожены).

**Зачем в этом месте порядка:** это готовит почву для пункта 5 (повышение цены) —
поднимать цену на визуально не изменившийся товар нечестно по отношению к игроку,
сначала товар должен реально стать лучше.

---

## 4. 🖼 Публичная карточка профиля — полностью в косметике
Сейчас публичная карточка (открывается тапом по нику игрока где-то на сайте) показывает
косметику маленькой полоской. Переделать так, чтобы вся карточка была полностью одета в
косметику игрока (фон, рамка, гало, ореол ника, титул, частицы) — адаптировать разметку
карточки под это, чтобы смотрелось цельно и красиво, а не как перегруженная деталями
визитка. Идёт сразу после пункта 3, чтобы показывать уже проработанные эффекты.

---

## 5. 💰 Повышение базовой цены косметики на +100 ✨ (для ВСЕХ предметов)
Новая базовая цена каждого товара = текущая цена + 100 зарников. Применяется ко всем
предметам всех слотов и редкостей без исключения. Идёт после пункта 3 (эффекты уже
улучшены — цена оправдана).

---

## 6. 🎁 Готовые пресеты косметики (наборы «под ключ»)
Игра сама предлагает готовые сеты косметики, подобранные так, чтобы предметы сочетались
между собой визуально (единая тема/стиль на ореол+рамку+гало+фон+титул). Игрок, который
не хочет перебирать всё вручную, покупает пресет одним действием.

**Цена пресета** = сумма цен всех предметов, входящих в набор (уже по НОВЫМ ценам из
пункта 5, отсюда и порядок — считать сумму нужно от актуальных цифр) **+ 100 ✨ сверху**
за готовое решение.

Идёт после пункта 5, чтобы формула считалась от финальных цен, а не от старых (иначе
пришлось бы пересчитывать пресеты второй раз).

Смотри: Пока что этот блок пропускаем и оставляем на складе хранится, МЕНЯТЬ ЦЕНЫ НЕ НАДО

---

## 7. 🖥 Полный редизайн вкладки «Внешний вид» — ✅ **СДЕЛАНО**

**Реализовано:** вкладки убраны — один непрерывный скролл по всем секциям
(ореол/рамка/гало/титул/фон/частицы/приветствие/темы), прилипающее превью
«Сейчас→Станет» под шапкой (`.looks-sticky`, `position:sticky; top:88px`) —
видно всегда, на любом скролле. Тонкий ряд чипов-якорей сверху скроллит к
секции (`scrollIntoView` + `scroll-margin-top`), не переключая панель.

**Темы профиля мигрированы** в ту же страницу отдельной секцией: тап по теме
показывает raw-строку превью (`/themes/preview/{id}`, тот же формат, что видит
бот) прямо в секции, без ухода в модалку — фильтры Все/Мои/Премиум, покупка/
экипировка инлайн. Старая вкладка Профиль→Темы (`#col-themes`) не удалена
(отдельная не блокирующая задача на потом, если захочешь убрать дубль).

**Проверено puppeteer на 390px:** после скролла на 900px превью остаётся
ровно под шапкой (`top:88px`, не уезжает); прыжок к последней секции (Темы)
сначала упирался в конец документа (нечего скроллить дальше) — добавлен
запас `padding-bottom:55vh` под секциями, теперь долетает точно
(`scroll-margin-top:96px`, финальный `top:95px`); тап по теме не открывает
модалку; полный цикл экипировка→«Применить»→«‹ Назад» работает.

**Дружелюбность:** убрал дублирующую интро-строку (почти дословно повторяла
уже существующую подсказку «Жми предмет — примерка сразу здесь»), не стал
плодить лишний текст. Остальное (усиленный «Топ слота», приятный момент
покупки, мини-превью пресетов) — не трогал в этот проход, было бы избыточным
дополнением поверх уже решённой структурной проблемы; можно вернуться отдельно,
если после смоука на телефоне почувствуется нехватка.

Цены/экономика не менялись (пункт 5 явно пропущен по твоей команде).

---

## 8. 🟡 Mythic-темы (`source="event"`) без механики выдачи
`theme_eclipsed`/`theme_void`/`theme_bloodmoon` (+5 seasonal + `theme_royal`) — получить
нельзя нигде, кроме ручной выдачи в dev-консоли. Нужно решение по дизайну (супер-редкий
приз ивента? награда сезона?). Не блокирует остальное, независимая задача.

---

## 9. 🟡 Балансовый прогон Боёвки 3.0
После недели живых данных — проверить кривую врагов Врат/Бездны (этажи 4–6), экономику
осколков призыва, дроп таргет-осколков, судьбу легаси-кода мирной боёвки
(`services/battle.py`, `pet_combat`, `COMBAT_*`). Фоновая задача, не срочная.

**Про доступ к БД:** если понадобится читать прод для этого прогона — нужен твой IP в
Trusted Sources БД (см. `project_db_trusted_sources.md`). Ты предложил пример
`178.197.199.243/32` — уточним актуальный твой IP, когда реально дойдём до этого пункта
(сейчас не требуется, этот прогон не в работе).

---

## 10. 🟡 `BOT_AUDIT.md`: П1–П6 (отдельный старый список, не связан с косметикой)
Стрик, скидка/слот Черепахи, гача-скидка, карточка Волка/Дракона, миграция
scheduler→FastAPI. Без изменений в приоритете, для полноты картины. - да, делаем

---

## 11. 🟡 Аудит ачивок: реально ли засчитываются игровые действия
Пройтись по ВСЕМ ачивкам из `core/registry.py` и проверить на деле (не по коду «на глаз»,
а по факту в игре), что метрика действительно растёт, когда игрок делает нужное действие —
и на боте, и на сайте (единый источник правды: если работает в одном месте и не работает
в другом — это баг паритета). Особое внимание — этим пяти (уже нашёл, где они должны
начисляться, но не проверял вживую):

- **🛒 Меценат** (`patron`, метрика `total_mora_spent_shop`) — начисляется в
  `FastAPI/routers/shop.py:99` (сайт) и `bot/handlers/shop.py:273` (бот). Два независимых
  места — проверить, что оба реально считают потраченное, и что суммы не расходятся.
- **🎲 Везунчик** (`lucky_one`, метрика `gamble_wins`) — 3 места в `services/skill_games.py`
  (по одному на каждую мини-игру). Проверить, что ВСЕ мини-игры реально шлют +1 при победе,
  не только какая-то одна.
- **⚔️ Дуэлянт** (`duelist`, метрика `duel_wins`) — есть явный след прошлого бага в коде:
  `FastAPI/routers/duels.py:156-163` — комментарий «duels accepted via the site never
  advance the winner's duel_wins achievement», рядом `bot/handlers/duel.py:205` — второй,
  независимый путь начисления для дуэлей из бота. Проверить оба пути вживую (принять дуэль
  с сайта И из чата), обёрнуто в `try/except: pass` в роутере сайта — если начисление тихо
  упадёт, игрок не узнает и метрика не вырастет молча.
- **🌟 Звезда чата** (`star`, метрика `weekly_top1_count`) — начисляется только раз в неделю
  фоновой задачей `services/scheduler.py:505-523` (не по факту действия игрока, а по крону).
  В `GAME_BIBLE.md` уже отмечен один прошлый фикс «больше не достаётся призракам» — значит
  тема с историей багов, стоит перепроверить на свежих реальных данных.
- **🌠 Звёздная Гача** (`star_gacha`, метрика `legendary_gacha_drops`) — 2 места в
  `services/gacha.py:270,413`, по одному на обычную и мульти-крутку. Проверить, что легендарные
  дропы считаются одинаково в обоих типах круток (не только в одиночной).

Не блокирует остальное, независимая проверка (можно делать в любой момент, не завязана на
косметику/деплой).

---

## 12. 🔴 Боёвка: ролям/тактике не хватает смысла — «просто спамь атаку»
Владелец: «стратегией и тактикой вообще не пахнет, танки/дальники/саппорты/дамагеры —
какой в них смысл, если можно просто всех юнитов вперёд послать и спамить атаку».
Отдельная большая задача, прорабатывать до мелочей — **не просто «добавить цифр»,
а разобраться, почему роли не работают механически.**

**Уже нашёл конкретную причину кодом (не на глаз), пока искал материал для блока —
это не гипотеза, а подтверждённый факт:**

- **Танк-«таунт» не делает вообще ничего.** Оба танковых навыка (`u_ice_golem`
  «Мёрзлый таунт», `u_strazh` «Бастионный таунт») ставят статус
  `intercept_all` (`services/battle3.py:1157-1187`). Но этот статус **читается
  только в `_pick_target()` (`battle3.py:283-307`) — а эта функция вызывается
  ИСКЛЮЧИТЕЛЬНО из `_exec_ult` (4 места, строки 348/365/382/398), то есть только
  когда СОЮЗНИК бьёт УЛЬТОЙ по врагу.** Реальный вражеский ИИ, который решает, кого
  атаковать (`_best_enemy_plan`, `battle3.py:521-567`), **вообще не смотрит на
  `intercept_all`**. Итог: поставил тауnt на танка — враг как бил дамагера/саппорта,
  так и продолжает бить, танк не защищает никого. Это мёртвый код, оставшийся от
  старой формационной (slot 0/1/2) системы «Боёвки 3.0», которую не перенесли в
  клеточную «Боёвку 4.0».
- **`role_pref` в ИИ (`dd:3, support:2, tank:1`) — это только tie-break**, а не
  реальный вес решения: `key = (round(ev,3), role_pref, -ti, -movecost)` — роль
  играет роль ТОЛЬКО когда чистый EV (ожидаемый урон) у двух целей математически
  ИДЕНТИЧЕН, что почти никогда не бывает. Фактически ИИ бьёт по чистой
  максимизации урона + небольшой плоский бонус против саппорта (`+atk*0.3`),
  позиция/роль цели почти не влияют.
- **Нет геометрической причины прятаться за танком.** `B4_ENEMY_MOVE=3` (враг
  двигается на 3 клетки/ход), `reachable()` блокирует только клетку, которую
  юнит физически занимает — нет «зоны контроля» вокруг танка. На поле 7×5 это
  уже давало врагу простор обойти; на новом 9×7 (пункт «вне плана» выше) — ещё
  больше. Стена из танков геометрически не мешает врагу дойти до дамагера сбоку.
- **Дальность DD и саппорта одинаковая** (`B4_RANGE_BY_ROLE: tank=1, dd=2,
  support=2`, `core/constants.py:878`) — у дамагера нет причины держаться позади
  саппорта или наоборот, оба одинаково «безопасны» на дистанции 2.
- Навыки (`skill`) стоят 3 AP против 2 AP на обычную атаку, кулдаун 2 раунда
  (`B4_SKILL_CD=2`) — при 4-5 AP на юнита это реально ограничивает частоту
  спама навыков, но раз позиционирование/угроза ничего не решают, оптимальная
  игра и так сводится к «куда дотянулся — туда и бей», без причины думать про
  порядок ходов или расстановку.

**Что это значит для объёма задачи:** это не «подкрутить пару чисел», это
структурная дыра — ключевой механизм ролевой тактики (перехват угрозы) не
подключён к текущему движку боя, и позиционирование не создаёт реального риска.
Чтобы роли ЗАРАБОТАЛИ, нужно решить минимум: (1) подключить `intercept_all`/
угрозу к `_best_enemy_plan`, а не только к ульт-таргетингу союзников; (2) дать
позиционированию физический смысл (зона контроля / штраф за проход мимо танка /
что-то структурное, не просто цифра); (3) пересмотреть, различается ли реальный
риск между DD и саппортом на одинаковой дальности; (4) перепроверить это же для
вражеского ИИ Врат/Бездны/Войны — фикс должен работать одинаково для всех
режимов, не только для одного.

**Это отдельная сессия/спек, не быстрый фикс.** Учитывая масштаб (переработка
центрального боевого ИИ + баланс ролей across все режимы боя), нужен отдельный
`brainstorming` → дизайн-спек → план, как и с «Внешним видом», а не правка «в лоб»
по одному сообщению. Не начинаю код по этому блоку, пока не будет отдельной
команды это спроектировать.

---

## 13. 🔴 Админка сайта: список забаненных/кикнутых + доступ разработчика к своим чатам
Владелец: зашёл на сайт под разработчиком в свой чат, хотел разбанить игрока (чтобы
тот смог зайти в группу), не нашёл на сайте, где посмотреть список забаненных/кикнутых
по своему чату — пришлось разбанивать командой `бот разбан, @username` в чате.

**Нашёл кодом две конкретные причины (не только «фичи не хватает» — реальные баги):**

- **Разработчик может не увидеть СВОЙ ЖЕ чат в списке админ-чатов на сайте.**
  `_get_actor_rank`/`_require_admin` (`FastAPI/routers/admin.py:32-63`) корректно дают
  `DEVELOPER_ID` ранг 6 («Владелец») в ЛЮБОМ чате — байпас уже есть и работает для
  действий. НО `my_admin_chats` (`admin.py:108-161`, эндпоинт списка чатов для
  свитчера на сайте) фильтрует строго `WHERE ucs.local_rank >= 1` из
  `user_chat_stats` — **без байпаса разработчика**. Если в чате разработчика нет
  явной строки `local_rank` (не был явно повышен командой бота, а просто владелец
  группы в самом Telegram), чат **не появится в списке на сайте вообще** — даже
  зная о существовании чата, не через что перейти в его админку. Это и есть,
  похоже, то самое «не нашёл, куда зайти».
- **Нет отдельного фильтра «забаненные/кикнутые».** В `admin_users`
  (`admin.py:206+`) каждая строка уже несёт `is_banned`/`was_kicked`/`global_ban`
  (`app.08.js:802-811` их и рисует бейджами + поднимает в сортировке), но
  **отдельного «показать только забаненных» переключателя нет** — приходится
  скроллить общий список участников и высматривать бейджи.

**Что нужно проработать (владелец просит «до мелочей», не наспех):**
1. Байпас разработчика в `my_admin_chats` — так же, как в `_get_actor_rank`:
   разработчик должен видеть в свитчере ЛЮБОЙ свой чат (где состоит), а не только
   те, где есть явная строка ранга. Отдельно продумать: разработчик-«владелец
   через DEVELOPER_ID» и разработчик-«обычный админ в чужом чате» — это ДВА
   разных случая (в первом полный доступ везде, во втором — как у любого другого
   администратора по его реальному рангу в ТОМ чате). Не путать эти два режима.
2. Фильтр/вкладка «🚫 Забаненные и кикнутые» в панели чата — отдельный список
   вместо общего member-list, с прямым действием «разбанить» одним тапом.
3. Свериться с правами по рангу везде в админке (кто видит/может разбанить —
   `rank_ban` порог из `chat_settings`, уже используется — не создавать новый
   парал­лельный механизм прав, переиспользовать существующий).

**Не начинаю код по этому блоку** — ждёт отдельной команды «делаем блок 13».

---

## 14. 🟡 Лимит ИИ-запросов «бот, вопрос» — 5/7/10 в день по VIP
Владелец: ограничить количество запросов к ИИ-помощнику (`services/ai_assistant.py`)
до **5 в день** на обычного игрока, **7 в день** при «VIP-паке VIP-1М», **10 в день**
при «VIP-2М и выше».

**Важно, нашёл при проверке — есть нестыковка терминов, нужно уточнение перед
реализацией:** в коде (`services/vip.py`, `VIP_TIERS`) реальные тиры VIP называются
`silver`/`gold` (цены в зарниках — 250✨/440✨, см. мок в `tools/preview_server.mjs`),
а не «VIP-1М»/«VIP-2М». Термины владельца похожи на пороги ПОТРАЧЕННОЙ суммы (моры?
зарников? рублей?), а не на названия существующих тиров подписки. **Нужно уточнить
у владельца**, что именно значит «VIP-1М»/«VIP-2М» — новые тиры, которых ещё нет, или
имелись в виду silver/gold, или порог общих трат (тогда это больше похоже на метрику
`total_mora_spent_shop`, ту же, что у ачивки «Меценат», см. блок 11).

**Сейчас в коде нет НИКАКОГО существующего дневного лимита на ИИ-запросы** —
`quota_hit`/429 в `ai_assistant.py:726-753` относится к ВНЕШНЕЙ квоте самого Gemini
API, не к лимиту на игрока. Это будет новый механизм с нуля: счётчик запросов в
сутки на `user_id` (сброс по UTC-суткам — паттерн уже есть у `count_today` в
`infrastructure/repositories/battles.py`, можно переиспользовать тот же подход),
проверка лимита ДО обращения к Gemini (чтобы не тратить внешнюю квоту впустую),
понятное сообщение игроку при исчерпании лимита («лимит на сегодня исчерпан,
обновится в 00:00 / получи больше с VIP»).

**Не начинаю код по этому блоку** — ждёт отдельной команды «делаем блок 14» (и
уточнения по тирам выше).

---

## ⛔ НЕ ТРОГАТЬ (явно оставлено по просьбе владельца)
Древо талантов «Небосвод Предвестника» — концепт готов и утверждён отдельно, но
реализация НЕ начинается, пока владелец сам не скажет «делаем древо талантов».





"Jul 22 17:27:39  2026-07-22 17:27:39.262 | INFO     | __main__:main:36 - ══════════════════════════════════════════════════
Jul 22 17:27:39  2026-07-22 17:27:39.263 | INFO     | __main__:main:37 - 🔮 ПРЕДВЕСТНИК V2 — ЗАПУСК СИСТЕМЫ
Jul 22 17:27:39  2026-07-22 17:27:39.263 | INFO     | __main__:main:38 - ══════════════════════════════════════════════════
Jul 22 17:27:39  2026-07-22 17:27:39.263 | INFO     | __main__:main:39 - 📊 Архитектура: PostgreSQL + asyncpg
Jul 22 17:27:40  2026-07-22 17:27:40.963 | INFO     | __main__:main:65 - 🌐 FastAPI мини-апп запущен на порту 8000 (prefix='/predvestnik')
Jul 22 17:27:40  2026-07-22 17:27:40.964 | INFO     | __main__:main:70 - 🐘 Подключение к PostgreSQL...
Jul 22 17:27:40  2026-07-22 17:27:40.964 | INFO     | infrastructure.database:create_pool:95 - 📦 asyncpg version: 0.30.0
Jul 22 17:27:40  2026-07-22 17:27:40.964 | INFO     | infrastructure.database:create_pool:96 - 🔬 Источники подключения (2): DATABASE_URL, PREDVESTNIK_DATABASE_URL
Jul 22 17:27:40  2026-07-22 17:27:40.964 | INFO     | infrastructure.database:create_pool:103 - 🔌 [DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 22 17:27:40  2026-07-22 17:27:40.964 | INFO     | infrastructure.database:create_pool:108 - 🌐 [DATABASE_URL] Цель: app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 22 17:27:41  2026-07-22 17:27:41.129 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [DATABASE_URL] DNS  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com → ['100.126.247.195']
Jul 22 17:27:47  2026-07-22 17:27:47.567 | INFO     | infrastructure.database:create_pool:95 - 📦 asyncpg version: 0.30.0
Jul 22 17:27:47  2026-07-22 17:27:47.567 | INFO     | infrastructure.database:create_pool:96 - 🔬 Источники подключения (2): DATABASE_URL, PREDVESTNIK_DATABASE_URL
Jul 22 17:27:47  2026-07-22 17:27:47.567 | INFO     | infrastructure.database:create_pool:103 - 🔌 [DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 22 17:27:47  2026-07-22 17:27:47.567 | INFO     | infrastructure.database:create_pool:108 - 🌐 [DATABASE_URL] Цель: app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 22 17:27:47  2026-07-22 17:27:47.569 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [DATABASE_URL] DNS  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com → ['100.126.247.195']
Jul 22 17:27:48  2026-07-22 17:27:48.295 | INFO     | infrastructure.database:create_pool:95 - 📦 asyncpg version: 0.30.0
Jul 22 17:27:48  2026-07-22 17:27:48.295 | INFO     | infrastructure.database:create_pool:96 - 🔬 Источники подключения (2): DATABASE_URL, PREDVESTNIK_DATABASE_URL
Jul 22 17:27:48  2026-07-22 17:27:48.295 | INFO     | infrastructure.database:create_pool:103 - 🔌 [DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 22 17:27:48  2026-07-22 17:27:48.295 | INFO     | infrastructure.database:create_pool:108 - 🌐 [DATABASE_URL] Цель: app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 22 17:27:48  2026-07-22 17:27:48.298 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [DATABASE_URL] DNS  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com → ['100.126.247.195']
Jul 22 17:27:49  2026-07-22 17:27:49.130 | INFO     | infrastructure.database:_diagnose:67 - ❌ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 22 17:27:49  2026-07-22 17:27:49.131 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 → OK
Jul 22 17:27:49  2026-07-22 17:27:49.131 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25061 → OK
Jul 22 17:27:49  2026-07-22 17:27:49.131 | INFO     | infrastructure.database:create_pool:103 - 🔌 [PREDVESTNIK_DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 22 17:27:49  2026-07-22 17:27:49.131 | INFO     | infrastructure.database:create_pool:108 - 🌐 [PREDVESTNIK_DATABASE_URL] Цель: private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 22 17:27:49  2026-07-22 17:27:49.154 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [PREDVESTNIK_DATABASE_URL] DNS  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com → ['10.114.0.2']
Jul 22 17:27:54  2026-07-22 17:27:54.001 | INFO     | infrastructure.database:create_pool:95 - 📦 asyncpg version: 0.30.0
Jul 22 17:27:54  2026-07-22 17:27:54.001 | INFO     | infrastructure.database:create_pool:96 - 🔬 Источники подключения (2): DATABASE_URL, PREDVESTNIK_DATABASE_URL
Jul 22 17:27:54  2026-07-22 17:27:54.001 | INFO     | infrastructure.database:create_pool:103 - 🔌 [DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 22 17:27:54  2026-07-22 17:27:54.002 | INFO     | infrastructure.database:create_pool:108 - 🌐 [DATABASE_URL] Цель: app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 22 17:27:54  2026-07-22 17:27:54.004 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [DATABASE_URL] DNS  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com → ['100.126.247.195']
Jul 22 17:27:55  2026-07-22 17:27:55.571 | INFO     | infrastructure.database:_diagnose:67 - ❌ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 22 17:27:55  2026-07-22 17:27:55.571 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 → OK
Jul 22 17:27:55  2026-07-22 17:27:55.571 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25061 → OK
Jul 22 17:27:55  2026-07-22 17:27:55.571 | INFO     | infrastructure.database:create_pool:103 - 🔌 [PREDVESTNIK_DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 22 17:27:55  2026-07-22 17:27:55.571 | INFO     | infrastructure.database:create_pool:108 - 🌐 [PREDVESTNIK_DATABASE_URL] Цель: private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 22 17:27:55  2026-07-22 17:27:55.589 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [PREDVESTNIK_DATABASE_URL] DNS  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com → ['10.114.0.2']
Jul 22 17:27:56  2026-07-22 17:27:56.299 | INFO     | infrastructure.database:_diagnose:67 - ❌ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 22 17:27:56  2026-07-22 17:27:56.300 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 → OK
Jul 22 17:27:56  2026-07-22 17:27:56.300 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25061 → OK
Jul 22 17:27:56  2026-07-22 17:27:56.300 | INFO     | infrastructure.database:create_pool:103 - 🔌 [PREDVESTNIK_DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 22 17:27:56  2026-07-22 17:27:56.300 | INFO     | infrastructure.database:create_pool:108 - 🌐 [PREDVESTNIK_DATABASE_URL] Цель: private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 22 17:27:56  2026-07-22 17:27:56.302 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [PREDVESTNIK_DATABASE_URL] DNS  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com → ['10.114.0.2']
Jul 22 17:27:56  2026-07-22 17:27:56.668 | INFO     | infrastructure.database:create_pool:95 - 📦 asyncpg version: 0.30.0
Jul 22 17:27:56  2026-07-22 17:27:56.668 | INFO     | infrastructure.database:create_pool:96 - 🔬 Источники подключения (2): DATABASE_URL, PREDVESTNIK_DATABASE_URL
Jul 22 17:27:56  2026-07-22 17:27:56.668 | INFO     | infrastructure.database:create_pool:103 - 🔌 [DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 22 17:27:56  2026-07-22 17:27:56.668 | INFO     | infrastructure.database:create_pool:108 - 🌐 [DATABASE_URL] Цель: app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 22 17:27:56  2026-07-22 17:27:56.671 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [DATABASE_URL] DNS  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com → ['100.126.247.195']
Jul 22 17:27:57  2026-07-22 17:27:57.156 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 22 17:27:57  2026-07-22 17:27:57.156 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 → TIMEOUT 8.0s
Jul 22 17:27:57  2026-07-22 17:27:57.156 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25061 → TIMEOUT 8.0s
Jul 22 17:27:57  2026-07-22 17:27:57.159 | INFO     | infrastructure.database:create_pool:114 - ✅ Internet  8.8.8.8:53 → OK
Jul 22 17:27:57  2026-07-22 17:27:57.159 | INFO     | infrastructure.database:create_pool:115 - 🔬 Диагностика завершена, пробуем asyncpg...
Jul 22 17:27:57  2026-07-22 17:27:57.159 | INFO     | infrastructure.database:create_pool:120 - 🐘 Пробуем подключиться через [DATABASE_URL]...
Jul 22 17:27:57  2026-07-22 17:27:57.159 | INFO     | infrastructure.database:create_pool:122 - 🐘 [DATABASE_URL] asyncpg create_pool — попытка 1/2 (timeout=30s)...
Jul 22 17:27:57  2026-07-22 17:27:57.192 | INFO     | infrastructure.database:create_pool:133 - ✅ PostgreSQL pool готов через [DATABASE_URL] (min=1 max=15, schema=predvestnik)
Jul 22 17:27:57  2026-07-22 17:27:57.193 | INFO     | __main__:main:73 - 🗄️  Инициализация схемы БД...
Jul 22 17:27:57  2026-07-22 17:27:57.193 | INFO     | bot.core.database:init_db:1435 - Проверка и создание таблиц PostgreSQL...
Jul 22 17:27:57  2026-07-22 17:27:57.814 | INFO     | bot.core.database:init_db:1515 - ✅ Схема PostgreSQL готова!
Jul 22 17:27:57  2026-07-22 17:27:57.814 | INFO     | __main__:main:75 - ✅ База данных готова!
Jul 22 17:27:57  2026-07-22 17:27:57.815 | INFO     | __main__:main:82 - 🔒 Ожидание advisory lock (единственный инстанс)...
Jul 22 17:28:02  2026-07-22 17:28:02.006 | INFO     | infrastructure.database:_diagnose:67 - ❌ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 22 17:28:02  2026-07-22 17:28:02.006 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 → OK
Jul 22 17:28:02  2026-07-22 17:28:02.007 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25061 → OK
Jul 22 17:28:02  2026-07-22 17:28:02.007 | INFO     | infrastructure.database:create_pool:103 - 🔌 [PREDVESTNIK_DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 22 17:28:02  2026-07-22 17:28:02.007 | INFO     | infrastructure.database:create_pool:108 - 🌐 [PREDVESTNIK_DATABASE_URL] Цель: private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 22 17:28:02  2026-07-22 17:28:02.012 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [PREDVESTNIK_DATABASE_URL] DNS  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com → ['10.114.0.2']
Jul 22 17:28:03  2026-07-22 17:28:03.590 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 22 17:28:03  2026-07-22 17:28:03.591 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 → TIMEOUT 8.0s
Jul 22 17:28:03  2026-07-22 17:28:03.591 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25061 → TIMEOUT 8.0s
Jul 22 17:28:03  2026-07-22 17:28:03.593 | INFO     | infrastructure.database:create_pool:114 - ✅ Internet  8.8.8.8:53 → OK
Jul 22 17:28:03  2026-07-22 17:28:03.593 | INFO     | infrastructure.database:create_pool:115 - 🔬 Диагностика завершена, пробуем asyncpg...
Jul 22 17:28:03  2026-07-22 17:28:03.593 | INFO     | infrastructure.database:create_pool:120 - 🐘 Пробуем подключиться через [DATABASE_URL]...
Jul 22 17:28:03  2026-07-22 17:28:03.593 | INFO     | infrastructure.database:create_pool:122 - 🐘 [DATABASE_URL] asyncpg create_pool — попытка 1/2 (timeout=30s)...
Jul 22 17:28:03  2026-07-22 17:28:03.626 | INFO     | infrastructure.database:create_pool:133 - ✅ PostgreSQL pool готов через [DATABASE_URL] (min=1 max=15, schema=predvestnik)
Jul 22 17:28:04  2026-07-22 17:28:04.303 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 22 17:28:04  2026-07-22 17:28:04.304 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 → TIMEOUT 8.0s
Jul 22 17:28:04  2026-07-22 17:28:04.304 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25061 → TIMEOUT 8.0s
Jul 22 17:28:04  2026-07-22 17:28:04.307 | INFO     | infrastructure.database:create_pool:114 - ✅ Internet  8.8.8.8:53 → OK
Jul 22 17:28:04  2026-07-22 17:28:04.307 | INFO     | infrastructure.database:create_pool:115 - 🔬 Диагностика завершена, пробуем asyncpg...
Jul 22 17:28:04  2026-07-22 17:28:04.307 | INFO     | infrastructure.database:create_pool:120 - 🐘 Пробуем подключиться через [DATABASE_URL]...
Jul 22 17:28:04  2026-07-22 17:28:04.307 | INFO     | infrastructure.database:create_pool:122 - 🐘 [DATABASE_URL] asyncpg create_pool — попытка 1/2 (timeout=30s)...
Jul 22 17:28:04  2026-07-22 17:28:04.360 | INFO     | infrastructure.database:create_pool:133 - ✅ PostgreSQL pool готов через [DATABASE_URL] (min=1 max=15, schema=predvestnik)
Jul 22 17:28:04  2026-07-22 17:28:04.673 | INFO     | infrastructure.database:_diagnose:67 - ❌ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 22 17:28:04  2026-07-22 17:28:04.673 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 → OK
Jul 22 17:28:04  2026-07-22 17:28:04.673 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25061 → OK
Jul 22 17:28:04  2026-07-22 17:28:04.673 | INFO     | infrastructure.database:create_pool:103 - 🔌 [PREDVESTNIK_DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 22 17:28:04  2026-07-22 17:28:04.673 | INFO     | infrastructure.database:create_pool:108 - 🌐 [PREDVESTNIK_DATABASE_URL] Цель: private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 22 17:28:04  2026-07-22 17:28:04.676 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [PREDVESTNIK_DATABASE_URL] DNS  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com → ['10.114.0.2']
Jul 22 17:28:10  2026-07-22 17:28:10.013 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 22 17:28:10  2026-07-22 17:28:10.013 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 → TIMEOUT 8.0s
Jul 22 17:28:10  2026-07-22 17:28:10.014 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25061 → TIMEOUT 8.0s
Jul 22 17:28:10  2026-07-22 17:28:10.017 | INFO     | infrastructure.database:create_pool:114 - ✅ Internet  8.8.8.8:53 → OK
Jul 22 17:28:10  2026-07-22 17:28:10.017 | INFO     | infrastructure.database:create_pool:115 - 🔬 Диагностика завершена, пробуем asyncpg...
Jul 22 17:28:10  2026-07-22 17:28:10.017 | INFO     | infrastructure.database:create_pool:120 - 🐘 Пробуем подключиться через [DATABASE_URL]...
Jul 22 17:28:10  2026-07-22 17:28:10.017 | INFO     | infrastructure.database:create_pool:122 - 🐘 [DATABASE_URL] asyncpg create_pool — попытка 1/2 (timeout=30s)...
Jul 22 17:28:10  2026-07-22 17:28:10.063 | INFO     | infrastructure.database:create_pool:133 - ✅ PostgreSQL pool готов через [DATABASE_URL] (min=1 max=15, schema=predvestnik)
Jul 22 17:28:10  2026-07-22 17:28:10.339 | INFO     | __main__:main:85 - 🔒 Advisory lock получен — этот инстанс единственный.
Jul 22 17:28:10  2026-07-22 17:28:10.339 | INFO     | __main__:main:88 - ⚙️  Инициализация Telegram Bot API...
Jul 22 17:28:10  2026-07-22 17:28:10.403 | INFO     | __main__:main:95 - 🔌 Подключение Middleware...
Jul 22 17:28:10  2026-07-22 17:28:10.404 | INFO     | __main__:main:103 - 📡 Регистрация роутеров...
Jul 22 17:28:10  2026-07-22 17:28:10.404 | INFO     | __main__:main:105 - ✅ Все роутеры подключены!
Jul 22 17:28:10  2026-07-22 17:28:10.471 | INFO     | __main__:main:131 - ✅ Кнопка меню → https://iesaroot-app-8kuyb.ondigitalocean.app/predvestnik
Jul 22 17:28:10  2026-07-22 17:28:10.471 | INFO     | __main__:main:138 - 🦄 RARITY_STICKER_ID установлен: CAACAgIAAxkBAAIDgmof-8HXbDv5WsJ4bPs7rqs2qMJqAAIvBAACeKazBLT_Kx2NSudQOwQ
Jul 22 17:28:10  2026-07-22 17:28:10.472 | INFO     | __main__:main:147 - ══════════════════════════════════════════════════
Jul 22 17:28:10  2026-07-22 17:28:10.472 | INFO     | __main__:main:148 - 🟢 БОТ ГОТОВ К ПРИЕМУ СООБЩЕНИЙ
Jul 22 17:28:10  2026-07-22 17:28:10.472 | INFO     | __main__:main:149 - ══════════════════════════════════════════════════
Jul 22 17:28:10  INFO:aiogram.dispatcher:Start polling
Jul 22 17:28:10  2026-07-22 17:28:10.473 | INFO     | services.scheduler:expedition_background_task:234 - Фоновый процесс экспедиций запущен.
Jul 22 17:28:10  2026-07-22 17:28:10.473 | INFO     | services.scheduler:daily_deal_task:347 - Фоновая задача акции дня запущена.
Jul 22 17:28:10  2026-07-22 17:28:10.474 | INFO     | services.scheduler:duel_and_auction_task:636 - Фоновая задача дуэлей/аукциона запущена.
Jul 22 17:28:10  2026-07-22 17:28:10.474 | INFO     | services.scheduler:chest_spawn_task:858 - Фоновая задача сундуков запущена.
Jul 22 17:28:10  2026-07-22 17:28:10.474 | INFO     | services.scheduler:anniversary_task:916 - Фоновая задача годовщин брака запущена.
Jul 22 17:28:10  2026-07-22 17:28:10.474 | INFO     | services.scheduler:smart_pulse_task:769 - Фоновая задача «Умный Пульс» запущена.
Jul 22 17:28:10  2026-07-22 17:28:10.474 | INFO     | services.scheduler:shadow_merchant_task:978 - Фоновая задача «Теневой Торговец» запущена.
Jul 22 17:28:10  2026-07-22 17:28:10.474 | INFO     | services.scheduler:crypto_alerts_task:268 - Фоновая задача ценовых алертов биржи запущена.
Jul 22 17:28:10  INFO:aiogram.dispatcher:Run polling for bot @IIIPredvestnikIIIBot id=8485867534 - '12 предвестник'
Jul 22 17:28:12  2026-07-22 17:28:12.678 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 22 17:28:12  2026-07-22 17:28:12.678 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 → TIMEOUT 8.0s
Jul 22 17:28:12  2026-07-22 17:28:12.678 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25061 → TIMEOUT 8.0s
Jul 22 17:28:12  2026-07-22 17:28:12.680 | INFO     | infrastructure.database:create_pool:114 - ✅ Internet  8.8.8.8:53 → OK
Jul 22 17:28:12  2026-07-22 17:28:12.681 | INFO     | infrastructure.database:create_pool:115 - 🔬 Диагностика завершена, пробуем asyncpg...
Jul 22 17:28:12  2026-07-22 17:28:12.681 | INFO     | infrastructure.database:create_pool:120 - 🐘 Пробуем подключиться через [DATABASE_URL]...
Jul 22 17:28:12  2026-07-22 17:28:12.681 | INFO     | infrastructure.database:create_pool:122 - 🐘 [DATABASE_URL] asyncpg create_pool — попытка 1/2 (timeout=30s)...
Jul 22 17:28:12  2026-07-22 17:28:12.712 | INFO     | infrastructure.database:create_pool:133 - ✅ PostgreSQL pool готов через [DATABASE_URL] (min=1 max=15, schema=predvestnik)
Jul 22 17:28:23  2026-07-22 17:28:23.923 | ERROR    | infrastructure.pg_adapter:_run:233 - PG error: duplicate key value violates unique constraint "active_expeditions_pkey"
Jul 22 17:28:23  DETAIL:  Key (pet_id)=(1) already exists.
Jul 22 17:28:23  SQL: INSERT INTO active_expeditions (pet_id, chat_id, duration_hours, cost_mora, ends_at) VALUES ($1, $2, $3, $4, NOW() + ($5 * INTERVAL '1 hour'))
Jul 22 17:28:23  Args: [1, -1003841515877, 8, 100, 7.88]
Jul 22 17:29:07  INFO:aiogram.event:Update id=976721089 is not handled. Duration 167 ms by bot id=8485867534"