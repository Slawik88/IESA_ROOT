# CASINO/PETS/STARDUST/ONLINE-MAFIA-20261023 — RELEASED TO MASTER AND LIVE

Дополнительный запрос «найди места, которые можно улучшить» выполнен:
- Casino draft/open/error/focus сохраняются по владельцу; отказ раскрывает форму
  даже после сворачивания во время запроса. Pending body по-прежнему заморожен.
- Dust shop: Enter/валидация/inline ошибки/Back с черновиком, VIP expiry/active,
  fractional progress и refresh с сохранением последнего состояния при сбое.
  Read/write generations + readySeq закрыли stale GET при reopening во время
  обмена и защитили данные при смене аккаунта. В чате также видны expiry/fraction.
- Pet chat: именные возвраты, точное восстановление при кормлении, уровни/названия
  талисманов и предупреждение переноса; убрана дублирующая кнопка списка.
- Новые browser regressions PASS (36 casino +6 dust visible layouts,409/503,
  фокус/Enter/Back, stale read ordering), PG dust/pet chat + patchnotes PASS.
  Критик отдельно подтвердил закрытие3гонок; экономика не менялась.
  Подробности в docs/audits/AUTONOMOUS_RELEASE_BACKLOG.md (верхняя запись).


Ветка codex/casino-polish в managed worktree; обе пачки rebased на master2f2e90ef:
C:/Users/makss/.codex/worktrees/casino-polish/IESA_ROOT.
Исходный backup-checkout и его изменения не затронуты. Казино/pets/dust
закоммичены526c0a69; Мафия +production timer/schema +casino fence —8314d6d6.
Оба коммита отправлены непосредственно в origin/master и подтверждены ls-remote.

