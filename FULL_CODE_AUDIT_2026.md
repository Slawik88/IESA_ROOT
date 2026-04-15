# 🔍 ПОЛНЫЙ АУДИТ КОДА — IESA ROOT + PredvestnikBot

> **Дата:** 15 апреля 2026  
> **Область:** Django-сайт (IESA_ROOT), Telegram-бот (PredvestnikBot), Mini App (frontend)  
> **Цель:** Найти ВСЕ баги, косяки, недочёты и дыры  

---

## 📋 ОГЛАВЛЕНИЕ

1. [КРИТИЧЕСКИЕ БАГИ (нужно фиксить СЕЙЧАС)](#-1-критические-баги)
2. [ВЫСОКИЙ ПРИОРИТЕТ (серьёзные проблемы)](#-2-высокий-приоритет)
3. [СРЕДНИЙ ПРИОРИТЕТ (заметные косяки)](#-3-средний-приоритет)
4. [НИЗКИЙ ПРИОРИТЕТ (мелочи и код-стайл)](#-4-низкий-приоритет)
5. [ФРОНТЕНД MINI APP (React/TSX)](#-5-фронтенд-mini-app)
6. [DJANGO САЙТ (шаблоны, вьюхи, модели)](#-6-django-сайт)
7. [СВОДНАЯ ТАБЛИЦА](#-7-сводная-таблица)

---

## 🔴 1. КРИТИЧЕСКИЕ БАГИ

### BUG-001: CORS `Access-Control-Allow-Origin: *` на ВСЕХ эндпоинтах Mini App
- **Файл:** `IESA_ROOT/miniapp_views.py`, строка 151
- **Код:**
```python
def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        ...
    }
```
- **Проблема:** Любой сайт в интернете может делать запросы к API мини-приложения. Злоумышленник может подставить iframe/скрипт на стороннем сайте, и если пользователь авторизован — украсть данные или выполнить операции от его имени.
- **Решение:** Заменить `"*"` на конкретный origin Telegram:
```python
def _cors_headers(request=None):
    origin = ""
    if request:
        origin = request.META.get("HTTP_ORIGIN", "")
    allowed = {"https://web.telegram.org", "https://webk.telegram.org", "https://webz.telegram.org"}
    if origin in allowed:
        return {"Access-Control-Allow-Origin": origin, ...}
    return {"Access-Control-Allow-Headers": "...", "Cache-Control": "no-cache"}
```

---

### BUG-002: `_DEVELOPER_ID` перезаписывается хардкодом — конфиг игнорируется
- **Файл:** `IESA_ROOT/miniapp_views.py`, строки 57 и 786
- **Код:**
```python
# Строка 57: импорт из config.py
try:
    from config import DEVELOPER_ID as _DEVELOPER_ID
except Exception:
    _DEVELOPER_ID = None

# Строка 786: ПЕРЕЗАПИСЫВАЕТСЯ хардкодом!
_DEVELOPER_ID = 1460945748
```
- **Проблема:** Импорт из config.py абсолютно бесполезен — значение всегда перезаписывается. Если DEVELOPER_ID изменится в config.py — miniapp_views.py не обновится. Также ID разработчика захардкожен в коде (утечка через Git).
- **Решение:** Удалить строку 786, использовать только импорт из config.

---

### BUG-003: Race condition в `add_mora()` — чтение баланса после commit
- **Файл:** `PredvestnikBot/database/db.py`, ~строка 4223
- **Код (упрощённо):**
```python
await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, uid))
await db.commit()        # ← отпускаем транзакцию
# ... другой запрос может изменить баланс тут ...
row = await db.fetchone("SELECT balance FROM users WHERE user_id=?", (uid,))  # STALE!
return row["balance"]
```
- **Проблема:** Между `commit()` и `SELECT` другой конкурентный запрос может изменить баланс. Возвращённое значение устаревшее.
- **Затронуто:** `add_mora()`, `transfer_mora()`, `create_loan()`, `add_family_wallet()`, `buy_lottery_ticket()` — все имеют тот же паттерн.
- **Решение:** Использовать `RETURNING` в PostgreSQL:
```python
row = await db.fetchone(
    "UPDATE users SET balance = GREATEST(0, balance + ?) WHERE user_id = ? RETURNING balance",
    (amount, uid)
)
```

---

### BUG-004: Race condition в покупках казино, гачи и магазина
- **Файл:** Множество файлов (`api/casino.py`, `api/gacha.py`, `handlers/casino.py`)
- **Проблема:** Паттерн "проверь баланс → списывай отдельным запросом":
```python
# 1) Проверка
row = await db.fetchone("SELECT balance FROM users WHERE user_id=?", (uid,))
if row["balance"] < price: raise ValueError(...)
# Тут другой запрос может списать!
# 2) Списание
await db.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (price, uid))
```
- **Решение:** Атомарное списание:
```python
cursor = await db.execute(
    "UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
    (price, uid, price)
)
if cursor.rowcount == 0:
    raise ValueError("Недостаточно Моры")
```
- **Примечание:** Некоторые эндпоинты (`roulette_spin`, `gacha roll`) УЖЕ используют атомарное списание — молодцы! Нужно привести остальные к такому же паттерну.

---

### BUG-005: `@csrf_exempt` на 100+ эндпоинтах без альтернативной защиты
- **Файл:** `IESA_ROOT/miniapp_views.py` — все функции
- **Проблема:** Каждый эндпоинт помечен `@csrf_exempt`. Хоть initData HMAC и валидируется, в dev-режиме (когда `_BOT_TOKEN` пуст) запросы принимаются по `?user_id=N` вообще без верификации.
- **Решение:** 
  1. Убедиться что `_BOT_TOKEN` ВСЕГДА установлен в продакшене
  2. Добавить `@require_POST` / `@require_GET` соответственно на каждый endpoint
  3. Убрать dev-fallback `?user_id=` в продакшене полностью

---

### BUG-006: SQL-инъекция через неэкранированный column name в `slot_col`
- **Файл:** `IESA_ROOT/miniapp_views.py`, ~строка 2160
- **Код:**
```python
if slot_col:
    cur.execute(
        f"UPDATE user_rpg_stats SET {slot_col}=NULL WHERE user_id={ph} AND chat_id={ph}",
        (uid, chat_id),
    )
```
- **Проблема:** `slot_col` берётся из БД (из `gacha_inventory`), но если злоумышленник напрямую модифицирует БД или найдёт способ вставить нужное значение — получит SQL-инъекцию.
- **Решение:** Белый список:
```python
VALID_SLOTS = {"weapon_id", "helmet_id", "armor_id", "boots_id", "artifact_id"}
if slot_col not in VALID_SLOTS:
    return JsonResponse({"error": "invalid slot"}, status=400, headers=headers)
```

---

### BUG-007: `roulette_losses` не сбрасывается при ошибке — бесконечная polosa удач
- **Файл:** `PredvestnikBot/api/roulette.py`, ~строка 208
- **Код:**
```python
async with postgres_connect() as db:
    if win:
        await db.execute("UPDATE user_mora SET roulette_losses=0 ...", (uid, chat_id))
    else:
        await db.execute("UPDATE user_mora SET roulette_losses=roulette_losses+1 ...", (uid, chat_id))
    # НЕТ await db.commit() !!!
```
- **Проблема:** После UPDATE нет `await db.commit()`. В зависимости от настроек autocommit пула, pity counter может НЕ сохраняться → пользователь не получает pity.
- **Решение:** Добавить `await db.commit()` после обоих веток `if win`.

---

## 🟠 2. ВЫСОКИЙ ПРИОРИТЕТ

### BUG-008: Open Redirect через `HTTP_REFERER`
- **Файлы:** `users/views.py`, `users/views_verification.py` — множество мест
- **Код:**
```python
referer = request.META.get('HTTP_REFERER', '/')
return redirect(referer)
```
- **Проблема:** Атакующий может отправить ссылку `https://mysite.com/login?next=https://evil.com`. После логина пользователь перенаправится на фишинговый сайт.
- **Решение:**
```python
from django.utils.http import url_has_allowed_host_and_scheme
if url_has_allowed_host_and_scheme(referer, settings.ALLOWED_HOSTS):
    return redirect(referer)
return redirect('core:home')
```

---

### BUG-009: Нет валидации владельца предмета в `miniapp_equip`
- **Файл:** `IESA_ROOT/miniapp_views.py`, ~строка 1050
- **Проблема:** Эндпоинт принимает `item_id` и экипирует его, но не проверяет что предмет принадлежит текущему `uid`. Пользователь может экипировать чужой предмет, передав чужой `item_id`.
- **Решение:** Добавить проверку `WHERE user_id = ? AND id = ?` в SQL-запрос.

---

### BUG-010: Тема профиля не валидируется по справочнику
- **Файл:** `IESA_ROOT/miniapp_views.py`, ~строка 1743
- **Код:** Проверяется только что тема куплена в `user_themes`, но не что `theme_key` вообще существует в конфиге `PROFILE_THEMES`.
- **Проблема:** Можно вставить произвольную строку (через модификацию запроса) — это может привести к XSS через CSS injection (`data-theme` атрибут на `<html>`).
- **Решение:** Добавить `if theme_key not in PROFILE_THEMES and theme_key != "default": return error`.

---

### BUG-011: Silent error handling в авторизации казначейства
- **Файл:** `IESA_ROOT/miniapp_views.py`, ~строка 1619
- **Код:**
```python
try:
    cur.execute("SELECT rank FROM user_stats ...")
    row = cur.fetchone()
    rank = row[0] if row else "user"
except Exception:
    rank = "user"  # ← ТИХО ставим "user" при любой ошибке!
```
- **Проблема:** Если БД упала или произошла другая ошибка → пользователь получит ранг "user" вместо отказа доступа. Нужно отклонять при ошибке.
- **Решение:** При исключении возвращать 403, а не тихо ставить "user".

---

### BUG-012: Нет проверки приватности в публичном профиле
- **Файл:** `users/views.py`, ~строка 160
- **Проблема:** Функции `profile_public_by_username()` и `profile_public_by_card()` показывают профиль без проверки настроек видимости пользователя. Если у пользователя есть опция "скрыть профиль" — она не проверяется.
- **Решение:** Проверять `user.is_visible` (или аналог) перед рендерингом.

---

### BUG-013: Protected Media — нет проверки ownership
- **Файл:** `IESA_ROOT/protected_media_views.py`, ~строка 15
- **Проблема:** Декоратор `@login_required` проверяет только авторизацию, но не владельца файла. Любой залогиненный пользователь может скачать файл другого пользователя, угадав имя.
- **Решение:** Добавить проверку принадлежности файла и защиту от path traversal.

---

### BUG-014: Duplicate form classes — `forms.py` vs `forms_verification.py`
- **Файл:** `users/forms.py` строки 136-160, `users/forms_verification.py`
- **Проблема:** `MemberSearchForm` и `VisitForm` определены в ОБОИХ файлах. Если фиксить баг — нужно обновлять два места. Рано или поздно они разъедутся.
- **Решение:** Удалить дубликаты из `forms.py`, импортировать из `forms_verification.py`.

---

### BUG-015: Двойной URL namespace в redirect
- **Файл:** `blog/views/comments.py`, ~строка 60
- **Код:**
```python
return redirect('blog:blog:post_detail', pk=pk)  # ❌ Двойной 'blog:'
```
- **Проблема:** Django может выбросить NoReverseMatch или неправильно разрезолвить URL.
- **Решение:** `return redirect('blog:post_detail', pk=pk)`

---

### BUG-016: Webhook Telegram без IP-фильтра и rate-limit
- **Файл:** `users/urls.py`, строка 9
- **Код:**
```python
path('telegram/webhook/<slug:secret>/', ...)
```
- **Проблема:** 
  1. Нет проверки что запрос пришёл с серверов Telegram (IP-диапазоны: `149.154.160.0/20`, `91.108.4.0/22`)
  2. Нет rate-limit на URL — можно брутфорсить `<secret>`
- **Решение:** Добавить middleware/декоратор с IP-фильтром Telegram + `@ratelimit(key='ip', rate='10/h')`.

---

## 🟡 3. СРЕДНИЙ ПРИОРИТЕТ

### BUG-017: `date.today()` вместо `datetime.now(UTC).date()` в miniapp boss
- **Файл:** `IESA_ROOT/miniapp_views.py`, ~строка 3763
- **Код:**
```python
today_str = __import__("datetime").date.today().isoformat()
```
- **Проблема:** `date.today()` использует ЛОКАЛЬНОЕ время сервера, не UTC. Если сервер на UTC+3, то с 21:00 до 00:00 UTC пользователь получит "завтрашний" результат.
- **Решение:**
```python
today_str = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
```

---

### BUG-018: `permanent=True` в redirect-правилах URL
- **Файл:** `IESA_ROOT/urls.py`, ~строка 342
- **Код:**
```python
RedirectView.as_view(url='/products/', permanent=True)
```
- **Проблема:** HTTP 301 кэшируется браузерами навсегда. Если позже понадобится изменить маршрут — пользователи со старым кэшем будут ходить по старому адресу.
- **Решение:** Использовать `permanent=False` (HTTP 302).

---

### BUG-019: Отсутствуют индексы на часто запрашиваемых полях
- **Файл:** `blog/models.py`
- **Проблема:** Модели `Post`, `Comment` не имеют `Meta.indexes` на:
  - `Post.status + Post.created_at` (используется в КАЖДОМ запросе списка постов)
  - `Comment.post` (для загрузки комментариев по посту)
  - `Post.author` (для фильтрации по автору)
- **Решение:** Добавить в `Meta.indexes`:
```python
class Meta:
    indexes = [
        models.Index(fields=['status', '-created_at']),
        models.Index(fields=['author', 'status']),
    ]
```

---

### BUG-020: N+1 запросы при отображении лайков/комментариев в профиле
- **Файлы:** `users/views.py` строки 104-107 и 267-285
- **Код:**
```python
all_posts = Post.objects.filter(author=user).select_related('author').prefetch_related('likes', 'comments')
```
- **Проблема:** В шаблоне вызывается `post.likes.count()` и `post.comments.count()` — это N+1 запросов (по 2 запроса на каждый пост).
- **Решение:** Использовать `annotate()`:
```python
all_posts = Post.objects.filter(author=user).select_related('author').annotate(
    likes_count=Count('likes', distinct=True),
    comments_count=Count('comments', distinct=True),
).order_by('-created_at')
```

---

### BUG-021: SPA-fallback regex слишком широкий
- **Файл:** `IESA_ROOT/urls.py`, ~строка 350
- **Код:**
```python
re_path(r'^app/.*$', miniapp_index)
```
- **Проблема:** Будет ловить `/app/admin/`, `/app/api/` и любые другие подпути. Если добавить новый route начинающийся с `/app/` — он может быть перехвачен.
- **Решение:** Убедиться что специфичные маршруты `/app/api/...` идут ПЕРЕД fallback-правилом.

---

### BUG-022: Нет `Content-Security-Policy` заголовка
- **Файл:** `IESA_ROOT/settings.py`
- **Проблема:** Нет CSP-заголовка. Это позволяет XSS-атакам загружать скрипты с любого домена.
- **Решение:** Добавить `django-csp` или middleware с CSP-заголовком.

---

### BUG-023: `notifications/utils.py` — NullPointer на удалённом авторе
- **Файл:** `notifications/utils.py`, строки 51-60
- **Код:**
```python
def notify_new_comment(comment):
    if comment.author != comment.post.author:  # ← author может быть None!
        create_notification(recipient=comment.post.author, ...)
```
- **Проблема:** Если автор поста был удалён (`on_delete=SET_NULL`), то `comment.post.author` = `None`, и `create_notification(recipient=None)` упадёт.
- **Решение:**
```python
if comment.post.author and comment.author != comment.post.author:
    ...
```

---

### BUG-024: Медиа-файлы раздаются через Django в продакшене
- **Файл:** `IESA_ROOT/urls.py`, ~строка 354
- **Проблема:** В коде есть комментарий "TODO: Move to DigitalOcean Spaces", но медиа всё ещё раздаются Django-воркерами. Это критично для производительности — каждый запрос медиа занимает worker.
- **Решение:** Настроить CDN или S3/Spaces direct URL.

---

### BUG-025: Отсутствует кастомный 403 handler
- **Файл:** `IESA_ROOT/urls.py`
- **Проблема:** При 403 ошибке пользователь видит дефолтный Django template, который может раскрывать debug-информацию.
- **Решение:** Добавить `handler403 = 'core.views.custom_403'` и шаблон.

---

### BUG-026: Сигнал `signals_partner.py` удаляет только что созданного партнёра
- **Файл:** `users/signals_partner.py`, строки 63-75
- **Проблема:** Post-save сигнал для Partner создаёт профиль, а потом сразу его удаляет и ставит `is_partner=False`. Вся партнёрская система может быть сломана этим сигналом.
- **Решение:** Удалить строки 63-75 или переписать логику сигнала.

---

### BUG-027: `exception as _e` vs `_log.debug` — правильно, но скрывает баги
- **Файл:** `PredvestnikBot/database/db.py` — 20+ мест
- **Код:**
```python
except Exception as _e:
    _log.debug("%s", _e)  # ← debug уровень, не видно в продакшене
```
- **Проблема:** `_log.debug()` скорее всего НЕ отображается в продакшен-логах (обычно уровень INFO+). Все ошибки DDL-миграций, ALTER TABLE и т.д. уходят в никуда.
- **Решение:** Заменить на `_log.warning()` или `_log.info()` для важных миграций.

---

### BUG-028: В `miniapp_equip` нет транзакции — неконсистентное состояние при ошибке
- **Файл:** `IESA_ROOT/miniapp_views.py`, ~строки 1263-1278
- **Код:**
```python
# 1) Снимаем текущий предмет со слота
cur.execute("UPDATE gacha_inventory SET equipped=0 WHERE id=?", (old_item_id,))
# 2) Очищаем слот в RPG-статах
cur.execute("UPDATE user_rpg_stats SET weapon_id=NULL WHERE ...", ...)
# 3) Ставим новый предмет
cur.execute("UPDATE gacha_inventory SET equipped=1 WHERE id=?", (new_item_id,))
# Если шаг 3 упал — шаги 1 и 2 уже выполнены! Предмет снят, но новый не надет.
conn.commit()
```
- **Проблема:** 3 UPDATE без транзакции. Если один из них упадёт — данные в неконсистентном состоянии.
- **Решение:** Обернуть в `BEGIN`/`COMMIT` или использовать `conn.autocommit = False`.

---

### BUG-029: Пустой `equip_ids` ломает SQL `WHERE id IN ()`
- **Файл:** `IESA_ROOT/miniapp_views.py`, ~строка 2072
- **Код:**
```python
placeholders = ",".join([ph] * len(eq_ids))
cur.execute(f"SELECT ... FROM gacha_inventory WHERE id IN ({placeholders})", equip_ids)
```
- **Проблема:** Если `eq_ids` = `[]`, то `placeholders` = `""`, SQL = `WHERE id IN ()` — синтаксическая ошибка.
- **Решение:** Проверять `if not eq_ids: return []` перед SQL.

---

### BUG-030: `available_spots` в Event — N+1 query в шаблоне
- **Файл:** `blog/models.py`, строки 206-212
- **Код:**
```python
@property
def available_spots(self):
    if self.max_participants:
        confirmed = self.registrations.filter(status='confirmed').count()
        return max(0, self.max_participants - confirmed)
    return None
```
- **Проблема:** Это property, которое делает `.count()` запрос к БД. В списке событий `for event in events` → N+1.
- **Решение:** Annotate в queryset заместо property.

---

## 🔵 4. НИЗКИЙ ПРИОРИТЕТ

### BUG-031: Нет валидации стоимости визита (negative cost)
- **Файл:** `users/forms_verification.py`, строки 48-68
- **Проблема:** Форма `VisitForm` не валидирует что `cost >= 0`. Партнёр может выставить отрицательную стоимость.
- **Решение:** Добавить `clean_cost()` с проверкой `if cost < 0: raise ValidationError(...)`.

---

### BUG-032: Хардкодед Cache-Control в views
- **Файлы:** `blog/views/posts.py` строка 79, `blog/views/events.py` строка 16
- **Код:**
```python
response['Cache-Control'] = 'public, max-age=120'
```
- **Проблема:** Магические числа разбросаны по разным файлам.
- **Решение:** Вынести в settings: `CACHE_TTL_POSTS = 120`.

---

### BUG-033: `time.time()` вместо Django timezone в PIN-генерации
- **Файл:** `users/models.py`, строка 227
- **Код:**
```python
def get_pin_remaining_seconds(self):
    interval = 720
    return interval - (int(time.time()) % interval)
```
- **Проблема:** `time.time()` всегда UTC, но может создать путаницу при дебаге.
- **Решение:** Использовать `django.utils.timezone.now().timestamp()`.

---

### BUG-034: Dev-баннер показывается ВСЕМ пользователям
- **Файл:** `templates/base.html`, строки ~155-160
- **Код:**
```html
<div class="dev-banner" id="dev-banner">
    <strong>Dev mode</strong> — Site is under active development.
</div>
```
- **Проблема:** Баннер показывается всем, даже в продакшене (если не скрыт CSS).
- **Решение:** Условие `{% if DEBUG %}` или проверка settings.

---

### BUG-035: Нет audit-логирования на sensitive-операции
- **Файлы:** `users/views.py` (`impersonate_user`), `miniapp_views.py` (переводы, покупки)
- **Проблема:** Нет логов для:
  - Имперсонация пользователя администратором
  - Переводы крупных сумм
  - Изменение рангов
  - Удаление контента
- **Решение:** Добавить `audit_log()` функцию или использовать Django's `LogEntry`.

---

## 🖥️ 5. ФРОНТЕНД MINI APP

### BUG-036: `AppContext.tsx` — приложение вечно крутится при ошибке загрузки
- **Файл:** `frontend/src/AppContext.tsx`, строки 30-44
- **Код:**
```tsx
try {
    const d = await fetchUserData(chatId);
    setUserData(d);
} catch {
    // игнорируем — не критично   ← КРИТИЧНО!
} finally {
    setLoading(false);
}
```
- **Проблема:** Если `fetchUserData` упадёт с ошибкой — `userData` останется `null`, `loading` станет `false`, и приложение покажет пустой экран без каких-либо сообщений об ошибке. Пользователь не понимает что происходит.
- **Решение:** Добавить `setError(message)` стейт и показывать плашку "Ошибка загрузки" с кнопкой "Повторить".

---

### BUG-037: Exchange.tsx — setState на каждый пиксель движения мыши
- **Файл:** `frontend/src/pages/Exchange.tsx`, строки 40-45
- **Код:**
```tsx
const handleMove = (clientX: number) => {
    if (!interactive) return;
    setHoverIdx(getIdxFromX(clientX));  // 60+ вызовов в секунду
};
```
- **Проблема:** `setState` на каждый `mousemove` вызывает ре-рендер всего компонента 60 раз в секунду. Это создаёт подвисания UI на слабых устройствах.
- **Решение:** Использовать `useRef` для `hoverIdx` или `requestAnimationFrame` throttle:
```tsx
const hoverRef = useRef(-1);
const handleMove = (clientX: number) => {
    hoverRef.current = getIdxFromX(clientX);
    // render only the sparkline via requestAnimationFrame
};
```

---

### BUG-038: Casino.tsx — баланс не проверяется перед ставкой
- **Файл:** `frontend/src/pages/Casino.tsx`, строки 60-75
- **Проблема:** Пользователь может ввести ставку больше баланса → API вернёт ошибку → плохой UX. Можно показывать текущий баланс и блокировать кнопку.
- **Решение:** Передавать баланс из `useAppContext()` и проверять `amt > balance` перед отправкой.

---

### BUG-039: Bank.tsx — нет retry при ошибке загрузки
- **Файл:** `frontend/src/pages/Bank.tsx`, строки 58-64
- **Проблема:** Если загрузка банка упала → пользователь видит ошибку и ему нужно перезагружать всю мини-аппку. Нет кнопки "Повторить".
- **Решение:** Добавить кнопку retry:
```tsx
<button onClick={reload}>🔄 Повторить</button>
```

---

### BUG-040: Gacha.tsx — `useCallback` без всех зависимостей
- **Файл:** `frontend/src/pages/Gacha.tsx`, строка 60
- **Код:**
```tsx
const handleRoll = useCallback(async (count: 1 | 10 | 50) => {
    // ...
}, [chatId, showToast]);  // ← отсутствует lastCount (если он вообще нужен)
```
- **Проблема:** `lastCount` не в зависимостях, но используется через `setLastCount(count)` — это не критично, т.к. `count` передаётся как аргумент. Однако стоит проверить все подобные паттерны.
- **Риск:** Средний — может привести к stale closures.

---

### BUG-041: Нет retry/error state во многих компонентах
- **Файлы:** `Achievements.tsx`, `Inventory.tsx`, `Season.tsx`, `Stars.tsx`
- **Проблема:** Если API вернул ошибку при загрузке данных — компоненты показывают пустоту или skeleton навечно.
- **Решение:** Единый паттерн: `{error && <ErrorCard onRetry={reload} />}`.

---

### BUG-042: Нет offline/no-network обработки
- **Файл:** Весь фронтенд
- **Проблема:** Если у пользователя пропал интернет — все запросы молча падают, ничего не показывается.
- **Решение:** Добавить глобальный `navigator.onLine` listener и плашку "Нет подключения".

---

## 🌐 6. DJANGO САЙТ

### BUG-043: `search.py` — `only()` без полей для avatar URL
- **Файл:** `blog/views/search.py`, строка 70
- **Код:**
```python
users_qs = User.objects.search(normalized).only(
    'id', 'username', 'first_name', 'last_name', 'email', 'is_verified', 'avatar', 'permanent_id',
)[:SEARCH_USERS_LIMIT]
```
- **Проблема:** `only('avatar')` загрузит только поле-путь. Если шаблон вызывает `user.avatar.url`, это не вызовет дополнительный запрос (хорошо), но если avatar — это ForeignKey или использует кастомный storage — может быть проблема.
- **Риск:** Низкий.

---

### BUG-044: `get_recommended_posts()` — N+1 в шаблоне detail
- **Файл:** `blog/models.py`, ~строка 73
- **Проблема:** Метод модели `get_recommended_posts()` выполняет 2+ запроса, и вызывается в шаблоне post_detail → для каждого рекомендованного поста.
- **Решение:** Предзагружать в view и передавать через context.

---

### BUG-045: IDOR в `log_visit` — любой партнёр может логировать визит любому
- **Файл:** `users/views_verification.py`, строки 225-240
- **Код:**
```python
@partner_required
def log_visit(request, member_id):
    member = get_object_or_404(User, id=member_id)  # Нет проверки принадлежности
```
- **Проблема:** Партнёр A может залогировать визит участника в партнёр B. Нет проверки что `member` связан с текущим партнёром.
- **Решение:** Добавить проверку что `member` авторизован для данного партнёра.

---

### BUG-046: Impersonate без rate-limit
- **Файл:** `users/views.py`, строка 364
- **Проблема:** Функция `impersonate_user()` позволяет админу войти от другого пользователя. Нет rate-limit и audit-log.
- **Решение:** `@ratelimit('ip', '5/h')` + `logger.warning('Admin %s impersonated %s', admin, target)`.

---

## 📊 7. СВОДНАЯ ТАБЛИЦА

| # | Файл | Критичность | Категория | Описание |
|---|------|-------------|-----------|----------|
| 001 | miniapp_views.py:151 | 🔴 КРИТ | Безопасность | CORS `*` на всех API |
| 002 | miniapp_views.py:786 | 🔴 КРИТ | Логика | DEVELOPER_ID перезаписывается хардкодом |
| 003 | db.py:4223+ | 🔴 КРИТ | Race Condition | add_mora/transfer/loan — stale balance |
| 004 | casino/gacha/shop | 🔴 КРИТ | Race Condition | Неатомарная проверка баланса |
| 005 | miniapp_views.py | 🔴 КРИТ | Безопасность | @csrf_exempt без альтернативы |
| 006 | miniapp_views.py:2160 | 🔴 КРИТ | SQL Injection | slot_col без whitelist |
| 007 | roulette.py:208 | 🔴 КРИТ | Логика | roulette pity не commit-ится |
| 008 | users/views.py | 🟠 ВЫСОК | Безопасность | Open redirect через REFERER |
| 009 | miniapp_views.py:1050 | 🟠 ВЫСОК | Безопасность | Экипировка чужого предмета |
| 010 | miniapp_views.py:1743 | 🟠 ВЫСОК | Валидация | Тема не валидируется по справочнику |
| 011 | miniapp_views.py:1619 | 🟠 ВЫСОК | Безопасность | Silent auth failure → "user" |
| 012 | users/views.py:160 | 🟠 ВЫСОК | Приватность | Публичный профиль без privacy check |
| 013 | protected_media_views.py | 🟠 ВЫСОК | Безопасность | Нет ownership check на файлы |
| 014 | users/forms.py | 🟠 ВЫСОК | Архитектура | Дублирующиеся формы |
| 015 | blog/comments.py:60 | 🟠 ВЫСОК | Роутинг | Двойной namespace `blog:blog:` |
| 016 | users/urls.py:9 | 🟠 ВЫСОК | Безопасность | Webhook без IP-фильтра/rate-limit |
| 017 | miniapp_views.py:3763 | 🟡 СРЕДН | Время | date.today() вместо UTC |
| 018 | urls.py:342 | 🟡 СРЕДН | Роутинг | permanent=True в redirects |
| 019 | blog/models.py | 🟡 СРЕДН | Производительность | Нет индексов на Post/Comment |
| 020 | users/views.py | 🟡 СРЕДН | Производительность | N+1 на likes/comments |
| 021 | urls.py:350 | 🟡 СРЕДН | Роутинг | SPA fallback regex слишком широкий |
| 022 | settings.py | 🟡 СРЕДН | Безопасность | Нет CSP заголовка |
| 023 | notifications/utils.py | 🟡 СРЕДН | NullPointer | author может быть None |
| 024 | urls.py:354 | 🟡 СРЕДН | Производительность | Медиа через Django |
| 025 | urls.py | 🟡 СРЕДН | UX | Нет кастомного 403 handler |
| 026 | signals_partner.py | 🟡 СРЕДН | Логика | Сигнал удаляет партнёра сразу |
| 027 | db.py (20+ мест) | 🟡 СРЕДН | Логирование | debug-уровень скрывает ошибки |
| 028 | miniapp_views.py:1263 | 🟡 СРЕДН | Транзакции | Нет транзакции при экипировке |
| 029 | miniapp_views.py:2072 | 🟡 СРЕДН | SQL | Пустой IN () при equip_ids=[] |
| 030 | blog/models.py:206 | 🟡 СРЕДН | Производительность | N+1 в available_spots |
| 031 | forms_verification.py | 🔵 НИЗ | Валидация | Нет проверки cost >= 0 |
| 032 | blog/views | 🔵 НИЗ | Код-стайл | Хардкод Cache-Control |
| 033 | users/models.py:227 | 🔵 НИЗ | Время | time.time() vs timezone |
| 034 | base.html | 🔵 НИЗ | UX | Dev-баннер всем |
| 035 | Множество | 🔵 НИЗ | Безопасность | Нет audit-логов |
| 036 | AppContext.tsx | 🟡 СРЕДН | UX | Нет обработки ошибки загрузки |
| 037 | Exchange.tsx | 🟡 СРЕДН | Производительность | setState на mousemove |
| 038 | Casino.tsx | 🔵 НИЗ | UX | Баланс не проверяется на клиенте |
| 039 | Bank.tsx | 🔵 НИЗ | UX | Нет retry при ошибке |
| 040 | Gacha.tsx | 🔵 НИЗ | React | useCallback deps неполные |
| 041 | Множество .tsx | 🔵 НИЗ | UX | Нет retry/error state |
| 042 | Весь фронтенд | 🔵 НИЗ | UX | Нет offline обработки |
| 043 | blog/search.py | 🔵 НИЗ | Производительность | only() без avatar fields |
| 044 | blog/models.py | 🔵 НИЗ | Производительность | N+1 в рекомендациях |
| 045 | views_verification.py | 🟡 СРЕДН | Безопасность | IDOR в log_visit |
| 046 | users/views.py | 🟡 СРЕДН | Безопасность | Impersonate без rate-limit |

---

## 📈 ИТОГО

| Критичность | Количество |
|-------------|-----------|
| 🔴 КРИТИЧЕСКИЕ | 7 |
| 🟠 ВЫСОКИЙ | 9 |
| 🟡 СРЕДНИЙ | 16 |
| 🔵 НИЗКИЙ | 14 |
| **ВСЕГО** | **46** |

---

## 🎯 ПЛАН ДЕЙСТВИЙ (приоритет)

### Фаза 1 — Безопасность (СЕЙЧАС)
1. Ограничить CORS на Telegram origins (BUG-001)
2. Убрать хардкод _DEVELOPER_ID (BUG-002)
3. Добавить whitelist на slot_col (BUG-006)
4. Пофиксить open redirect (BUG-008)
5. Проверить ownership в miniapp_equip (BUG-009)
6. Добавить IP-фильтр на webhook (BUG-016)

### Фаза 2 — Race Conditions
7. `add_mora` → использовать RETURNING (BUG-003)
8. Атомарные списания во всех покупках (BUG-004)
9. Коммит pity counter в рулетке (BUG-007)
10. Транзакция в экипировке (BUG-028)

### Фаза 3 — UX и Производительность
11. Индексы на Post/Comment (BUG-019)
12. N+1 запросы (BUG-020, 030, 044)
13. Обработка ошибок во фронтенде (BUG-036, 039, 041)
14. Exchange mousemove throttle (BUG-037)

### Фаза 4 — Мелочи и Качество
15. Дублирующиеся формы (BUG-014)
16. Двойной namespace (BUG-015)
17. UTC vs local time (BUG-017)
18. Dev баннер условно (BUG-034)
19. Audit logging (BUG-035)
