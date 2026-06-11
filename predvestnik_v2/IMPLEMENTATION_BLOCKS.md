# IMPLEMENTATION BLOCKS — донат / VIP / БП / глобальная модерация

> Источник: `FUTURE_IDEAS.md` (340 строк, всё «РЕШЕНО» уже зафиксировано там).
> Каждый блок ниже — самодостаточный план реализации, привязанный к
> КОНКРЕТНЫМ файлам/функциям/таблицам ТЕКУЩЕГО проекта (после ресёрча
> кодовой базы), плюс учёт того, как блок стыкуется с ОСТАЛЬНЫМИ блоками.
>
> **Как работаем**: пишешь "делаем блок N" — начинаю реализацию именно
> этого блока. Если блок на практике лёгкий — могу слить с соседним по
> ходу работы (предложу, прежде чем менять объём).

---

## Порядок и зависимости

```
Блок 1 (Зарники: Stars-покупка + обмен + донат-магазин)  ← фундамент
   │
   └──▶ Блок 2 (VIP: ядро подписки — таблица/тарифы/сервис)
            │
            ├──▶ Блок 3 (VIP-бейдж: централизованный хелпер + роллаут ~45 мест)
            ├──▶ Блок 4 (VIP-плюшки: варпы / лимит ника / +1 слот / пробники / напоминание)
            └──▶ Блок 5 (Боевой пропуск — платный трек = активный VIP)

Блок 6 (Глобальная модерация: ядро — таблицы/сервис/middleware/команды)
   │       независим от 1-5, можно делать параллельно
   └──▶ Блок 7 (Глобальная модерация: сайт /admin/global)

Блок 8 (доделки веб-панели чата) — независим от всего, можно в любой момент.
```

Рекомендованный порядок: **1 → 2 → 3 → 4 → 5**, отдельно **6 → 7**, **8** — когда удобно.

---

## Принципы (из «Стратегии монетизации» — НЕ отдельный блок)

Это не код, а рамки, которые уже учтены в тарифах VIP (Блок 2) и наградах
БП (Блок 5) — отдельной реализации не требует, но держим в голове при
любых правках 1/2/5:
- Косметика и удобство — да; прямое преимущество "сильнее" — нет.
- Эксклюзивных питомцев/контента за донат не вводим (закрыто).
- Гача/крафт/зоопарк/дуэли/аукцион/браки/ачивки/кланы — бесплатны и не
  блокируются отсутствием доната.

---

## БЛОК 1 — Зарники: покупка за Stars + обмен + донат-магазин

**Зависимости:** нет (фундамент). От него зависят Блок 2 и Блок 5 (тратят ✨).
**Текущее состояние**: валюта/баланс/аудит/отображение/трата на 9 тем — готовы
(`users.user_balance_zarniki`, `wallet_log.delta_zarniki`). Не хватает: покупки,
обмена, доп. предметов магазина.

### 1.1 Константы — `core/constants.py`
Новая секция после блока "Exchange Event" (~строка 330, рядом с
`EXCHANGE_RATE_MORA_PER_DIAMOND`):
```python
# ── Зарники: донат-экономика ─────────────────────────────────────
ZARNIKI_PER_STAR: int = 10              # 1⭐ = 10✨

STARS_PACKAGES: list[tuple[int, int]] = [
    (20, 200), (50, 500), (100, 1000),
    (200, 2000), (300, 3000), (400, 4000),
]  # (stars, zarniki); произвольная сумма = stars × ZARNIKI_PER_STAR

ZARNIKI_TO_MORA_RATE: float = 3.0       # 1✨ = 3🪙
ZARNIKI_TO_DIAMONDS_RATE: float = 0.05  # 1✨ = 0.05💎 (20✨ = 1💎)
```

### 1.2 Покупка ✨ за Telegram Stars (XTR)
**Новый файл `bot/handlers/payments.py`**, регистрируется в `bot/__main__.py`
рядом с остальными роутерами (как `economy.py`).

- `cmd_buy_zarniki` (`"бот купить зарники"` / `"бот донат"`) — инлайн-клавиатура:
  6 кнопок пакетов (`"20⭐ → 200✨"` … `"400⭐ → 4000✨"`) + кнопка `"✏️ Своя сумма"`.
- `cb_buy_package(callback)` — на нажатие пакета:
  ```python
  await bot.send_invoice(
      chat_id=callback.from_user.id,
      title="Зарники ✨",
      description=f"{zarniki}✨ Зарников",
      payload=f"zarniki:{zarniki}",
      currency="XTR",
      prices=[LabeledPrice(label=f"{zarniki}✨", amount=stars)],
  )
  ```
  Для `XTR` `amount` = целое число звёзд напрямую (не ×100, в отличие от фиатных валют).
- `"✏️ Своя сумма"` — research подтвердил: FSM (aiogram States) в проекте НЕ
  встречен → без FSM. Бот отвечает `"Ответьте на это сообщение количеством ⭐
  (1-100000)"`; новый хэндлер с фильтром `F.reply_to_message`, сверяет текст
  родительского сообщения с маркером → парсит число → `send_invoice` с
  `payload=f"zarniki:{stars*ZARNIKI_PER_STAR}"`, `amount=stars`.
  *(Если при реализации найдётся FSM в другом хэндлере — использовать его
  вместо reply-маркера.)*
- `@router.pre_checkout_query()` — обязателен, ответ `ok=True` за <10с
  (внешних проверок нет, отказ только при невалидном payload).
- `@router.message(F.successful_payment)`:
  ```python
  payload = message.successful_payment.invoice_payload  # "zarniki:N"
  amount = int(payload.split(":")[1])
  await economy.add_balance(db, user_id, zarniki=amount, source="stars_purchase",
                             note=f"{message.successful_payment.total_amount}⭐")
  await message.answer(f"✅ Начислено {amount}✨ Зарников!")
  ```
  Без возвратов — `refundStarPayment` не реализуем (зафиксировано в FUTURE_IDEAS).

### 1.3 Обмен ✨ → 🪙/💎
**Новая функция `infrastructure/repositories/economy.py`** (рядом с `add_balance`,
переиспользует тот же `log_wallet`):
```python
async def exchange_zarniki(
    db: PGAdapter, user_id: int, amount: float, to: str,
    chat_id: int | None = None,
) -> tuple[bool, str]:
    """✨ → 🪙 (×ZARNIKI_TO_MORA_RATE) или ✨ → 💎 (×ZARNIKI_TO_DIAMONDS_RATE).
    Одностороннее, без лимита (РЕШЕНО в FUTURE_IDEAS)."""
    if amount <= 0 or to not in ("mora", "diamonds"):
        return False, "Некорректные параметры обмена."
    row = await db.fetchrow(
        "SELECT user_balance_zarniki FROM users WHERE user_tg_id = $1", user_id)
    current = float((row and row["user_balance_zarniki"]) or 0)
    if current < amount:
        return False, f"Недостаточно ✨ (есть {current:.0f})."
    if to == "mora":
        gained = amount * ZARNIKI_TO_MORA_RATE
        await add_balance(db, user_id, mora=gained, zarniki=-amount,
                           source="zarniki_exchange", chat_id=chat_id,
                           note=f"✨{amount:.0f}→🪙{gained:.0f}")
        return True, f"✅ Обменяно ✨{amount:.0f} → 🪙{gained:.0f}"
    gained = amount * ZARNIKI_TO_DIAMONDS_RATE
    await add_balance(db, user_id, diamonds=gained, zarniki=-amount,
                       source="zarniki_exchange", chat_id=chat_id,
                       note=f"✨{amount:.0f}→💎{gained:.2f}")
    return True, f"✅ Обменяно ✨{amount:.0f} → 💎{gained:.2f}"
```
Одна запись в `wallet_log` с обеими дельтами сразу — `add_balance`/`log_wallet`
это уже умеют (`delta_zarniki` + `delta_mora`/`delta_diamonds` в одной строке).

**Бот**: команда `"бот обмен <сумма> мора"` / `"бот обмен <сумма> алмазы"` в
`bot/handlers/economy.py`, рядом с местом, где уже читается
`zarniki = float(balance.get('user_balance_zarniki', 0))`.

**Сайт**: новый эндпоинт `POST /wallet/exchange-zarniki {amount, to}` в
`FastAPI/routers/wallet.py` → вызывает `exchange_zarniki`. UI — кнопка
"🔄 Обменять" рядом с отображением ✨ на карточке профиля (`app.js` около
строки 197, где сейчас `${Math.floor(d.zarniki||0)}`), открывает мини-форму
(число + переключатель 🪙/💎).

### 1.4 Донат-магазин (новая категория предметов)
**`core/registry.py`** — добавить в `ITEMS_REGISTRY` записи с
`category: "donate"` и полем `price_zarniki`. По принципам "Стратегии
монетизации" (удобство, не P2W) — кандидаты на базе УЖЕ существующих
механик:

