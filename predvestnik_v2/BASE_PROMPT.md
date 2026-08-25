# ПРЕДВЕСТНИК V2 — BASE PROMPT

**Проект:** Telegram-бот + FastAPI мини-апп. Репо: `Slawik88/IESA_ROOT` → `predvestnik_v2/`
**Деплой:** DigitalOcean, URL: `https://iesaroot-app-8kuyb.ondigitalocean.app/predvestnik`
**БД:** PostgreSQL (asyncpg + PGAdapter схема `predvestnik`, `?` → `$1,$2...`)
**Бот:** aiogram 3.x, `@IIIPredvestnikIIIBot`

## ИЕРАРХИЯ (железные правила)
```
core/           ← константы/реестры. Без внешних зависимостей
services/       ← бизнес-логика. Без bot.* / FastAPI.*
infrastructure/ ← только SQL в repositories/
bot/            ← Telegram-адаптер
FastAPI/        ← Web-адаптер
```
- `increment_metric(db, uid, METRIC_NAME)` — metric_name из registry, НЕ ключ ачивки
- `auction_lots.item_name` = `"Название||real_item_id"` → split("||")[1]
- `item_id_or_pet_id` = хэш abs(hash(item_id))%10^9, не настоящий id
- `FastAPI/static/app.01.js`…`app.11.js` — общий classic script (не ES-модули); проверять синтаксис изменённой части и собранного `/static/app.js`

## КЛЮЧЕВЫЕ ФАЙЛЫ
| Файл | Назначение |
|---|---|
| `core/constants.py` | Все числа (цены, лимиты) |
| `core/registry.py` | ITEMS_REGISTRY, ACHIEVEMENTS, CRAFT_RECIPES |
| `core/themes.py` | THEMES (top/sep/bot/accent) |
| `FastAPI/static/app.01.js`…`app.11.js` | Исходные части общего classic-script; production и preview отдают их как `/static/app.js` строго в порядке `FastAPI/main.py` |
| `services/scheduler.py` | Фоновые задачи |
| `GAME_BIBLE.md` | Полный снимок текущих механик, формул, наград и команд; обновляется только по подтверждённому коду |
| `AI_KNOWLEDGE.md` | База знаний ИИ-помощника («бот, вопрос»): стиль/характер + игровые факты. Правится владельцем как текст, уходит в промпт Gemini целиком (HTML-комменты вырезаются); справка команд подмешивается автоматически из HELP_PAGES |
| `ai_knowledge/*.md` | Динамические темы ИИ (get_topic_details): подробная дока по темам, ИИ запрашивает сам по мере надобности. Цифры походов/питомцев/VIP автогенерируются из core/registry.py (services/ai_assistant.py::_TOPIC_AUTOGEN) — всегда актуальны; .md-файлы дополняют их и правятся как текст |
| `docs/audits/AUTONOMOUS_RELEASE_BACKLOG.md` | Единственная оперативная очередь автономной работы и release-рисков |
| `FUTURE_IDEAS.md` | Идеи владельца на будущее, не автоматическая очередь реализации |
| `GAME_RECONSTRUCTION_3_0.md` | Живой контракт основной игры: забеги, сложность, shadow-награды и спутники |
| `BATTLE_VFX_CONCEPT.md` | Действующий стандарт игрового фидбека и accessibility для Reconstruction и будущих игр |
| `PRODUCT.md` + `DESIGN.md` | Дизайн-контекст (/impeccable): стратегия продукта и визуальная система «Золото в темноте» — читать перед любой UI-работой |
| `COSMETICS_COLLECTION_DESIGN_RULES.md` | Механические правила оформления карточек/иконок коллекций косметики (медальоны, анимация, прогресс-индикаторы, антипаттерны) — читать перед добавлением НОВОЙ линейки, чтобы не переспрашивать владельца заново |
| `COSMETICS_LIFECYCLE_POLICY.md` | Правило сохранения старой/BP-косметики: архив для владельца по умолчанию, read-only аудит, versioned migration, ledger и откат; читать до любого удаления ID |
| `AUTONOMOUS_MODE.md` + `AUTONOMOUS_AGENT_POLICY.md` | Самостоятельный цикл и обязательные границы качества/проверок |
| `LOCAL_PREVIEW.md` | Обязательный local-first контур перед production: preview-сервер `:8402`, VS Code Ports, моки, Puppeteer/smoke-проверки и границы стенда |
| `PRODUCTION_RELEASE_CHECKLIST.md` | Обязательный release-gate: сравнение production/local, актуализация `📣 Что нового`, проверки и только затем явно разрешённый деплой |

## КРИТИЧЕСКИЕ ПРАВИЛА
- `services/` не импортирует `bot.*` / `FastAPI.*`
- `let/const` только вверху script (TDZ!)
- `${...}` только в backtick-строках
- PostgreSQL ON CONFLICT: `table.column + $N`
- Дублированные JS-функции — проверять `node --check`
- Перед КАЖДЫМ production-деплоем сравнить точный production revision с локальным кодом, обновить `FastAPI/static/updates.json` реальными пользовательскими изменениями и пройти `PRODUCTION_RELEASE_CHECKLIST.md`; одинаковая live/local лента при пользовательском diff блокирует релиз
- Не трогать `g:\IESA_ROOT\` корень (IESA Django) и `g:\IESA_ROOT\frontend\` (старый React-мини-апп "predvestnik-miniapp", без коммитов с апреля — мёртвый параллельный трек, не наш код)

## ENV (DigitalOcean)
`BOT_TOKEN`, `DATABASE_URL`, `DEVELOPER_ID=1460945748`, `ROOT_PATH=/predvestnik`, `PORT=8000`, `BOT_USERNAME=IIIPredvestnikIIIBot`, `GEMINI_API_KEY` (опц. — ИИ-помощник, без ключа вежливо отключён)

## ПАМЯТЬ (C:\Users\makss\.claude\projects\g--IESA-ROOT\memory\)
- НЕ чистить каждую сессию.
- Раз в несколько сессий — или когда видно, что инфо устарела/тема закрыта — пройтись по `MEMORY.md` и убрать:
  - записи про баги/задачи, которые решены и больше не всплывают
  - project-память про темы, с которых команда явно переключилась
  - дубли/противоречия после новых указаний пользователя
- Цель — экономия токенов: `MEMORY.md` грузится целиком в каждую сессию.

*Обновлено: 2026-08-24 | Автономный режим: AUTONOMOUS_MODE.md | Очередь: docs/audits/AUTONOMOUS_RELEASE_BACKLOG.md | Release-gate: PRODUCTION_RELEASE_CHECKLIST.md | Идеи: FUTURE_IDEAS.md | Игровой контент: GAME_BIBLE.md*
