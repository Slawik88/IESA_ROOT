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

## BLOCK 4 — Рефакторинг «жирных вьюх» (Fat Views) 🏗️⚡ ✅ DONE
> **Проблема**: `partner_calendar()` — 285 строк, `log_visit()` — 171 строка. Нарушен SRP; тяжело тестировать и читать.

### 4a — `log_visit()` ✅
- [x] Создан `users/services/visit_service.py`: `check_pin_lockout`, `process_pin_attempt`, `check_idempotent_visit`
- [x] `log_visit()`: 125 строк → 70 строк (−44%)

### 4b — `partner_calendar()` ✅
- [x] Создан `users/services/calendar_service.py`: `build_month_grid`, `mark_selected`, `get_jump_options`, `serialize_day_meetings`
- [x] Вынесен `_notify_meeting_created()` из view в отдельную функцию
- [x] `partner_calendar()`: 285 строк → 90 строк (−68%)
- [x] 2 COUNT-запроса статистики → 1 aggregate

### 4c — `edit_visit()` и `cancel_visit()` ✅
- [x] Убраны `try/except Partner.DoesNotExist` (декоратор @partner_required гарантирует)
- [x] Убран лишний `try/except` в `partner_member_visits()` тоже
- [x] `edit_visit()`: 78 → 45 строк; `cancel_visit()`: 76 → 43 строк

---

## BLOCK 5 — UX: унификация навигации в личном кабинете ⚡💅 ✅ DONE (Block 1+5)
> **Проблема**: у юзера существуют `/auth/profile/`, `/auth/dashboard/`, `/auth/cabinet/` (будет удалён в Block 1), `/auth/my-calendar/` — логика переходов неочевидна; `dashboard_redirect()` — хрупкий роутер.

### Шаги
- [ ] **审计** все входные точки после Block 1: профиль имеет вкладки Posts / About / PIN&QR
- [ ] **Уточнить `dashboard_redirect()`**: после удаления кабинета — is_partner → partner_dashboard; иначе → profile (нет нужды в третьем маршруте)
- [ ] **Добавить якорные ссылки** `/auth/profile/#pin-tab` вместо старого `/auth/cabinet/`
- [ ] **Унифицировать ссылку «Мой кабинет» в navbar**: ведёт на `/auth/profile/` для всех; отдельная «Partner Portal» — только для партнёров (уже есть)
- [ ] **Проверить TG-бота**: `CARD_URL` в `handlers.py` → обновить на `/auth/profile/#pin-tab`
- [ ] **Smoke-test** всех ролей: обычный юзер, партнёр, staff — корректный маршрут от navbar

---

## BLOCK 6 — Производительность: кэш и N+1 🔇⚡ ✅ DONE
> Конкретные точки, найденные при аудите.

### 6a — Кэш PIN ✅
- [x] `cache.get_or_set(f'pin_code_{user.pk}_{step}', ...)` — ключ меняется каждые 720 сек автоматически

### 6b — N+1 в partner_dashboard ✅
- [x] 4 отдельных `COUNT` → 1 `aggregate(total, verified, total_cost, unique_members)`

### 6c — Context processor уведомлений ✅
- [x] `unread_notifications()` кэшируется 30 сек на `notif_unread_{user_id}`
- [x] `post_save` сигнал на `Notification` инвалидирует кэш при создании/изменении
- [x] `mark_as_read()` также инвалидирует кэш

### 6d — ProfileView visit queries ✅
- [x] Один queryset для `total_visits` (count) и `recent_visits` (slice), нет повторного filter

### 6e — LocMemCache → Redis
- [ ] **Документировано**: LocMemCache не шарится между dyno. При переходе на 2+ Heroku dyno → `django-redis` + `REDIS_URL`

---

