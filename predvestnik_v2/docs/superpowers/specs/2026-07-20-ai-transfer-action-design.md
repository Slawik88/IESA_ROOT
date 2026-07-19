# ИИ-помощник: перевод валюты по кнопке — дизайн

**Дата:** 2026-07-20
**Статус:** утверждён пользователем в диалоге (сессия 2026-07-20), реализуется сразу.

## Суть

Новый инструмент ИИ `propose_transfer(amount, currency, target)` — ИИ **предлагает** перевод,
исполняет ТОЛЬКО игрок нажатием кнопки. Расширяет паттерн `propose_expedition`.

## Требования пользователя (дословно зафиксированы)

1. `@username` указан → резолвим точно по нему.
2. Имя без @ («переведи 500 моры лилит») → ищем совпадения среди участников ЭТОГО чата
   (username + локальный ник), несколько кандидатов → кнопка на каждого.
3. «моей супруге/мужу» → таблица браков (`get_user_marriage`).
4. Бот сам НЕ переводит — только кнопки; кнопка **одноразовая**, двойной клик не должен
   переводить дважды.

## Решение одноразовости

Таблица `ai_pending_actions` (id, user_id, chat_id, action_type, payload JSON, executed,
created_at). В callback кнопки — только id строки + id получателя. Исполнение — атомарный
`UPDATE ... SET executed=TRUE WHERE id=? AND user_id=? AND executed=FALSE AND created_at >
NOW()-INTERVAL '10 minutes' RETURNING payload` — тот же паттерн, что onboarded/ai_hint_shown.
Гонка двойного клика, рестарт бота, протухание (TTL 10 мин) — всё закрыто одной строкой SQL.
Список разрешённых получателей хранится в payload — кнопка с чужим target_id (теоретически
подделанный callback) отклоняется.

## Проверки — паритет с ручной «бот перевод»

На этапе предложения (в tool): группа, глобальный ползунок `tab_economy`, `rank_give` чата,
не себе, не боту. На этапе исполнения: `transfer_currency` (тот же, что PayCB) — FOR UPDATE
на отправителе, проверка баланса внутри.

## Валюты

`TRANSFER_CURRENCIES` (mora/diamonds/dark_mora/zarniki), по умолчанию mora.

## Файлы

- `bot/core/database.py` — CREATE TABLE ai_pending_actions
- `infrastructure/repositories/ai_assistant.py` — create_pending_action / consume_pending_action
- `services/ai_assistant.py` — tool `propose_transfer` + резолюция получателя
- `bot/handlers/common.py` — AiActionCB (act="tr", pa_id, target_id), кнопки, исполнение
