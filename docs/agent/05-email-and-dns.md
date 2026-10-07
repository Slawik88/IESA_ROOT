# 05 · Почта сайта и DNS (iesasport.ch)

## Кто что отправляет

| Что | Через что |
|---|---|
| Письма сайта (подтверждение e-mail, сброс пароля, визиты) | **CleverReach** REST API (`CLEVERREACH_*` в DO). Код: `users/email_service.py::_send`, `IESA_ROOT/cleverreach_email_backend.py` (бэкенд Django, когда заданы ключи). Отправитель `noreply@iesasport.ch`, имя «IESA Sport». При сбое CleverReach — запасной SMTP (`settings_addon.py`, Resend, если задан `RESEND_API_KEY` — **сейчас не задан**) |
| Почтовые ящики людей (`iesa@iesasport.ch` и др.) | **Google Workspace** (MX `aspmx.l.google.com` + alt1–4) |
| Админ-уведомления в Telegram | `TELEGRAM_BOT_TOKEN` (бот-администратор сайта), см. `users/telegram_notify.py` |

Локально (`settings_dev.py`) письма печатаются в консоль.

### Порядок каналов (важно)

1. **SMTP — основной, если заданы `EMAIL_HOST` + `EMAIL_HOST_PASSWORD`** (код: `settings_addon.py`,
   `users/email_service.py::_send`; флаг `EMAIL_PREFER_SMTP`). CleverReach тогда — только запасной.
2. Иначе (так было до 2026-10-07 и пока переменных нет) — CleverReach, запасной SMTP.

**Инцидент 2026-10-07:** CleverReach отвечал `401 Unauthorized` на `POST /v3/mailings.json`, а запасного SMTP
не было (`Connection refused`) → письма подтверждения и сброса пароля не уходили. Причина 401 не установлена
(токен/refresh-токен приложения CleverReach). Способ отправки через CleverReach — «рассылка + sendpreview» —
хрупкий, он рассчитан не на транзакционные письма; надёжнее настоящий SMTP.

### Как включить SMTP через Google Workspace (рекомендуемо)

1. В аккаунте `iesa@iesasport.ch`: myaccount.google.com → Безопасность → включить двухэтапную проверку →
   «Пароли приложений» → создать пароль «IESA site» (16 символов; показывается один раз). Если пункта нет —
   его закрыл администратор Workspace (admin.google.com → Безопасность).
2. DigitalOcean → App-Level Environment Variables (см. `03-hosting-and-deploy.md`):
   `EMAIL_HOST=smtp.gmail.com`, `EMAIL_PORT=587`, `EMAIL_HOST_USER=iesa@iesasport.ch`,
   `EMAIL_HOST_PASSWORD=<пароль приложения, Encrypt>`, `EMAIL_FROM=IESA Sport <iesa@iesasport.ch>`.
   (Адрес `noreply@` как отправитель потребует отдельного алиаса «Отправлять как» — отправляй с `iesa@`.)
3. После деплоя проверка в Console: `python manage.py cr_test_send --to <адрес>` (команда использует общий
   путь `_send`) и письмо «Resend confirmation» из профиля.
SPF/DKIM для Google уже настроены (см. таблицу DNS ниже), отдельно ничего добавлять не нужно.
Лимит Workspace — порядка 2000 писем/сутки на ящик; для объёмов больше — Resend/Postmark + DNS-записи.

## DNS-зона

Зона `iesasport.ch` — в **DigitalOcean**: `https://cloud.digitalocean.com/networking/domains/iesasport.ch`
(NS `ns1/ns2/ns3.digitalocean.com`). Записи (на 2026-10-07):

| Тип | Хост | Значение / смысл |
|---|---|---|
| A / AAAA | `@` | адреса приложения DO (`162.159.140.98`, `172.66.0.96`, IPv6 — управляются DO; **не менять руками**) |
| MX | `@` | Google Workspace (приоритеты 1, 5, 5, 10, 10) |
| TXT | `google._domainkey` | DKIM Google Workspace |
| TXT | `crsend._domainkey` | DKIM **CleverReach** (подпись писем сайта) |
| TXT | `@` | **SPF**: `v=spf1 include:_spf.google.com include:spf.crsend.com ~all` (добавлен 2026-10-07) |
| TXT | `_dmarc` | **DMARC**: `v=DMARC1; p=quarantine; pct=25; rua=mailto:iesa@iesasport.ch; adkim=r; aspf=r` (добавлен 2026-10-07) |
| CNAME | `iesasport.ch` (по факту хост `iesasport.ch.iesasport.ch`) | мусорная запись, безвредна, можно удалить |

Записи `www` **нет** (хотя Django разрешает хост `www.iesasport.ch`). Если понадобится — добавить CNAME
`www` → `iesasport.ch.` (или адрес приложения DO) и домен в настройках приложения.

### Зачем SPF/DMARC

Без них любой мог рассылать письма «от @iesasport.ch». Сейчас SPF жёсткий мягко (`~all`), DMARC в режиме
карантина для 25 % подозрительных писем с отчётами на `iesa@iesasport.ch`. Через 2–3 недели без жалоб на
недоставку поднять `pct=25` → `100`, при желании `~all` → `-all`.

### Проверка записей из терминала (PowerShell)

```powershell
Resolve-DnsName iesasport.ch -Type TXT -Server ns1.digitalocean.com      # SPF
Resolve-DnsName _dmarc.iesasport.ch -Type TXT -Server ns1.digitalocean.com
```

### Добавляя нового отправителя писем

Любой новый сервис, шлющий «от iesasport.ch» (Resend, Mailchimp…), нужно внести: `include:` в SPF (одна
SPF-запись на домен, **не создавай вторую**), DKIM-записи, которые он выдаст, и проверить DMARC.

## Антиспам по почте (почему так)

Сайт не должен рассылать письма на чужие адреса: лимиты на письма в `users/antispam.py` (3/ч на адрес и т.д.),
одноразовые адреса не принимаются, формы закрыты Turnstile. Подробности — `04-auth-and-registration.md`.