Казино: RTP рун95,572→98,143%, выплаты31,659→33,422%, чистаяпобеда4,307→5,111%.
Пустота7→6, Fehu8→9, тройкаFehu×11→×8,5. Колесо: один0→×1,5, один×3→×2;
RTP97,5%, выплаты55→60%, чистаяпобеда30→35%. Кости: преимущество4→2%.
Настоящие WAAPI-барабаны, stagger landing, cancel on leave, reduced motion;
итог/выплата раздельно, история, CTA320×640,6read-onlyзначков с прошлыми партиями.
Покупка1Мора=1жетон, вывод1:1. Bonus и redeemable раздельны, выбранныйпул
фиксируется в ставке. Gift1000 и его выигрыши невыводимы. Legacy total прежний,
redeemable=min(chips//10,historicalMoraSpent), остальное bonus, миграция одинраз.
Вывод+canonicalMora ledger+immutable receipt атомарны; итогМоры≤2^53−1.
Pending body/action_id сохраняются по владельцу в sessionStorage после reload/401/429.
Rolling rollout защищён SQL trigger: INSERT/UPDATE кошелька требует
transaction-local writer_version2, который выставляет lock_wallet. Старые
операции откатываются целиком; PG proof проверяет INSERT conflict/UPDATE,
списание Моры и отсутствие утечки marker после commit/rollback. Откат к старому
приложению сам по себе не снимает эту защиту.

Питомцы: новый bot/chat/pets.py + pet_menu/details/builds; durable owner/chat/72h
buttons в infrastructure/repositories/pet_chat.py. Group+DM, все registry/помощь:
питомцы, отправить/покормить питомца, лагерь, вылазка, выслеживание, испытание,
бестиарий. Все действия существующих сервисов: gear/build/talismans/presets,
кормление, отправка/возвращение/развилка,лагерь,trial,tracking,outing.
Подтверждения сохраняют цену/сборку/уровень/неделю; replay до проверкисвежести.
Каждый callback перечитывает block/deleted/system/module/chat/section/group/command.
Критик помог закрыть bypass выключеннойподкоманды и stale-weektrial.

Звёздная пыль: пользователь отверг14дней/30. УДАЛЕНЫ все caps: rollingVIP,
future7, balance1400, petdaily42. Не возвращать их.100пыли=1деньVIP,
любой доступный срок, оплаченный VIP продлевается. Источник — общий звёздный
след отряда: trek/exp2пыли/час,watch0,2. Max интенсивности пересечений,
не сумма питомцев. Обычный лут каждого прежний. Fraction/remainder сохраняются,
микросекунды целочисленные, immutable интервалы, out-of-order возвращения
доплачивают разницу. Нет companion/VIP/gear множителей. В общей tx claim_run.
Max48pet+24chat=72пыли/сутки<100стоимостиVIP. Долгие накопления могуткупитьнедели.
бот звездопад: secrets0..1,0..24пыли,1попытка/account/UTCday,нулевыетожефиксируются;
красивые labels+0–5звёзд. бот пыль / бот вип за пыль [дней], все в помощи.
Shop изpets/VIP, app54, arbitrarydays, durablepending, expectedowner, guarded
refresh после смены аккаунта. Startup bot+web обеспечивают schema+flag.

Симуляции actualcore+energy+3slots:120000персон×30дней и12000×180(12профилей),
seed20261023. Средний607,684пыли/30дней;5,577целыхVIP+остаток,медиана6;
180дней→5,986/месяц. Активный1409,154пыли/30дней;13,598целыхVIP+остаток,медиана14;
180дней→14,014/месяц. Непрерывный≈16,72/месяц, дозоры+команда≈3,75.
Это сценарии, не телеметрия. docs/audits/STAR_DUST_BALANCE_2026_10_23.md +
соседние JSONresults/180d, tools/simulate_star_dust.py.6000случайныхпорядков
пересечений совпали с независимым эталоном критика.

Патчноуты:7записей updates.json + FastAPI/static/patch-notes/2026-10-23.json;
cover штатный. После выкладки владелец админка→Патч-ноуты→предпросмотр/Отправить,
как docs/PATCH_NOTES.md. В канал не отправляли.
PASS: casino rules(900k+точныйперебор), casinoPG,cashoutPG,petsPG,pet_chatPG,
star_dustPG(нулевойroll,overlap/reverse/fraction/race/rollback,20+30daysVIP,
paidVIP,owner/gates/help),patchnotescontract16постов,ASGIstatic(rooted/unrooted),
publicroutes,pycompile,nodecheck,diffcheck. Browsercasino36layouts/reels/reducedmotion/
lostcommit+reload+401/429; dust6layouts+15days+lostcommit/reload/429/replay — PASS.
NodeVM критик:delayed account switch — PASS послеисправления.
Старый красный master gate shell_v3_contract:ожидает3игрывместо4 и старуюglintстроку;
несвязанныйgateнеправили. Финальная визуальная критика закрыта: казино без общего rewardhero, деньги
вышеистории,единицыставки,пустыесекторы; формаcashout6размеров безперекрытияdock.
Скриншоты: predvestnik_v2/.local/{casino-final-proof,dust-ui}; внешние копии
C:/Users/makss/.codex/visualizations/2026/10/22/01a165b2-9c11-7560-bdaa-2f50eeebe2e6/casino-polish/review-2026-10-23.
Локальный изолированный PostgreSQL55439 и UI-stand остановлены после проверок.
Release verification2026-10-23T15:27:33Z PASS on live App Platform:
public bundle1074286bytes SHA256a7e5c59d2824325304cab3f6506e4f8f9b341aebd6a83ce0307acae42d5bdcfd
matches the complete local production bundle exactly; casino/trail/online-Mafia
CSS and updates.json exact bytes. Health/ready200; casino/dust/Mafia/staff API401.
Runtime flags game_casino_v1/star_dust_v1/game_mafia_online alltrue; durable
owner-mafia-online-2026-10-23 activation receipt present. Website serves new code.
Mafia unique source services/API/controller copied byte-identically (app55/56),
newer master app50/51/skins prices preserved. Fixed original missing bot startup
schema and supervised timer (production web lifespan is off). Command is in DM,
group and generated help. PG fullgame/resilience/lifecycle/access/poll and real
browser mobile/two-player/recovery suites PASS; independent release critic ACCEPT.
Combined release casino36layouts +dust6layouts and lost-reply regressions PASS.
Final patchnotes contract18posts PASS after preserving concurrent master updates.
Evidence .local/master-release-live.json and external copy under
C:/Users/makss/.codex/visualizations/2026/10/22/01a165b2-9c11-7560-bdaa-2f50eeebe2e6/casino-polish/master-release-2026-10-23/.
Production deployment completed automatically; DigitalOcean login not needed.
Isolated PostgreSQL55439 and UI stand stopped. NO Telegram channel messages sent;
TGK drafts and in-app feed are delivered through the existing mechanism.
All requested implementation/master publishing complete; no required work remains.

# Состояние: админка 2.0 — люди и лица

Дата: 20.10.2026 · ветка `codex/admin-v2` · релиз `254f2f4d`…`6b8f89f6`, полировка поверх

## Цель

Пересобрать веб-админку `/bot-admin` так, чтобы персонал узнавал людей визуально (фото и полезная
информация) на всех экранах, а привычные действия стали проще: одна шторка действий, списки с лицами,
«что требует внимания» на главном и единый словарь действий. Порядок работы: инвентарь → диагноз →
кликабельный прототип → фазы Ф1–Ф5, каждая отдельным коммитом.

## Сделано

- `254f2f4d` — кликабельный прототип `design-concepts/admin-redesign/index.html` на боевом `admin.css`
  (эталон UX для остальных фаз).
- `f5a0aa3f` (Ф1) — фото людей в поиске и карточке. Аватары: Telegram Bot API через подписанную ссылку
  (`services/admin_avatars.py`, `GET /bot-admin/avatar/{uid}?t=…`, HMAC `uid:exp`, TTL 3 ч), кэш,
  плейсхолдер-инициал; наружу уходит только подписанный адрес.
- `e09e6c16` (Ф2) — все действия над человеком в одной шторке: группы «В этом чате / Везде / Профиль /
  Служебное», подсказки-последствия, красное для опасных, выбор чата (по умолчанию самый свежий).
- `4a35ba22` (Ф3) — лица в журнале, жалобах (повторные нарушители, цель, автор, закрывший), отчёте
  рассылки и списке отозванных владельцев; helper `pinline` (фото 22 px + имя + @ник).
- `414b11f4` — дробление JS: `admin.js` (ядро) + `admin-lists.js` (журнал и жалобы) + `admin-boot.js`
  (старт). Версии по содержимому: `page.py` `_TYPES`, `index.html`, тест `test_bot_admin_page.py`.
- `8c6ef5ac` (Ф4) — «Требуют внимания» на главном: баны во всех чатах, повторные жалобы (3+ за 30 дней),
  контроль персонала + до 3 проблемных чатов и кнопка «Все проблемы чатов». Порядок нижней панели:
  Игроки, Жалобы, Журнал, Рассылка, остальное — «Ещё».
- `d1f0b22a` (Ф5) — единый словарь действий по прототипу: «Замутить в чате», «Выгнать из чата»,
  «Забанить в чате», «Выдать предупреждение», «Изменить роль» и т. д. — одинаково в шторке, формах,
  подтверждениях и на экране владельца чата; плашки внимания — лёгкие `.pflag` вместо чипов.

## Полировка после релиза

- Заголовки разделов добавлены туда, где их не было: «Рассылка», «Настройки», «Функции», «Промокоды» —
  с той же иконкой и подписью, что в нижней панели и экране загрузки.
- Журнал перестроен по прототипу: событие и чат в первой строке, ниже — кто/кому, время и причина.
  Чат больше не повторяется в мета-строке; для переключателя, где чат уже назван в описании, ссылка не
  дублируется. Причина стоит после времени, а не перед автором.
- Жалобы: три счётчика («Новых / В работе / Закрыто») всегда в одном ряду, включая 320 px.
- Карточка игрока: балансы на телефоне 2×2, на широком экране — четыре в ряд; у игрока без @ника
  в строке и шапке больше нет повтора `id5002 · ID 5002`.
- Поиск промокодов на узком экране занимает отдельную строку, кнопки «Пачка» и «+ Новый» не сжимают
  подсказку до обрезки.
- `unwarn_all` оставлен в группе «В этом чате»: одиночное действие API требует `chat_id` и снимает
  предупреждения только в выбранном чате. Подсказка исправлена («в этом чате»); массовое «снять варны
  везде» — отдельное действие в режиме выбора игроков. Перенос в «Везде» сломал бы запрос.
- Стенд `tools/admin_stand.py` снова отдаёт все `admin*.js`/`admin*.css` после дробления ядра; фикстуры
  дополнены поиском, вниманием, рассылкой, промокодами, функциями и карточкой игрока, журнал приведён
  к реальной форме (`title` + пустой `text` + отдельный `chat`).

## Ключевые файлы

- `FastAPI/static/bot-admin/admin.js`, `admin-lists.js`, `admin-boot.js`, `admin.css`, `index.html`
- `FastAPI/routers/bot_admin/page.py` (`_TYPES`, версии статики)
- `FastAPI/routers/bot_admin/people.py`, `auth.py`, `reports.py`, `access.py`, `broadcasts.py`
- `services/admin_avatars.py`, `services/admin_people.py`
- `FastAPI/static/design-concepts/admin-redesign/index.html` — эталон UX
- Тесты без БД: `tools/test_bot_admin_page.py`, `test_bot_admin_ui_contract.py`,
  `test_bot_admin_avatars.py`, `test_bot_admin_access_guard.py`
- Тесты с БД: `tools/test_bot_admin_chats_reports_pg.py`, `test_bot_admin_people_pg.py`,
  `test_bot_admin_reports_pg.py`, `test_bot_admin_owner_pg.py`, `test_bot_admin_matrix_pg.py`

## Проверки (что реально прогнано)

- `node --check` для трёх JS — OK.
- `python -m py_compile` изменённых python-файлов — OK.
- `test_bot_admin_page.py` — OK (версии по содержимому, ETag, три скрипта с `?v={{VER}}`).
- `test_bot_admin_ui_contract.py` — OK (пины `actionForm` и `bulkRun` обновлены осознанно: изменён
  только текст подсказок, логика опасных действий не тронута).
- `test_bot_admin_avatars.py` — OK (подпись, срок, негативный кэш, mime, плейсхолдер, токен-гейт).
- `test_bot_admin_access_guard.py` — OK, 68 маршрутов под стражем.
- PostgreSQL 17.11, отдельный временный кластер (пустая БД, ICU en-US):
  `test_bot_admin_chats_reports_pg.py` — OK, включая новые проверки `/people/attention` (403 игроку, бан
  раньше жалоб без дубля, «⚠️ жалоб: 3», контроль, avatar URL, `limit` режет показ); `test_bot_admin_people_pg.py` — OK.
  Оба прогона — временные копии с обходом двух известных красных master: карточка чата читает живую
  таблицу прав бота (порог варна 3, тест ждёт устаревшее 2) и VIP `days_left` в CEST равен 8 при
  ожидании 7. Сами тесты в репозитории не менялись.
- Стенды в браузере (статические, с подменённым `fetch`): старт с тремя скриптами; журнал и жалобы с
  лицами; строки «Требуют внимания»; шторка действий; путь «строка → форма → подтверждение» для
  «Забанить в чате»; экран владельца чата с теми же четырьмя подписями; падение `/people/attention` не
  скрывает проблемы чатов; `revoke_sessions` скрыт у игрока без роли; ник не дублируется. Консоль чистая,
  горизонтального переполнения нет.
- `tools/admin_stand.py`: 10 вкладок (`people, reports, journal, broadcast, access, settings, metrics,
  health, promo, switches`) × 320/390/430 × dark/light — 0 переполнений и 0 JS-ошибок. Отдельно карточка
  игрока и шторка действий на 320/390 в двух темах — 0 ошибок; проверены 2×2 балансов, отсутствие дубля
  `id5002 · ID 5002`, три KPI жалоб, заголовки новых разделов и полная строка поиска промокодов.
- `git diff --check` — чисто.
- **Не запускались:** живой Telegram-клиент и полный `tools/run_preprod_tests.ps1` (общий прогон).

## Риски и границы

- Аватары: ссылка подписана ключом от `BOT_TOKEN`; без токена ссылок нет — фронт показывает инициал.
  Bot API может не отдать фото (приватность) — тот же плейсхолдер, без битых картинок и ошибок.
- База только читается: новых таблиц и миграций нет; `bot_staff_watch` создаётся службой при первом
  обращении (как и раньше в поиске).
- `unwarn_all` в карточке игрока — это действие **в выбранном чате**: API принимает `chat_id` и снимает
  варны только там. Массовое «снять варны везде» доступно через выбор нескольких игроков. Не переносить
  одиночную строку в группу «Везде» без нового серверного действия.
- Журнал и ранги чата сохраняют слова «варн / мут / кик / бан»: это имена рангов и события, они
  закреплены тестами (`test_bot_admin_chats_reports_pg.py`, `test_bot_admin_people_pg.py`) и совпадают
  с сообщениями бота в чате. Шторка и подтверждения говорят глаголами прототипа — это осознанная
  граница; полное переименование затронуло бы бота и БД.
- `GET /people/attention` отдаёт до 50 строк; повторные жалобы видны только тем, кому открыт раздел
  «Жалобы» (проверка через `admin_access.min_rank`).
- `repeat_offenders` на главном читает `bot_reports`; индекса под `status <> 'rejected'` нет. Миграции в
  этой волне запрещены, поэтому индекс не добавлялся: при росте таблицы нужен
  `CREATE INDEX ... ON bot_reports (created_at) WHERE status <> 'rejected'` (или кэш). `total` в
  `/people/attention` считает показанные строки, а не всех; интерфейс его не показывает.

## Следующий шаг

1. Прогнать на пустой БД остальные админские пг-наборы (`reports`, `owner`, `matrix`, `access`) и решить
   судьбу двух известных красных: порог варна в карточке чата и таймзонный `days_left` у VIP.
2. При росте `bot_reports` добавить индекс под повторные жалобы (см. «Риски») или короткий кэш.
3. Открыть админку в Telegram на телефоне и на десктопе: светлая и тёмная тема, длинные названия
   чатов, люди без фото, клавиатура поверх поиска.
4. Собрать замечания владельца. Отдельно решить, нужен ли продуктовый переход «варн → предупреждение»
   в журнале и рангах (это бот + существующие тесты, не только админка).
5. При дальнейшем росте `admin.js` дробить по тому же рецепту: новый файл → `page.py` `_TYPES` →
   `index.html` → фикстура в `test_bot_admin_page.py` → сканирование хуков в `test_bot_admin_ui_contract.py`.

## PETS-UX / MINES-20261021 — released

User authorized simulations and production release via master. Worktree:
`C:/Users/makss/.codex/worktrees/pets-ux-audit/IESA_ROOT`, codex/pets-ux-audit.
Runtime release pushed to master: c252a155 (pets aa528f22, Mine e05288b1), based
on latest 76cb5d29; patch note draft added in 76dafba5. Original F: backup
checkout and unrelated tracks untouched. No channel message was sent.

Shipped: shared overlay background lock and restoration (320/390/430 tested),
companion/trial/build rest preservation, stale price/busy talisman guards,
companion reward receipt, inventory talisman effects, installed-schema SELECT
probe. Mine safe first-open auto wins remain valid but are unranked; seasonal
filter precedes per-player best selection. Offline/replay/progression preserved;
subsecond leaderboard values display milliseconds and rules explain eligibility.

PASS: 12 focused Python suites repeated after rebase, 4 JS suites; independent
read-only release_critic ACCEPT (no P0–P2 blockers). Actual rules/service
simulation: 17,280 rest cases, no invariant failures; 15 first-open wins from
10,000 deterministic easy boards. Policy/loot/XP cap/prices unchanged.
Five gear slots and new mode remain a design proposal, not released content.

Live HTTP verification PASS: 5 exact JS/CSS SHA256 matches, new asset version
in index, new feed entries and Mine shell rules, health/ready 200 and protected
pets/inventory/Mine/profile APIs 401. Evidence output/pets-release/after-deploy.json.
Browser screenshots output/playwright/pets-20261021/.

Full post-rebase gate: 225 total, 184 PASS /41 FAIL. One new missing patch-note
coverage failure fixed in 76dafba5 and contract retested PASS. Remaining 40
also fail on clean e6e75861 source in same disposable DB/env (corrected .env.test
setup); 38 matching terminal errors, 2 different assertions under shared fixture
pollution. Not a green full gate. Full logs and comparison JSON under
output/pets-release/. No failures in targeted pets-v2/inventory-v1/Mine/local games.
Real Telegram iOS/Android gesture smoke not performed; local Chromium checked.

Task complete for the released fixes. Known unrelated test/fixture debt remains
in the single release backlog; no production data cleanup or reward migration.

## WAVE-GAMES-GEAR-20261021 — RELEASED

Same worktree. User explicitly demands all unfinished work and immediate master
pushes. Confirmed NEW implementation: five pet equipment slots + separate quick
«Вылазка», gear ALSO affects current trips and Следы (both async answers YES).
No further approval needed for that scope. Mafia generated images must match
Predvestnik OBSIDIAN/cold violet style. Leaderboard ~minute load goes LAST.

Stage1 shipped to master5c7fa566 atop18417a3d: nontrivial Mine v2 boards,
legacy negotiation/replay preserved; longpress/F/difficulty gameplay fixes;
Rhythm4s field/no target start/gift/resume/restore with full reaction window.
Targeted rules/PG/JS/static gates PASS; independent read-only ACCEPT.

Mafia shipped3757e89e (rebased onto8e2eb05c early-accessLeague work preserved).
Production HTTP identity PASS:8JS/CSS exact SHA256,6art200,manifest404,
health/ready/feed/auth; output/pets-release/mafia-after-deploy.json. Reviewer
resumed and final ACCEPT; all caption findings fixed. Private TGK draft includes
real role screenshot; no channel messages sent.

Gear+outing locally complete: core/pet_equipment.py; ownservice/repo; equipment
JSONB onstate, parts/outings tables installed under old schema advisorylock,
installed schema probe remains SELECT-only. app49registeredinbundle, petcardlink,
hubouting, allbusyfilters. Fivefunctional slots/10items/3tiers; free starteronce,
craft8,upgrade12/24; per-pet bound, revisions avoid lost-response nonceghosts.
Gear affects existing preview/claim/advice/rest/build changes,625dailyXPcap stays.
Outing7choices/9events,3options each,HP4/supplies3,bank/halfrescue/completionbonus,
32parts/run,3starts/day/account,energy10; gearimmutable snapshot,expectedstep,
actionreceipt/userlock. Lastreceipt persists, costs/heal actual deltas exposed.
PASS actualPG gearclaim/ownership/rest/staleprice/busy/resume; two connections
samechoice->oneapply,differentleave->onereward; rules/advice/static/trailcontracts,
JSnonce/recovery/recommendations. 60000simulation/96builds,maxXPx1.2208;
independent79896outcomeoracle and finalrelease_critic ACCEPT. Browser playedall7,
reloadsavedreceipt, craftedlensfor8from10parts/equipped;320/390/430nooverflow.
Proof output/playwright/gear-20261022. Oct22feed+TGKdraft includesall3newfeatures.

Gear74a2df4f pushedmaster. Final leaderboard batch locally complete (lasttask).
Causes: restored active client never requestedranking; coldstartwaitedgamebootstrap;
96SQL/46DDL for20players and schemaCREATEINDEX blockedbyordinarywriter.
Fixed independent restore/cold GET, coalesceddifficultyrequests+dirtytrailingafter
confirmedwin, retry/online; batchrefs collision/race-safe sortedIDs/separateSELECT,
batchresolver; public/MineSELECTschemafastpath andtransaction/advisoryrepair;
oneCTEtop+personal exactties,partialseasonindex.
PASS warmprobe15SQL/0DDL/~12ms andno writerblocking;100000mixedruns14.75ms
fullreply,EXPLAIN4.303msseasonindex. Bulkrefs cold2conn+reverseorder race+forced
collision; ties1/1/3,personalplace25,exclusiveend/unrankedzero/privacy PG PASS.
MinePG,sharedMafia/RhythmPG +independentdecoratorprobe +4JS suites/newloading
suitePASS. Read-onlycritic finalACCEPT (alsoeasy->hard->easylate responseprobe).
Firstschema repair creates normalindex, canwaitwriters once;warmread0DDL.
Browseractualrestore18cellsactive->reload: leaderboardloaded (emptytestboard),
proofoutput/playwright/leaderboard-20261022/restored-loaded.png.

All requested implementation and rollout complete. Runtime master446e47b7
(gear74a2df4f,Mafia3757e89e,Mine/Rhythm5c7fa566). Final production verification
PASS asset_version 710b638fa34288be16a4:8JS/CSS exactSHA256,12JPG/WebP exactbytes,
all6newfeedIDs,24HTTPchecks inclhealth/ready200 andprivateAPIs401.
Evidence output/pets-release/final-after-deploy.json; screenshotpaths above.
Notes/feed/staticgates PASS. Cleanworktree beforethishandoffupdate.
Oct22TGKdraft has3newfeatures/screenshots+leaderboardfix; Oct21-gamesdraft has
Mine/Rhythmfixes. Readabletext output/pets-release/tgk-2026-10-22.html (547chars).
NOchannelmessages sent. Imagegen builtin; finalassets andfullpromptmanifest under
FastAPI/static/mafia-art/. RealdeviceTelegramgesturetestnotperformed, Chromium
smokes above. Fullprojectgate40pre-existingbaselinefailures remainsseparated
anddocumented; thiswave'stargetedgatesallpass. No furtherrequestedwork pending.
Local Stand59754on8403 --trailnone,persona990000001,dummy123456:stand,
PG55432 disposable shared cluster; do not stop sharedPG. Worktree retained.

## 2026-10-22 — owner-requested complete Pets UI rebuild

Active worktree pets-ux-audit, branch codex/pets-ux-audit; frontend only app40/41/49,
trail CSS + feed/day patch note. Overview/collection/camp, contextual preparation,
5-slot comparison, send draft with fresh authoritative quote, nested history and
navigation/dialog race guards. No balance/service/schema changes. Read-only critic
ACCEPT; focused executable UI/contract/rules/advice/static-delivery checks PASS.
Browser actual exp6h -> gear change -> resume retained intent; Escape pet-send;
Back free-filter; Tab trap; 320px pageY0/sheetY351; outing reload/resume/early-return2.
Fresh proof output/playwright/pets-redesign-20261022/{before,after}/.
Final release checks/master push remain; no Telegram channel messages sent.

Post-push refinement: MINIAPP_DESIGN_RULES one-primary-action emphasis checked;
neutral selection/decoration, secondary compare/feed/camp/outing actions ghost,
first ready claim primary, retained draft respects busy state. Actual-render
regressions and independent read-only critic PASS. Pending final deployed identity.
Next owner task: attractive Chests tab redesign, keep published odds/prices unchanged.
