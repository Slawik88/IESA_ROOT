# IESA Sport — UX/UI Audit v3 (Polish iteration, 2026-05-22)

> **Контекст**: продакшен `iesasport.ch` запущен. Аудит составлен по живому фидбэку от пользователя после релиза v2 (блоки 1–10).
> **Цель**: довести до идеала. Закрыть UX-долг по 17 пунктам, реализовать красивую белую тему, найти непереведённые места, починить кривое мобильное поведение.
> **Принцип работы**: один блок за раз. Юзер пишет «**Делаем блок N**» → я открываю этот файл, смотрю секцию блока N, делаю всё что там написано.
> **Принятые решения**:
> - Light theme → **полностью самостоятельная палитра** (блок 13).
> - Логотип → **CSS mix-blend-mode** (без замены файла).
> - Аудит хранится в `ui_ux_audit_v3.md` (этот файл).

---

## 📋 ОГЛАВЛЕНИЕ БЛОКОВ

| #  | Блок | Приоритет | Время | Покрывает пункты фидбэка |
|----|------|-----------|-------|--------------------------|
| 1  | Логотип: убрать «квадрат» через mix-blend-mode | 🔴 высокий | 15 мин | 3 |
| 2  | Поля login/register/connect-tg: focus НЕ белый | 🔴 высокий | 30 мин | 4 |
| 3  | Профиль: PIN для всех + `pts` letter-spacing + email | 🔴 высокий | 1 ч | 5, 7, 14 |
| 4  | Ширина: pcp-wrap, qa-onb-section, hero (container-limited) | 🟡 средний | 30 мин | 6 |
| 5  | Footer: убрать белую полосу + mobile bottom-nav overlap | 🔴 высокий | 30 мин | 8, 9 (часть) |
| 6  | Mobile: центральная QR-кнопка не работает + connect-tg fallback | 🔴 высокий | 1 ч | 9 (часть), 13 |
| 7  | Profile edit: соцсети overflow + placeholder неотличим | 🟡 средний | 1 ч | 10, 11 |
| 8  | Anchor навигация: подсветка целевого блока | 🟢 низкий | 30 мин | 12 |
| 9  | Telegram Bot: HTML escape + message length + asyncio проверка | 🔴 высокий | 1 ч | 16 |
| 10 | SSE notifications/stream: async-fix («took too long» warning) | 🟡 средний | 45 мин | из логов |
| 11 | STYLEGUIDE.md 404 + аудит не-стилизованных страниц | 🟡 средний | 1 ч | 2 (часть), 15 |
| 12 | i18n: найти все непереведённые места | 🟡 средний | 1.5 ч | 2 (часть) |
| 13 | **LIGHT THEME** — полная переработка (7 подблоков) | 🔴 главный | 5-7 ч | 2 (главное) |

**Суммарное время**: ~14-16 часов (можно по 1-2 блока в день).

---

## 🔥 BLOCK 1 — Логотип: убрать «квадрат» через mix-blend-mode

### Проблема (пункт 3 из фидбэка)
Логотип `static/img/logo.png` — PNG с прозрачным фоном, но **силуэт runner-а тёмно-серый**. На тёмном фоне сайта (`#0e0e18`) тёмный силуэт сливается с фоном и остаётся **визуальный квадрат** там где у PNG области с антиалиасингом + полутенями. Это особенно заметно на:
- Navbar (десктоп + мобиль)
- Login hero (`reg-logo`, `ar-logo`)
- Register hero (`reg-logo`)
- Email footer (если используется)

### Файлы
- `IESA_ROOT/static/img/logo.png` — сам файл (не трогаем)
- `IESA_ROOT/templates/partials/_navbar.html:13` — `<img ... class="navbar-logo">`
- `IESA_ROOT/users/templates/users/login.html` — поиск `.ar-logo img`
- `IESA_ROOT/users/templates/users/register.html:33` — `.reg-logo img`
- `IESA_ROOT/static/css/layout.css:88,692` — стили `.navbar-logo`

### Решение
Применить CSS-эффект, который "осветляет" тёмные пиксели логотипа в зависимости от фона:

```css
/* В layout.css (или новый блок в dark-theme-fixes.css) */
.navbar-logo,
.reg-logo img,
.ar-logo img,
.footer-logo img {
    /* Вариант A: mix-blend-mode — для тёмных PNG на тёмном фоне */
    mix-blend-mode: screen;
    /* Если screen слишком ярко → попробовать lighten */

    /* Вариант B (если A не подойдёт): brightness fix */
    /* filter: brightness(1.15) contrast(1.1); */
}

/* Для светлой темы — отключить mix-blend-mode */
:root[data-theme="light"] .navbar-logo,
:root[data-theme="light"] .reg-logo img,
:root[data-theme="light"] .ar-logo img {
    mix-blend-mode: normal;
    filter: none;
}
```

### Шаги
1. Открыть `dark-theme-fixes.css`, добавить блок `/* ── Logo blending ── */` в конец.
2. Применить `mix-blend-mode: screen` к 4 классам логотипа.
3. Проверить на 3 страницах: `/`, `/auth/login/`, `/auth/register/`.
4. Если `screen` даёт слишком красный/яркий результат → попробовать `lighten` или `filter: brightness(1.1)`.
5. Тестировать light-тему (в блоке 13 будет адресовано).

### Acceptance
- Лого визуально «сливается» с фоном везде где есть.
- Нет видимой границы PNG-rectangle.

---

## 🔥 BLOCK 2 — Поля login/register/connect-tg: focus НЕ белый

### Проблема (пункт 4)
На скриншотах пользователя: при фокусе на инпутах login/register они **визуально светятся / становятся слишком яркими**. Видно белый/светлый фон, плохо читается тёмный текст.

### Анализ (что в коде сейчас)
```
login.html:94      .af-wrap input:focus { background:rgba(220,38,38,.05); ... }
register.html:121  .rf-wrap input:focus { background:rgba(220,38,38,.04); ... }
register.html:150  background-color: rgba(220,38,38,.05) !important;  ← дубль с !important
```
Технически `rgba(220,38,38,.05)` — это **полупрозрачный красный 5%** на тёмном фоне. Не белый. Но при autofill браузера (Chrome/Edge) или при определённых условиях видно «светлый» эффект.

### Корневые причины
1. **Browser autofill** (особенно Edge/Firefox): хотя есть `-webkit-autofill` override, для Firefox это не сработает (Firefox использует `:autofill`).
2. **`box-shadow: 0 0 0 3px rgba(220,38,38,.12)`** при focus создаёт яркое красное «гало» вокруг инпута, что визуально выглядит «бело-красно».
3. **`background: rgba(220,38,38,.05)`** на тёмном фоне выглядит почти белым из-за наложения цветов.

### Решение
- Изменить focus-background на **более тёмный с лёгкой подсветкой**, а не светлее.
- Расширить autofill override на Firefox (`:autofill` pseudo).

### Файлы
- `IESA_ROOT/users/templates/users/login.html:94, 98` — `.af-wrap input:focus` + autofill
- `IESA_ROOT/users/templates/users/register.html:121, 124, 145-150` — `.rf-wrap input:focus` + autofill (есть дубль `!important`, стоит зачистить)
- `IESA_ROOT/users/templates/users/connect_telegram.html` — проверить такой же фикс
- `IESA_ROOT/static/css/dark-theme-fixes.css:487-489` — autofill override `-webkit-text-fill-color: #fff !important`