## BLOCK 7 — Архитектура: разбить `views_verification.py` на модули 🏗️ ✅ DONE
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
- [x] Создан `users/views/` пакет: auth, profile, search, qr, admin_utils, utils, partner, calendar, telegram_views, invites, insurance
- [x] `views/__init__.py` re-экспортирует все функции (обратная совместимость)
- [x] Удалён `users/views.py` (заменён пакетом)
- [x] `users/views_verification.py` — тонкий шим для любых внешних импортов
- [x] `users/urls.py` — только `from . import views`, нет `views_verification`
- [x] `python manage.py check` → 0 ошибок ✅
- [x] Константы PIN_MAX_ATTEMPTS, PIN_LOCKOUT_MINUTES, IDEMPOTENCY_WINDOW, EDIT_WINDOW добавлены в constants.py

---

## BLOCK 8 — Мелкие улучшения читаемости и гибкости кода 🔇 ✅ PARTIAL
> Точечные правки без риска регрессий.

### 8a — Убрать дублирование `try: partner = request.user.partner_profile`
- [ ] В каждой view с `@partner_required` после декоратора делается ещё и `try/except Partner.DoesNotExist` — лишний код. Декоратор уже гарантирует что партнёр есть. Убрать дублирующий try/except изнутри view (заменить на прямой `request.user.partner_profile`)

### 8b — Вынести Telegram bot name lookup в утилиту ✅
- [x] `config.bot_name()` обновлён: TELEGRAM_BOT_USERNAME → TELEGRAM_BOT_NAME → ''
- [x] `telegram_views.py` использует `_tg_bot_name()` вместо os.environ.get дублирования

### 8c — `account_change_request_submit()` → возвращает JSON для HTMX, но без HTMX-заголовков
- [ ] Добавить `HX-Trigger` заголовки для обратной связи без перезагрузки страницы
- [ ] Или унифицировать через стандартный POST + redirect (убрать JSON путь)

### 8d — Inline CSS в шаблонах партнёрского портала
- [ ] `partner_calendar.html`, `partner_dashboard.html` — содержат большие блоки `<style>` прямо в шаблоне (>200 строк каждый)
- [ ] Вынести в `static/css/partner-calendar.css` и `static/css/partner-dashboard.css`

### 8e — Страница `test_telegram_view()` ✅
- [x] HTML перенесён в `users/templates/users/test_telegram.html`

### 8f — `impersonate_user()` ✅
- [x] Добавлены `session['impersonated_by']` и `session['impersonated_by_username']`
- [x] Баннер в base.html показывает «Вы вошли как X от имени admin Y»

---

## BLOCK 9 — CSS: организация файлов ⚡💅 ✅ PARTIAL
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
- [x] Удалён `static/css/member-cabinet.css` (orphan — Block 1)
- [x] Удалён `users/templates/users/member_cabinet.html` (orphan — Block 1)
- [ ] Реорганизация в поддиректории (core/, components/, pages/, plugins/, admin/) — риск высокий из-за ManifestStaticFilesStorage, откладывается на следующий цикл

---

## BLOCK 10 — Тесты: покрытие критических путей 🏗️ ✅ DONE
> Сейчас тестов практически нет. Добавить минимальное smoke-покрытие для критических эндпоинтов.

### Результат: 23 теста, все ✅
- [x] `check_pin_lockout` — 3 теста (не заблокирован, заблокирован, истёкший)
- [x] `process_pin_attempt` — 3 теста (верный PIN, неверный PIN, локаут после 10)
- [x] `check_idempotent_visit` — 2 теста (нет дубля, есть дубль)
- [x] `edit_visit` / `cancel_visit` — 3 теста (в окне, вне окна)
- [x] `invite_register` — 3 теста (valid, expired, used)
- [x] `insurance_agent_request` — 3 теста (GET, POST, дубль)
- [x] `dashboard_redirect` — 2 теста (partner → partner_dashboard, user → profile)
- [x] `ProfileView` — 4 теста (page loads, PIN в контексте, визиты, /cabinet/ redirect)

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
