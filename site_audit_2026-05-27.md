# IESA Sport — аудит багов сайта (2026-05-27)

> Найдены конкретные баги и риски при пробеге по коду. Каждый блок — независимая
> единица работы: «делаем блок N» → я фикшу именно эти пункты, коммичу, иду дальше.
>
> Блоки отсортированы по приоритету (🔴 критично → 🟢 косметика).

---

## 🔴 Блок 1 — Кнопка регистрации не кликабельная (КРИТИЧНО)

**Файл:** [register.html:437-501](IESA_ROOT/users/templates/users/register.html#L437-L501)

**Симптом (подтверждён пользователем):** после ввода ника и email кнопка «Continue»
остаётся серой / не реагирует на клик.

**Корневая причина:**
- `window._regValidity = {un: false, em: false, ...}` — стартовое значение `false`.
- В `isStepValid(1)`: `if (V.un === false && username.length >= 3) return false`.
- `V.un` становится `true` ТОЛЬКО когда `fetch('/check-username/')` вернул `{available: true}`.
- Между keystroke и ответом проходит `setTimeout(500ms)` + сетевая задержка → пользователь жмёт кнопку **до** ответа → она disabled.
- В `.catch()` блок-fetch вообще **не сбрасывает state** → если сеть упала или API дал 500, кнопка disabled навсегда.

**Что чинить:**
1. Перевести `_regValidity` на tri-state: `null` (неизвестно) / `true` (ok) / `false` (явно занято).
2. В `isStepValid(1)` блокировать только при ЯВНОМ `V.un === false`.
3. Добавить sync-валидацию в момент клика (regex + минимальная длина), а проверку занятости — только через server-side при submit (server вернёт ошибку формы — это уже работает).
4. В `.catch(fetch)` сбрасывать state в `null` (не блокировать на network errors).

**Затрагивает:** регистрацию пользователей — **блокер для онбординга**.

---

## 🔴 Блок 2 — Security: 13 ссылок `target="_blank"` без `rel="noopener"`

**Проблема:** reverse tabnabbing — открытая через `target=_blank` страница получает доступ к `window.opener` и может перенаправить родительское окно на фишинговую страницу.

**Файлы (13 мест):**
- [templates/core/htmx/partner_modal.html:42, 45](IESA_ROOT/templates/core/htmx/partner_modal.html)
- [users/templates/users/connect_telegram_code.html:511](IESA_ROOT/users/templates/users/connect_telegram_code.html)
- [users/templates/users/profile.html:971, 974, 977, 980](IESA_ROOT/users/templates/users/profile.html)
- [users/templates/users/profile_public.html:223-225](IESA_ROOT/users/templates/users/profile_public.html)
- + ещё 3 шаблона

**Что чинить:**
- Везде где есть `target="_blank"` добавить `rel="noopener noreferrer"`.
- Делается одним глобальным regex-replace.

---

## 🟡 Блок 3 — 77 `<button>` без атрибута `type`

**Проблема:** в HTML5 у `<button>` без `type` дефолт = `type="submit"`. Если такая кнопка находится внутри `<form>`, нажатие на неё **сабмитит форму** — может ломать UX (например, кнопка-icon для toggle открывает submit вместо вызова JS).

**Топ файлов:**
- [base.html](IESA_ROOT/templates/base.html): 4 (back-to-top, qr-close, pwa-install, mbn-center-btn)
- [profile.html](IESA_ROOT/users/templates/users/profile.html): много (видны при поиске)
- [post_list.html, comments_section.html, event_detail.html](IESA_ROOT/blog/templates/blog/) и т.д.

**Что чинить:** добавить `type="button"` ко всем `<button>`, которые не должны сабмитить форму. Только реальные submit-кнопки оставить без type или явно `type="submit"`.

---

## 🟡 Блок 4 — Live-валидация без UX-индикации загрузки

**Файл:** [register.html:600-660](IESA_ROOT/users/templates/users/register.html)

**Проблема:**
- `setTimeout(500ms)` перед fetch для username, `600ms` для email.
- На медленной сети fetch может идти секунды.
- Пользователь видит, что что-то набрал, но индикатор `…` появляется коротко, дальше пусто.
- Если он быстро перейдёт к email — username state остаётся `false` и кнопка disabled непредсказуемо.

**Что чинить:**
1. Показывать spinner всё время пока fetch не вернулся.
2. На клик «Continue» если live-check ещё не закончен — показать сообщение «Ещё проверяем…» вместо silent-блока кнопки.
3. Уменьшить debounce до 300ms (быстрее реагирует).

---

## 🟡 Блок 5 — Hardcoded `/admin/` URLs в шаблонах (4 места)

**Файлы:**
- [core/admin_analytics.html:122, 123, 126](IESA_ROOT/core/templates/core/admin_analytics.html)
- [gallery/gallery.html:255](IESA_ROOT/gallery/templates/gallery/gallery.html)

**Проблема:** hardcoded paths `/admin/`, `/admin/users/user/`, `/admin/users/insuranceagentrequest/`, `/admin/gallery/photo/add/`. Если Django admin будет перенесён на `/dj-admin/` или подобное — ссылки сломаются молча.

**Что чинить:** заменить на Django `{% url 'admin:index' %}`, `{% url 'admin:users_user_changelist' %}` и т.п.

---

## 🟡 Блок 6 — `insurance_agent.html`: msgid на русском (нарушение i18n)

**Файл:** [insurance_agent.html](IESA_ROOT/users/templates/users/insurance_agent.html)

**Проблема:** ~33 msgid написаны на русском (`{% trans "Здоровье и жизнь" %}`, `{% trans "Личный агент" %}` и т.д.). Это нарушение стандарта Django i18n (msgid должны быть на исходном языке — EN). В прошлой сессии переводы добавлены, но шаблон стоит привести к стандарту.

**Что чинить:**
1. Заменить все msgid на английский (`{% trans "Health & life" %}` и т.д.).
2. В .po файлах добавить новые msgid и удалить старые русские.
3. Скомпилировать .mo.

---

## 🟢 Блок 7 — UX мелочи в шаблонах

**Что замечено при беглом просмотре:**
- [base.html:443](IESA_ROOT/templates/base.html): кнопка `back-to-top` без `type` (Блок 3, но тут отдельно потому что важна — кнопка floating справа внизу).
- [offline.html:36](IESA_ROOT/templates/offline.html): `onclick="window.location.reload()"` — inline handler, мог бы быть delegated.
- В нескольких местах HTMX-запросы используют `hx-post` к hardcoded путям, а не `{% url %}` (надо проверить).

**Что чинить:** мелкие шероховатости — после блоков 1-6.

---

## 🟢 Блок 8 — `scripts/test_view.py` мусор в репозитории

**Файл:** [IESA_ROOT/scripts/test_view.py](IESA_ROOT/scripts/test_view.py)

**Проблема:** dev-скрипт с `print()` отладкой попал в репозиторий — 20 print-инструкций. Это не runtime-баг, но мусор.

**Что чинить:** удалить файл или переместить в `tests/` с нормальными assertions.

---

## ⚠️ Не нашёл проблем (хорошие новости)

- ✅ `DEBUG = False` в production
- ✅ `SECRET_KEY` берётся из env
- ✅ `CSRF_TRUSTED_ORIGINS` настроен
- ✅ `ALLOWED_HOSTS` не пустой
- ✅ CSP middleware на месте
- ✅ Все fetch POST используют CSRF token (по результатам автопроверки)
- ✅ Нет open-redirect (`redirect(request.GET.get('next'))` без валидации) в views
- ✅ Нет TODO/FIXME комментариев
- ✅ Нет `console.log` в шаблонах
- ✅ Нет `except: pass`
- ✅ Все `<img>` имеют `alt`
- ✅ `LastOnlineMiddleware` уже использует cache rate-limit (5 мин)

---

## 📋 Как работаем

Пишите **«делаем блок N»** — я открываю файлы из блока, чиню только эти проблемы,
коммичу и пушу.

Рекомендую начать с **Блока 1** — это критичный блокер для регистрации новых
пользователей.