### Шаги
1. **login.html**: заменить
   ```css
   .af-wrap input:focus { 
     border-color: rgba(220,38,38,.6); 
     background: rgba(255,255,255,.04);          /* было rgba(220,38,38,.05) — стало нейтральнее */
     box-shadow: 0 0 0 3px rgba(220,38,38,.10);  /* было .12 → .10, менее агрессивно */
   }
   ```
2. **register.html**: аналогично + удалить дубль `!important` в строках 145-150 (это переопределение того же правила).
3. **Autofill cross-browser** (добавить в `dark-theme-fixes.css` глобально):
   ```css
   /* Firefox autofill */
   input:autofill,
   input:-moz-autofill {
     box-shadow: 0 0 0 1000px #12111c inset !important;
     -moz-text-fill-color: #fff !important;
   }
   /* Edge autofill (chromium) — same as webkit */
   input:-webkit-autofill {
     transition: background-color 9999s ease-in-out 0s;  /* trick: задерживаем встроенный bg */
   }
   ```
4. **connect_telegram.html** — найти и применить тот же подход к code-input полю.

### Acceptance
- При focus инпуты остаются **тёмными** с **тонкой красной обводкой**, без светлой подсветки.
- Browser autofill (Chrome/Firefox/Edge) сохраняет тёмный фон.

---

## 🔥 BLOCK 3 — Профиль: PIN для всех + `pts` letter-spacing + Physical Card email

### Подпункт 3a — PIN-код для всех (не только active)
**Пункт 5 фидбэка.** Сейчас у новых юзеров `membership_status != 'active'` показывается только QR. Пользователь хочет: **PIN и QR — единое целое, всегда вместе**.

**Анализ**: у каждого юзера в БД есть и `permanent_id` (для QR), и `pin_code` (по умолчанию генерируется). Проверка:
- `profile.html:207` — `{% if profile_user.membership_status == 'active' %}` — гейтит обе вещи
- `profile.html:663-672` — QR показывается только при active

**Файлы**:
- `IESA_ROOT/users/templates/users/profile.html:207, 222, 254, 663, 824, 870-872, 913` — все `{% if ... membership_status == 'active' %}` гейты
- `IESA_ROOT/users/models.py` — проверить дефолт `membership_status` (должен быть `active` для всех)
- `IESA_ROOT/templates/base.html:870, 887` — mobile bottom-nav QR гейт

**Решение**:
1. **Проверить дефолт в `User` модели**: `membership_status = models.CharField(... default='active')`. Если default — `'pending'`, то изменить на `'active'`. Это **главный фикс** — пользователь сам сказал "у юзеров по стандарту профиль активный".
2. После изменения дефолта — **новые юзеры будут active автоматически**, существующие нужно мигрировать:
   ```python
   # migrations/0030_default_active_membership.py
   from django.db import migrations
   def make_all_active(apps, schema_editor):
       User = apps.get_model('users', 'User')
       User.objects.filter(membership_status='pending').update(membership_status='active')
   class Migration(migrations.Migration):
       dependencies = [('users', '0029_drop_orphaned_messaging_tables')]
       operations = [migrations.RunPython(make_all_active, migrations.RunPython.noop)]
   ```
3. **Альтернатива (если хочется сохранить гейтинг)**: убрать `{% if membership_status == 'active' %}` вокруг PIN-блока в `profile.html`, оставить вокруг **Physical Card** (т.к. её действительно нет у новых).

**Acceptance**: новый юзер регистрируется → видит в профиле и PIN, и QR; mobile bottom-nav center показывает QR-кнопку.

---

### Подпункт 3b — Activity Level: «pts» буквы наезжают
**Пункт 14 фидбэка.** В блоке Activity Level число + «pts» отображается как `0pts` где `p` и `t` наезжают друг на друга.

**Причина**:
```
profile-page.css:215  .level-pts-big { font-size: 3.2rem; ... letter-spacing: -.05em; }
profile-page.css:216  .level-pts-lbl { font-size: .8rem; color: var(--muted); }
```
Inline-span `.level-pts-lbl` **наследует `letter-spacing: -.05em`** от родителя `.level-pts-big`. На 3.2rem `-0.05em = ~2.5px`, что огромно для мелкого текста.

**Решение**:
```css
/* profile-page.css:216 — заменить */
.level-pts-lbl { 
    font-size: .8rem; 
    color: var(--text-muted); 
    font-weight: 500; 
    letter-spacing: 0;          /* сбрасываем наследование */
    display: inline-block;
    margin-left: .35em;         /* отделяем от числа */
    vertical-align: baseline;
}
```

**Также** заменить `var(--muted)` (нерабочая) → `var(--text-muted)` (см. блок 9b прошлого аудита).

**Acceptance**: «pts» читаемо рядом с числом, не наезжает.

---

### Подпункт 3c — Physical Card: неправильный email
**Пункт 7 фидбэка.** `profile.html:872` — текст «Not yet issued — contact **admin**@iesasport.ch». Корректный email — `iesa@iesasport.ch` (видно в `_footer.html:27`).

**Решение**:
```diff
- {% trans "Not yet issued — contact admin@iesasport.ch" %}
+ {% trans "Not yet issued — contact iesa@iesasport.ch" %}
```
**Внимание**: т.к. меняется msgid, обновить `.po` файлы переводов (uk, en, ru).

**Поиск**: `grep -r "admin@iesasport" IESA_ROOT/` — мог встречаться ещё где-то.

**Acceptance**: email корректный во всех местах; переводы обновлены.

---

## 🟡 BLOCK 4 — Ширина блоков: pcp-wrap, qa-onb-section, hero

### Проблема (пункт 6)
Блоки «Профіль — 0% complete» (`.pcp-wrap`) и «Get started — quick actions» (`.qa-onb-section`) **растянуты на 100% ширины**. На больших мониторах (1920px+) это выглядит как длинная узкая полоска через весь экран.

### Анализ
```
profile.html:364  .pcp-wrap { padding: .85rem 1.25rem; ... } 
profile.html:412  .qa-onb-section { padding: .85rem 1.25rem; ... }
```
Нет `max-width`, нет `.container-limited` wrapper. В то же время основной контент профиля внутри `.container-limited` (1200px).

### Решение
Опции (выбрать одну):
- **A** (рекомендую): обернуть оба блока в `<div class="container-limited">` — тогда они подчинятся общим ограничениям сайта.
- **B**: добавить `max-width: 1200px; margin: 0 auto;` прямо в CSS-правила `.pcp-wrap` и `.qa-onb-section`.
- **C**: вложить в существующий `.cab-wrap` (если он уже container-limited).

### Файлы
- `IESA_ROOT/users/templates/users/profile.html:468-503` (pcp-wrap блок), `:505-526` (qa-onb-section блок)
- `IESA_ROOT/static/css/profile-page.css` — где `.cab-wrap` (если есть) — проверить структуру

