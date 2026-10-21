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

## PETS-UX / MINES-20261021 — release preparation

User explicitly authorized simulations and production release via master. Worktree:
`C:/Users/makss/.codex/worktrees/pets-ux-audit/IESA_ROOT`, branch codex/pets-ux-audit.
Rebased onto master 76cb5d29; pets aa528f22, Mine e05288b1.
Latest upstream Telegram names/patch notes retained. Original F: backup checkout and unrelated tracks untouched.

Pets: overlay scroll lock verified at 320/390/430; companion/trial/build rest
preserved; stale price and busy talisman guards; separate companion receipt;
read-only inventory effects; schema catalog probe replaces hot-path DDL.
Mines: seed536/first14 naturally wins first click; classify auto wins as unranked
without deleting wins/history/progression. Filter seasonal runs BEFORE DISTINCT
so an ordinary win becomes the player's best. Positive subsecond times show ms.
Both server actions and offline imports covered by SQL/replay tests.

PASS: 12 focused Python gates + Mines lifecycle/accessibility and Trail recovery/
recommendations JS. Actual rules/service simulation: 17,280 rest cases, no
invariant failures; 15 automatic wins / 10,000 deterministic easy boards.
Full gate e6e75861+patch: 187/222 pass, 35 fail. All 35 failures reproduced using
clean e6e75861 source exported via git archive and identical local test DB/env;
not a green full gate. No failures in active pets-v2, inventory, Mines or local
games suites. Logs output/pets-release/, browser evidence output/playwright/.

Five gear slots/new mode remain a design proposal, not shipped. Simulation
shows blindly copying talisman multipliers from 2 to 5 slots is unsuitable;
prices, rewards, drops, XP caps and paid mechanics unchanged by this release.
Final review ACCEPT (release_critic), no P0–P2 blockers in our diff; reviewer
independently repeated 4 Python +4 JS suites. All 12 targeted Python suites
repeated after rebase PASS. Release feed audit READY. Full post-rebase gate
still running, output/pets-release/final-gate.log; do not claim it is green.
Next: push master and verify deployed bundles plus health/readiness/auth.
Real Telegram iOS/Android gesture smoke remains outside available hardware.