| id | Название | Эффект | price_zarniki |
|---|---|---|---|
| `zarniki_fatigue_reset` | ✨ Эликсир бодрости | мгновенно `fatigue → 0` у одного питомца | 30 |
| `zarniki_cooldown_skip` | ✨ Кристалл времени | обнуляет `wolf_cooldown_until` (зоопарк) | 50 |
| `zarniki_nickname_token` | ✨ Жетон смены ника | +1 к месячному лимиту смены ника (Блок 4) | 20 |

> **Уточнить при реализации блока**: финальный список/эффекты — опционально
> добавить ещё 1-2 позиции. `zarniki_cooldown_skip` пока нацелен на
> `wolf_cooldown_until` (единственный явный таймер в `user_zoo_stats`) —
> расширение на крафт/вылупление можно добавить позже без изменения схемы.

Покупка — расширить `infrastructure/repositories/economy.py::buy_item()`
опциональным параметром `p_zarniki: float = 0` (по аналогии с `p_mora`/`p_dia`),
списывающим `zarniki` через тот же `add_balance`. Витрина — новая под-вкладка
"✨ Донат" в существующем разделе "Магазин" (`app.js`, рядом с
`gacha`/`dark`-вкладками, которые уже строятся из `SRC`/`ITEMS_REGISTRY`).

### 1.5 `app.js:1733` — активация `SRC.zarniki`
Сейчас: `zarniki: {label:'Зарники ✨', desc:'...', action:null}`.
По образцу `dark` (line 1732, `action:{l:'🌑 Открыть Тёмную Мору',
f:"goTo('market','dark')"}`):
```javascript
zarniki: {label:'Зарники ✨', desc:'Приобретается за донат-валюту Зарники (Telegram Stars). 1 Звезда = 10 Зарников.',
          action:{l:'✨ Купить Зарники', f:"openTelegramLink('https://t.me/IIIPredvestnikIIIBot?start=buyzarniki')"}}
```
`openTelegramLink` — стандартный метод Telegram WebApp API (открывает чат с
ботом). Глубокая ссылка `?start=buyzarniki` → существующий `/start`-хэндлер
(`bot/handlers/common.py`) получает новую ветку: при `start_param ==
"buyzarniki"` сразу вызывать `cmd_buy_zarniki` (показать пакеты) — без
дополнительного клика "напишите /купить_зарники".

---

## БЛОК 2 — VIP-подписка: ядро

**Зависимости:** Блок 1 (тратит ✨). От Блока 2 зависят 3, 4, 5.

### 2.1 Таблица `vip_subscriptions`
В `bot/core/database.py::init_db()`, рядом с другими `CREATE TABLE IF NOT
EXISTS` (тот же идемпотентный приём, что и для существующих таблиц):
```sql
CREATE TABLE IF NOT EXISTS predvestnik.vip_subscriptions (
    user_id          BIGINT PRIMARY KEY REFERENCES predvestnik.users(user_tg_id),
    tier             TEXT NOT NULL,              -- '1m' | '3m' | '8m' | '12m'
    started_at       TIMESTAMP DEFAULT NOW(),
    expires_at       TIMESTAMP NOT NULL,
    last_probnik_at  TIMESTAMP DEFAULT NULL,
    expiry_notified  BOOLEAN DEFAULT FALSE
);
```
Один пользователь — одна строка (продление/смена тарифа = `UPDATE`; история
покупок не требуется по ТЗ — при необходимости видна через `wallet_log`,
`source='vip_purchase'`).

### 2.2 Тарифы — `core/registry.py`
Рядом с `ACHIEVEMENT_LEVEL_REWARDS` (тот же стиль "id → параметры/награды",
все значения — из таблицы тарифов FUTURE_IDEAS.md, раздел "Тарифы — РЕШЕНО"):
```python
VIP_TIERS: dict[str, dict] = {
    "1m": {
        "label": "VIP-1М", "duration_days": 30, "price_zarniki": 150,
        "gift": {"mora": 200, "diamonds": 1,
                 "items": (("spin_token_novice", 2), ("food_basic", 1))},
        "weekly": (("spin_token_novice", 1),),
        "extra_slot": False,
    },
    "3m": {
        "label": "VIP-3М", "duration_days": 90, "price_zarniki": 400,
        "gift": {"mora": 300, "diamonds": 2,
                 "items": (("spin_token_novice", 1), ("spin_token_standard", 1), ("food_basic", 5))},
        "weekly": (("spin_token_novice", 2),),
        "extra_slot": True,
    },
    "8m": {
        "label": "VIP-8М", "duration_days": 240, "price_zarniki": 1000,
        "gift": {"mora": 500, "diamonds": 5,
                 "items": (("spin_token_premium", 2), ("spin_token_diamond", 1), ("food_basic", 5))},
        "weekly": (("spin_token_novice", 1), ("spin_token_standard", 1)),
        "extra_slot": True,
    },
    "12m": {
        "label": "VIP-12М", "duration_days": 365, "price_zarniki": 1600,
        "gift": {"mora": 500, "diamonds": 10,
                 "items": (("spin_token_diamond", 3), ("spin_token_premium", 3),
                           ("spin_token_standard", 3), ("spin_token_novice", 5),
                           ("food_basic", 15), ("soul_shard", 5), ("exp_boost_2h", 4))},
        "weekly": (("spin_token_novice", 1),),
        "extra_slot": True,
    },
}
```

### 2.3 `services/vip.py` (новый, без `bot.*`/`FastAPI.*`)
```python
async def is_vip_active(db, user_id: int) -> bool: ...

async def get_vip_info(db, user_id: int) -> dict | None:
    """{'tier','tier_label','expires_at','days_left'} либо None."""

async def purchase_vip(db, user_id: int, tier: str, chat_id=None) -> tuple[bool, str]:
    """
    1. Проверка ✨-баланса (price_zarniki тарифа).
    2. add_balance(db, user_id, zarniki=-price, source="vip_purchase", note=tier)
    3. UPSERT vip_subscriptions:
       - новой подписки нет / истекла → started_at=NOW(), expires_at=NOW()+duration
       - активна → expires_at += duration (стек поверх остатка — "докупил")
       - tier обновляется на новый В ЛЮБОМ случае (апгрейд действует сразу),
         expiry_notified сбрасывается в FALSE
    4. Разовый подарок (gift) — НАВСЕГДА, при КАЖДОЙ покупке любого тарифа:
       mora/diamonds через add_balance(source="vip_gift"),
       items — тем же путём, что и награды ачивок (инвентарный репозиторий).
    """

async def get_extra_pet_slots(db, user_id: int) -> int:
    """0 или 1 — для Блока 4 (+1 слот питомника, тарифы с extra_slot=True)."""
```
`purchase_vip` переиспользует ровно те примитивы, что уже использует выдача
наград ачивок (`ACHIEVEMENT_LEVEL_REWARDS` → `add_balance` + инвентарь) —
никакой новой инфраструктуры начисления не требуется.

> **Решение по апгрейду/стеку зафиксировано здесь** (в FUTURE_IDEAS не было
> явного пункта про "купил VIP, имея активный VIP") — стек длительности +
> мгновенная смена тарифа + повторная выдача gift при каждой покупке
> логично следует из пункта 6 ("при оформлении ЛЮБОГО тарифа") и
> отсутствия отдельного "апгрейда". Если при реализации захочется иначе —
> меняется только шаг 3 в `purchase_vip`.

### 2.4 Бот: `bot/handlers/vip.py` (новый)
- `"бот vip"` / `"бот вип"` — статус: если активна — тариф + дата истечения
  + дней осталось; если нет — список тарифов с ценами и кратким описанием
  плюшек, инлайн-кнопки "Купить VIP-1М" … "VIP-12М".
- `cb_vip_buy(callback)` — вызывает `purchase_vip`, показывает результат
  (включая список выданных предметов из `gift`).

### 2.5 Сайт: `FastAPI/routers/vip.py` (новый) + вкладка "👑 VIP"
- `GET /vip/status` → `{active, tier, tier_label, expires_at, days_left,
  tiers: [...]}` (список тарифов из `VIP_TIERS` для отображения, даже если
  не активен).
- `POST /vip/purchase {tier}` → вызывает тот же `purchase_vip` (общая логика
  бот/сайт — единая точка истины).
- `app.js` — новая вкладка по аналогии с существующими разделами магазина:
  4 карточки тарифов (цена/подарок/пробники/доп.слот), кнопка "Купить" →
  `POST /vip/purchase`.

## БЛОК 3 — VIP-бейдж везде (~45 точек)