### Шаги
1. Прочитать секцию hero+бары в profile.html (строки ~460-530), понять обвёрстку.
2. Применить вариант A: обвернуть `.pcp-wrap` и `.qa-onb-section` в `<div class="container-limited">` (внутри hero-секции если она full-width, либо снаружи).
3. Проверить на 1920px и 2560px — должно ограничиваться 1200px.

### Acceptance
- На 1920px+ оба блока остаются в пределах 1200px центрального контейнера.
- На мобиле — занимают всю ширину как раньше.

---

## 🔥 BLOCK 5 — Footer: белая полоса + mobile bottom-nav overlap

### Подпункт 5a — Белая полоса над футером
**Пункт 8 фидбэка.** Над `.footer-enhanced` (тёмный) видна **светлая горизонтальная полоса** шириной во всю страницу.

**Возможные причины** (нужно определить точно при выполнении блока):
1. **Body или main имеет белый/светлый background-color** (наследуется от Bootstrap дефолтов на каких-то страницах).
2. **`.container-limited-main-pad`** имеет `padding-bottom: 4rem` (layout.css:469), что само по себе не должно быть белым — но если есть `background: white` где-то выше — тогда полоса.
3. **Какой-то inline-стиль** в шаблоне (например `<section>` с белым фоном).
4. **`homepage.css:1656 background: white`** — `.partner-card-compact .btn-outline-primary` (но это кнопка, не полоса).
5. **`utilities.css:879`** и **`responsive.css:1271`** — есть `background: white` правила, нужно проверить контекст.

**Шаги диагностики**:
1. В Chrome DevTools на странице где видна полоса → inspect полосу → найти класс/тег.
2. Подозреваемые: `main`, `body`, `.container-limited-main-pad`, любая секция с `bg-white` или `bg-light` Bootstrap-классом.

**Решение** (после диагностики):
- Если виноват `body` — `body { background: var(--bg-body) !important; }` в base.css.
- Если виноват `.container-limited-main-pad` — убрать любой белый bg.
- Глобальный фикс: в `dark-theme-fixes.css` добавить `body, main, .main-header-pad { background: var(--bg-body); }`.

### Подпункт 5b — Mobile: nav перекрывает футер
**Пункт 9 (часть)**: на телефонах `.mobile-bottom-nav` (fixed, bottom:0) перекрывает нижнюю часть футера.

**Анализ**:
```
responsive.css:201   main#main-content { padding-bottom: calc(72px + env(safe-area-inset-bottom)) !important; }
```
Сейчас padding-bottom добавляется к `main`. Но **футер** находится ВНУТРИ или СНАРУЖИ main? В `base.html:120-131`:
```html
<main class="main-header-pad" id="main-content" role="main">
    {% block content %}...{% endblock %}
</main>
{% include "partials/_footer.html" %}   ← футер СНАРУЖИ main
```
Футер снаружи → `padding-bottom` на main НЕ помогает футеру. Поэтому на мобиле bottom-nav (fixed) перекрывает футер.

**Решение**:
```css
/* responsive.css в @media (max-width: 767.98px) */
.footer-enhanced {
    padding-bottom: calc(72px + env(safe-area-inset-bottom));
}
/* Альтернатива (если контент короткий): */
body {
    padding-bottom: calc(72px + env(safe-area-inset-bottom));
}
main#main-content { padding-bottom: 0 !important; }  /* убрать со main */
```

**Файлы**:
- `IESA_ROOT/static/css/responsive.css:200-203` — текущий фикс (на main)
- `IESA_ROOT/static/css/responsive.css:1078-1085` — секция футера для мобиля

### Acceptance
- Белая полоса больше не видна над футером на десктопе.
- На мобиле футер полностью виден, не перекрывается bottom-nav.

---

## 🔥 BLOCK 6 — Mobile: QR-кнопка не работает + connect-tg fallback

### Подпункт 6a — Центральная QR-кнопка не работает
**Пункт 9 (часть)**: «центральная красная кнопка с иконкой qr кода — не работает».

**Анализ**:
```
base.html:870  {% if user.membership_status == 'active' and user.permanent_id %}
base.html:872  <button class="mbn-item mbn-center-btn mbn-qr-btn" id="mbn-qr-btn" ...>
```
Кнопка показывается ТОЛЬКО при `membership_status == 'active'`. JS-обработчик:
```
base.html:466-491  qrBtn.addEventListener('click', openQR);
```

**Если пользователь видит QR-кнопку, но клик не работает**, причины:
1. **JS не загружен** (после ошибки в другом месте).
2. **Overlay z-index** конфликтует.
3. **Pointer-events: none** где-то наследуется.

**Если пользователь видит «+» кнопку (mbn-actions-btn), но ОЖИДАЕТ QR** — корневая проблема в том, что `membership_status != 'active'` (см. **блок 3a**).

**Решение**: после реализации **блока 3a** (membership_status default → active) — кнопка QR будет показываться. Если и после этого клик не работает — посмотреть консоль на ошибки JS.

### Подпункт 6b — TG-бот «не найден» → ручной поиск
**Пункт 13 фидбэка.** Когда `https://t.me/IESA_Administrator_bot` не открывается (бот недоступен в регионе пользователя), нужен **fallback**: «попробуй найти вручную: `@IESA_Administrator_bot`».

**Файлы**:
- `IESA_ROOT/users/templates/users/connect_telegram.html` — основная страница привязки
- Поиск: `grep -r "t.me/IESA" IESA_ROOT/`

**Решение** — добавить в connect_telegram.html (после основной кнопки):
```html
<details style="margin-top:1rem;">
    <summary style="cursor:pointer;color:rgba(255,255,255,.6);font-size:.85rem;">
        {% trans "Bot link doesn't work? Try manual search" %}
    </summary>
    <div style="margin-top:.5rem;padding:.75rem;background:rgba(255,255,255,.04);border-radius:8px;font-size:.82rem;color:rgba(255,255,255,.7);">
        <p>{% trans "1. Open Telegram app" %}</p>
        <p>{% trans "2. In the search field at the top, type:" %}</p>
        <code style="background:rgba(220,38,38,.12);padding:.25rem .5rem;border-radius:5px;color:#f87171;font-weight:700;cursor:pointer;" onclick="navigator.clipboard.writeText('@IESA_Administrator_bot');this.innerHTML='✓ {% trans "Copied" %}';">@IESA_Administrator_bot</code>
        <p style="margin-top:.5rem;">{% trans "3. Press 'Start' button in the bot" %}</p>
    </div>
</details>
```

### Acceptance
- После блока 3a: QR-кнопка появляется у всех юзеров и работает.
- На connect_telegram странице есть раскрывающийся блок с инструкцией по ручному поиску бота.

---

## 🟡 BLOCK 7 — Profile Edit: соцсети overflow + placeholder неотличим

### Подпункт 7a — «Соціальні мережі та посилання» уходит за экран
**Пункт 10 фидбэка.** На мобиле блок с соц-сетями в `profile_edit.html` (заголовок «Соціальні мережі та посилання (приклади нижче)») **обрезается справа** — половина за экраном.

