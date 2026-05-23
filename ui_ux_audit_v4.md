# IESA Sport — UX/UI Audit v4 (ACR + Validation Round, 2026-05-23)

> Контекст: после релиза v3 (audit v3 — все 13 блоков + хотфиксы) пользователь дал
> большой пакет фидбэка по ACR-форме, валидации, регистрации, PIN в профиле,
> уведомлениям и админ-функционалу.
> Структура: 12 блоков. По очереди — пользователь пишет «Делаем блок N».

---

## 📋 ОГЛАВЛЕНИЕ

| # | Блок | Приоритет | Ориент. время |
|---|------|-----------|---------------|
| 1 | ACR форма: убрать минимум 50 символов в description, новый placeholder | 🔴 высокий | 15 мин |
| 2 | BUSINESS CATEGORY — перевести опции и группы (uk/fr/de) | 🔴 высокий | 30 мин |
| 3 | Placeholder во всех формах — явно отличается от текста (italic + opacity) | 🟡 средний | 30 мин |
| 4 | Ошибки валидации — рядом с полем, понятный текст, aria-describedby | 🔴 высокий | 1 ч |
| 5 | Регистрация: блокировать переход между шагами при ошибках валидации | 🔴 высокий | 1 ч |
| 6 | ACR: динамическая форма по desired_type (partner/staff/president) | 🔴 главный | 2 ч |
| 7 | ACR: First/Last name отдельные поля + новый choice 'president' | 🟡 средний | 30 мин |
| 8 | PIN сразу в профиле после регистрации — проверить все гейты | 🟡 средний | 20 мин |
| 9 | TG/site-уведомления о ACR-заявке — debug + фикс если не работает | 🔴 высокий | 30 мин |
| 10 | Django admin: ACR action — Approve (с выбором роли) / Reject | 🔴 главный | 1.5 ч |
| 11 | Profile badges — гибкое отображение всех ролей экосистемы | 🟡 средний | 1 ч |
| 12 | ACR на отдельной странице `/auth/account-upgrade/` + manage existing | 🟡 средний | 1.5 ч |

**Суммарное время**: ~12 часов (2-3 дня по 1-2 блока).

---

## BLOCK 1 — ACR: минимум description = 0, новый placeholder

### Проблема
- `acr_form.html:117-120`:
  ```html
  <textarea name="reason" ... minlength="50"></textarea>
  <div class="acr-hint"><span id="acr-char-count">0</span> / 2000 chars (min. 50)</div>
  ```
- Юзер видит `Минимум 70 символов` (видимо предыдущая версия), считает что должно быть необязательно.
- Placeholder сейчас: `Describe your business/role and why you want to join IESA. What value can you offer to members?`

### Решение
- Убрать `minlength="50"` (или поставить `0`).
- Убрать hint `(min. 50)`.
- Новый placeholder (попросить расширенно):
  > «Опишите свою деятельность и почему хотите присоединиться к IESA. Можете указать дополнительные контакты для связи (Telegram, WhatsApp, рабочий email), специализацию, опыт, что угодно — это поможет нам быстрее обработать заявку.»
- Перевести на uk/fr/de через `sync_translations.py`.

### Файлы
- `users/templates/users/partials/acr_form.html`
- `scripts/sync_translations.py`

---

## BLOCK 2 — BUSINESS CATEGORY переводы (9 групп + 40+ опций)

### Проблема
- На скриншоте — выпадающий список категорий полностью на английском.
- Группы: Sports & Fitness, Health & Wellness, Insurance & Financial Services, Retail & Equipment, Professional Services, Education & Events, Travel & Outdoor, Food & Hospitality, Other.
- Опции (40+): Gym / Fitness Center, Martial Arts School, Yoga / Pilates Studio, etc.

### Решение
- Добавить в `KNOWN_TRANSLATIONS` в `scripts/sync_translations.py` все 9 названий групп + все 40+ опций на uk/fr/de.
- Прогнать `python scripts/sync_translations.py` → обновятся .po + .mo.

### Файлы
- `scripts/sync_translations.py` (расширить KNOWN_TRANSLATIONS)
- `locale/*/LC_MESSAGES/django.po` + .mo (автоматически)

---

## BLOCK 3 — Placeholder явно отличается от введённого текста

### Проблема (повтор из v3 блок 7b, но не везде применено)
- В ACR форме (на скриншоте): placeholder «root» для FULL NAME выглядит так же как введённый текст. Юзер не понимает: уже введено или это пример.
- Также в `acr_form.html:128-140` и других полях.

