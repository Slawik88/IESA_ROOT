# Биржа монет v2 — Этап 0: ревизия существующей реализации

Дата: 17.10.2026. Ветка: `codex/exchange-v2` (база `origin/master` `fcecff0d`).
Скоуп: только чтение и документирование — код, балансы и флаги не менялись.

## 1. Карта действующих частей (биржа монет v1, скрытая)

Все публичные флаги закрыты; для игроков ничего не включено. Действующие
части — ниже; «действующая» = код на master и подключённая инфраструктура, а не
доступная игрокам функция.

Флаги (`infrastructure/repositories/system_flags.py`, таблица `system_flags`):

- `economy_player_exchange_v1` — «Биржа монет игроков (dev)», по умолчанию
  выключен (fail-closed: известный экспериментальный ключ остаётся выключенным
  даже до создания таблицы).
- `economy_player_exchange_shorts_v1` — «Шорты биржи монет игроков (dev)», по
  умолчанию выключен.

Слои:

- `core/player_exchange_v1.py` (234 стр.) — чистые правила: выпуск 1 000 000
  монет (3 знака), тариф создания 2 000 ✨, вклад Моры 10 000–1 000 000,
  аукцион 24 ч, сетка казны ±2/4/6/8/10%, эмиссия ≤10%/24 ч (кулдаун 7 дней),
  вестинг 30+180 дней, ликвидность: лок 30 дней, ожидание 24 ч, ≤10%, кулдаун
  7 дней; комиссии maker 10 б.п. / taker 25 б.п. при min-нотионале 10 Моры.
- `core/player_exchange_shorts_v1.py` (350 стр.) — модель шортов v1: гейты
  (7 дней, 100 сделок, 20 трейдеров, 50 000 объёма в неделю), маржа
  200%/150%/120%, штраф ликвидации 8% (5% ликвидатору, 3% страховке), ставка от
  утилизации пула займа.
- `services/player_exchange_v1.py` (2 467 стр.) — все писатели: создание,
  аукцион, лимитные заявки, мэтчинг, эмиссия, вестинг, казна, ликвидность,
  займ/шорты; recovery-эндпоинты; фоновое обслуживание (расчёт аукционов,
  эмиссий, выводов ликвидности, риск-обслуживание шортов, замороженные
  требования). Все денежные движения — через `economy_ledger` (19 вызовов),
  каждая операция с action id.
- `infrastructure/repositories/player_exchange_v1.py` (3 396 стр.) — DDL: 29
  таблиц (`player_coins_v1`, `player_coin_*`, `player_exchange_*`), append-only
  триггеры, singleton `player_exchange_schema_v1`.
- `FastAPI/routers/player_exchange_v1.py` (541 стр.) — 28 маршрутов
  `/player-exchange/v1/...` (+`/shorts/...`); recovery и отмена доступны даже
  при закрытом флаге — но только тем, у кого есть собственное состояние.
- `FastAPI/main.py` — роутер подключён; DDL `ensure_player_exchange_v1`
  выполняется в lifespan при каждом старте; ошибка DDL фатальна только если
  флаг включён.
- `services/scheduler.py` — каждые 10 минут (при ошибке — 30 с) прогоняются
  расчёт аукционов, эмиссий, выводов ликвидности и риск-обслуживание шортов; на
  пустых данных это no-op, но код жив.
- UI: `FastAPI/static/app.14.js` (300 стр.) — скрытый экран «Биржа монет»
  (вход `#cc-exchange-v1` скрыт, пока флаг выключен и нет состояния для
  восстановления); `index.html` — страница `#pg-exchange-v1`.
- Стенды/тесты: `tools/test_player_exchange_v1_rules.py`, `..._pg.py` (1 945
  стр.), `..._ui_contract.py`, `test_player_exchange_recovery_ui.js`,
  `test_player_exchange_shorts_model_rules.py`, `tools/simulate_player_exchange_v1.py`
  (100 000 прогонов), `tools/simulate_player_exchange_shorts_v1.py`.

Смежные модули (не биржа игрока, не трогаем):

- `services/crypto_exchange.py` + `FastAPI/routers/exchange.py` — retired
  lore-рынок (информационный), в `main.py` помечен `exchange_retired`. Его
  модель цены — старая интерполяция (узлы каждые 30 мин на секрете, smoothstep,
  пол 20% базы, 7-дневные мировые фазы); по ТЗ v2 не переносится без проверки и
  нашему сценарию не нужна.