**Зависимости:** Блок 2 (`is_vip_active()`).
**Принцип**: бейдж = `👑 ` перед именем. Источник истины для самой "формулы"
бейджа — `services/profile_render.py::format_display_name()`. Бот получает
бейдж АВТОМАТИЧЕСКИ через уже существующий `resolve_display_name()` (одна
точка правки, ~0 новых call-sites); сайт — через новое поле `is_vip` в JSON +
JS-хелпер `vipName()`.

### 3.1 `services/profile_render.py` (новый файл, без `bot.*`/`FastAPI.*`)
```python
def format_display_name(name: str, is_vip: bool) -> str:
    """Единственное место, определяющее как выглядит VIP-бейдж."""
    return f"👑 {name}" if is_vip else name
```

### 3.2 Бот — расширение `resolve_display_name()` (`services/utils.py:35`)
```python
async def resolve_display_name(db, user_id, chat_id, fallback) -> str:
    from infrastructure.repositories.users import get_nickname
    from services.vip import is_vip_active
    from services.profile_render import format_display_name
    nick = await get_nickname(db, user_id, chat_id)
    name = safe_html(nick if nick else fallback)
    return format_display_name(name, await is_vip_active(db, user_id))
```
Эффект: КАЖДЫЙ существующий вызов `resolve_display_name(...)` в проекте
автоматически начинает показывать бейдж — без правки самих call-sites.
Подтверждённый автоматический бенефициар: `marriage.py:36` (`initiator_name`).

#### 3.2.1 Дедуп `duel.py::_get_name` (строки 24-26)
Тело `_get_name` дословно повторяет `resolve_display_name`. Удалить функцию,
заменить 4 вызова (строки 123, 124, 175, 176) на прямой
`resolve_display_name(db, ...)`. Результат: `duel.py:136,205` (вызов и
объявление победителя) получают бейдж бесплатно, плюс минус один дублирующий
хелпер (DRY).

### 3.3 Бот — места, где имя приходит МИМО `resolve_display_name`
`resolve_target()` (`services/utils.py:48`) возвращает СЫРОЕ имя
(`first_name`/`username`, без nickname-резолва и без `safe_html`!) — там, где
это сырое имя идёт прямо в `target_link`, нужно явно обернуть:

| Файл:строка | Сейчас | Стало |
|---|---|---|
| `marriage.py:50,82` | `target_name` из `resolve_target()` → прямо в `target_link` | `target_name = await resolve_display_name(db, target_id, chat_id, target_name)` перед сборкой `target_link` — заодно чинит отсутствующий `safe_html` |
| `moderation.py:80,100` | то же (`target_name` сырой) | то же оборачивание перед `target_link` |
| `bot/handlers/profile.py:58` | `p_name = marriage["user1_name"/"user2_name"]` (сырой username из SQL) | `p_name = await resolve_display_name(db, partner_id, message.chat.id, p_name)` |

### 3.4 Бот — `stats.py` лидерборд: без N+1
`stats.py:116-118` строит имя инлайн (`safe_html(user["user_tg_username"] or
...)`), БЕЗ вызова `resolve_display_name` — и это правильно, потому что
леадерборд рендерит до ~20 строк за раз, а `resolve_display_name` делает 2
запроса (nickname + VIP) НА КАЖДОЕ имя. Вместо этого — один `LEFT JOIN` на всю
выборку:
```sql
LEFT JOIN predvestnik.vip_subscriptions v
  ON v.user_id = u.user_tg_id AND v.expires_at > NOW()
-- SELECT ... , (v.user_id IS NOT NULL) AS is_vip
```
```python
name = format_display_name(
    safe_html(user["user_tg_username"] or f"Пользователь {user['user_tg_id']}"),
    user["is_vip"],
)
```
Этот же "VIP-JOIN" паттерн (`LEFT JOIN ... vip_subscriptions ... expires_at >
NOW()` → булево `is_vip`) переиспользуется ниже для сайта (3.6) — таким
образом `format_display_name()` вызывается ДВУМЯ способами: (а) через
`resolve_display_name` (одиночные имена, есть лишний запрос — не страшно),
(б) напрямую с `is_vip` из JOIN (списки, без лишних запросов).

### 3.5 Бот — оставшиеся точки из FUTURE_IDEAS (рефактор "найти имя → обернуть/завести на `resolve_display_name`")
Не покрыты текущим ресёрчем построчно — единообразный паттерн, применяется
по аналогии с 3.2/3.3:
- `bot/handlers/identity.py` — собственный/чужой профиль, шаринг-анкета.
- `bot/handlers/warps.py` — упоминания актора/цели в варп-ответах (не путать
  с Блоком 4.2 — там доп. ФРАЗЫ для VIP, здесь — бейдж к ИМЕНИ в любом варпе).
- `bot/handlers/events.py` — вход/выход/приветствие участника чата.

### 3.6 Сайт — backend: VIP-JOIN в JSON-эндпоинтах
Тот же паттерн, что в 3.4 (`LEFT JOIN predvestnik.vip_subscriptions v ON
v.user_id = <id> AND v.expires_at > NOW()` → `(v.user_id IS NOT NULL) AS
is_vip`):

| Роутер:строка | id для JOIN | Новое поле в JSON |
|---|---|---|
| `profile.py:25,75` (свой профиль) | `user_id` | `"is_vip"` в return dict (~строка 85) |
| `duels.py:17,34` (`/active` и `/history`, ×2 джойна) | `uc.user_tg_id` / `ud.user_tg_id` | `challenger_is_vip`, `challenged_is_vip` |
| `auction.py:29` (`/lots`) | `u.user_tg_id` (seller) | `seller_is_vip` |
| `marriage.py:94` (`/proposals`) | proposer id | `proposer_is_vip` |
| `marriage.py:23,54` (`/`) | partner id | `partner_is_vip` |
| `top.py:14` (`/local`, `/global`) | `r["user_tg_id"]` | `is_vip` |
| `admin.py` (список участников + журнал модерации → `app.js:2875,3087,3114`) | соответствующий `user_tg_id` | `is_vip` — конкретные SELECT'ы найти при реализации (не покрыты ресёрчем) |

### 3.7 Сайт — `app.js`: хелпер + точки рендера
Хелпер — рядом с другими общими функциями (после `let/const`-блока — TDZ):
```javascript
function vipName(name, isVip) {
  return isVip ? `👑 ${name}` : name;
}
```

| Строка | Было | Стало |
|---|---|---|
| 187 | `` @${d.username\|\|'Игрок'} `` | `` @${vipName(d.username\|\|'Игрок', d.is_vip)} `` |
| 1259 | `` ${d.challenger_name\|\|'Игрок'} `` | `` ${vipName(d.challenger_name\|\|'Игрок', d.challenger_is_vip)} `` |
| 1274 | `` ${d.challenged_name\|\|'Игрок'} `` | `` ${vipName(d.challenged_name\|\|'Игрок', d.challenged_is_vip)} `` |
| ~1287/1292 | `` vs ${vs\|\|'Игрок'} `` (история дуэлей) | то же через `vipName`; источник `is_vip` для `vs` — уточнить при реализации (вероятно тот же `challenger/challenged_is_vip`, в зависимости от того, кто `vs`) |
| 2050 | `` ${r.username} `` | `` ${vipName(r.username, r.is_vip)} `` |
| 2274 | `` 👤 ${l.seller_name\|\|'Игрок'} `` | `` 👤 ${vipName(l.seller_name\|\|'Игрок', l.seller_is_vip)} `` |
| 2356 | `` @${p.proposer_name\|\|'ID'+p.proposer_id} `` | `` @${vipName(p.proposer_name\|\|'ID'+p.proposer_id, p.proposer_is_vip)} `` |
| 2383 | `` ${m.partner_name\|\|'Партнёр'} `` | `` ${vipName(m.partner_name\|\|'Партнёр', m.partner_is_vip)} `` |
| 2875, 3087, 3114 | `` @${u.user_tg_username\|\|...} `` / `` @${l.target_name\|\|...} `` | то же через `vipName(..., u.is_vip / l.is_vip)` — поле `is_vip` из 3.6 (`admin.py`) |

> После правки — обязательно `node --check FastAPI/static/app.js` (правило проекта).

---

## БЛОК 4 — VIP-плюшки (4 независимые подсистемы)

**Зависимости:** Блок 2. Каждая из 4.1-4.5 самодостаточна — можно делать по
одной или все разом.

### 4.1 Лимит смены ника — 5/мес/чат, VIP = безлимит
Новые колонки в `user_chat_stats` (PK уже `(user_tg_id, chat_tg_id)` — ровно
та гранулярность, что нужна для "локально на чат"):
```sql
ALTER TABLE predvestnik.user_chat_stats
  ADD COLUMN IF NOT EXISTS nickname_changes_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS nickname_changes_reset_at TIMESTAMP DEFAULT NOW();
```
(`bot/core/database.py::init_db()`, рядом с `CREATE TABLE user_chat_stats`;
`ADD COLUMN IF NOT EXISTS` идемпотентно и безопасно для существующих строк).