**Файлы**:
- `IESA_ROOT/users/templates/users/profile_edit.html` — найти inline-блок с заголовком "Соціальні мережі"
- Скорее всего: `<div style="display:grid;grid-template-columns:1fr 1fr;...">` или `flex` без `flex-wrap`

**Решение**:
1. Найти блок (grep `Соціальні\|Social\|GitHub:.*Telegram:`).
2. Применить медиа-запрос:
   ```css
   @media (max-width: 575.98px) {
       .pe-social-examples { grid-template-columns: 1fr; }   /* было 1fr 1fr */
       .pe-social-grid    { grid-template-columns: 1fr; }
   }
   ```
3. Заголовок «(приклади нижче)» вынести на новую строку на мобиле.

### Подпункт 7b — Placeholder неотличим от введённого текста
**Пункт 11 фидбэка.** В формах соц-сетей плейсхолдер визуально такой же как введённый текст → юзер не понимает что это пример.

**Анализ**: проверить CSS для `input::placeholder` в profile_edit.html. Часто проблема — placeholder имеет тот же цвет что и обычный текст.

**Решение**:
```css
/* В profile_edit.html или profile-page.css */
.pe-form input::placeholder,
.pe-form textarea::placeholder {
    color: rgba(255,255,255,.25);            /* было ~.6 → ярче |||  стало .25 → тусклее */
    font-style: italic;                       /* отличаем италиком */
    opacity: 1;                               /* Firefox по умолчанию .5 */
}
.pe-form input::-webkit-input-placeholder { color: rgba(255,255,255,.25); font-style: italic; }
.pe-form input::-moz-placeholder           { color: rgba(255,255,255,.25); font-style: italic; opacity: 1; }
```

**Можно усилить эффект** — добавить иконку-подсказку слева от placeholder’а:
```html
<input type="text" placeholder="напр.: https://example.com" class="placeholder-hinted">
```
```css
.placeholder-hinted::placeholder::before { content: '💡 '; }
/* CSS не поддерживает ::before на placeholder — пропускаем, оставляем только цвет/style */
```

### Acceptance
- На мобиле блок соц-сетей помещается на экран (одна колонка).
- Placeholder визуально явно отличается от введённого текста (приглушённый italic).

---

## 🟢 BLOCK 8 — Anchor навигация: подсветка целевого блока

### Проблема (пункт 12)
Когда юзер кликает на якорную ссылку (например `/auth/profile/#pin-section`), браузер прокручивает к блоку, но **визуально не выделяет** куда мы попали. Юзер теряется.

### Решение
Добавить **CSS `:target` подсветку**:
```css
/* В base.css или components.css */

/* Любой блок к которому привели через #anchor — подсвечиваем на 1.5с */
:target {
    animation: target-flash 1.5s ease-out;
}
@keyframes target-flash {
    0%   { box-shadow: 0 0 0 4px rgba(220,38,38, 0); background-color: rgba(220,38,38, 0); }
    20%  { box-shadow: 0 0 0 4px rgba(220,38,38,.4); background-color: rgba(220,38,38,.08); }
    100% { box-shadow: 0 0 0 4px rgba(220,38,38, 0); background-color: rgba(220,38,38, 0); }
}

/* scroll-margin — чтобы при scroll-into-view не упиралось в sticky-navbar */
:target {
    scroll-margin-top: 80px;
}
```

### Файлы
- `IESA_ROOT/static/css/base.css` (или новый блок в `dark-theme-fixes.css` для совместимости с light)
- Применить ко **всем** id-якорям, или к специфическим классам (например `.flash-target`).

### Шаги
1. Добавить CSS-блок выше в `base.css`.
2. Проверить на: profile.html (`#pin-section`, `#qr-section`), любой пост блога с `#comments`.
3. Если для каких-то секций эффект мешает — добавить класс `.no-flash`.

### Acceptance
- При клике на якорную ссылку — секция куда мы попали мигает красным контуром на 1.5 секунды.
- `scroll-margin-top: 80px` предотвращает упирание в navbar.

---

## 🔥 BLOCK 9 — Telegram Bot: HTML escape + message length + async

### Подпункт 9a — `Unsupported start tag "task"` 
**Из логов** (16:41:07):
```
ERROR: Telegram sendMessage error: {'description': 'Bad Request: can\'t parse entities: Unsupported start tag "task" at byte offset 1525'}
```
Также:
```
ERROR: Telegram sendMessage error: {'description': 'Bad Request: message is too long'}
```

**Причина**: в `handlers.py:392-404`:
```python
async def handle_echo(chat_id: int, text: str, user_db) -> Reply:
    msg = (
        f"🔁 {text}\n\n"            # ← text вставляется СЫРЫМ
        "<i>" + _('I repeat...') + "</i>"
    )
```
Бот эхо-репитит произвольный текст юзера БЕЗ HTML-экранирования. Если в тексте есть `<task>`, `<script>` или любые `<...>` — это ломает HTML parsing на стороне Telegram API.

При очень длинном тексте (> 4096 символов) — Telegram возвращает `message is too long`.

**Файлы**:
- `IESA_ROOT/users/telegram/handlers.py:392-404` — `handle_echo`
- Проверить все остальные handlers — везде где есть `f"... {user_input} ..."` → надо escape.

**Решение**:
```python
import html  # Python stdlib

async def handle_echo(chat_id: int, text: str, user_db) -> Reply:
    # Экранируем HTML-специальные символы юзера ↓
    safe_text = html.escape(text, quote=False)
    
    # Обрезаем чтобы итоговое сообщение не превысило 4096
    if len(safe_text) > 3000:
        safe_text = safe_text[:3000] + "…"
    
    msg = (
        f"🔁 {safe_text}\n\n"
        "<i>" + _('I repeat your messages in test mode. '
                  'Use buttons or commands below.') + "</i>"
    )
    ...
```

Лучше — **завести helper** `_safe_html(text, max_len=3000)` в `handlers.py` и применять везде где вставляется user-input.

### Подпункт 9b — При неправильном коде привязки бот «зависает»
**Пункт 16 фидбэка.** Юзер вводит неправильный код привязки → бот молчит / зависает.

**Анализ**: при вводе произвольного текста срабатывает `handle_echo`. Если юзер должен был ввести 6-значный код, а ввёл что-то другое — нет специальной обработки. Echo пытается отправить — и падает на HTML injection (см. 9a).

**Решение** в `handle_echo`:
```python
async def handle_echo(chat_id: int, text: str, user_db) -> Reply:
    safe_text = html.escape(text[:200], quote=False)  # обрезаем сразу для безопасности
    
    # Если текст похож на код привязки (6 цифр) — даём специальный ответ
    cleaned = text.strip().replace(' ', '').replace('-', '')
    if cleaned.isdigit() and len(cleaned) == 6:
        msg = (
            "⚠️ <b>Код привязки вводится не в боте, а на сайте!</b>\n\n"
            f"Ваш код: <code>{cleaned}</code>\n\n"
            "1. Откройте /auth/connect-telegram/ на сайте\n"
            "2. Введите этот код в поле\n"
            "3. Нажмите «Привязать»"
        )
        kb = _kb([_url_btn("🔗 Открыть сайт", CONNECT_TG_URL)])
        return msg, kb
    
    # Обычный echo (с escape)
    msg = f"🔁 {safe_text}\n\n<i>" + _('I repeat...') + "</i>"
    ...
```

