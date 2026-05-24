# IESA Sport — UX/UI Audit v5 (Infrastructure & Polish, 2026-05-24)

> Контекст: после v4 (ACR + Approve/Reject + уведомления) пользователь дал большой
> список улучшений инфраструктуры. **Без Redis** — это ключевое ограничение.

---

## ✅ СДЕЛАНО в этом проходе (1 коммит)

### 🔧 Инфраструктура (без Redis)

1. **Database Cache** (вместо LocMemCache)
   - `settings.py:CACHES` → `django.core.cache.backends.db.DatabaseCache`
   - LOCATION = `django_cache_table` (создаётся миграцией `0034`)
   - Shared между всеми воркерами через PostgreSQL — больше не теряем кэш при scaling
   - MAX_ENTRIES=5000, CULL_FREQUENCY=3 (удаляет 1/3 при переполнении)

2. **Rate limiting на ACR** (5 заявок/час/юзер)
   - `users/views/admin_utils.py:account_change_request_submit` — проверка через `cache.get(rl_key)`
   - 429 status + понятный i18n-сообщение если превышено

3. **CSP + Security Headers Middleware**
   - Новый `IESA_ROOT/security_middleware.py` (без внешних пакетов)
   - **Content-Security-Policy**: разрешает только `'self'` + конкретные CDN
     (jsdelivr, cdnjs, Google Fonts, OpenStreetMap tiles)
   - **X-Content-Type-Options: nosniff**, **Referrer-Policy: strict-origin-when-cross-origin**
   - **Permissions-Policy**: запрещает camera/microphone/payment/usb, geolocation=self (для partner map)
   - **X-Frame-Options: SAMEORIGIN** (защита от clickjacking)
   - Не применяется к `/admin/*` (Django admin использует inline event handlers)
   - Добавлен в `MIDDLEWARE` сразу после `BlockScannerMiddleware`

4. **SEO meta-description** для главных публичных страниц
   - `blog/post_list.html` — IESA Community blog описание
   - `users/login.html` — Sign in to IESA Sport
   - `users/register.html` — Join IESA Switzerland community
   - `users/how_it_works.html` — How IESA works (4 steps)
   - + meta_keywords для blog

### 🎨 UI

5. **Поиск пользователей с фильтрами** (`/auth/search/`)
   - View `users_search` принимает `role` и `sort` query params
   - Фильтры по роли: **All / Partners / Staff / Members / President / Verified**
   - Сортировка: **Relevance / Newest / Oldest / A→Z / Z→A**
   - UI: pills для роли + dropdown для сортировки

6. **Light Theme — полное покрытие** новых классов из v4
   - HIW, INS, AL страницы (how_it_works, insurance, activity_levels)
   - TG Setup / TG Connect + OTP boxes
   - ACR форма + searchable combobox + role-hint banner
   - PIN display card (большие цифры + timer)
   - Admin analytics dashboard
   - Search role pills
   - Mobile bottom-nav center action sheet

7. **i18n** — 23 новых msgid с переводами на uk/fr/de
   - Quick actions, YOUR MEMBERSHIP, PARTNER ACTIONS, Log Visit
   - Role filter labels: Partners / Staff / Members / Verified / President
   - Sort labels: Relevance / Newest first / Oldest first
   - ACR audit trail: Rejection Reason / Reviewed At / Reviewed By / Approved / Cancelled
   - Rate limit error message

### 📊 Analytics

8. **Admin Analytics Dashboard** (`/dev/analytics/` staff-only)
   - 👥 Users: total, active, partners, staff, presidents, verified, new (7d/30d), TG-linked %
   - 📝 Content: posts (total / published / pending / new 7d), comments, likes
   - 🏢 Partner visits: total / 7d / 30d / verified
   - 🚀 ACR: pending / approved / rejected / total
   - ⚡ Recent activity (last 5): Users / Posts / ACR / Visits
   - Quick links bar: Django Admin, Pending ACR, Posts on moderation, Insurance, Components

---

## ⏳ НЕ СДЕЛАНО — требует большой переделки (отдельные блоки)