`bot/handlers/nicknames.py`, перед вызовом `set_nickname()`:
```python
from services.vip import is_vip_active
from core.constants import NICKNAME_FREE_CHANGES_PER_MONTH

if not await is_vip_active(db, user_id):
    row = await db.fetchrow(
        "SELECT nickname_changes_count, nickname_changes_reset_at "
        "FROM user_chat_stats WHERE user_tg_id=$1 AND chat_tg_id=$2",
        user_id, chat_id)
    count = row["nickname_changes_count"] if row else 0
    reset_at = row["nickname_changes_reset_at"] if row else now
    if (now.year, now.month) != (reset_at.year, reset_at.month):
        count = 0  # новый календарный месяц — сброс
    if count >= NICKNAME_FREE_CHANGES_PER_MONTH:
        await message.answer(
            "❌ Лимит смены ника исчерпан (5/мес в этом чате). "
            "Сброс в начале следующего месяца.\n"
            "Хочешь менять ник без ограничений? Оформи VIP ✨ — «бот вип»")
        return
    await db.execute(
        "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, nickname_changes_count, nickname_changes_reset_at) "
        "VALUES ($1,$2,$3,$4) ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE "
        "SET nickname_changes_count=$3, nickname_changes_reset_at=$4",
        user_id, chat_id, count + 1, now)
```
Сброс по календарному месяцу — выбран как "проще в реализации" вариант из
двух, предложенных в FUTURE_IDEAS. Новая константа:
```python
# core/constants.py
NICKNAME_FREE_CHANGES_PER_MONTH: int = 5
```
`zarniki_nickname_token` (Блок 1.4): при `count >= LIMIT` и наличии токена в
инвентаре — списать 1 токен, пропустить отказ БЕЗ инкремента `count` (токен
даёт ровно одну "внеплановую" смену, не сдвигает лимит на будущее).

### 4.2 Варпы — `responses_vip` (доп. фразы, не новые команды)
`core/warp_responses.py`: добавить опциональный ключ `responses_vip:
list[str]` в записи `ALL_WARP_COMMANDS` — точечно, не для всех варпов сразу
(можно начать с нескольких популярных и расширять).

`bot/handlers/warps.py:98`:
```python
# было:
template = random.choice(responses)
# стало:
pool = responses
if warp_data.get("responses_vip") and await is_vip_active(db, user_id):
    pool = responses + warp_data["responses_vip"]
template = random.choice(pool)
```
VIP-фразы ДОБАВЛЯЮТСЯ к общему пулу (больше разнообразия для VIP), не
заменяют обычные — соответствует принципу "косметика, не P2W". Точные имена
переменных в области видимости строки 98 (`warp_data`/`responses`/`db`/
`user_id`) — свериться при реализации.

> Не путать с Блоком 3.5 (`warps.py`) — там бейдж 👑 к ИМЕНИ актора/цели в
> варп-ответе, здесь — доп. варианты ТЕКСТА самого ответа.

### 4.3 +1 слот питомника (тарифы ≥3 мес, read-time бонус)
`get_extra_pet_slots()` уже спроектирован в Блоке 2.3:
```python
async def get_extra_pet_slots(db, user_id: int) -> int:
    info = await get_vip_info(db, user_id)
    if info and VIP_TIERS[info["tier"]]["extra_slot"]:
        return 1
    return 0
```
Применяется ТОЛЬКО в проверках вместимости (НЕ меняет хранимый `max_slots` —
`expand_max_slots()`/cap=6 остаются отдельной независимой механикой
"Расширителя слота"):
- `FastAPI/routers/zoo.py:312`: `if occupied >= stats["max_slots"] +
  await get_extra_pet_slots(db, user["id"]):`
- `bot/handlers/zoo.py:448`: аналогично.

Сообщения об ошибке (`zoo.py:315-317`, `bot/zoo.py:451`) — обновить
отображаемое число слотов на `stats['max_slots'] + extra`, чтобы игрок видел
реальный текущий лимит (с учётом VIP).

### 4.4 Еженедельные пробники (`VIP_TIERS[tier]["weekly"]`)
`services/scheduler.py` — новая ветка по образцу существующей еженедельной
(Mon 00:00, ~строка 311 в `duel_and_auction_task`):
```python
if now.weekday() == 0 and now.hour == 0 and now.minute == 0:
    rows = await db.fetch(
        "SELECT user_id, tier FROM predvestnik.vip_subscriptions WHERE expires_at > NOW()")
    for r in rows:
        for item_id, qty in VIP_TIERS[r["tier"]]["weekly"]:
            # тем же способом, что выдача gift.items в Блоке 2.3
            await <инвентарный репозиторий>.add_item(db, r["user_id"], item_id, qty)
        await bot.send_message(r["user_id"], "🎁 Еженедельный VIP-бонус начислен! Загляни в инвентарь.")
```
Размещение — либо новый `asyncio.create_task(...)` в `bot/__main__.py` рядом
со строкой 144 (как `duel_and_auction_task`), либо (предпочтительнее, чтобы
не плодить лишний `while True: sleep(60)`) — добавить веткой в УЖЕ
существующую еженедельную проверку `duel_and_auction_task` на строке ~311.
Решить при реализации.

### 4.5 Напоминание об истечении подписки
В той же еженедельной/минутной задаче — проверка `expiry_notified=FALSE`
(защита от повторной отправки):
```python
soon = await db.fetch(
    "SELECT user_id, tier, expires_at FROM predvestnik.vip_subscriptions "
    "WHERE expires_at BETWEEN NOW() AND NOW() + INTERVAL '3 days' AND expiry_notified = FALSE")
for r in soon:
    await bot.send_message(r["user_id"],
        f"⏳ Твой VIP-{VIP_TIERS[r['tier']]['label']} истекает "
        f"{r['expires_at']:%d.%m}. Продлить — «бот вип».")
    await db.execute(
        "UPDATE predvestnik.vip_subscriptions SET expiry_notified=TRUE WHERE user_id=$1",
        r["user_id"])
```
Окно "3 дня" — новая константа `VIP_EXPIRY_REMINDER_DAYS: int = 3`
(`core/constants.py`), легко поменять. При продлении/покупке (`purchase_vip`,
Блок 2.3) `expiry_notified` уже сбрасывается в `FALSE` — следующее истечение
снова даст уведомление.

## БЛОК 5 — Боевой пропуск (Battle Pass)

**Зависимости:** Блок 2 (платный трек = `is_vip_active()`).

### 5.1 Таблица `battle_pass_progress`
```sql
CREATE TABLE IF NOT EXISTS predvestnik.battle_pass_progress (
    user_id              BIGINT NOT NULL REFERENCES predvestnik.users(user_tg_id),
    season_id            TEXT NOT NULL,
    xp                   INTEGER DEFAULT 0,
    level                INTEGER DEFAULT 1,
    claimed_free_levels  INTEGER[] DEFAULT '{}',
    claimed_paid_levels  INTEGER[] DEFAULT '{}',
    PRIMARY KEY (user_id, season_id)
);
```
`INTEGER[]` — нативный тип Postgres/asyncpg: `claimed_free_levels @>
ARRAY[N]` для проверки, `array_append(...)` для добавления. Если при
реализации `?`→`$N`-обёртка PGAdapter окажется неудобной с массивами —
fallback: `TEXT` c CSV (`"1,2,5"`) и парсинг в Python; деталь хранения, не
меняет остальной дизайн.

### 5.2 Сезоны и награды — `core/registry.py`
По аналогии с `ACHIEVEMENT_LEVEL_REWARDS` (`Dict[int, {"mora","diamonds","items"}]`),
но с разделением на бесплатный/платный трек:
```python
BATTLE_PASS_SEASONS: dict[str, dict] = {
    "s1": {
        "label": "Сезон 1",
        "starts_at": "2026-07-01",
        "ends_at": "2026-08-10",   # +40 дней
        "max_level": 50,
    },
}

BATTLE_PASS_REWARDS: dict[int, dict] = {
    1:  {"free": {"mora": 50,  "diamonds": 0,  "items": ()},
         "paid": {"mora": 0,   "diamonds": 1,  "items": (("spin_token_novice", 1),)}},
    2:  {"free": {"mora": 0,   "diamonds": 0,  "items": (("food_basic", 1),)},
         "paid": {"mora": 0,   "diamonds": 1,  "items": ()}},
    # ... 3-49 — числа подбираются при балансировке (FUTURE_IDEAS: "невысокие,
    # но не слишком низкие" XP-веса и награды)
    50: {"free": {"mora": 500, "diamonds": 0,  "items": (("spin_token_standard", 2),)},
         "paid": {"mora": 0,   "diamonds": 10, "items": (("spin_token_diamond", 1),)}},
}
```
> Полная таблица 1-50 — вне рамок планирования (явно отмечено в FUTURE_IDEAS
> как "подбирается при балансировке"). Формат записи финален — заполняется
> построчно при реализации по образцу выше.