### Подпункт 9c — Проверка asyncio
**Пункт 16 (часть)**: «убедись ещё что ты используешь асинхронную библеотеку для бота asyncio».

**Анализ**:
- `client.py` — использует `httpx.AsyncClient` ✓ (после прошлого фикса)
- `dispatcher.py` — все handlers объявлены как `async def` ✓
- `handlers.py` — использует `sync_to_async` для DB-операций ✓

**Что проверить**:
- В webhook view (`telegram_views.py`?) — должна быть `async def telegram_webhook`, обрабатывающая POST.
- `apps.py` — webhook auto-register не должен блокировать startup.

**Файлы**:
- `IESA_ROOT/users/telegram_views.py` (или где-то в users/views.py) — `telegram_webhook` endpoint
- `IESA_ROOT/users/apps.py` — `ready()` метод с webhook регистрацией

**Решение**: проверить и при необходимости перевести на `async def`. Логи показывают:
```
INFO telegram_views Webhook received: type=message update_id=98935034
```
Значит webhook работает. Но **synchronous handler в asgi-context** может блокировать event loop. 

**Шаг**: открыть `telegram_views.py`, проверить:
- Это `async def`? Если да — ок.
- Внутри есть `await process_incoming_update(data)`? Если да — ок.
- Нет ли `time.sleep` или blocking IO? Удалить.

### Acceptance
- Бот корректно обрабатывает любые сообщения юзера (включая `<script>`, `<task>` и т.п.) без 400-х ошибок.
- Сообщения > 4096 символов обрезаются перед отправкой.
- Если юзер прислал 6 цифр — бот подсказывает где их ввести.
- Webhook полностью async.

---

## 🟡 BLOCK 10 — SSE `/notifications/stream/`: async fix

### Проблема (из логов)
Повторяющиеся WARNING’и:
```
WARNING Application instance <Task pending name='Task-114' ...> for connection 
<WebRequest at 0x... method=GET uri=/notifications/stream/ clientproto=HTTP/1.1> 
took too long to shut down and was killed.
```
Каждые 30-60 секунд в проде.

### Причина
`notifications/views.py:82-103` — функция `event_generator()` использует **синхронный `time.sleep(30)`** внутри view, привязанного к Django sync ORM (`Notification.objects.filter(...).count()`).

В Daphne (ASGI) это работает, но **блокирует event loop** на 30 секунд за раз. Когда Daphne пытается gracefully shutdown — задача «висит» в `time.sleep` и убивается принудительно через 60с.

### Решение
Переписать как **async generator** + `asyncio.sleep` + `sync_to_async` для ORM:

```python
import asyncio
from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse

@login_required
async def notification_stream(request):
    """SSE — теперь полностью async."""
    user_id = request.user.pk
    
    @sync_to_async
    def get_count():
        return Notification.objects.filter(recipient_id=user_id, is_read=False).count()
    
    async def event_generator():
        last_count = -1
        start = asyncio.get_event_loop().time()
        try:
            count = await get_count()
            last_count = count
            yield f"event: badge\ndata: {count}\n\n"
            
            while asyncio.get_event_loop().time() - start < 50:
                await asyncio.sleep(30)
                count = await get_count()
                if count != last_count:
                    last_count = count
                    yield f"event: badge\ndata: {count}\n\n"
                else:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
    
    response = StreamingHttpResponse(event_generator(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
```

### Файлы
- `IESA_ROOT/notifications/views.py:73-108` — переписать `notification_stream`
- `IESA_ROOT/notifications/urls.py` — проверить что роут не требует sync wrapper

### Caveats
- `@login_required` совместим с async-views (Django ≥ 4.1).
- Если в `IESA_ROOT/IESA_ROOT/asgi.py` ASGI handler не настроен на async — проверить (но Daphne сам async по природе).

### Acceptance
- WARNING `took too long to shut down` исчезает из логов.
- Badge продолжает обновляться у клиента каждые 30с.

---

## 🟡 BLOCK 11 — STYLEGUIDE.md 404 + не-стилизованные страницы

### Подпункт 11a — STYLEGUIDE.md 404
**Пункт 15 фидбэка.** Запрос `https://iesasport.ch/STYLEGUIDE.md` → 404.

**Причина**: STYLEGUIDE.md лежит в корне репо (`g:\IESA_ROOT\STYLEGUIDE.md`), но Django не обслуживает файлы из корня репо. Также в `components.html` (playground) есть `<a href="/STYLEGUIDE.md">` — ссылка на несуществующий URL.

**Решение** (выбрать одну):
- **A**: Скопировать `STYLEGUIDE.md` в `IESA_ROOT/static/STYLEGUIDE.md` → URL станет `/static/STYLEGUIDE.md`.
- **B**: Добавить URL pattern, который читает файл из FS и отдаёт как `text/markdown`:
  ```python
  # core/views.py
  @user_passes_test(lambda u: u.is_staff)
  def styleguide_md(request):
      from django.conf import settings
      import os
      path = os.path.join(settings.BASE_DIR.parent, 'STYLEGUIDE.md')
      with open(path, 'r', encoding='utf-8') as f:
          return HttpResponse(f.read(), content_type='text/markdown; charset=utf-8')
  # urls.py
  path('STYLEGUIDE.md', views.styleguide_md, name='styleguide_md'),
  ```
- **C**: Убрать ссылку из `components.html`, чтобы не звать несуществующий URL. Самое простое.

**Рекомендую C** (для staging) + опционально A (для общего доступа), потому что STYLEGUIDE — это dev-документ, его никто кроме нас не должен видеть в проде.

### Подпункт 11b — Аудит не-стилизованных страниц
**Пункт 2 фидбэка (часть)**: «накйди страници котоыре ещё не стилизованые, к примеру как эта https://iesasport.ch/auth/how-it-works/».

**Кандидаты на проверку** (страницы из URL):
- `/auth/how-it-works/` → `how_it_works.html` — есть собственные стили в `<style>` (см. lines 1-150). Нужно сравнить с общим дизайном — возможно нужно перенести в `pages.css` и проверить адаптивность.
- `/auth/insurance-agent/` → `insurance_agent.html` — 74KB страница, проверить.
- `/auth/activity-levels/` → `activity_levels_info.html` — упомянуто в design_audit.md как **полностью светлая тема**, не работает на тёмном фоне. Это критичный кандидат.
- `/auth/connect-telegram/` → проверить (часто посещается).
- `/auth/profile/c5499b9a-...` (QR overlay) — большой response 818 bytes, ок.
- Все error pages: 404, 500 — проверить что отрисованы в стиле сайта.
- `/admin/` — Django admin, не наш стиль (ок).

**Шаги аудита**:
1. Список URL → открыть каждую страницу.
2. Для каждой:
   - Использует ли `{% extends "base.html" %}` ? (Если да — наследует общий стиль.)
   - Есть ли inline `<style>` блок, противоречащий design tokens?
   - Адаптируется ли на мобиле?
   - Все ли строки переведены (`{% trans %}`)?
3. Список «**требует переделки**»: внести сюда в этот блок.