### Решение
Стиль placeholder во всех ACR-полях:
- `font-style: italic`
- `opacity: 0.55` (заметно тусклее введённого текста)
- Если в placeholder автоматически вставляется текущее значение юзера (например `placeholder="{{ user.email }}"` + `value="{{ user.email }}"`) — убрать автоподстановку. Либо placeholder, либо value, но не одновременно одинаковый текст.

### Файлы
- `users/templates/users/partials/acr_form.html` (CSS + структура)
- `users/templates/users/profile.html` (CSS блока `.acr-input::placeholder`)

---

## BLOCK 4 — Ошибки валидации: понятные + рядом с полем

### Проблема (скриншот 1)
- Ошибка: «* Це поле обов'язкове.» — внизу формы, без указания **какого** поля.
- Юзер не понимает что заполнить.

### Решение
1. **Backend** (`users/views/profile.py:account_change_request_submit`):
   - Возвращать `errors: {field_name: [messages]}` вместо общего `error`.
2. **Frontend** (`acr_form.html` JS submit handler):
   - Очищать все предыдущие inline-ошибки.
   - Для каждого `field_name` из ответа — найти `[name="field_name"]` и:
     - Добавить класс `.acr-input-error` (красный border)
     - Вставить `<div class="acr-field-error">` рядом с полем (под input)
     - Установить `aria-invalid="true"` + `aria-describedby="err-{field_name}"`
   - Если ошибка не привязана к полю — `acr-error-bar` сверху формы (как сейчас).
3. **HTML5 нативная валидация**: добавить `pattern`, `minlength`, `type="email"` где надо — браузер сам покажет понятную ошибку до отправки.

### Файлы
- `users/views/profile.py` (или где `account_change_request_submit`)
- `users/templates/users/partials/acr_form.html` (CSS + JS)

---

## BLOCK 5 — Регистрация: блокировать переход при невалидных полях

### Проблема
- Юзер может нажать «Continue» на шаге 1 (Account) даже если пароль не валиден или email пустой.
- Сейчас валидация только на server-side при submit.

### Решение
1. **Шаг 1 (Account)** — `Continue` disabled пока:
   - username не валиден (live-check возвращает ok)
   - email не валиден (live-check)
2. **Шаг 2 (Password)** — `Continue` disabled пока:
   - password1 не соответствует критериям (len ≥ 8, uppercase, number, special)
   - password1 === password2 (match)
3. **Шаг 3 (Confirm)** — submit disabled пока:
   - membership_consent НЕ отмечен (уже сделано)
   - Все предыдущие шаги валидны (повторная проверка)

### Файлы
- `users/templates/users/register.html` (JS — расширить step-validation в существующем мульти-степ-handler)

---

## BLOCK 6 — ACR: динамическая форма по desired_type 🔴 главный

### Проблема
- Юзер выбирает «Association Staff (IESA)» — но форма требует business_category, address. Эти поля не подходят для частного лица (программист-волонтёр без бизнеса).
- Юзер физически не может подать заявку.

### Решение — show/hide поля по `desired_type`

**Когда desired_type = `partner` (External Partner):**
- ✅ business_category (required)
- ✅ address (required)
- ✅ first_name + last_name (required, отдельно)
- ✅ contact_phone
- ✅ contact_telegram
- ✅ contact_email
- ✅ reason / description

**Когда desired_type = `association_staff`:**
- ❌ скрыть business_category (или показать узкий выбор — программист, дизайнер, юрист, координатор)
- ❌ скрыть address
- ❌ скрыть contact_telegram (по запросу пользователя)
- ✅ first_name + last_name
- ✅ contact_phone
- ✅ contact_email
- ✅ reason / description (короткий — чем хочешь помогать)

**Когда desired_type = `president`** (новая категория, см. блок 7):
- Только first_name + last_name + contact_phone + contact_email.
- Submitting → создаёт заявку, админ approve вручную.

### Реализация
- JS toggle: `[data-acr-field]` data-attributes + `[data-show-when-desired]="partner"`
- При выборе desired_type → показать поля с `data-show-when-desired*=value` или без `data-show-when-desired` (общие)

### Файлы
- `users/templates/users/partials/acr_form.html` (data-атрибуты + JS toggle)
- `users/views/profile.py` (backend: не требовать поля если desired_type=`staff`)
- `users/models.py` AccountChangeRequest: добавить first_name / last_name отдельно (или использовать сплит contact_name) — см. блок 7

---