> **Идея на будущее** (FUTURE_IDEAS п.4): сезонные темы (`core/themes.py`,
> `rarity:"seasonal"`) как награда верхних уровней платного трека — ЕСЛИ
> владение темой хранится в общей инвентарной таблице по id `theme_*` (как
> остальные 9 Zarniki-тем, см. коммит "тематический рендер для всех 9 Premium
> Zarniki-тем") — это просто ещё один элемент в `"items"`, отдельной механики
> не требуется. Проверить механизм владения темами при реализации.

### 5.3 Константы — `core/constants.py`
```python
BATTLE_PASS_XP_PER_LEVEL: int = 100   # линейная шкала; подбирается при балансировке
BATTLE_PASS_MAX_LEVEL: int = 50

BATTLE_PASS_XP_WEIGHTS: dict[str, int] = {
    # metric_name (как в ACHIEVEMENTS registry) -> XP за единицу
    "duels_won": 10,
    "eggs_hatched": 5,
    "expeditions_completed": 8,
    "crafts_completed": 5,
    "daily_quests_completed": 15,
    # ... остальные релевантные метрики — свериться со списком в registry при реализации
}
```

### 5.4 `services/battle_pass.py` (новый, без `bot.*`/`FastAPI.*`)
```python
def get_active_season() -> dict | None:
    """Текущий сезон по дате (BATTLE_PASS_SEASONS), либо None между сезонами."""

async def add_xp(db, user_id: int, metric_name: str, delta: float = 1.0) -> None:
    """
    weight = BATTLE_PASS_XP_WEIGHTS.get(metric_name)
    if not weight or not get_active_season(): return
    UPSERT battle_pass_progress: xp += weight*delta,
    level = min(MAX_LEVEL, 1 + xp // XP_PER_LEVEL)
    """

async def get_progress(db, user_id: int) -> dict | None:
    """
    None если сейчас нет активного сезона. Иначе:
    {'season','level','xp','xp_to_next','max_level',
     'claimed_free','claimed_paid','paid_track_open': await is_vip_active(db,user_id)}
    """

async def claim_reward(db, user_id: int, level: int, track: str) -> tuple[bool, str]:
    """
    track: 'free' | 'paid'.
    - level <= progress.level (достигнут) и level <= max_level
    - level not in claimed_<track>_levels
    - track == 'paid' -> require is_vip_active(db, user_id); иначе
      "🔒 Нужен активный VIP, чтобы забрать награду платного трека."
    - выдать BATTLE_PASS_REWARDS[level][track] (mora/diamonds через add_balance,
      items — тем же путём, что gift в Блоке 2.3/награды ачивок)
    - append level в claimed_<track>_levels (array_append)
    """
```

**Важно (РЕШЕНО в FUTURE_IDEAS)**: при истечении VIP посреди сезона —
`claimed_paid_levels`/`level`/`xp` НЕ откатываются и НЕ сбрасываются. Просто
`paid_track_open=False` → `claim_reward(track='paid')` отказывает для НОВЫХ
запросов, а уже полученные награды остаются полученными. При новой
покупке/продлении VIP — `paid_track_open` снова `True`, и все уровни
`<= progress.level`, которых нет в `claimed_paid_levels` (включая
достигнутые ВО ВРЕМЯ паузы VIP), становятся доступны для `claim`. Отдельной
логики "разморозки" не требуется — это естественное следствие независимости
`claimed_paid_levels`/`level` от `is_vip_active()`.

### 5.5 XP-хук — ОДНА точка интеграции
`services/achievements.py::increment_metric()` — добавить в конец тела:
```python
async def increment_metric(db, user_id, metric_name, delta=1.0, chat_id=None):
    ... существующая логика ачивок ...
    if metric_name in BATTLE_PASS_XP_WEIGHTS:
        from services.battle_pass import add_xp
        await add_xp(db, user_id, metric_name, delta)
    return ...
```
Эффект: КАЖДЫЙ существующий вызов `achievements.increment_metric(db, uid,
METRIC_NAME)` по всему проекту (десятки точек — дуэли/экспедиции/гача/крафт и
т.д.) автоматически начисляет XP БП без правки самих call-sites — тот же
паттерн, что Блок 3.2 (`resolve_display_name`).

> **Важно**: хук добавляется ТОЛЬКО в `achievements.increment_metric`, НЕ в
> `services/quests.py::increment_metric` (другая функция с тем же именем,
> другая сигнатура) — иначе одно игровое действие, трекаемое и в ачивках, и
> в квестах под одинаковым `metric_name`, начислит XP ДВАЖДЫ. Если для
> какого-то действия из `BATTLE_PASS_XP_WEIGHTS` нет соответствующей ачивки
> (метрика существует только в `quests.py`) — варианты: (а) завести
> минимальную ачивку-трекер под эту метрику (даже без видимых наград), либо
> (б) точечный отдельный вызов `add_xp()` прямо в этом хэндлере. Свериться
> со списком метрик в `core/registry.py` (ACHIEVEMENTS) и `quests.py` при
> реализации.

### 5.6 Бот: `bot/handlers/battle_pass.py` (новый)
- `"бот бп"` / `"бот боевой пропуск"`:
  - Если `get_active_season() is None` — "Сезон скоро начнётся, следи за анонсами!"
  - Иначе: `🎫 {season.label} | Уровень {level} | {format_progress_bar(xp % XP_PER_LEVEL, XP_PER_LEVEL)}`
    — переиспользует `format_progress_bar()` из `services/formatting.py`
    (тот же хелпер, что и другие прогресс-бары проекта).
  - Список наград для уровней `level-2 .. level+3` (окно вокруг текущего, не
    все 50 сразу) с пометками: "✅ получено" / "🎁 доступно — забрать" /
    "🔒 нужен VIP" (paid, !paid_track_open) / "⏳ ещё не достигнут".
  - Инлайн-кнопки "Забрать" на доступные позиции.
- `cb_bp_claim(callback)` → `claim_reward(db, user_id, level, track)`.

### 5.7 Сайт: `FastAPI/routers/battle_pass.py` (новый) + вкладка "🎫 БП"
- `GET /battle_pass/status` → `{active: bool, season_label, level, xp,
  xp_to_next, max_level, paid_track_open, rewards: [{level, free:{...,status},
  paid:{...,status}}]}` — `status ∈ {claimed, available, locked_vip,
  locked_level}`, посчитан на бэкенде (фронту не нужно знать правила —
  только рендерить).
- `POST /battle_pass/claim {level, track}` → `claim_reward` (общая логика
  бот/сайт — единая точка истины, как и `purchase_vip` в Блоке 2).
- `app.js` — новая вкладка: прогресс-бар + список уровней в две колонки
  (Бесплатный/VIP), кнопка "Забрать" на каждой доступной ячейке.

### 5.8 Ротация сезонов
`get_active_season()` (5.4) уже ВЫЧИСЛЯЕТСЯ по датам из `BATTLE_PASS_SEASONS`
— смена сезона происходит АВТОМАТИЧЕСКИ, без участия `scheduler.py`: новая
запись в `battle_pass_progress` для нового `season_id` создаётся лениво при
первом `add_xp()` (старые записи прошлых сезонов остаются как история).
Добавление нового сезона = добавление записи в `BATTLE_PASS_SEASONS` +
`BATTLE_PASS_REWARDS` (конфигурация, без миграций).

Уведомление "сезон скоро закончится" (упомянуто в FUTURE_IDEAS как "ротация —
scheduler.py") — опционально, не блокирует основной функционал: в
существующей ежедневной задаче (`daily_deal_task`, `services/scheduler.py`)
добавить проверку — если до `ends_at` текущего сезона осталось ≤3 дня,
разослать активным игрокам (`level > 1`) одно сообщение "Сезон
заканчивается, успей забрать награды!". Строгая защита от повтора (как
`expiry_notified` в 4.5) — по желанию, не критична (1 admin-сообщение/день в
последние 3 дня — приемлемо).

## БЛОК 6 — Глобальная модерация: ядро

**Зависимости:** нет (независим от 1-5). Источник — раздел "Глобальная
система варнов и банов экосистемы бота" в FUTURE_IDEAS, почти всё там РЕШЕНО.

### 6.1 Таблицы
```sql
CREATE TABLE IF NOT EXISTS predvestnik.global_sanctions (
    id            SERIAL PRIMARY KEY,
    target_type   TEXT NOT NULL,        -- 'user' | 'chat'
    target_id     BIGINT NOT NULL,
    sanction_type TEXT NOT NULL,        -- 'warn' | 'restrict' | 'ban'
    reason        TEXT,
    issued_by     BIGINT NOT NULL,
    created_at    TIMESTAMP DEFAULT NOW(),
    expires_at    TIMESTAMP NULL,       -- NULL = бессрочно
    revoked_at    TIMESTAMP NULL,
    revoked_by    BIGINT NULL
);

CREATE TABLE IF NOT EXISTS predvestnik.sanction_appeals (
    id            SERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL,
    sanction_id   INTEGER NOT NULL REFERENCES predvestnik.global_sanctions(id),
    text          TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT NOW(),
    status        TEXT DEFAULT 'pending',  -- pending | accepted | rejected
    resolved_by   BIGINT NULL,
    resolved_at   TIMESTAMP NULL
);
```
Активна санкция, если `revoked_at IS NULL AND (expires_at IS NULL OR
expires_at > NOW())`. **Решение по "не более одной активной restrict/ban"**
(FUTURE_IDEAS оставляла открытым): при выдаче новой `restrict`/`ban` на ту же
цель — СНАЧАЛА авто-`revoke` существующей активной `restrict`/`ban`
(`revoked_by = issued_by` новой, отдельной пометки не нужно — видно по
времени), ПОТОМ `INSERT` новой. `warn` — без этого ограничения, копится
сколько угодно. Это сохраняет `global_sanctions` чисто append-only
(полный аудит) при соблюдении правила "≤1 активная restrict/ban".

### 6.2 `infrastructure/repositories/global_moderation.py` (новый)
```python
async def get_active_restriction(db, target_type: str, target_id: int) -> dict | None:
    """Активная restrict ИЛИ ban для цели (их не более одной — см. 6.1)."""

async def issue_sanction(db, target_type, target_id, sanction_type, reason,
                          issued_by, expires_at=None) -> int:
    """revoke текущей активной restrict/ban той же цели (если sanction_type
    in ('restrict','ban')), затем INSERT новой. Возвращает id."""

async def revoke_sanction(db, sanction_id: int, revoked_by: int) -> bool: ...

async def list_sanctions(db, target_type, target_id, active_only=False) -> list[dict]: ...
async def list_active(db, sanction_type: str | None = None) -> list[dict]:
    """Для сайта — 'список активных ограничений' (7.x)."""

async def get_user_chat_ids(db, user_id: int) -> list[int]:
    """SELECT DISTINCT chat_tg_id FROM user_chat_stats WHERE user_tg_id=$1 — для рассылки уведомлений."""

async def create_appeal(db, user_id, sanction_id, text) -> int: ...
async def get_active_sanction_for_user(db, user_id) -> dict | None:
    """Для 'бот апелляция' — есть ли вообще что оспаривать."""
async def list_appeals(db, status: str | None = None) -> list[dict]: ...
async def resolve_appeal(db, appeal_id, status, resolved_by) -> None: ...
```

### 6.3 `services/global_moderation.py` (новый, без `bot.*`/`FastAPI.*`)
```python
RANK_ALLOWED: dict[int, dict[str, set[str]]] = {
    1: {"user": {"warn"}},
    2: {"user": {"warn", "restrict"}, "chat": {"warn", "restrict"}},
    3: {"user": {"warn", "restrict", "ban"}, "chat": {"warn", "restrict", "ban"}},
}

def can_issue_global_sanction(actor_rank: int, target_type: str,
                               sanction_type: str, target_global_rank: int = 0) -> bool:
    if target_type == "user" and target_global_rank >= actor_rank:
        return False  # антипир: нельзя тронуть равного/старшего штата.
                       # Побочный эффект (ЖЕЛАЕМЫЙ): Разработчик (3) >= Разработчик (3)
                       # → True>=True → блок — Разработчик иммунен даже к самому себе,
                       # без отдельного спецслучая.
    return sanction_type in RANK_ALLOWED.get(actor_rank, {}).get(target_type, set())

async def is_user_banned(db, user_id) -> bool: ...
async def is_chat_banned(db, chat_id) -> bool: ...
async def get_user_restriction(db, user_id) -> dict | None:
    """Активная restrict для юзера (не ban — ban проверяется отдельно/раньше)."""
async def get_chat_restriction(db, chat_id) -> dict | None: ...

def restriction_message(restriction: dict) -> str:
    until = "навсегда" if not restriction["expires_at"] else f"до {restriction['expires_at']:%d.%m.%Y}"
    return (f"🚫 Экономические команды недоступны ({restriction['reason']}) — {until}.\n"
            f"Оспорить: «бот апелляция <текст>»")

async def issue_global_sanction(db, bot, actor_id, actor_rank, target_type, target_id,
                                 sanction_type, reason, expires_at=None) -> tuple[bool, str]:
    """can_issue_global_sanction → repo.issue_sanction → notify_sanction(action='issued')."""

async def revoke_global_sanction(db, bot, actor_id, actor_rank, sanction_id) -> tuple[bool, str]:
    """проверка прав по sanction.sanction_type/target → repo.revoke_sanction → notify(action='revoked')."""

async def notify_sanction(db, bot, target_type, target_id, sanction_type, reason, action) -> None:
    """
    action: 'issued' | 'revoked'.
    target_type=='user' → for chat_id in get_user_chat_ids(db, target_id): bot.send_message(chat_id, text)
                           (рассылка ВО ВСЕ чаты юзера — решает проблему заблокированных ЛС)
    target_type=='chat' → bot.send_message(target_id, text)
    Каждая отправка — try/except TelegramForbiddenError/TelegramBadRequest
    (бот мог быть удалён из части чатов с тех пор) — проверить при реализации,
    есть ли уже общий safe-send хелпер (например рядом с уведомлениями в
    duel_and_auction_task, scheduler.py:240-300) — переиспользовать вместо нового.
    """
```

### 6.4 Middleware `bot/middlewares/global_sanctions_mw.py` (новый)
Регистрируется В `bot/__main__.py` СРАЗУ ПОСЛЕ `db_middleware` (строки 88-92,
нужен `data["db"]`), ДО `pet_bonuses_middleware`/`streak_middleware` —
глобальный бан должен останавливать обработку раньше всего остального.
```python
class GlobalSanctionsMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        db = data["db"]
        user_id = event.from_user.id if event.from_user else None
        chat_id = getattr(event, "chat", None) and event.chat.id

        actor_rank = data.get("global_rank", 0)  # уточнить: db_middleware уже
        # пишет global_rank в data при авто-выставлении DEVELOPER_ID=3 — если
        # нет, один SELECT users.global_rank здесь.
        if actor_rank >= 3:
            return await handler(event, data)  # Разработчик — иммунитет (302)

        if chat_id and await global_moderation.is_chat_banned(db, chat_id):
            return  # бот молчит (264) — апдейт не идёт дальше
        if user_id and await global_moderation.is_user_banned(db, user_id):
            return  # бот молчит везде (264)

        if chat_id:
            data["chat_restricted"] = await global_moderation.get_chat_restriction(db, chat_id)
        if user_id:
            data["user_restricted"] = await global_moderation.get_user_restriction(db, user_id)
        return await handler(event, data)
```

### 6.5 Экономические хэндлеры — проверка `restricted`-флагов
"Экономическая часть" по таблице FUTURE_IDEAS: гача / аукцион / дуэли / обмен
/ переводы / крафт. В начале каждого такого хэндлера:
```python
restriction = data.get("user_restricted") or data.get("chat_restricted")
if restriction:
    return await message.answer(global_moderation.restriction_message(restriction))
```
Точный список файлов/функций — открытый вопрос FUTURE_IDEAS ("нужен точный
список команд/категорий"), составить при реализации; ориентир по названиям
хэндлеров: gacha-команды, `bot/handlers/economy.py` (обмен/переводы),
`bot/handlers/auction.py`, `bot/handlers/duel.py`, крафт (вероятно в
`bot/handlers/zoo.py` или отдельном craft-хэндлере). Профиль/помощь/модерация
— БЕЗ проверки (продолжают работать при `restrict`, как решено).

### 6.6 `bot/handlers/global_moderation.py` (новый) — команды РАБОТАЮТ в любом чате И в ЛС
```
бот глоб варн @user <причина>          / бот глоб снять варн <id>
бот глоб ограничить @user <причина> [срок]  / бот глоб снять ограничение @user
бот глоб бан @user <причина> [срок]    / бот глоб разбан @user      — только Разработчик
бот глоб бан чат <chat_id> <причина>   / бот глоб разбан чат <chat_id> — только Разработчик
бот глоб санкции @user                 / бот глоб санкции чат <chat_id>
бот апелляция <текст>
```
- Целеуказание — **`resolve_target(message, db, args)` уже умеет** резолвить
  `@username`/числовой ID БЕЗ привязки к чату/`reply_to_message`
  (`services/utils.py:69-89`, прямой запрос к `users`) — отдельная
  `resolve_global_target()` НЕ нужна (YAGNI), используем существующую функцию
  напрямую (она же работает и в ЛС).
- `[срок]` — переиспользовать парсер длительности из `cmd_mute`/`cmd_ban`
  (`bot/handlers/moderation.py`, формат `Nм/Nч/Nд`) — найти и применить тот же
  парсер, не писать новый.
- Каждая команда: `actor_rank = users.global_rank` юзера → если `< 1`, тихо
  игнорировать (не глобальная команда для обычных игроков) → резолв цели →
  `target_rank = users.global_rank` цели (для `target_type='chat'` — 0) →
  `can_issue_global_sanction(...)` → `issue_global_sanction`/`revoke_global_sanction`
  → ответ пользователю.
- `бот апелляция <текст>`:
  ```python
  sanction = await get_active_sanction_for_user(db, user_id)
  if not sanction:
      return await message.answer("У тебя нет активных глобальных санкций.")
  await create_appeal(db, user_id, sanction["id"], text)
  await bot.send_message(DEVELOPER_ID,
      f"📨 Апелляция от {user_id} на санкцию #{sanction['id']}:\n{text}")
  await message.answer("✅ Апелляция отправлена. Ответ придёт уведомлением.")
  ```

### 6.7 `services/roles.py` — расширение
Согласно ресёрчу `global_rank`/`GLOBAL_RANKS_MAP` УЖЕ существуют как
"косметический лейбл" — проверить при реализации, что там есть, и ДОПОЛНИТЬ
(не дублировать):
- `GLOBAL_RANKS_MAP` — подтвердить значения `{1:"Хелпер", 2:"Ст.хелпер",
  3:"Разработчик"}` соответствуют текущему реестру.
- Добавить `can_issue_global_sanction()` (6.3) — по аналогии с уже
  существующей `can_assign_local_rank()` (то же место в файле, тот же стиль).

---

## БЛОК 7 — Глобальная модерация: сайт

**Зависимости:** Блок 6.

### 7.1 `FastAPI/routers/global_admin.py` (новый), префикс `/admin/global`
Гейт по `global_rank ≥ 1` — НЕ по `local_rank` (в отличие от
`/admin/{chat_id}/...`). По аналогии с `_require_admin` в `admin.py`:
```python
async def _require_global(db, user_id: int) -> int:
    """Возвращает global_rank или 403, если < 1. DEVELOPER_ID — особый случай
    (см. 229: разработчик уже имеет global_rank=3 через db_middleware)."""
```

| Эндпоинт | Доступ | Назначение |
|---|---|---|
| `GET /admin/global/chats` | ≥1 | "Все чаты" — список ВСЕХ чатов с ботом (315) |
| `GET /admin/global/chats/{chat_id}/members` | ≥1 | участники ЛЮБОГО чата — переиспользовать список из `admin.py` (участники текущего чата), но БЕЗ требования `local_rank` к этому чату |
| `GET /admin/global/sanctions?type=&active_only=` | ≥1 | список активных ограничений (316), по чатам и по юзерам |
| `POST /admin/global/sanctions` `{target_type,target_id,sanction_type,reason,duration_days}` | по `can_issue_global_sanction` | выдать санкцию (issue_global_sanction) |
| `POST /admin/global/sanctions/{id}/revoke` | по `can_issue_global_sanction` цели | снять/изменить срок |
| `GET /admin/global/sanctions/search?target_type=&target_id=` | ≥1 | история цели: активные + снятые/истёкшие, `issued_by`/`revoked_by` (317) |
| `GET /admin/global/log?page=` | ≥1 | общий журнал всех `global_sanctions` (319) |
| `GET /admin/global/appeals?status=` | ≥1 | список апелляций (311) |
| `POST /admin/global/appeals/{id}/resolve` `{action: accept\|reject}` | accept→revoke санкции, `ban`-санкции — только Разработчик (≥3) |
| `POST /admin/global/ranks` `{user_id, global_rank}` | только Разработчик (≥3) | назначить/снять Хелпера/Ст.хелпера (321) |

Каждый ответ — флаги прав по аналогии с `admin.py` (`"can_warn":
actor_rank>=1, "can_restrict": actor_rank>=2, "can_ban": actor_rank>=3,
"can_manage_ranks": actor_rank>=3`), фронт показывает/скрывает кнопки по ним
— тот же принцип, что уже работает в `/admin/{chat_id}`.

### 7.2 `/profile/me` — добавить `global_rank`
В тот же return dict, что Блок 3.6 добавляет `is_vip` (`profile.py:73-85`):
```python
"global_rank": row["global_rank"] or 0,
```
(сырое число, а не отформатированная строка `"rank"`, которая там уже есть)
— фронт использует его, чтобы показать/скрыть пункт меню "Глобальная
модерация".

### 7.3 `app.js` — раздел "🛡 Глобальная модерация"
Виден если `profile.global_rank >= 1` (из 7.2). Вкладки:
- **Все чаты** — список чатов → клик → список участников (как в обычной
  панели чата) → клик по участнику → форма "выдать санкцию" (тип зависит от
  `can_warn`/`can_restrict`/`can_ban`).
- **Активные ограничения** — единый список restrict/ban (юзеры + чаты),
  кнопки снять/изменить срок.
- **Журнал** — лог всех `global_sanctions` (кто/кого/когда/тип/причина).
- **Апелляции** — список + "снять санкцию"/"отклонить".
- **Управление штатом** (только при `global_rank>=3`) — назначить/снять
  Хелпера/Ст.хелпера по ID.

> После правки — `node --check FastAPI/static/app.js`.

## БЛОК 8 — Доработки веб-панели администрирования чата

**Зависимости:** нет (независим от 1-7). Источник — раздел "Веб-панель
администрирования чата" в FUTURE_IDEAS: бот и сайт уже синхронизированы
напрямую через общие таблицы Postgres (без кэша), часть бот-команд просто
не имеет зеркала на сайте — "5-6 точечных доработок без архитектурных
изменений".

### 8.0 Предпосылка — Developer bypass в `_get_actor_rank`/`_require_admin`
`FastAPI/routers/admin.py:24-40`: `_get_actor_rank(db, user_id, chat_id)`
читает `user_chat_stats.local_rank` (0, если строки нет). Для
`DEVELOPER_ID` (`global_rank=3`) панель должна работать в ЛЮБОМ чате даже
БЕЗ строки `user_chat_stats` — единственный bypass в начале функции:
```python
async def _get_actor_rank(db, user_id: int, chat_id: int) -> int:
    if user_id == DEVELOPER_ID:
        return 6  # Владелец в любом чате
    ...
```
`_require_admin` менять не нужно — она просто вызывает `_get_actor_rank`.
`DEVELOPER_ID` — импорт из `core.constants` (уже задан через ENV).

`/my-chats` (admin.py:52-68) фильтрует `WHERE ucs.user_tg_id = ? AND
ucs.local_rank >= 1 AND ucs.is_left = FALSE` — для Developer этот список
будет пуст для чатов без вступления. Добавить ветку: `if user_id ==
DEVELOPER_ID:` → список ВСЕХ чатов бота (`SELECT DISTINCT chat_tg_id, ...`),
без фильтра по рангу/участию.

> Не путать с Блок 7.1 `/admin/global/chats`: та вкладка — для
> `global_rank≥1` (Хелперы/Ст.хелперы тоже) и ведёт к ГЛОБАЛЬНЫМ санкциям.
> Этот bypass — для Developer'а в ОБЫЧНОЙ локальной панели конкретного чата
> (участники/настройки/ЧС/чистка/журнал).

### 8.1 Чёрный список чата (новая вкладка)
`infrastructure/repositories/blacklist.py` уже содержит ПОЛНОЕ CRUD —
`get_chat_blacklist`, `add_to_chat_blacklist`, `remove_from_chat_blacklist`
над готовой таблицей `chat_blacklist(chat_id, user_id, reason, added_by,
added_at)`. Нужны только 3 новых эндпоинта в `admin.py`:
```python
@router.get("/{chat_id}/blacklist")        # _require_admin >= rank_ban, get_chat_blacklist
@router.post("/{chat_id}/blacklist")       # body: {user_id, reason}, anti-peer как в /action
@router.delete("/{chat_id}/blacklist/{user_id}")
```
Порог — `rank_ban` (ЧС по тяжести близок к бану). На фронте — вкладка
"Чёрный список" рядом с "Участники".

### 8.2 Управление рангами (сайт сейчас read-only)
Бот: `TextCmd(["выдать ранг","дать ранг","сет ранг","ранг"])`
(`bot/handlers/admin.py:78`) → `roles.can_assign_local_rank(...)`
(`services/roles.py:34-49`) → `chat.set_local_rank(db, target_id, chat_id,
new_rank_id)` (`bot/handlers/admin.py:158`). Те же примитивы переиспользуем:
```python
@router.post("/{chat_id}/users/{user_id}/rank")
async def admin_set_rank(chat_id, user_id, body: SetRankRequest,
                          db=Depends(get_db), user=Depends(require_tg_user)):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    target_rank = ...  # как в /action, admin.py:227-232
    ok, err = roles.can_assign_local_rank(
        user["id"], actor_rank, target_rank, body.new_rank, DEVELOPER_ID)
    if not ok:
        raise HTTPException(403, err)
    await chat.set_local_rank(db, user_id, chat_id, body.new_rank)
    await log_moderation_action(db, chat_id, user_id, user["id"], f"rank_{body.new_rank}", None)
```
В `/users` (admin.py:112-165) у каждой строки уже есть `can_act = actor_rank
> local_rank` (строка 157) — добавить `"can_set_rank": r["can_act"]` и
`"max_assignable_rank": actor_rank - 1`. Фронт — выпадающий список рангов
`0..max_assignable_rank` рядом с именем участника (подписи —
`roles.LOCAL_RANKS_MAP`, продублировать в app.js как остальные статичные
тексты).

### 8.3 5 недостающих rank_*-настроек
`bot/handlers/chat_settings.py:24-34` — полный `_RANK_SETTINGS` (9 ключей):
`rank_warn/mute/kick/ban` на сайте уже есть (`Settings`-модель,
admin.py:178-181) + **`rank_shield/immune/duel/marriage/give`**
отсутствуют. Они уже хранятся в той же `chat_settings`-таблице (раз бот их
читает/пишет) — просто добавить 5 полей в `Settings` и прокинуть в
GET/POST `/{chat_id}/settings` (169-217). Заодно добавить `purge_min_rank`
(использует `bot/handlers/purge.py:81`, задаётся командой `настройка
чистки`/`ранг чистки` — `moderation.py:373`) — десятая настройка той же
группы "пороги рангов", нужна для 8.5.

Фронт: вместо текущих 4 rank_*-полей — все 10, с подписями из
`_RANK_SETTINGS` (+ "Норма для чистки" для `purge_min_rank`). Источник
подписей — либо бэк отдаёт `{key, emoji, label}` в GET `/settings` (по
образцу `_rank_label`/`_RANK_SETTINGS`), либо продублировать в app.js
(проще, раз он classic-script без общих импортов).

### 8.4 Щит vs Иммунитет — развести механики и поправить порог
**Две РАЗНЫЕ, уже существующие в БД механики**
(`user_chat_stats.is_immune` + `.immune_until`, видно из
`purge.py:128-135`):
- **Щит** (временный) — бот: `защита`/`защитить` (`moderation.py:280`) /
  `снять защиту`/`убрать щит` (315). Ставит `immune_until` (дату), `is_immune`
  не трогает. Свой порог — `rank_shield`.
- **Иммунитет** (постоянный) — бот: `иммунитет`/`абсолют`
  (`moderation.py:242`). Ставит `is_immune=1, immune_until=NULL`. Свой порог
  — `rank_immune`.

На сайте (`admin.py:218-324`, `/action`) сейчас есть ТОЛЬКО action
`"immune"` (315-319) — фактически это реализация ЩИТА
(`set_immunity(db, chat_id, user_id, 1, until)`, `until` = +24ч по
умолчанию), но ошибочно гейтится порогом `rank_mute` (строка 241:
`"immune": "rank_mute"` — баг из FUTURE_IDEAS). Снять-щит и постоянный
иммунитет на сайте отсутствуют вовсе. Исправление — 4 action вместо 1:
```python
_required = {
    ...,
    "shield":       "rank_shield",  # = старый "immune": set_immunity(db,...,1, until=+24ч)
    "unshield":     "rank_shield",  # set_immunity(db,...,0, None)  (если is_immune не permanent)
    "set_immune":   "rank_immune",  # set_immunity(db,...,1, None)  — навсегда
    "unset_immune": "rank_immune",  # set_immunity(db,...,0, None)
}
```
(точные аргументы `set_immunity()` для permanent-варианта — сверить с
`moderation.py:242` при реализации; переименование `"immune"`→`"shield"` —
проверить, не дёргает ли фронт старое имя где-то ещё, иначе оставить
`"immune"` как алиас вместо чистки всех вызовов). На фронте — две отдельные
кнопки "🛡 Щит (24ч)" / "🔰 Иммунитет (навсегда)" + парные "Снять".

### 8.5 UI чистки (purge)
`bot/handlers/purge.py`: `чистка <DD.MM-DD.MM> <норма>` / `конец чистки`
ставят/снимают `chat_settings.is_purging`
(`mod_db.update_chat_settings(db, chat_id, is_purging=True/False)`, строки
82/231) + блокируют чат `set_chat_permissions`, затем снимают мут
участникам с `local_rank >= purge_min_rank`. Новые эндпоинты:
```python
@router.post("/{chat_id}/purge/start")   # body: {start_date, end_date, norm}
@router.post("/{chat_id}/purge/stop")
@router.get("/{chat_id}/purge/status")   # is_purging + текущие параметры
```
Логика — та же последовательность, что в `purge.py:60-219` (сбор
статистики, отчёт, "досье" нарушителей с inline-кнопками варн/кик/бан — это
ОСТАЁТСЯ в Telegram; сайт только ЗАПУСКАЕТ/ОСТАНАВЛИВАЕТ и показывает
`is_purging`). Порог — `rank_kick` (`purge.py:65` уже требует
`check_admin_rights(..., 4, ...)`, т.е. порог кика). На фронте — в
"Настройки" (или отдельный блок) "Чистка": период+норма, кнопка
Старт/Стоп + индикатор `is_purging`.

### 8.6 История банов/киков/вышедших
Бот: `баны`/`черный список`/`кто в бане` и `кики`/`выгнанные`
(`moderation.py:701-722`, оба через общий `build_mod_list(db, chat_id,
action_type, title, empty_msg)` — `moderation_logs WHERE action_type IN
('ban','kick')`); `ушли`/`вышли` (725) → `mod_db.get_left_users(db,
chat_id)` (`user_chat_stats WHERE is_left=TRUE`, не входит в обычный
`/users`).

Сайт уже имеет `/{chat_id}/logs` (admin.py:327+, постраничный журнал
`moderation_logs`) — для "Баны"/"Кики" хватит query-параметра `?action=ban`
/ `?action=kick` к ТОМУ ЖЕ эндпоинту (переиспользование, без новой
таблицы). Для "Вышедшие" — отдельный лёгкий `GET /{chat_id}/left`
(`mod_db.get_left_users`, уже готов). На фронте — 2-3 фильтра/под-вкладки
рядом с "Журнал", не новый раздел.

### Структура сайта после Блока 8 (для `local_rank>=1`)
"Мои чаты" → дашборд чата → вкладки: **Участники** (+смена ранга, 8.2) /
**Чёрный список** (новая, 8.1) / **Настройки** (10 rank_*-порогов вместо 4,
8.3 + щит/иммунитет, 8.4 + чистка, 8.5) / **Журнал** (+фильтры
баны/кики/вышедшие, 8.6).

---

## Идеи на будущее (не блоки — фиксация для последующих сессий)

Явно отмечены в FUTURE_IDEAS как "на будущее", не реализуются сейчас, но
логически продолжают Блоки 1-8 — имена/таблицы выше намеренно с ними не
конфликтуют:

1. **«подарить вип @user 1 месяц»** — виральная раздача VIP другому игроку
   (за ✨ дарителя, доп. монетизация Блока 2) — новая команда в
   `bot/handlers/vip.py` (Блок 2.4) + `purchase_vip(..., target_user_id=...)`.
2. **«Стаж VIP»** — счётчик суммарных месяцев VIP в профиле (косметика,
   титул/достижение) — поле-аккумулятор у `vip_subscriptions`/
   `user_chat_stats`, инкремент при истечении/продлении (Блок 2/4).
3. **Сезонные темы Battle Pass** — топовые награды платного трека сезона =
   эксклюзивная тема из `core/themes.py` с новым `rarity:"seasonal"` (Блок
   5.2, `BATTLE_PASS_REWARDS`) — требует добавить поле `rarity` в `THEMES`
   (сейчас структура только `top/sep/bot/accent`, без rarity).