**Файлы кандидатов** (предварительно):
- `IESA_ROOT/users/templates/users/how_it_works.html`
- `IESA_ROOT/users/templates/users/insurance_agent.html`
- `IESA_ROOT/users/templates/users/activity_levels_info.html` (главный — light theme)
- `IESA_ROOT/users/templates/users/connect_telegram.html`
- `IESA_ROOT/templates/404.html`, `templates/500.html` (если есть)
- `IESA_ROOT/products/templates/products/product_detail.html`
- `IESA_ROOT/users/templates/users/users_search.html`

### Acceptance
- `/STYLEGUIDE.md` или возвращает 200, или удалён сам линк из playground.
- Список не-стилизованных страниц **зафиксирован** в этом блоке после ревизии.
- Для каждой страницы из списка решено: переделать / оставить / удалить.

---

## 🟡 BLOCK 12 — i18n: непереведённые места

### Проблема (пункт 2 фидбэка часть)
«найди места которые не переведены». На скриншотах видно смесь украинского и английского:
- «Welcome Back» (en) + «Ім'я користувача» (uk) — login
- «Access your account» (en) + «Зареєструватися» (uk) — login
- «Join the Community» (en) + «Реєстрація» (uk) — register
- «Continue» (en) + «Account» (en) + «Email адреса» (uk) — register stepper
- «Profile», «ACTIVITY LEVEL», «To Intermediate», «complete» — местами не переведены

### Шаги аудита (для блока 12)
1. **Сгенерировать `messages` файл**:
   ```bash
   cd IESA_ROOT
   python manage.py makemessages -l uk -l ru -l en --ignore=node_modules --ignore=static
   ```
2. **Открыть `locale/uk/LC_MESSAGES/django.po`** — найти msgid без msgstr.
3. **Поиск hardcoded английского** в шаблонах:
   ```bash
   grep -rn ">[A-Z][a-z]*\|>Sign\|>Welcome\|>Continue\|>Search" IESA_ROOT/templates IESA_ROOT/users/templates IESA_ROOT/blog/templates | grep -v "{% trans" | grep -v "{%trans"
   ```
4. **Список найденных** добавить в этот блок (вторая итерация).

### Подозреваемые места (из скриншотов и кода)
- `login.html` — заголовок «Access your account», подзаголовок «Enter your credentials...», фичи списка «Digital card & PIN code», «Posts, feed & community», «Events, RSVPs & benefits»
- `register.html` — «Join the Community», «Create your account...», stepper «Account», «Confirm»
- `register.html` — «Continue», «New member» badge
- Profile — «pts», «To Intermediate», «complete», «Get started — quick actions», «ACTIVITY LEVEL»
- Подпись плейсхолдеров — «type to search...», «e.g. johndoe», «your@email.com»
- Bot welcome message — на русском, нужно ли на украинском/английском?
- `STYLEGUIDE.md` — не переводить (dev doc).
- Footer copyright — «IESA Association. All rights reserved.» — должно переводиться.

### Файлы
- `IESA_ROOT/locale/uk/LC_MESSAGES/django.po` — добавить переводы
- `IESA_ROOT/locale/ru/LC_MESSAGES/django.po`
- `IESA_ROOT/locale/en/LC_MESSAGES/django.po` (база)
- Все шаблоны где не использован `{% trans %}` — обернуть.

### Шаги при выполнении блока
1. Прогнать `makemessages` локально (или на heroku через `heroku run`).
2. Получить список untranslated msgid.
3. Перевести все.
4. Сгенерировать .mo через `compilemessages`.
5. Закоммитить .po + .mo.
6. **Внимание**: после изменения msgid (например в блоке 3c — Physical Card email) нужно обновить переводы для нового текста.

### Acceptance
- На страницах login/register нет смеси языков — всё на одном.
- В .po файле нет `msgstr ""` (пустых переводов) для активных msgid.

---

## 🔴 BLOCK 13 — LIGHT THEME (полная переработка)

> Главный блок. ~5-7 часов. Разбит на 7 подблоков.
> **Решение**: полностью самостоятельная палитра, переработать как полноценную тему.

### Текущее состояние
В `base.html:747-765` есть всего ~15 строк CSS для `data-theme="light"`:
```css
:root[data-theme="light"] {
  --bg-body:      #f4f6fb;
  --bg-surface:   #ffffff;
  --text-primary: #0f172a;
  --text-muted:   #64748b;
  --bdr:          rgba(0,0,0,.1);
  --nav-bg:       rgba(255,255,255,.95);
}
```
Это **только базовые токены**. Все компоненты (cards, forms, buttons, hero, profile, dashboards) остаются тёмными → визуальное «лоскутное одеяло».

### Цель
Сделать light-тему **первого класса**, не хуже dark.

---

### 13a — Light Design Tokens (фундамент)

**Файлы**:
- `IESA_ROOT/static/css/variables.css` — добавить расширенный блок light-токенов
- ИЛИ создать новый `IESA_ROOT/static/css/light-theme.css`, подключённый через `base.html` после `dark-theme-fixes.css` с весом `[data-theme="light"]`

**Решение**: создать `light-theme.css` (загружается ПОСЛЕ всех тёмных стилей):

```css
/* ============================================================
   IESA LIGHT THEME — overrides для data-theme="light"
   Загружается ПОСЛЕ dark-theme-fixes.css.
   ============================================================ */

:root[data-theme="light"] {
    /* ── Surface scale (инверсия dark) ── */
    --surface-0:   #f8fafc;       /* фон страницы (было #0e0e18) */
    --surface-1:   #ffffff;       /* карточки (было #111118) */
    --surface-2:   #f1f5f9;       /* hover (было #1a1a24) */
    --surface-3:   #e2e8f0;       /* приподнятый */

    --bg-body:     #f8fafc;
    --bg-surface:  #ffffff;
    --bg-surface-hover: #f1f5f9;
    --bg-overlay:  rgba(255,255,255,.98);

    /* ── Text (WCAG AA на белом фоне) ── */
    --text-primary:   #0f172a;    /* 18:1 — заголовки */
    --text-secondary: #334155;    /* 11:1 */
    --text-muted:     #64748b;    /* 5.6:1 — мелкий текст */
    --text-light:     #94a3b8;    /* 3.1:1 — декоративный */
    --text-on-dark:   #0f172a;    /* инверсия */
    --text-on-dark-muted: #475569;

    /* ── Borders (на белом фоне) ── */
    --border-color:        rgba(0,0,0,.1);
    --border-color-light:  rgba(0,0,0,.06);
    --border-color-hover:  rgba(0,0,0,.18);
    --border-faint:        rgba(0,0,0,.04);
    --border-soft:         rgba(0,0,0,.08);
    --border-strong:       rgba(0,0,0,.15);
    --border-dark:         rgba(0,0,0,.08);
    --border-dark-hover:   rgba(0,0,0,.15);

    /* ── Greys (адаптированные для light) ── */
    --gray-50:  rgba(0,0,0,.025);
    --gray-100: rgba(0,0,0,.05);
    --gray-200: rgba(0,0,0,.08);
    --gray-300: rgba(0,0,0,.12);
    --gray-400: rgba(0,0,0,.25);
    --gray-500: rgba(0,0,0,.4);
    --gray-600: rgba(0,0,0,.55);
    --gray-700: rgba(0,0,0,.7);
    --gray-800: rgba(0,0,0,.85);
    --gray-900: rgba(0,0,0,.95);

    /* ── Тени (более выраженные на белом) ── */
    --shadow-card:       0 2px 10px rgba(0,0,0,.05), 0 1px 3px rgba(0,0,0,.04);
    --shadow-card-hover: 0 8px 24px rgba(0,0,0,.10), 0 3px 8px rgba(0,0,0,.05);
    --shadow-card-lg:    0 4px 16px rgba(0,0,0,.06), 0 1px 4px rgba(0,0,0,.04);

    /* ── Navbar / footer ── */
    --nav-bg:    rgba(255,255,255,.92);
    --footer-bg: #1e293b;    /* тёмный футер на светлом сайте — контрастно */

    /* ── Card gradients ── */
    --gradient-card:       linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
    --gradient-card-light: linear-gradient(145deg, rgba(0,0,0,.02) 0%, rgba(0,0,0,.01) 100%);
    --gradient-card-red:    linear-gradient(135deg, rgba(220,38,38,.04) 0%, rgba(185,28,28,.06) 100%);
    --gradient-card-blue:   linear-gradient(135deg, rgba(37,99,235,.04) 0%, rgba(30,78,216,.06) 100%);
    --gradient-card-amber:  linear-gradient(135deg, rgba(217,119,6,.04) 0%, rgba(180,67,9,.06) 100%);
    --gradient-card-emerald:linear-gradient(135deg, rgba(5,150,105,.04) 0%, rgba(4,120,87,.06) 100%);
}
```

