# 02 · Устройство сайта IESA

Каталог: `IESA_ROOT/` (там `manage.py`). Python 3.11, Django 5.2.9, виртуальное окружение `.venv/` в корне
репозитория (не коммитится).

## Приложения Django

| Приложение | За что отвечает |
|---|---|
| `core` | Главная, преимущества, партнёры на карте, `AdminAppeal` (обращения), политика `/privacy/`, админ-аналитика, настраиваемый `CustomAdminSite` |
| `users` | **Главное.** Модель `User` (qr/uuid, TOTP-PIN, активность), вход/регистрация, профиль, партнёрский портал (визиты, календарь, аналитика), инвайты, Telegram-привязка, подтверждение e-mail, антибот, соцвход |
| `blog` | Посты (соцсеть), комментарии, лайки, события и регистрации на них, подписки на авторов |
| `gallery` | Фото/альбомы |
| `products` | Каталог товаров |
| `notifications` | Внутренние уведомления (опрос по HTMX, без WebSocket) |

Корень проекта (`IESA_ROOT/IESA_ROOT/`): `settings.py` (+ `settings_addon.py`: логи, почта, CleverReach, Telegram),
`settings_dev.py` (локально), `urls.py`, `security_middleware.py` (CSP и заголовки; HTMX-перехват логина),
`cleverreach_email_backend.py`, `storage.py` (DigitalOcean Spaces), `protected_media_views.py`.

## Где что искать

- **Вход / регистрация / профиль**: `users/views/` (`auth.py`, `profile.py`, `onboarding.py`, `partner.py` …),
  `users/forms.py`, шаблоны `users/templates/users/`. URL: префикс `/auth/` (`users/urls.py`).
- **Модель пользователя**: `users/models.py` (`User`, `Partner`, `Visit`, `InviteToken`, `AccountChangeRequest` …).
- **Почта**: `users/email_service.py` (`_send` → CleverReach, запасной SMTP), письма подтверждения —
  `users/services/email_verification.py`, шаблоны `users/templates/users/email/`.
- **Антибот и лимиты**: `users/antispam.py`, `users/ratelimit_utils.py`.
- **Общие шаблоны**: `templates/base.html`, `templates/partials/` (`_navbar.html`, `_footer.html`, `_tour.html`).
- **Статика**: `static/css`, `static/js` (`tour.js`, `touch-gestures.js` …), `static/service-worker.js` (PWA-кэш;
  страницы `/auth/login|register|password-reset|email|partner` намеренно не кэшируются; версия кэша в файле).
- **Переводы**: `locale/{uk,de,fr}/LC_MESSAGES/django.po` + собранный `.mo` (оба коммитятся). Основной язык
  интерфейса — английский (msgid = английский текст); дополнительно `uk`, `de`, `fr`. Контент моделей
  переводится через `django-modeltranslation` (`translation.py` в приложениях).
- **Тесты**: `users/tests*.py`, `blog/tests*.py` и др. (`python manage.py test`, см. `07-local-run-and-tests.md`).

## Принятые соглашения

- Новые строки интерфейса оборачивай в `{% trans %}` / `gettext`; для новых msgid добавляй переводы uk/de/fr и
  пересобирай `.mo` (в репозитории так делалось скриптом через `polib`). На деплое `start.sh` ещё раз
  синхронизирует и компилирует переводы.
- Стили: тёмная тема, красный акцент (`#dc2626`); шрифт полей ввода ≥ 16 px (иначе iOS приближает страницу);
  цели нажатия ≥ 44 px; на экранах ≤ 640 px проверяй форму вручную в мобильной эмуляции 375×812.
- Файлы в репозитории частично с CRLF, частично с LF — не «чини» окончания строк целыми файлами.
- Статика на проде хешируется (`CompressedManifestStaticFilesStorage`): ссылка `{% static 'x' %}` на
  несуществующий файл **ломает рендер страницы** (ValueError) только на проде. Перед пушем проверяй (см. 07).
- Rate-limit (`django-ratelimit`, `block=True` по умолчанию): счётчик в `LocMemCache` отдельно в каждом
  процессе. Устойчивые счётчики (почта, регистрация по IP) — в БД-кэше (`antispam.throttle`).
- Фоновые задачи отсутствуют (нет Celery); уведомления — опросом HTMX.

## Особенности модели доступа

Роли: обычный участник (`membership_status='active'` сразу после регистрации), партнёр (`is_partner`),
staff/superuser, «президент». Подтверждение e-mail **ничего не блокирует** (только баннер) — это осознанно.