## BLOCK 7 — First/Last name отдельные поля + president choice

### Проблема
- Сейчас `contact_name` — одно поле. Хочется first_name + last_name **отдельно**.
- Нет роли «Президент» в DESIRED_TYPE_CHOICES.

### Решение
1. **Модель `AccountChangeRequest`** (`users/models.py:734`):
   - Добавить `first_name = CharField(max_length=100)`
   - Добавить `last_name = CharField(max_length=100)`
   - `contact_name` оставить (deprecated) или вычислять `f"{first_name} {last_name}".strip()`
   - В `DESIRED_TYPE_CHOICES`: добавить `('president', _('President of Association'))`
   - Создать migration.

2. **Форма ACR** — заменить одно поле FULL NAME на два:
   ```html
   <input name="first_name" placeholder="John" required>
   <input name="last_name"  placeholder="Doe"  required>
   ```

### Файлы
- `users/models.py`
- Новая migration `0031_*`
- `users/templates/users/partials/acr_form.html`

---

## BLOCK 8 — PIN сразу в профиле после регистрации (проверка гейтов)

### Проблема (повтор из v3 block 3a)
- Пользователь говорит «я уже просил, но ты не сделал».
- В блоке 3a v3 я убрал гейт `membership_status == 'active'` вокруг `#pin-section`. Также в blocks 2-3 v3 добавлен `membership_consent` — теперь юзер всегда `active` после регистрации.
- **Возможный остаток**: где-то ещё проверяется доступ к PIN (например в context_processor, view, или контекст профиля передаёт `current_pin=None`).

### Решение
1. Найти все места `current_pin` в profile views и template:
   ```bash
   grep -rn "current_pin\|get_current_pin" IESA_ROOT/
   ```
2. Убедиться что `profile.html` всегда получает `current_pin` (даже если `membership_status` НЕ active).
3. Если view передаёт `current_pin=None` для inactive — изменить логику: PIN всегда доступен если есть `totp_secret`.
4. **Проверить визуально на тестовом аккаунте**: зарегистрироваться → войти → есть ли PIN.

### Файлы
- `users/views/profile.py` (передача `current_pin` в context)
- `users/templates/users/profile.html` (рендеринг PIN-секции)

---

## BLOCK 9 — TG/site уведомления о ACR не пришли

### Проблема
- Юзер подал заявку → в Django admin запись появилась, но **не получил** TG/site-уведомление.
- В блоке 4 v3 hotfix я добавил `_notify_admins_account_upgrade` через signal `post_save` на `AccountChangeRequest`.

### Возможные причины
1. **Signal не зарегистрирован** — `notifications/apps.py` загружает `signals.py`, но import ошибся (impоrt `Visit` или `AccountChangeRequest` упал → весь файл failed).
2. **AdminNotificationProfile** для админа не имеет `account_upgrade` в `telegram_events` / `site_events`.
3. **`exclude_user_id`** — если админ подал заявку сам себе, я его исключил.
4. **TG send fail** — chat_id не привязан или send_message упал silently.

### Решение
1. Проверить логи на «account_upgrade notification failed» / «AdminNotificationProfile query failed».
2. Открыть Django admin → AdminNotificationProfile → убедиться что у root отмечены `account_upgrade` в **обоих** списках (telegram_events + site_events).
3. Добавить explicit logging при срабатывании signal — `logger.info("[signals] account_upgrade triggered for %s", instance.pk)`.

### Файлы
- `notifications/signals.py` — debug logging
- (если нужно) Django admin → проверить чекбоксы у root

---

## BLOCK 10 — Django admin: ACR Approve/Reject actions 🔴 главный

### Проблема (фидбэк пользователя)
- В Django admin есть запись `AccountChangeRequest`, но **нет функционала**:
  - Approve → автоматически выдать партнёра / staff / president (создать `Partner` запись / поставить `is_staff=True`)
  - Reject → пометить статус + причина
  - Создать связанный `Partner` объект для external_partner

### Решение
В `users/admin.py` для `AccountChangeRequest`:
1. **Кастомные actions** в `actions = []`:
   ```python
   @admin.action(description="✅ Approve & assign role")
   def approve_request(self, request, queryset):
       for acr in queryset:
           if acr.desired_type == 'partner':
               # Создать Partner объект из ACR
               from users.models import Partner
               Partner.objects.create(
                   user=acr.user,
                   company_name=...,
                   business_category=acr.business_category,
                   ...
               )
               acr.user.is_partner = True
               acr.user.save()
           elif acr.desired_type == 'association_staff':
               acr.user.is_staff = True
               acr.user.save()
           elif acr.desired_type == 'president':
               # Кастом — например is_president поле или группа
               ...
           acr.status = 'approved'
           acr.save()
   ```
