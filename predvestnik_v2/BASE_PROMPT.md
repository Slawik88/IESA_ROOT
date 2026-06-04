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
- `FastAPI/static/app.js` — classic script (не ES-модуль), проверять `node --check`

## КЛЮЧЕВЫЕ ФАЙЛЫ
| Файл | Назначение |
|---|---|
| `core/constants.py` | Все числа (цены, лимиты) |
| `core/registry.py` | ITEMS_REGISTRY, ACHIEVEMENTS, CRAFT_RECIPES |
| `core/themes.py` | THEMES (top/sep/bot/accent) |
| `FastAPI/static/app.js` | JS ~1825 строк — ТОЛЬКО grep+offset Read |
| `services/scheduler.py` | Фоновые задачи |
| `AUDIT_V3.md` | Рабочий план по блокам (пиши "делаем блок N") |

## КРИТИЧЕСКИЕ ПРАВИЛА
- `services/` не импортирует `bot.*` / `FastAPI.*`
- `let/const` только вверху script (TDZ!)
- `${...}` только в backtick-строках
- PostgreSQL ON CONFLICT: `table.column + $N`
- Дублированные JS-функции — проверять `node --check`
- Не трогать `g:\IESA_ROOT\` корень (IESA Django)

## ENV (DigitalOcean)
`BOT_TOKEN`, `DATABASE_URL`, `DEVELOPER_ID=1460945748`, `ROOT_PATH=/predvestnik`, `PORT=8000`, `BOT_USERNAME=IIIPredvestnikIIIBot`

*Обновлено: 2026-06-04 | Полный план: AUDIT_V3.md*