**Шаги**:
1. Создать файл `IESA_ROOT/static/css/light-theme.css` с токенами выше.
2. Подключить в `base.html` ПОСЛЕ всех тёмных:
   ```html
   <link rel="stylesheet" href="{% static 'css/dark-theme-fixes.css' %}">
   <link rel="stylesheet" href="{% static 'css/partner-dashboard.css' %}">
   <link rel="stylesheet" href="{% static 'css/light-theme.css' %}">    <!-- NEW -->
   ```
3. Удалить старый блок light-темы (15 строк) из `base.html:747-765` — он перенесён в light-theme.css.

---

### 13b — Navbar / footer / bottom-nav

**Цели**:
- Navbar на светлой теме: белый фон с тонкой тенью, тёмный текст
- Footer: тёмный (как сейчас) — контрастно
- Mobile bottom-nav: белый фон, тёмные иконки, красная активная

**Что добавить в `light-theme.css`**:
```css
:root[data-theme="light"] {
    /* Navbar */
    .iesa-navbar { background: rgba(255,255,255,.92) !important; backdrop-filter: blur(20px); border-bottom: 1px solid rgba(0,0,0,.08); }
    .nav-link, .navbar-brand { color: #0f172a !important; }
    .nav-link:hover { color: var(--primary) !important; }
    .btn-nav-icon { color: #0f172a; }
    .btn-nav-icon:hover { background: rgba(0,0,0,.05); }
    .navbar-search-dropdown { background: #fff !important; border: 1px solid rgba(0,0,0,.08); }

    /* Profile dropdown */
    .prof-nav-drop-menu { background: #fff !important; border: 1px solid rgba(0,0,0,.08); }
    .pnd-user-name { color: #0f172a; }
    .pnd-item { color: #334155 !important; }
    .pnd-item:hover { background: #f1f5f9 !important; color: #0f172a !important; }

    /* Mobile bottom-nav */
    .mobile-bottom-nav { background: rgba(255,255,255,.97) !important; border-top: 1px solid rgba(0,0,0,.08); }
    .mbn-item { color: rgba(0,0,0,.55) !important; }
    .mbn-item.active { color: var(--primary) !important; background: rgba(220,38,38,.06) !important; }

    /* Footer остаётся тёмным (для контраста) */
    /* .footer-enhanced — без изменений */
}
```

---

### 13c — Cards / Forms / Buttons / Inputs

**Файлы для override** (всё в `light-theme.css`):

```css
:root[data-theme="light"] {
    /* Карточки */
    .card, .pp-card, .cab-card, .iesa-article, .notification-item {
        background: #fff !important;
        border-color: rgba(0,0,0,.08) !important;
        color: #0f172a;
    }
    .dash-stat-card { background: #fff !important; border: 1px solid rgba(0,0,0,.08); }
    .dash-stat-val { color: #0f172a !important; }
    .dash-stat-lbl { color: #475569 !important; }

    /* Inputs */
    .form-control, .form-select {
        background: #fff !important;
        border: 1.5px solid rgba(0,0,0,.12) !important;
        color: #0f172a !important;
    }
    .form-control:focus, .form-select:focus {
        background: #fff !important;
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 3px rgba(220,38,38,.12) !important;
        color: #0f172a !important;
    }
    .form-control::placeholder { color: rgba(0,0,0,.35) !important; }
    
    /* Login/Register inputs */
    .af-wrap input, .rf-wrap input, .rf-wrap select {
        background: #f8fafc !important;
        border: 1.5px solid rgba(0,0,0,.10) !important;
        color: #0f172a !important;
    }
    .af-wrap input:focus, .rf-wrap input:focus {
        background: #fff !important;
        border-color: rgba(220,38,38,.5) !important;
        box-shadow: 0 0 0 3px rgba(220,38,38,.12) !important;
    }
    
    /* Buttons остаются как есть (primary красный — нейтральный) */
    /* Только outline-buttons */
    .btn-outline-light, .btn-outline-secondary { color: #0f172a !important; border-color: rgba(0,0,0,.15) !important; }
    .btn-outline-light:hover { background: rgba(0,0,0,.05) !important; }
    
    /* Modal */
    .modal-content { background: #fff !important; color: #0f172a; }
    .modal-header, .modal-footer { border-color: rgba(0,0,0,.08) !important; }
    
    /* Dropdown */
    .dropdown-menu { background: #fff !important; border: 1px solid rgba(0,0,0,.08); }
    .dropdown-item { color: #334155 !important; }
    .dropdown-item:hover { background: #f1f5f9 !important; color: #0f172a !important; }
    
    /* Tables */
    .table { color: #0f172a; }
    .table th { background: #f1f5f9 !important; color: #0f172a; }
    .table-hover tbody tr:hover { background: #f8fafc !important; }
}
```

---

### 13d — Profile + Dashboards

**Файлы для проверки**: `profile.html`, `dashboard.css`, `profile-page.css`, `partner-dashboard.css`, `partner_dashboard.html`, `partner_analytics.html`.