2. **Кастомный change view** — добавить большую кнопку «Approve & assign» прямо на странице ACR.
3. **Reject action** — `status='rejected'` + опционально `rejection_reason`.

### Файлы
- `users/admin.py` — расширить `AccountChangeRequestAdmin`
- `users/models.py` — добавить `rejection_reason` поле, возможно `is_president` BooleanField

---

## BLOCK 11 — Profile badges: гибкое отображение ролей

### Проблема (скриншот 2)
- Сейчас бейджи в hero профиля: Admin, Учасник, Верифікований.
- Юзер хочет более гибкое отображение, в зависимости от статуса:
  - is_superuser → 👑 Owner
  - is_staff → 🛡 Admin / Staff
  - is_partner → 🤝 Partner (внешний)
  - association_staff → 🏛 Association Staff (внутренний)
  - is_president → 👤 President
  - membership_status='active' → 🎫 Member
  - is_verified → ✓ Verified

### Решение
Найти `profile.html:200-215` (block с `.cab-badges`), переделать:
```html
{% if profile_user.is_superuser %}<span class="sb sb-owner">👑 Owner</span>{% endif %}
{% if profile_user.is_staff and not profile_user.is_superuser %}<span class="sb sb-staff">🛡 Staff</span>{% endif %}
{% if profile_user.is_president %}<span class="sb sb-president">👤 President</span>{% endif %}
{% if profile_user.is_partner %}<span class="sb sb-partner">🤝 Partner</span>{% endif %}
{% if profile_user.membership_status == 'active' %}<span class="sb sb-member">🎫 Member</span>{% endif %}
{% if profile_user.is_verified %}<span class="sb sb-verified">✓ Verified</span>{% endif %}
```

### Файлы
- `users/templates/users/profile.html` (cab-badges block)
- `users/models.py` (возможно добавить `is_president`)
- CSS для новых стилей `.sb-owner`, `.sb-president`

---

## BLOCK 12 — ACR на отдельной странице + manage existing

### Проблема
- Сейчас ACR форма — секция внизу профиля.
- Юзер хочет: отдельная страница `/auth/account-upgrade/`, доступная из quick-nav.
- Также продумать сценарии:
  - **User уже партнёр** → может подать на смену типа (partner → staff)?
  - **User уже staff** → может ли смена на partner?
  - **User president** → не нужно повышения
  - **Pending заявка** → видит статус, может **отменить** или **отредактировать**

### Решение
1. **View**: `users/views/profile.py` → `account_upgrade_page(request)`:
   - GET: рендерит `users/account_upgrade.html` (новая страница)
   - POST: тот же handler что сейчас (`account_change_request_submit`)
2. **URL**: `path('account-upgrade/', views.account_upgrade_page, name='account_upgrade_page')` (уже есть `account_change_request_submit`)
3. **Template** `users/account_upgrade.html`:
   - Extends `base.html`
   - Breadcrumb: Profile → Account Upgrade
   - Если pending → большая карточка с информацией + кнопка «Cancel application»
   - Если нет pending → форма (`{% include 'users/partials/acr_form.html' %}`)
   - Если уже партнёр/staff → форма для смены роли (другой текст в hero)
4. **Quick-nav** в profile.html: ссылка `Apply for partner` теперь ведёт на `/auth/account-upgrade/` (а не на `#acr-section`).
5. **Удалить** ACR секцию из profile.html — теперь там только профиль, без формы.
6. **Cancel application** — новый endpoint `users:cancel_acr` → меняет status на `'cancelled'`.

### Файлы
- `users/urls.py` — новый path
- `users/views/profile.py` — новые views (page + cancel)
- Новый template `users/templates/users/account_upgrade.html`
- `users/templates/users/profile.html` — удалить ACR секцию, изменить ссылку quick-nav
- `users/models.py` — choices: добавить `'cancelled'` в STATUS_CHOICES

---

## Итог

Команда выполнения: «**Делаем блок N**» (например «Делаем блок 1»).

После завершения всех блоков:
- ACR будет на отдельной странице, форма красивая, поиск работает
- Все категории переведены
- Валидация понятная, регистрация безопасная
- PIN сразу виден
- Уведомления приходят с кликом на админку
- Django admin даёт Approve/Reject actions
- Badges в профиле адаптивно показывают все роли