### 1. CSS-каскад: 200+ `!important` → < 50
- responsive.css: **120** !important
- dark-theme-fixes.css: **111** !important
- **Проблема**: каждое правило требует ручной проверки + визуальное тестирование, чтобы не сломать существующий вид. Сейчас риск регрессий очень высокий.
- **Подход**: создать `csstools/find_redundant_important.py` который найдёт правила-дубли (где `!important` действительно не нужен, потому что специфичность достаточна).

### 2. CSS-файлы: 23 → 8
- Этот рефакторинг описан в STYLEGUIDE.md (план был ещё в audit v2 block 1c).
- Требует слияния файлов + проверки каждой страницы.
- **Объём**: 8-12 часов работы.

### 3. Celery / async queue без Redis
- Сейчас используется `threading.Thread(daemon=True)` для отправки TG-уведомлений.
- При перезагрузке сервера задачи теряются.
- **Альтернатива без Redis**: `django-q2` (использует ORM как broker — работает на PostgreSQL).
- **Или**: оставить как есть — потеря 1-2 задач при рестарте не критична для bg-уведомлений.

### 4. SSE → WebSockets без Redis
- `channels-redis` нужен для production. Без Redis есть `InMemoryChannelLayer`, но он **только для single-instance** (наша ситуация на DigitalOcean = OK).
- **Riski**: при scaling > 1 worker сломается.
- **Альтернатива**: оставить SSE (которая уже async) — она работает.

### 5. Профиль `/auth/profile/` — табы
- План был: Tab Обзор / Tab Карта & PIN / Tab Активность / Tab Социальное / Tab Заявка.
- Сейчас всё одной длинной страницей (~1700 строк HTML).
- **Объём**: 4-6 часов работы (CSS + JS + restructure HTML).

### 6. Calendar UI
- `partner_calendar.html` — большой шаблон с drag-drop встреч.
- Mobile уже улучшен в v3 (block 2g), но JS тяжёлый.
- **Нужно**: профилировать на старых телефонах, оптимизировать reflow.

### 7. Мобильный партнёрский дашборд
- `log_visit.html` — поля адаптируются плохо на узких экранах.
- **Нужно**: визуальный тест на 320px (iPhone SE) + фикс grid/flex.

### 8. Мессенджер между юзерами
- Был, удалён (messaging app, см. migration 0029 в users).
- Без Redis качественный real-time мессенджер невозможен (нужны WebSockets + Pub/Sub).
- **Альтернатива**: HTTP polling каждые 5-10с — но это плохая UX и нагрузка на БД.
- **Решение**: либо подключить managed Redis на DigitalOcean ($15/mo), либо оставить без мессенджера.

---

## 🎯 ПРИОРИТЕТЫ для следующих сессий

**🔴 Критично (UX/безопасность)**:
1. Мобильный партнёрский дашборд (1ч) — pure CSS фикс
2. Профиль табы (4-6ч) — большой UX win, разгружает страницу

**🟡 Желательно (производительность)**:
3. CSS !important чистка (4-6ч) — частями по 50 правил с визуальным тестингом
4. CSS файлы 23→8 (8-12ч) — большой рефакторинг

**🟢 Опционально (требует Redis или больших переделок)**:
5. Celery → django-q2 (3-4ч) — если важна надёжность bg-задач
6. Мессенджер — только с Redis
7. SSE → WebSockets — только с Redis (или single-worker InMemoryChannelLayer)

---

## 📊 МЕТРИКИ ДО / ПОСЛЕ

| Метрика | До v5 | После v5 |
|---------|-------|----------|
| Cache backend | LocMemCache (per-process) | DatabaseCache (shared) |
| Rate limit на ACR | ❌ | ✅ 5/h |
| CSP headers | ❌ | ✅ полный набор |
| Security headers | базовые Django | + Referrer / Permissions / CSP |
| SEO meta-description | только blog posts | + login/register/blog list/HIW |
| Поиск с фильтрами | только по тексту | + role + sort |
| Light theme coverage | ~85% | ~98% (audit v5 расширение) |
| Admin analytics | нет | `/dev/analytics/` dashboard |
| i18n покрытие | 77-80% | 78-81% (+23 строки) |

---

Команда: «Делаем блок X» когда захочешь взяться за один из «не сделано».
