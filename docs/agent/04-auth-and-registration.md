# 04 · Вход, регистрация, аккаунты

Подробная история и обоснования: `IESA_ROOT/docs/audits/2026-10-07-auth-registration/README.md`.
Тут — карта «что и где», включая **где лежат ключи**.

## Что есть на сайте

| Возможность | Где в коде | Заметки |
|---|---|---|
| Регистрация (3 шага) | `users/views/auth.py: RegisterView`, `users/forms.py`, `users/templates/users/register.html` | после успеха — автоматический вход и переход в профиль; согласие на членство обязательно |
| Вход | `LoginView` там же, `login.html` | по имени (без учёта регистра) **или e-mail**: `users/auth_backends.py` |
| Сброс пароля | `PasswordReset*View` в `auth.py`, шаблоны `password_reset_*.html`, письма `users/email/password_reset.*` | ссылка 2 ч; `/auth/password-reset/` |
| Подтверждение e-mail | `users/services/email_verification.py`, `/auth/email/verify/<token>/` | ничего не блокирует |
| Вход через соцсети | `users/social.py` (адаптеры), `users/allauth_urls.py`, `socialaccount/*.html`, `partials/_social_login.html` | библиотека `django-allauth`, подключён **только** OAuth-поток |
| Антибот | `users/antispam.py`, `partials/_antibot.html` | honeypot, подписанный таймер, Turnstile, одноразовые e-mail, лимиты в БД-кэше |
| Переключение аккаунтов | `users/account_switch.py`, `templates/partials/_account_switcher.html` | подписанная кука `iesa_accounts` |
| Очистка ботов | `python manage.py prune_bot_accounts` (по умолчанию dry-run; `--delete`) | |
| Политика конфиденциальности | `/privacy/` (`core/templates/core/privacy.html`) | **заглушка**: «готовится, всех уведомим» — заменить настоящим текстом |

Политика паролей: длина ≥ 8, не из популярных, не только цифры, не похож на логин. Правила «заглавная буква +
спецсимвол» **сняты намеренно** (мобильные менеджеры паролей не проходили) — классы остались в
`users/validators.py`.

## Где лежат ключи (значения НЕ в репозитории)

Все — переменные окружения DigitalOcean (App-Level, см. `03-hosting-and-deploy.md`).

### Google (вход через Google) — **включён**
- Переменные: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
- Консоль: `https://console.cloud.google.com/auth/overview?project=iesa-510918` (проект **IESA**, id
  `iesa-510918`; аккаунт Google Workspace `iesa@iesasport.ch`). Раздел «Google Auth Platform»:
  Clients → «IESA website» (Web application), Branding (домен `iesasport.ch`, ссылка на политику `/privacy/`),
  Audience (**In production**, тип External).
- Разрешённые origins: `https://iesasport.ch`, `https://www.iesasport.ch`.
  Redirect URI: `https://iesasport.ch/accounts/google/login/callback/` и то же для `www`.
- Секрет клиента показывается **один раз** при создании. Потерян — создать новый секрет в том же клиенте и
  обновить `GOOGLE_CLIENT_SECRET`.

### Cloudflare Turnstile (капча) — **включён**
- Переменные: `TURNSTILE_SITE_KEY` (публичный), `TURNSTILE_SECRET_KEY`.
- Панель: `https://dash.cloudflare.com/` → Turnstile → виджет «IESA website» (аккаунт `iesa@iesasport.ch`,
  режим Managed; домены `iesasport.ch`, `www.iesasport.ch`). Нужен только для виджета, DNS сайта не в Cloudflare.
- Нет ключей → проверка просто выключена (остальные защиты работают). Cloudflare недоступен → пускаем людей.
- Проверка Turnstile на локальной машине — тестовые ключи Cloudflare `1x00000000000000000000AA` /
  `1x0000000000000000000000000000000AA` (всегда проходят).

### Microsoft / Facebook / Apple — **код есть, ключей нет, не используем**
Кнопка появляется, когда заданы `MICROSOFT_*`, `FACEBOOK_*` или `APPLE_*` (имена — в `03-…`). Решение
пользователя: Facebook и Apple не нужны (платно); Microsoft — по желанию позже. Redirect URI всегда вида
`https://iesasport.ch/accounts/<провайдер>/login/callback/`.

### Почта (письма подтверждения, сброса пароля)
`CLEVERREACH_*` — см. `05-email-and-dns.md`.

## Правила соцвхода (не нарушать)

- E-mail, подтверждённый провайдером и совпавший с существующим участником → вход в его аккаунт.
- E-mail совпал, а провайдер его не подтверждает → **никогда не привязывать**, показать сообщение (иначе
  захват аккаунта).
- Новый участник → `membership_status='active'`, уникальный `username`, `email_verified_at` выставлен.
- У allauth подключены только `/accounts/<провайдер>/login/` и `/accounts/3rdparty/…`; его страницы
  входа/регистрации/пароля **не** подключать (обход антибота). Бэкенд `allauth.account…AuthenticationBackend`
  в `AUTHENTICATION_BACKENDS` **не добавлять** (пускал бы по неоднозначному e-mail).
- `django.contrib.auth.backends.ModelBackend` из `AUTHENTICATION_BACKENDS` **не убирать**: на него ссылаются
  уже выданные сессии и `login(..., backend=…)` в инвайтах/impersonate — иначе всех разлогинит.

## Антибот: что и сколько

Порог/места: `users/antispam.py` (письмо подтверждения — 3/ч на адрес, 10/сутки на аккаунт, 300/ч на сайт;
сброс пароля — 3/ч на адрес, 20/ч на IP; регистрация — 60 попыток/ч на IP) и `users/ratelimit_utils.py`
(регистрация 30 POST/ч, вход 40/ч, сброс 10/ч). Формы, которые принимают публичный POST, обязаны включать
`{% include "users/partials/_antibot.html" %}` и проверять `antispam.bot_problem(request)` во view.

## Тесты

`users/tests_auth_flows.py`, `tests_antibot_social.py`, `tests_account_switch.py`, `tests_email_verification.py`
(общий помощник `tests_support.human_fields()` — валидный токен таймера для POST). Добавляя публичную форму —
добавь тест на бота (нет токена → отказ).

## Подводные камни

- Кнопки провайдеров — отдельные `<form>`; **нельзя** вставлять их внутрь другой формы (внутренний `</form>`
  обрежет внешнюю). В `register.html` они вынесены над формой.
- **CSP `form-action`** (`IESA_ROOT/security_middleware.py`) действует и на редирект после POST: хосты провайдеров
  (`accounts.google.com` и др.) обязаны быть в списке, иначе кнопка входа крутится бесконечно. Новый провайдер —
  добавить его домен авторизации в `form-action`.
- DO-панель: после смены `GOOGLE_*` нужен деплой, иначе кнопки не появятся.
- Google-приложение в режиме *Testing* пускает только тест-пользователей — оставляй **In production**.
