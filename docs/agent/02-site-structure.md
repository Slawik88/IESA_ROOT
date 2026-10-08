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
- **Правила UI (аудит 2026-10)** — токены в `static/css/variables.css`:
  - Анимируем только `transform`/`opacity` (+ дешёвые paint-свойства: цвет, тень, фильтр). **Никогда** не анимируем
    `width/height/top/left/margin/padding/gap/background-position`. Вместо `transition: all` пиши
    `transition: <время easing>; transition-property: var(--transition-props);`.
  - Полосы прогресса: `width:100%` + `transform: translateX(calc(var(--p) * 1% - 100%))`, значение кладём в `--p`.
  - Красный **текст** на тёмном — `var(--primary-text)` (`#f87171`, 5.7:1), не `var(--primary)` (4.0:1). Белый текст на
    красной кнопке — фон `#dc2626` и темнее. Текст `rgba(255,255,255,a)` — `a ≥ .5`; шрифт ≥ 11 px.
  - Зоны нажатия — `var(--tap-min)` (44 px) для `pointer: coarse`; на тач-экранах поля ввода ≥ 16 px.
  - `overflow-x: hidden` на `html/body` и `overflow: hidden` на предках ломают `position: sticky` — используй
    `overflow: clip`. Подпись иконочной кнопки прячь как visually-hidden, не `display:none` (иначе пропадает accessible name).
  - Необратимые действия (удаление) — с подтверждением (`hx-confirm` + переведённая строка).
  - **Мобильный «поток» (аудит 2026-10, этап 2)** — на телефонах страница — одна монолитная поверхность: блоки идут
    от края до края и разделены тонкой линией, а не рамкой-карточкой. Примитивы в `static/css/layout.css`
    (токены `--flow-gutter`, `--field-gap`, `--label-gap`, `--field-h`, `--bottom-nav-h`, `--bar-h` в `variables.css`):
    `.flow-section` / `.flow-card` (рамка только с 768 px), `.form-compact` (подпись 4 px над полем, 12 px между
    строками), `.seg` (сегментные вкладки: одна строка, прокручивается вбок, не переносится), `.action-bar`
    (Сохранить/Отмена 50/50, sticky над нижней навигацией — класс ставь **последним ребёнком формы** и не клади его
    в предка с `overflow: hidden/auto`, иначе sticky «приклеится» к предку; при открытом `.action-bar` FAB «наверх»
    поднимается выше него и прячется, пока в поле идёт ввод).
  - **Auth-каркас**: `users/auth_shell.html` + `static/css/auth-shell.css` (+ `static/js/auth-shell.js`) — общий вид входа,
    регистрации, сброса пароля, инвайтов и `socialaccount/*`: split-screen с 769 px, плоская форма на телефонах. Новая
    публичная страница аккаунта = `{% extends "users/auth_shell.html" %}` + блок `au_main` (панель бренда — `au_side`).
    Формы с `data-au-once` блокируют кнопку после первого нажатия.
  - **Главная на телефоне** (`static/css/home-mobile.css`, ≤767.98 px; десктоп не меняется): первый экран = hero + лента видов спорта +
    плитки-шорткаты в разделы; все списки карточек — свайп-ряды (`data-snap` на контейнере → CSS scroll-snap,
    точки рисует `static/js/mobile-showcase.js`). Новый свайп-ряд = добавить `data-snap` контейнеру карточек.
  - **Шаблоны без BOM.** Лишний U+FEFF в шаблоне просачивается в ответ перед `<!DOCTYPE>`: браузер включает quirks-режим и переносит
    `<head>` в `<body>` (так вела себя главная). Тест `core.tests.HtmlStartsCleanTests` ловит это; сохраняй шаблоны как UTF-8 **без BOM**.
  - Глобальные грабли, которые уже вылечены: `label[for]` и чекбоксы больше не получают `min-height: 44px`
    (из-за этого каждая подпись поля была 44 px и формы растягивались вдвое) — зона нажатия чекбокса это строка
    `label` вокруг него; поля ModelForm без `form-control` рендерились без ширины — классы задаются в форме.
- Файлы в репозитории частично с CRLF, частично с LF — не «чини» окончания строк целыми файлами.
- Статика на проде хешируется (`CompressedManifestStaticFilesStorage`): ссылка `{% static 'x' %}` на
  несуществующий файл **ломает рендер страницы** (ValueError) только на проде. Перед пушем проверяй (см. 07).
- Rate-limit (`django-ratelimit`, `block=True` по умолчанию): счётчик в `LocMemCache` отдельно в каждом
  процессе. Устойчивые счётчики (почта, регистрация по IP) — в БД-кэше (`antispam.throttle`).
- Фоновые задачи отсутствуют (нет Celery); уведомления — опросом HTMX.

## Особенности модели доступа

Роли: обычный участник (`membership_status='active'` сразу после регистрации), партнёр (`is_partner`),
staff/superuser, «президент». Подтверждение e-mail **ничего не блокирует** (только баннер) — это осознанно.