```css
:root[data-theme="light"] {
    /* Profile */
    .cab-wrap, .cab-hero { background: linear-gradient(135deg, #f8fafc, #fff) !important; color: #0f172a; }
    .cab-name { color: #0f172a !important; }
    .cab-sub { color: var(--text-muted) !important; }
    .cab-card { background: #fff !important; }
    .cab-card-title { color: #475569 !important; }

    /* Activity Level pts */
    .level-pts-big { color: var(--primary) !important; }
    .level-pts-lbl { color: #64748b !important; }

    /* Visit History rows */
    .vh-item { background: #fff; border-color: rgba(0,0,0,.06); }
    .vh-partner { color: #0f172a; }
    .vh-service { color: #475569; }
    .vh-cost { color: #0f172a; }
    .vh-date { color: #64748b; }

    /* Partner dashboard sidebar */
    .dash-sidebar { background: #fff !important; border-right: 1px solid rgba(0,0,0,.08); }
    .dash-sidebar__brand { color: #0f172a; }
    .dash-nav-item { color: #334155 !important; }
    .dash-nav-item:hover, .dash-nav-item.active { background: rgba(220,38,38,.08) !important; color: var(--primary) !important; }

    /* Partner pp-wrap */
    .pp-wrap { background: #f8fafc !important; }
    .pp-card { background: #fff !important; border: 1px solid rgba(0,0,0,.08) !important; }
    .pp-btn-ghost { background: #fff !important; color: #0f172a !important; border-color: rgba(0,0,0,.12) !important; }
}
```

---

### 13e — Blog / Events / Comments

**Файлы**: `post_list.html`, `post_detail.html`, `cmd-bar.css`, comments.

```css
:root[data-theme="light"] {
    /* Post detail article */
    .pd-article { background: #fff !important; border: 1px solid rgba(0,0,0,.08) !important; }
    .pd-title { color: #0f172a !important; }
    .pd-content { color: #334155 !important; }
    .pd-content h1, .pd-content h2, .pd-content h3 { color: #0f172a !important; }
    .pd-content blockquote { border-left-color: var(--primary); color: #475569 !important; }
    .pd-meta { color: #64748b !important; border-bottom-color: rgba(0,0,0,.08); }
    
    /* Comments */
    .pd-comments-wrap { background: #fff !important; border: 1px solid rgba(0,0,0,.08) !important; }
    .pd-comment-form textarea { background: #f8fafc !important; border-color: rgba(0,0,0,.12) !important; color: #0f172a !important; }
    .pd-comment-form textarea:focus { background: #fff !important; }
    .cm-comment { background: #f8fafc; }
    
    /* Command bar */
    .cmd-bar { background: #fff !important; border: 1px solid rgba(0,0,0,.08) !important; }
    .cmd-input { background: transparent !important; color: #0f172a !important; }
    .cmd-input::placeholder { color: rgba(0,0,0,.35) !important; }
    .cmd-tab--active { background: rgba(220,38,38,.08); color: var(--primary); }
    .cmd-select { background: #f8fafc !important; color: #0f172a !important; border-color: rgba(0,0,0,.12); }
}
```

---

### 13f — Hero / Homepage / Misc

**Файлы**: `index.html`, `homepage.css`.

```css
:root[data-theme="light"] {
    /* Hero — переключаем градиенты */
    #hp-hero {
        background: 
            radial-gradient(ellipse 60% 40% at 15% 20%, rgba(220,38,38,.05) 0%, transparent 55%),
            linear-gradient(135deg, #f8fafc 0%, #ffffff 50%, #f1f5f9 100%) !important;
    }
    .hp-h2, .hero-title, .iesa-do-grid h3 { color: #0f172a !important; }
    .hp-sub { color: #475569 !important; }
    .hero-stat-num { color: var(--primary); }
    .hero-stat-label { color: #64748b; }

    /* Hero canvas — стираем (на белом частицы не видны) */
    #hp-hero-canvas { opacity: .3 !important; }

    /* Hero kicker */
    .hero-kicker { background: rgba(220,38,38,.08) !important; color: var(--primary) !important; border-color: rgba(220,38,38,.2); }

    /* Section eyebrows */
    .section-eyebrow { color: var(--primary); }

    /* iesa-do-grid items */
    .iesa-do-item { background: #fff !important; border: 1px solid rgba(0,0,0,.06) !important; box-shadow: var(--shadow-card); }
    .iesa-do-item h4 { color: #0f172a; }
    .iesa-do-item p { color: #475569; }

    /* Partner cards (homepage) */
    .partner-card-compact { background: #fff !important; border: 1px solid rgba(0,0,0,.08) !important; }

    /* Benefits */
    .benefit-card { background: #fff !important; border: 1px solid rgba(0,0,0,.08) !important; border-top: 4px solid var(--primary); }
    .benefit-card-title { color: #0f172a; }
    .benefit-card-description { color: #475569; }
}
```

---

### 13g — Theme toggle UX

**Цели**:
1. Кнопка переключения темы — более заметная, в правильном месте.
2. Сохранение выбора в localStorage уже есть — оставить.
3. **Системная тема по умолчанию** — `prefers-color-scheme: light`:
   ```js
   var saved = localStorage.getItem('iesa-theme');
   if (!saved) saved = matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
   ```
4. **Анимация переключения**: добавить `transition: background-color .25s, color .25s` на `body`, `card`, etc.

**Файлы**:
- `base.html:766-788` — расширить JS логику theme toggle
- `light-theme.css` — добавить smooth transitions

```css
:root[data-theme="light"] body,
:root[data-theme="light"] .card,
:root[data-theme="light"] .iesa-navbar,
:root[data-theme="light"] .iesa-article,
:root[data-theme="light"] .cab-card,
:root[data-theme="light"] .pp-card {
    transition: background-color .25s, color .25s, border-color .25s;
}
```

### Acceptance блока 13
- Переключение dark↔light работает плавно на ВСЕХ страницах.
- На light-теме все компоненты выглядят как первоклассный продукт (не «лоскутное одеяло»).
- На больших мониторах + мобиле light-тема не ломается.
- Auto-detect системной темы при первом заходе.

---

## ✅ Итог

| Блок | Описание | Время |
|------|----------|-------|
| 1 | Логотип mix-blend-mode | 15 мин |
| 2 | Input focus (login/register/connect-tg) | 30 мин |
| 3 | PIN+pts+email | 1 ч |
| 4 | Ширина блоков | 30 мин |
| 5 | Footer fix + bottom-nav overlap | 30 мин |
| 6 | QR mobile + TG fallback | 1 ч |
| 7 | Profile edit social overflow + placeholder | 1 ч |
| 8 | Anchor подсветка | 30 мин |
| 9 | TG bot HTML escape + async | 1 ч |
| 10 | SSE async fix | 45 мин |
| 11 | STYLEGUIDE 404 + un-styled audit | 1 ч |
| 12 | i18n untranslated | 1.5 ч |
| 13 | LIGHT THEME (7 подблоков) | 5-7 ч |

**Команда выполнения**: `"Делаем блок N"` (например «Делаем блок 1»).

---

## 📝 Заметки на полях

- Все commit-сообщения для блоков должны включать ссылку на пункт фидбэка (например `fix(ux/audit-v3-1): logo mix-blend-mode — feedback #3`).
- После блоков 1-9 (быстрые) → 1 коммит «polish v3 part 1».
- После блоков 10-12 (средние) → 1 коммит «polish v3 part 2».
- После блока 13 (light theme) → отдельный коммит «feat: light theme v2».
- В конце — обновить `STYLEGUIDE.md` с описанием light темы и new naming conventions.

> **Готов к команде «Делаем Блок N». Жду! 🚀**
