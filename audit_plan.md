# IESA Sport — Аудит и план рефакторинга
> Стратегия: **один блок → тест → галочка → следующий блок**. Код меняем только когда явно запущен нужный блок.

---

## Обозначения
- `[ ]` — не сделано
- `[x]` — выполнено
- ⚡ высокий приоритет / видимый импакт
- 🏗️ архитектура
- 🐛 баг / регрессия
- 💅 UX / визуал
- 🔇 тихая оптимизация

---

## BLOCK 1 — Удаление `/auth/cabinet/` и перенос PIN-гайда в профиль ⚡ ✅ DONE
> **Цель**: выпилить бесполезный отдельный роут; информацию о PIN-коде (гайд + текущий PIN + секунды) перенести как отдельную вкладку «PIN & QR» внутри страницы профиля.

### Шаги
- [x] **Изучить `member_cabinet.html`** — зафиксировать весь отображаемый контент (PIN, таймер, QR-ссылка, гайд, список визитов, Telegram-статус, статус карты)
- [x] **Добавить секцию "PIN & Card"** в `profile.html` (раздел #pin-section + Visit History)
  - PIN-код с таймером обратного отсчёта
  - QR-ссылка (кнопка скачать + предпросмотр)
  - Статус физической карты (`card_active`, `card_issued_at`)
  - Telegram: привязан / не привязан + кнопка «Привязать»
  - Последние 5 визитов (краткий вид)
  - Гайд «Как использовать PIN» (сворачиваемый аккордеон)
- [x] **Перенести PIN-логику в `ProfileView.get_context_data()`** — added recent_visits, card_active, card_issued_at, used PIN_INTERVAL constant
- [x] **Удалить `member_cabinet()`** из `views_verification.py`
- [x] **URL `/auth/cabinet/`** → постоянный редирект 301 на `/auth/profile/#pin-section`
- [x] **Обновить все ссылки** на `/auth/cabinet/`:
  - `_navbar.html` → `#pin-section`; `handlers.py` CARD_URL; `notify.py`; `dashboard_redirect()`
- [ ] **Удалить CSS-файл** `static/css/member-cabinet.css` — стили перенесены в `profile.html <style>`
- [ ] **Удалить шаблон** `users/templates/users/member_cabinet.html` — больше не используется
- [x] **Smoke-test**: `manage.py check` → 0 ошибок ✅

---

## BLOCK 2 — DRY: устранить дублирование кода уведомлений о визитах 🏗️ ✅ DONE
> **Проблема**: логика создания уведомлений (in-site + Telegram) для visit-событий продублирована в `log_visit()`, `edit_visit()`, `cancel_visit()` — три почти одинаковых блока ~30 строк каждый.

### Шаги
- [x] **Создан** `users/services/visit_notifications.py` — 3 функции: `notify_visit_logged`, `notify_visit_edited`, `notify_visit_cancelled`
- [x] **Заменены** повторяющиеся блоки в `log_visit()`, `edit_visit()`, `cancel_visit()` — каждый теперь 1 строка
- [x] **Удалено дублирование `MemberSearchForm`** из `forms.py` (оставлен только в `forms_verification.py`)
- [x] **Удалён дублирующий `VisitForm`** из `forms.py`
- [ ] **Тест**: создать, отредактировать и отменить визит — уведомления приходят как раньше

---

## BLOCK 3 — Вынести «магические числа» и строки в константы 🔇 ✅ DONE
> **Проблема**: числа типа `720` (секунды PIN), `6` (длина PIN), `3600` (TTL QR-кэша) разбросаны по нескольким файлам — риск рассинхронизации при изменении бизнес-логики.

### Шаги
- [x] **Добавлено в `users/constants.py`**:
  ```python
  PIN_INTERVAL       = 720    # секунды между сменами PIN (12 мин)
  PIN_LENGTH         = 6      # цифр в PIN
  QR_CACHE_TTL       = 3600   # секунды кэша QR-изображения
  WEBHOOK_RATE_LIMIT = 300    # запросов/мин на Telegram webhook
  PROFILE_POSTS_PER_PAGE   = 12
  SEARCH_RESULTS_PER_PAGE  = 20
  PARTNER_VISITS_PER_PAGE  = 15
  PARTNER_HISTORY_LIMIT    = 20
  ```
- [x] **Заменены** `720` → `PIN_INTERVAL` в views.py, views_verification.py
- [x] **Заменены** `len(pin) != 6` → `PIN_LENGTH` в forms_verification.py
- [x] **Заменены** `3600` → `QR_CACHE_TTL` в qr_image()
- [x] **Заменены** `_count >= 300` → `WEBHOOK_RATE_LIMIT` в webhook view
- [x] **Заменены** `paginate_by = 12` → `PROFILE_POSTS_PER_PAGE`
- [ ] Месячные аббревиатуры в partner_calendar — оставлено на Block 4b
- [x] **Тест**: `manage.py check` → 0 ошибок ✅

---

## BLOCK 4 — Рефакторинг «жирных вьюх» (Fat Views) 🏗️⚡
> **Проблема**: `partner_calendar()` — 285 строк, `log_visit()` — 171 строка. Нарушен SRP; тяжело тестировать и читать.

### 4a — `log_visit()` (171 строк → ≤80)
- [ ] **Вынести PIN-валидацию** в отдельный метод/утилиту: `validate_pin_attempt(user, pin) → (ok: bool, error: str)`
  - Включает проверку lockout, инкремент failed_pin_attempts, сброс счётчика
- [ ] **Вынести idempotency-check** в утилиту: `check_idempotent_visit(partner, member, window=300) → Visit|None`
- [ ] **Оставить в view** только: get form → validate → call utils → create Visit → notify (через Block 2)
- [ ] Результирующий `log_visit()` ≤ 80 строк

### 4b — `partner_calendar()` (285 строк → ≤100)
- [ ] **Вынести** построение месячной сетки в `users/services/calendar_service.py`:
  - `build_month_grid(year, month, meetings_by_date) → list[list[CellDict]]`
  - `get_jump_options(current_year, current_month) → list[dict]`
- [ ] **Вынести** сериализацию встреч дня для JS: `serialize_day_meetings(meetings) → list[dict]`
- [ ] **Вынести** POST-логику создания встречи: `handle_meeting_create(partner, data) → Meeting|ValidationError`
- [ ] Результирующий `partner_calendar()` ≤ 100 строк

### 4c — `edit_visit()` и `cancel_visit()` (78 и 76 строк → ≤50)
- [ ] После Block 2 (notify service) — обе вьюхи сократятся органически
- [ ] Вынести проверку `EDIT_WINDOW` в декоратор или утилиту: `@within_edit_window` 
- [ ] Тест: каждый сценарий end-to-end

---

## BLOCK 5 — UX: унификация навигации в личном кабинете ⚡💅
> **Проблема**: у юзера существуют `/auth/profile/`, `/auth/dashboard/`, `/auth/cabinet/` (будет удалён в Block 1), `/auth/my-calendar/` — логика переходов неочевидна; `dashboard_redirect()` — хрупкий роутер.

### Шаги
- [ ] **审计** все входные точки после Block 1: профиль имеет вкладки Posts / About / PIN&QR
- [ ] **Уточнить `dashboard_redirect()`**: после удаления кабинета — is_partner → partner_dashboard; иначе → profile (нет нужды в третьем маршруте)
- [ ] **Добавить якорные ссылки** `/auth/profile/#pin-tab` вместо старого `/auth/cabinet/`
- [ ] **Унифицировать ссылку «Мой кабинет» в navbar**: ведёт на `/auth/profile/` для всех; отдельная «Partner Portal» — только для партнёров (уже есть)
- [ ] **Проверить TG-бота**: `CARD_URL` в `handlers.py` → обновить на `/auth/profile/#pin-tab`
- [ ] **Smoke-test** всех ролей: обычный юзер, партнёр, staff — корректный маршрут от navbar

---

## BLOCK 6 — Производительность: кэш и N+1 🔇⚡
> Конкретные точки, найденные при аудите.

### 6a — Кэш PIN в ProfileView
- [ ] `ProfileView.get_context_data()` вычисляет PIN при каждом запросе
- [ ] PIN меняется раз в 720 сек — добавить `cache.get_or_set(f'pin_{user.pk}', lambda: user.get_current_pin(), timeout=seconds_remaining)`
- [ ] Инвалидировать кэш при смене `totp_secret`

### 6b — N+1 в `partner_dashboard()` для recent_members
- [ ] Проверить `select_related('member')` для агрегации по последним клиентам — убедиться что нет N+1 при рендеринге аватаров
- [ ] Добавить `prefetch_related` там где не хватает

### 6c — Двойной `.count()` в `notifications/views.py`
- [ ] lines 11 и 34: два почти одинаковых `filter(...).count()` — объединить в одно обращение

### 6d — `ProfileView`: два запроса вместо одного
- [ ] `_get_public_profile_context()`: `exists()` + `count()` по одной таблице — заменить на `aggregate(count=Count(), is_sub=...)` (уже частично сделано — верифицировать)

### 6e — LocMemCache → Redis (опционально, при масштабировании)
- [ ] `settings.py` использует `LocMemCache` — не шарится между воркерами Heroku
- [ ] При переходе на 2+ dyno: добавить `django-redis` + `REDIS_URL` env
- [ ] Пока: задокументировать ограничение в `audit_plan.md`

---

## BLOCK 7 — Архитектура: разбить `views_verification.py` на модули 🏗️
> **Проблема**: 1600+ строк в одном файле = нечитаемо, сложно искать, тяжело тестировать. Аналогично тому как `blog/views/` разбит на подпапку.

### Предложенная структура
```
users/views/
  __init__.py        # re-export всех view-функций для обратной совместимости
  auth.py            # login, logout, register
  profile.py         # ProfileView, ProfileEditView, profile_public_*, deactivate, dashboard_redirect
  partner.py         # partner_dashboard, log_visit, edit_visit, cancel_visit, partner_member_visits, partner_analytics, partner_profile_edit
  calendar.py        # partner_calendar, delete_meeting, user_calendar
  verification.py    # public_profile, member_cabinet (если не удалён), server_time
  telegram.py        # telegram_webhook_view, connect_telegram_code_view, disconnect_telegram_view, telegram_login_callback_view, test_telegram_view
  invites.py         # invite_list, invite_generate, invite_register
  insurance.py       # insurance_agent_request, _notify_admins_insurance
  qr.py              # qr_image, activity_levels_info
  search.py          # users_search
  impersonate.py     # impersonate_user, account_change_request_submit
```

### Шаги
- [ ] Создать `users/views/` директорию
- [ ] Перенести по одному модулю, сохраняя `__init__.py` как point of re-export
- [ ] Обновить `users/urls.py` — импортировать из нового пакета (минимальные изменения, т.к. `views_verification.*` заменяется на `views.*`)
- [ ] `python manage.py check` → 0 ошибок после каждого переноса

---

## BLOCK 8 — Мелкие улучшения читаемости и гибкости кода 🔇
> Точечные правки без риска регрессий.

### 8a — Убрать дублирование `try: partner = request.user.partner_profile`
- [ ] В каждой view с `@partner_required` после декоратора делается ещё и `try/except Partner.DoesNotExist` — лишний код. Декоратор уже гарантирует что партнёр есть. Убрать дублирующий try/except изнутри view (заменить на прямой `request.user.partner_profile`)

### 8b — Вынести Telegram bot name lookup в утилиту
- [ ] `os.environ.get('TELEGRAM_BOT_USERNAME', os.environ.get('TELEGRAM_BOT_NAME', 'IESA_Administrator_bot'))` — три вхождения в views_verification.py
- [ ] Вынести в `users/telegram/config.py` как функцию `bot_name()` (уже частично есть, проверить)

### 8c — `account_change_request_submit()` → возвращает JSON для HTMX, но без HTMX-заголовков
- [ ] Добавить `HX-Trigger` заголовки для обратной связи без перезагрузки страницы
- [ ] Или унифицировать через стандартный POST + redirect (убрать JSON путь)

### 8d — Inline CSS в шаблонах партнёрского портала
- [ ] `partner_calendar.html`, `partner_dashboard.html` — содержат большие блоки `<style>` прямо в шаблоне (>200 строк каждый)
- [ ] Вынести в `static/css/partner-calendar.css` и `static/css/partner-dashboard.css`

### 8e — Страница `test_telegram_view()` — HTML генерируется в Python строке
- [ ] views_verification.py ~150 строк: Python-строки `html = f"<html>...900 chars..."` — антипаттерн
- [ ] Перенести в шаблон `users/templates/users/test_telegram.html`

### 8f — `impersonate_user()` — нет трассировки оригинального администратора
- [ ] После impersonate нет записи «кто зашёл под кем»
- [ ] Добавить `request.session['impersonated_by'] = request.user.pk` и показывать баннер в базовом шаблоне

---

## BLOCK 9 — CSS: организация файлов ⚡💅
> 23 CSS-файла в одной плоской директории. Сложно ориентироваться.

### Предложенная структура
```
static/css/
  core/           variables.css, base.css, layout.css, responsive.css, utilities.css, animations.css
  components/     components.css, bootstrap.min.css, cmd-bar.css
  pages/          homepage.css, profile-page.css, partner-dashboard.css, dashboard.css, pages.css
                  product-cards.css, events-timeline.css, member-cabinet.css (к удалению в Block 1)
  plugins/        lightbox-custom.css, touch-gestures.css
  admin/          admin-enhanced.css, admin-appeal.css
  fixes/          dark-theme-fixes.css, style.css
```

### Шаги
- [ ] Создать поддиректории
- [ ] Перенести файлы
- [ ] Обновить все `{% load static %}` и `<link>` ссылки в шаблонах
- [ ] Проверить ManifestStaticFilesStorage — хеши перегенерируются автоматически при `collectstatic`
- [ ] `collectstatic` на локальной машине → нет ошибок

---

## BLOCK 10 — Тесты: покрытие критических путей 🏗️
> Сейчас тестов практически нет. Добавить минимальное smoke-покрытие для критических эндпоинтов.

### Приоритеты
- [ ] `log_visit()` — PIN validation, lockout after 10 attempts, idempotency window
- [ ] `edit_visit()` / `cancel_visit()` — 20-min window enforcement
- [ ] `invite_register()` — invalid token, already-used token, correct flow
- [ ] `insurance_agent_request()` — duplicate request prevention
- [ ] `dashboard_redirect()` — роутинг по роли
- [ ] `member_cabinet()` (до его удаления) → убедиться что вкладка в профиле выдаёт тот же контент

---

## Резюме проблем по категориям

### Архитектурные (системные)
| # | Проблема | Блок |
|---|----------|------|
| A1 | `views_verification.py` — 1600 строк, монолит | Block 7 |
| A2 | LocMemCache не работает при 2+ dyno на Heroku | Block 6e |
| A3 | Нет сервисного слоя — бизнес-логика в view | Block 4 |
| A4 | Нет тестов для критических flows | Block 10 |

### DRY-нарушения
| # | Проблема | Блок |
|---|----------|------|
| D1 | Логика уведомлений о визитах × 3 | Block 2 |
| D2 | `MemberSearchForm` объявлен дважды | Block 2 |
| D3 | PIN-расчёт в двух местах (views.py + views_verification.py) | Block 1 / 3 |
| D4 | `try: partner_profile` после `@partner_required` | Block 8a |
| D5 | Bot name lookup × 3 | Block 8b |

### UX / Флоу
| # | Проблема | Блок |
|---|----------|------|
| U1 | `/auth/cabinet/` — отдельная страница для PIN без реального контента | Block 1 ⚡ |
| U2 | 3 роута (profile / dashboard / cabinet) путают пользователя | Block 5 |
| U3 | HTML в Python-строке в `test_telegram_view()` | Block 8e |

### Читаемость / Гибкость
| # | Проблема | Блок |
|---|----------|------|
| R1 | Magic numbers разбросаны (720, 6, 3600...) | Block 3 |
| R2 | Большие `<style>` блоки прямо в шаблонах | Block 8d |
| R3 | CSS в одной плоской директории (23 файла) | Block 9 |
| R4 | Inline HTML в Python в test_telegram | Block 8e |

---

*Последнее обновление: 2026-05-12 | Исполнитель: Claude Sonnet 4.6*