- `core/zarniki_exchange_v1.py` + сервис/репозиторий — обменник ✨→Мора/Алмазы
  (10 Мора и 0.01 ♦ за 1✨, лимит 50✨/сутки), живёт под `shop_v1`; это не биржа
  монет, оставляем как есть.

## 2. Совместимость с кошелёком и журналом

- Мора двигается только канонической операцией
  `economy_ledger.apply_balance_change` (идемпотентный operation_id, журнал с
  before/after по каждой валюте). Валюты леджера: mora (отображение — целые),
  diamonds (2 знака), dark_mora, zarniki.
- Требования ТЗ §13 (атомарность, идемпотентность, фиксированная точность,
  запрет минусов, восстановление после рестарта) уже обеспечены общей
  платформой леджера; v2 строится на тех же примитивах.
- Собственный учёт монеты (токен-леджеры, append-only события, квитанции) у v1
  отдельный от кошелька — это соответствует §13 («первоначальное создание
  монет и все дальнейшие движения отражаются в учёте»).

## 3. Состояние флагов и старые обязательства

Что можно утверждать сейчас:

- Код: все писатели биржи и шортов закрыты флагом; выключенный флаг не
  позволяет создать ни одной строки в таблицах биржи (создание монеты —
  единственный источник остальных записей). Фоновое обслуживание не создаёт
  данные само по себе.
- Локальные архивы прода (`.codex/snapshots/production-*-2026-09-19.dump`)
  старше появления биржи (первая волна — 26.09.2026), поэтому текущее
  состояние прод-данных ими не доказывается. Локальный preprod-кластер
  (порт 5433) недоступен без пароля.

Открытый пункт (требуется владелец): read-only DSN прод-базы (процедура как в
LCB-002; только чтение, `default_transaction_read_only=on`). После получения —
прогнать пакет из Приложения A. До получения доступа никакие миграции,
удаления или «переносы» не выполняются. Утверждение «переносить нечего»
считаем неподтверждённым данными и держим открытым.

## 4. Расхождения v1 с новым ТЗ v2

1. Цена: v1 — стакан и мэтчинг игроков (цена зависит от заявок и сделок);
   v2 — только серверный алгоритм, стакан игрокам не выводится, сделки не
   двигают курс. Торговое ядро v1 (аукцион/заявки/мэтчинг/сетка казны) в основу
   v2 не берём.
2. Шорт: v1 — пул займа от игроков (депозиты, pro-rata выдача, проценты,
   замороженные требования, страховка дефицита); v2 — заём из системного
   резерва монеты без пула игроков. Модель v1 пересобирается.
3. Создание монеты: v1 — аукцион 24 ч, вестинг, распределение genesis
   (30/20/20/30), фиксированный тариф 2 000 ✨, вклад 10 000–1 000 000 Моры;
   v2 — тариф 1 000–5 000 ✨ на выбор, вклад Мора или алмазы, стартовая цена по
   формуле, без аукциона и вестинга.
4. Комиссии: v1 — maker/taker 10/25 б.п., 70/30 сжигание/страховка; v2 —
   распределение комиссий отдельно согласуется (ТЗ §8).
5. Управление владельца: эмиссия, вестинг, казна, ликвидность — в v1 скрытые
   админ-контуры; в v2 не выводятся игрокам, v1 не включается.
6. UI: v1 — монолитный экран со стаканом, аукционом, казной, вестингом,
   займом; v2 — новые экраны по ТЗ §12, v1-интерфейс основой не является.
7. Обучение: демо-кошелёк исключён владельцем — в v2 не делаем (в v1 его и не
   было).
8. Требования к генератору цены (серверное время, восстановление истории,
   правило пропущенных интервалов, секрет) — в v1 отсутствуют; старая
   интерполяция lore-рынка по ТЗ не переносится.
9. Учёт средней себестоимости, срок котировки, «Пока вас не было» — в v1 нет:
   это новые контракты v2.
10. Обязательства прода — проверить по пакету Приложения A, когда будет
    read-only доступ (пункт 3).

## 5. Что переиспользуем и что нет

Переиспользуем: канонический кошелёк/журнал (`economy_ledger`), паттерны
идемпотентности и action id, system_flags, DDL-паттерн `ensure_tables`,
recovery-контракт (доступность собственного состояния при закрытом флаге),
фоновый контур scheduler, оболочку и компоненты сайта.

Не переиспользуем: аукцион, стакан, лимитные заявки, мэтчинг, пул займа,
эмиссию, вестинг, казну, ликвидность, экран app.14, любую интерполяцию цены.

## Приложение A — пакет проверки прода (read-only)

Выполнять в схеме `predvestnik` в режиме только чтения:

```sql
BEGIN TRANSACTION READ ONLY;
SELECT key, enabled, label FROM predvestnik.system_flags
 WHERE key IN ('economy_player_exchange_v1','economy_player_exchange_shorts_v1');
SELECT singleton, schema_version, installed_at
  FROM predvestnik.player_exchange_schema_v1;
SELECT 'player_coins_v1' AS t, count(*) FROM predvestnik.player_coins_v1
UNION ALL SELECT 'player_coin_accounts_v1', count(*) FROM predvestnik.player_coin_accounts_v1
UNION ALL SELECT 'player_coin_events_v1', count(*) FROM predvestnik.player_coin_events_v1
UNION ALL SELECT 'player_coin_mora_accounts_v1', count(*) FROM predvestnik.player_coin_mora_accounts_v1
UNION ALL SELECT 'player_coin_auction_bids_v1', count(*) FROM predvestnik.player_coin_auction_bids_v1
UNION ALL SELECT 'player_coin_auction_settlements_v1', count(*) FROM predvestnik.player_coin_auction_settlements_v1
UNION ALL SELECT 'player_coin_orders_v1', count(*) FROM predvestnik.player_coin_orders_v1
UNION ALL SELECT 'player_coin_trades_v1', count(*) FROM predvestnik.player_coin_trades_v1
UNION ALL SELECT 'player_exchange_fee_fund_v1', count(*) FROM predvestnik.player_exchange_fee_fund_v1
UNION ALL SELECT 'player_coin_market_state_v1', count(*) FROM predvestnik.player_coin_market_state_v1
UNION ALL SELECT 'player_coin_emissions_v1', count(*) FROM predvestnik.player_coin_emissions_v1
UNION ALL SELECT 'player_coin_liquidity_withdrawals_v1', count(*) FROM predvestnik.player_coin_liquidity_withdrawals_v1
UNION ALL SELECT 'player_coin_mora_ledger_v1', count(*) FROM predvestnik.player_coin_mora_ledger_v1
UNION ALL SELECT 'player_coin_short_reserves_v1', count(*) FROM predvestnik.player_coin_short_reserves_v1
UNION ALL SELECT 'player_coin_lending_positions_v1', count(*) FROM predvestnik.player_coin_lending_positions_v1
UNION ALL SELECT 'player_coin_short_positions_v1', count(*) FROM predvestnik.player_coin_short_positions_v1
UNION ALL SELECT 'player_coin_short_cash_ledger_v1', count(*) FROM predvestnik.player_coin_short_cash_ledger_v1
UNION ALL SELECT 'player_coin_short_interest_accruals_v1', count(*) FROM predvestnik.player_coin_short_interest_accruals_v1
UNION ALL SELECT 'player_coin_short_interest_pauses_v1', count(*) FROM predvestnik.player_coin_short_interest_pauses_v1
UNION ALL SELECT 'player_coin_short_loans_v1', count(*) FROM predvestnik.player_coin_short_loans_v1
UNION ALL SELECT 'player_coin_short_interest_claims_v1', count(*) FROM predvestnik.player_coin_short_interest_claims_v1
UNION ALL SELECT 'player_coin_short_frozen_claims_v1', count(*) FROM predvestnik.player_coin_short_frozen_claims_v1
UNION ALL SELECT 'player_coin_short_frozen_interest_claims_v1', count(*) FROM predvestnik.player_coin_short_frozen_interest_claims_v1
UNION ALL SELECT 'player_coin_short_frozen_interest_settlements_v1', count(*) FROM predvestnik.player_coin_short_frozen_interest_settlements_v1
UNION ALL SELECT 'player_coin_short_reserve_ledger_v1', count(*) FROM predvestnik.player_coin_short_reserve_ledger_v1
UNION ALL SELECT 'player_coin_short_buyback_cycles_v1', count(*) FROM predvestnik.player_coin_short_buyback_cycles_v1
UNION ALL SELECT 'player_coin_short_events_v1', count(*) FROM predvestnik.player_coin_short_events_v1
UNION ALL SELECT 'player_coin_short_maintenance_cursor_v1', count(*) FROM predvestnik.player_coin_short_maintenance_cursor_v1
ORDER BY t;
ROLLBACK;
```

Ожидаемый результат при «переносить нечего»: оба флага `enabled = 0`; все
счётчики биржи и шортов — `0`; `player_exchange_schema_v1` содержит только
служебную строку версии. Любая ненулевая строка — обязательство, к которому
готовится отдельный переход (ничего не удалять).
