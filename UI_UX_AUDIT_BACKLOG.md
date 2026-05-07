# UI/UX AUDIT BACKLOG — IESA ROOT
> Глубокий аудит фронтенда. Дата генерации: **2026-05-06**.
> Аудитор: Senior UI/UX Engineer / Frontend Architect.
> Объём анализа: **42** шаблона, **15** CSS-файлов, **13** JS-файлов.
> Метод: статический анализ кода, трассировка cascade, оценка mobile/desktop/touch‑юзабилити.
>
> **Не исправлять вручную** — этот файл является приоритизированной очередью. Формат: `[ ]` — не сделано, `[x]` — выполнено.
>
> ## Ключевые системные находки (TL;DR)
> 1. **`!important` использован 1157 раз** в 11 CSS‑файлах (153 в `dark-theme-fixes.css`, 464 в `utilities.css`, 192 в `admin-enhanced.css`). Это «specificity war» — любое исправление каскада требует ещё одного `!important`.
> 2. **42 из 42 шаблонов содержат блоки `<style>`**. Десятки `<style>` повторяют одни и те же стили (auth‑страницы, кабинеты), часть содержит `:root` с переопределением CSS‑переменных дизайн‑системы.
> 3. **Дизайн‑система разорвана надвое**: `components.css:1-1349` использует `var(--*)` из `variables.css`, а `components.css:1350-2040` — это «вмёрженный» старый `modern-design.css` со СВОИМ `:root`, своими (конфликтующими) тенями, и дубликатами `.card`, `.btn`, `.btn-primary`, `.form-control`, `.modal-content`, `.alert`, `.badge`, `.table`, `.pagination`. Второй блок выигрывает по каскаду и портит первый.
> 4. **`base.css:357-419` — корень проблемы белого фона в тёмной теме**: 41 селектор скопом получает `--bg-surface: #ffffff` (включая `.card`, `.dropdown-menu`, `.modal-content`, `.event-card`, `.benefit-card`, `#hp-offers`, `.profile-edit-card` и т. д.). Поэтому `dark-theme-fixes.css` существует в принципе и заполнен `hardcoded #111118` без переменных.
> 5. **Каждая крупная страница (homepage, member_cabinet, partner_dashboard, login, register) переопределяет свой `:root`** с конфликтующими значениями: `--bg0`, `--bg1`, `--card`, `--text` различаются между страницами → одинаковые компоненты выглядят по-разному.

---

## БЛОК 1: МОБИЛЬНАЯ АДАПТИВНОСТЬ (Mobile-First & Responsive)

### 🔴 КРИТИЧЕСКИЕ

- [ ] **U1-01** [responsive.css:48-52](IESA_ROOT/static/css/responsive.css#L48-L52) — **Глобальное `min-height/min-width: 44px` на `a, button, [role=button], label[for], input[type=checkbox|radio]`** — применяется на ВСЕХ устройствах, не только touch. На десктопе ссылки в футере, иконки соцсетей, текстовые кнопки получают огромный «невидимый» padding 44×44, ломая компактные тулбары и table‑actions. **Редизайн**: обернуть правило в `@media (hover: none) and (pointer: coarse)`.

- [ ] **U1-02** [responsive.css:56](IESA_ROOT/static/css/responsive.css#L56) — **`input, textarea, select { font-size: 16px !important }` глобально без media-query** — это ХАК для предотвращения зума на iOS, но он применяется на всех экранах, перекрывая плотные таблицы фильтров на десктопе, поиск в navbar, OTP‑боксы. **Редизайн**: применять только в `@media (max-width: 767.98px)` (как уже есть на 624 — это дубль).

- [ ] **U1-03** [base.html:344](IESA_ROOT/IESA_ROOT/templates/base.html#L344) — **`<main style="padding-top:70px;">` хардкод высоты header inline** — ломается, когда на мобиле header сжимается до 50‑52px (см. responsive.css:169) и появляется dev-banner высотой ~25px. На устройстве с нотчем + dev-banner получается двойной `padding-top` через `safe-area-inset-top`. **Редизайн**: вынести в CSS-переменную `--header-h` и пересчитывать через JS либо использовать `padding-top: var(--header-h);` с разными значениями в media-queries.

- [ ] **U1-04** [base.html:626-634](IESA_ROOT/IESA_ROOT/templates/base.html#L626-L634) — **Inline `style="width:22px;height:22px;border-radius:50%;..."` для аватара в bottom-nav** — фиксированный 22px на всех устройствах. На iPhone Mini (320px) занимает много места, на больших Android (450px+) теряется. **Редизайн**: вынести в `.mbn-item img` с `clamp(20px, 5.5vw, 26px)`.

- [ ] **U1-05** [components.css:1858-1860](IESA_ROOT/IESA_ROOT/static/css/components.css#L1858-L1860) — **`.auth-body { padding: 2rem 1.5rem }` без media-query**, при этом login.html переопределяет на `2.5rem 3.2rem` на десктопе. Несогласованные отступы. На iPhone SE (320px) форма с padding 1.5rem дает только 256px рабочей ширины — поля «дышат» едва. **Редизайн**: единая токен‑шкала `var(--auth-pad)` от 1rem до 3rem через `clamp()`.

- [ ] **U1-06** [responsive.css:689-696](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L689-L696) — **`.table-mobile-cards tbody tr { background: white }` хардкод белого** в тёмной теме. На страницах партнёра (visits) на мобиле получаются белые «полоски» поверх тёмного фона. **Редизайн**: использовать `var(--bg-surface)` (но сначала исправить U3-01) или `background: rgba(255,255,255,.04)`.

- [ ] **U1-07** [layout.css:782-784](IESA_ROOT/IESA_ROOT/static/css/layout.css#L782-L784) — **На мобильных `main#main-content { padding-top: 0.5rem !important }`**, но в base.html на main стоит `style="padding-top:70px;"` — конфликт инлайна (specificity 1000) и `!important` CSS. На разных браузерах ведёт себя по‑разному. **Редизайн**: убрать inline-style из base.html, оставить класс.

### 🟠 ВЫСОКИЙ ПРИОРИТЕТ

- [ ] **U1-08** [responsive.css:1097-1102](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L1097-L1102) — **Кнопка `#back-to-top` на мобиле = 40×40 px** — ниже 44px рекомендуемого Apple Touch Target минимума. **Редизайн**: 44×44 минимум, или скрыть на устройствах с bottom-nav (она и так перекрывает).

- [ ] **U1-09** [layout.css:553-554](IESA_ROOT/IESA_ROOT/static/css/layout.css#L553-L554) — **`.navbar-search-dropdown { min-width: 360px }`** — на 360px-устройствах (iPhone SE) дропдаун шире viewport на 1px, выезжает за край и активирует горизонтальный скролл (если бы не overflow-x:hidden на body). На очень узких устройствах чаще обрезается до `calc(100vw-1rem)` через `responsive.css:776`. **Редизайн**: `min-width: min(360px, calc(100vw - 2rem))`.

- [ ] **U1-10** [member_cabinet.html:7-...](IESA_ROOT/IESA_ROOT/users/templates/users/member_cabinet.html#L7) — **2400+ строк inline `<style>`** в кабинете участника, с переопределением `:root` (`--bg0: #0a0a0f`). Любое изменение глобальной палитры не дойдёт сюда. На мобиле этот мегафайл стилей грузится при каждом заходе (`extra_css` block). **Редизайн**: вынести в `static/css/member-cabinet.css` + `<link>` в `extra_css`.

- [ ] **U1-11** [partner_dashboard.html:11-29](IESA_ROOT/IESA_ROOT/users/templates/users/partner_dashboard.html#L11-L29) — **Аналогично U1-10: переопределение `:root` со своими `--bg0: #06060d`, `--text: rgba(255,255,255,0.88)`**, тут же `--r: 16px` (на cabinet — `--r: 20px`). У карточек разные радиусы на разных страницах. **Редизайн**: убрать локальный `:root`, использовать глобальные токены.

- [ ] **U1-12** [pages.css:34](IESA_ROOT/IESA_ROOT/static/css/pages.css#L34) — **`.profile-edit-card { padding: 30px }` фиксированный** на всех экранах. На <360px съедает 19% ширины. На responsive.css:662 переопределяется на `1.25rem` для <768px, но не для очень узких (<360). **Редизайн**: `clamp(0.75rem, 4vw, 1.875rem)`.

- [ ] **U1-13** [register.html:79](IESA_ROOT/IESA_ROOT/users/templates/users/register.html#L79) — **`.reg-grid { grid-template-columns: 1fr 1fr }` без mobile-fallback в самом файле** — есть медиа-правило в register.html ниже, но текст «Регистрация» с двумя колонками на 768-991px (планшет‑портрет) выглядит сжатым. Поля Email и Phone уезжают друг на друга. **Редизайн**: переключаться на 1 колонку уже с 768px (планшет‑портрет), 2 колонки только на ≥992px.

- [ ] **U1-14** [responsive.css:836-837](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L836-L837) — **На устройствах <576px `.profile-stat-grid { grid-template-columns: 1fr !important }`** — все stat-карточки в столбик. Если их 4‑6, страница профиля становится длинной «лентой» из стат-блоков. **Редизайн**: 2 колонки на <576px (есть пространство для пары шт.), 1 колонка только при <360px.

- [ ] **U1-15** [register.html:63-67](IESA_ROOT/IESA_ROOT/users/templates/users/register.html#L63-L67) — **`.reg-steps { width: fit-content }`** — на узких экранах (<400px) если все шаги длинные («ACCOUNT INFO», «PROFILE INFO», «CONFIRMATION») они вылезают за viewport либо обрезаются. **Редизайн**: `flex-wrap: wrap` + укоротить лейблы на мобиле через CSS.

- [ ] **U1-16** [responsive.css:1234-1260](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L1234-L1260) — **`@media print` отключает `header, footer, .navbar`, но НЕ отключает `dev-banner`** — при печати поста виден development banner. **Редизайн**: добавить `.dev-banner` в скрытие при `@media print`.

- [ ] **U1-17** [base.html:170](IESA_ROOT/IESA_ROOT/templates/base.html#L170) — **`<button class="navbar-toggler">` без `aria-controls` для свёрнутого состояния badge с уведомлениями** — навбар-тоглер не обновляет `aria-expanded` динамически когда Bootstrap collapse скрывает меню. **Редизайн**: проверить bootstrap initialization handler — добавить `aria-controls="navbarNav"`, добавить ARIA‑live для badge уведомлений.

### 🟡 СРЕДНИЙ ПРИОРИТЕТ

- [ ] **U1-18** [responsive.css:55-57](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L55-L57) — **`input { font-size: 16px !important }`** ломает дизайн админ-фильтров где нужен мелкий шрифт (например, в partner_dashboard поиск). **Редизайн**: исключить `.compact-input`, `.filter-input` из правила.

- [ ] **U1-19** [responsive.css:843-882](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L843-L882) — **Селекторы `[class*="cabinet"]`, `[class*="pin-code"]`** — атрибутные селекторы со wildcard работают медленнее обычных и хрупки при рефакторинге. **Редизайн**: добавить конкретный класс `.cab-card` и т.д.

- [ ] **U1-20** [responsive.css:912](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L912) — **`.auth-light-side { padding: 1.5rem !important }`** на мобиле + в самой login.html карточка имеет `padding: 1.8rem 1.6rem` — два конфликтующих правила. **Редизайн**: вынести padding в одно место.

- [ ] **U1-21** [profile.html / profile_public.html] — **`profile-id-badge { word-break: break-all; font-size: 0.875rem }` на мобиле** — UUID 36 символов в одну строку с break-all выглядит неаккуратно. **Редизайн**: показывать сокращённый UUID (первые 8 + ... + последние 4) с возможностью «копировать полный».

- [ ] **U1-22** [user_cabinet PIN] — **`.pin-display, .pin-digits { font-size: clamp(2rem, 10vw, 3rem) }`** на мобиле — это нормально, но `letter-spacing: 0.15em` на узком экране делает 6-значный PIN шире viewport. **Редизайн**: уменьшить letter-spacing до 0.05em на <400px.

- [ ] **U1-23** [touch-gestures.css] — **Не проверено: возможно, swipe-навигация конфликтует с горизонтальной прокруткой `.pp-nav`** на partner_dashboard (`overflow-x: auto`). Свайп влево по навигации может закрыть мобильное меню. **Редизайн**: добавить класс‑флаг `.no-swipe-close` на горизонтально-скроллируемые элементы.

---

## БЛОК 2: ЭРГОНОМИКА И UX (Удобство использования)

### 🔴 КРИТИЧЕСКИЕ

- [ ] **U2-01** [base.html:436-442](IESA_ROOT/IESA_ROOT/templates/base.html#L436-L442) — **`htmx:responseError` обрабатывает только `status === 403`**, всё остальное (500, 503, network) **только пишется в console.error**. Пользователь не видит **никакой обратной связи** при ошибке HTMX-запроса (сабскрайбы, лайки, комменты). **Редизайн**: показывать toast «Ошибка сервера, попробуйте позже» для 5xx, retry-кнопку для 503, «Нет связи» для status=0.

- [ ] **U2-02** [base.html:230-238](IESA_ROOT/IESA_ROOT/templates/base.html#L230-L238) — **Поиск в navbar: `delay:400ms`, но нет debounce на показ "Loading..."**. Спиннер `#search-spinner` подключён через `hx-indicator`, но пользователь печатает «kit», за 400мс это успевают **3 запроса** (по букве). На медленном CPU спиннер мигает. **Редизайн**: увеличить delay до 600мс OR добавить minimum visible spinner duration через CSS animation (300мс).

- [ ] **U2-03** [base.html:160](IESA_ROOT/IESA_ROOT/templates/base.html#L160) — **`onclick="document.getElementById('dev-banner').remove()"`** — DEV banner показывается ВСЕМ пользователям в проде, и закрытие НЕ запоминается (нет `localStorage`). При следующем визите снова видно. **Редизайн**: либо скрывать в production через Django settings (`{% if DEBUG %}`), либо `localStorage.setItem('dev-banner-dismissed', '1')`.

- [ ] **U2-04** [register.html] — **Регистрация одна длинная форма** (~10 полей: username, email, password, password2, first_name, last_name, phone, dob, country, sport...). Шаги показаны (`reg-steps`) но это **визуальная декорация**, не настоящие шаги. **Редизайн**: разбить на 3 шага: (1) Email+Password, (2) Profile data, (3) Confirmation. Это снижает abandonment на 25-40% по UX‑бенчмаркам.

- [ ] **U2-05** [layout.css:332-345](IESA_ROOT/IESA_ROOT/static/css/layout.css#L332-L345) — **Кнопки в footer соцсетей размером 40×40, но `min-height/min-width: 44px` глобально добавит 4px невидимого пространства**. Пользователь промахивается мимо иконки, попадая в «прозрачную» зону. **Редизайн**: либо размер 44×44, либо убрать глобальное правило (см. U1-01).

- [ ] **U2-06** [base.html:489-513](IESA_ROOT/IESA_ROOT/templates/base.html#L489-L513) — **Logout confirm modal** — заголовок «Confirm Logout» с иконкой sign-out-alt, **окрашен `bg-warning bg-opacity-10`** (жёлтый), но кнопка «Logout» = `btn-danger` (красная). Цвета не согласованы — пользователь видит жёлтый «warning» header, потом красную «danger» кнопку. **Редизайн**: либо весь modal warning-themed (с amber-кнопкой), либо весь danger-themed.

- [ ] **U2-07** [base.html:411-443](IESA_ROOT/IESA_ROOT/templates/base.html#L411-L443) — **HTMX configRequest добавляет CSRF**, но если CSRF отсутствует в DOM — **молча ничего не делает**. На сессионных таймаутах запросы возвращают 403, ловится только в `htmx:responseError` через `window.location.reload()` — это **жёсткий refresh теряющий все несохранённые формы**. **Редизайн**: вместо `reload` показать модал «Сессия истекла, авторизуйтесь снова» с возможностью повторить запрос после логина.

- [ ] **U2-08** [post_create / register / profile_edit] — **Длинные формы без auto-save / draft** — если пользователь начал писать пост и страница перезагрузилась — всё пропало. **Редизайн**: localStorage auto-save для post_create, profile_edit (raw data, не файлы) с восстановлением при возврате. Удаление draft после успешного submit.

- [ ] **U2-09** [base.html:156-161](IESA_ROOT/IESA_ROOT/templates/base.html#L156-L161) — **Dev‑banner перекрывает первые 25-30px hero‑секции** на мобильных (когда ширина текста увеличивается). Hero `padding-top` не учитывает высоту dev-banner. **Редизайн**: использовать `position: sticky` для banner и пересчитывать `padding-top` главного контента.

### 🟠 ВЫСОКИЙ ПРИОРИТЕТ

- [ ] **U2-10** [base.html:241-265](IESA_ROOT/IESA_ROOT/templates/base.html#L241-L265) — **Notifications dropdown: `hx-trigger="load, click from:#notificationsToggle"` — load запрашивает уведомления при ЛЮБОЙ загрузке страницы**, даже если пользователь не открыл колокольчик. Это лишний запрос на каждый pageview. **Редизайн**: убрать `load`, делать `intersect once` или `click` only. Badge `unread_notifications_count` уже содержит число — этого достаточно для индикации.

- [ ] **U2-11** [base.html:589-596](IESA_ROOT/IESA_ROOT/templates/base.html#L589-L596) — **HTMX badge polling каждые 60с** для непрочитанных. На странице открытой 8 часов это **480 запросов на пользователя**. **Редизайн**: использовать `every 5m`, или Server‑Sent Events (SSE) при наличии mod_wsgi/Daphne, или WebSocket‑сервис.

- [ ] **U2-12** [base.html:283-305](IESA_ROOT/IESA_ROOT/templates/base.html#L283-L305) — **Profile dropdown на десктопе vs Bottom nav на мобиле дублируют функционал**, но на странице партнёра в нав‑дропдауне показывается «Partner Portal», а в bottom‑nav — нет. Inconsistent IA. **Редизайн**: унифицировать — на мобиле тоже добавить дополнительный экран для партнёров (например, через slide-up панель из bottom-nav).

- [ ] **U2-13** [member_cabinet PIN display] — **PIN цифры огромные (`clamp(2rem, 10vw, 3rem)`) но не имеют tap-to-copy** — пользователь видит, читает, переключается на партнёрский терминал, набирает руками. **Редизайн**: tap по цифрам копирует в clipboard с feedback toast. На партнёрском терминале сейчас нужно ввести вручную — это OK с точки зрения безопасности, но для самопроверки полезно.

- [ ] **U2-14** [profile.html — H‑hierarchy] — **Заголовки часто перепутаны**: `<h1>` в Hero, `<h2>` в section-title с фоновой иконкой; местами `.h1` (класс, не тег) применяется к `<div>`. У search engines сбита иерархия. **Редизайн**: ревизия каждой страницы с `<h1>` в одном экземпляре, остальные через `<h2>-<h4>`, никогда не использовать класс `.h1` без тега `h1`.

- [ ] **U2-15** [member_scan_card.html] — **Сканер карты, скорее всего, не имеет tactile-feedback** при успешном сканировании. PIN после сканирования показывается, но без vibration API на мобильных. **Редизайн**: `if (navigator.vibrate) navigator.vibrate(50)` на успех.

- [ ] **U2-16** [base.html:411-433](IESA_ROOT/IESA_ROOT/templates/base.html#L411-L433) — **HTMX afterSwap инициализирует ВСЕ toasts через bootstrap.Toast**, даже те которые уже были инициализированы. На странице со многими swap’ами получится утечка bootstrap‑Toast инстансов. **Редизайн**: проверять `bootstrap.Toast.getInstance(toast)` перед `new`.

- [ ] **U2-17** [post_create] — **Пост‑создание: textarea с минимальной высотой** (?) и без счётчика символов / preview. **Редизайн**: добавить счётчик remaining chars (если есть лимит), предпросмотр (live render markdown), drag‑drop для изображений.

- [ ] **U2-18** [partner_dashboard "VISITS"-table] — **На мобиле в partner_dashboard tabular `data-label`-pattern** делает каждую строку «карточкой», но кнопка действия (Edit, Cancel) уезжает вниз. На десктопе — справа. Inconsistent action-position. **Редизайн**: на мобиле кнопки в footer карточки (sticky `position: sticky; bottom: 0` если карточка длинная).

- [ ] **U2-19** [base.html:344-353](IESA_ROOT/IESA_ROOT/templates/base.html#L344-L353) — **Django messages показываются в alert внутри container-limited**, но если message длинный (>200 символов) — на узких экранах кнопка-крестик `btn-close` уезжает за край. **Редизайн**: alert с `position: relative` и `padding-right: 3rem` чтобы крестик всегда оставался внутри.

- [ ] **U2-20** [base.html:580-583](IESA_ROOT/IESA_ROOT/templates/base.html#L580-L583) — **`#back-to-top` показывается всегда (CSS управляет visibility через `.visible` класс), но JS с `scroll`-обработчиком в каком файле?** Возможно, нет JS-handler-а, и кнопка никогда не появляется. **Редизайн**: проверить и добавить scroll listener в `mobile-optimization.js` или `page-effects.js`.

### 🟡 СРЕДНИЙ ПРИОРИТЕТ

- [ ] **U2-21** [base.html:170-172](IESA_ROOT/IESA_ROOT/templates/base.html#L170-L172) — **Burger toggler на мобиле: `aria-label="Toggle navigation"`** не локализован для русских пользователей? Проверить — Django i18n вероятно справляется, но точно ли есть перевод. **Редизайн**: убедиться что `{% trans %}` оборачивает все aria-label.

- [ ] **U2-22** [base.html `.notifications-dropdown` 320×400 max] — **Если уведомлений 50, скролл внутри dropdown работает**, но на mobile это часто непредсказуемо (overflow-y vs touch). **Редизайн**: на <768px notifications открывать как полноэкранный модал, не dropdown.

- [ ] **U2-23** [post_detail.html] — **Лайки/комменты — кнопка-сердечко без подтверждения отмены лайка**. Случайный двойной‑тап — лайк ставится и снимается, пользователь не понимает что произошло. **Редизайн**: после анимации лайка подождать 200мс перед возможностью повторного клика (debounce CSS pointer-events).

- [ ] **U2-24** [event_detail.html — RSVP] — **Регистрация на ивент `Я иду` без confirm**. Если ивент платный — двойной‑тап = двойная регистрация (race condition уже исправлен B2-06, но UX-проблема осталась). **Редизайн**: для платных ивентов всегда confirm modal.

- [ ] **U2-25** [profile_deactivate_confirm.html] — **Подтверждение удаления аккаунта** — нужна 2-step проверка: введите ваш email или username для подтверждения. Сейчас неизвестно, проверить требуется. **Редизайн**: input-confirmation pattern (как у GitHub).

- [ ] **U2-26** [base.html:472-486](IESA_ROOT/IESA_ROOT/templates/base.html#L472-L486) — **copy-to-clipboard не возвращает фокус** на исходный элемент после успеха. Скрин-ридер не объявляет «скопировано». **Редизайн**: `aria-live` region + `aria-label` обновлять на «Скопировано в буфер».

- [ ] **U2-27** [admin_appeal_form] — **Форма обращения**: textarea `minlength=20` приводит к тому, что коротенькие сообщения «Помогите!» отвергаются без объяснения. **Редизайн**: показывать счётчик «осталось 12 символов до минимума».

---

## БЛОК 3: ВИЗУАЛЬНЫЙ МУСОР И КОНСИСТЕНТНОСТЬ (UI Design)

### 🔴 КРИТИЧЕСКИЕ

- [ ] **U3-01** [base.css:357-419](IESA_ROOT/IESA_ROOT/static/css/base.css#L357-L419) — **41 селектор ОДНИМ махом получает `--bg-surface: #ffffff` (БЕЛЫЙ ФОН)** в тёмной теме сайта. Этот блок — **первопричина** существования `dark-theme-fixes.css` со 153 `!important`. Селекторы перекрывают: `.card`, `.dropdown-menu`, `.modal-content`, `.event-card`, `.benefit-card`, `.product-card`, `.profile-edit-card`, `.auth-card`, `#hp-offers`, `#hp-events`, `#hp-partners` и т. д. **Редизайн**: УДАЛИТЬ этот блок целиком; вместо этого создать explicit‑компоненты `.card-light`, `.section-light` для редких случаев светлого контейнера на тёмной странице.

- [ ] **U3-02** [components.css:1359-1378](IESA_ROOT/IESA_ROOT/static/css/components.css#L1359-L1378) — **`:root` блок с переопределением `--shadow-sm`, `--shadow-md`, `--shadow-lg`, `--shadow-xl`** в середине components.css! Старый файл `modern-design.css` был «вмёрджен» механически без рефакторинга. Это ЛОМАЕТ все тени в дизайн-системе: они становятся красноватыми (tint rgba(220,38,38,...)), хотя в `variables.css` определены нейтральные shadow. **Редизайн**: удалить весь блок `:root` из components.css, использовать только канонические переменные из `variables.css`.

- [ ] **U3-03** [components.css:1383-1392](IESA_ROOT/IESA_ROOT/static/css/components.css#L1383-L1392) — **Глобальное переопределение `html, body` шрифта** на `-apple-system, BlinkMacSystemFont,...` ЗАМЕНЯЕТ загруженный `Inter` из variables.css. На системах без Inter получают системный шрифт; на системах с Inter — тоже системный (приоритет родного Apple). **Редизайн**: удалить этот `html,body` блок, оставить шрифт только в `variables.css`/`base.css`.

- [ ] **U3-04** [components.css:1397-1409 vs 330-342](IESA_ROOT/IESA_ROOT/static/css/components.css#L1397-L1409) — **Дубль `.card` в одном файле**: первый `.card { border-radius: var(--radius-card) /* 20px */ }`, второй `.card { border-radius: 16px; transform: translateY(-4px) /* hover */ }`. Второй выигрывает каскад. Border-radius разные — компоненты отрисовываются с разной геометрией в разных контекстах. **Редизайн**: оставить ОДНО определение `.card` использующее токены.

- [ ] **U3-05** [components.css:1420-1444 vs 22-119](IESA_ROOT/IESA_ROOT/static/css/components.css#L1420-L1444) — **Дубль `.btn`, `.btn-primary`, `.btn-success`, `.btn-danger`** — второй блок переопределяет padding, border-radius и УБИРАЕТ `:focus-visible` стиль (определён только в первом). Доступность пострадала. **Редизайн**: удалить дубли, добавить `:focus-visible` в каноническое определение.

- [ ] **U3-06** [components.css:1297-1300](IESA_ROOT/IESA_ROOT/static/css/components.css#L1297-L1300) — **`.partner-logo-placeholder` использует `linear-gradient(135deg, #667eea 0%, #764ba2 100%)`** — фиолетовый градиент, не имеющий отношения к бренду IESA (красный). У партнёра без логотипа отображается фиолетовая буква-плейсхолдер на красном сайте. **Редизайн**: использовать `var(--gradient-primary)` или нейтральный `var(--gray-700)`.

- [ ] **U3-07** [layout.css:711-728](IESA_ROOT/IESA_ROOT/static/css/layout.css#L711-L728) — **`.messaging-btn.active { background-color: #667eea }`** — снова фиолетовый. Inconsistent с brand-цветом. **Редизайн**: `var(--primary)`.

- [ ] **U3-08** [components.css:1557-1577](IESA_ROOT/IESA_ROOT/static/css/components.css#L1557-L1577) — **Alerts из «модерн» блока используют ДРУГИЕ цвета** чем из канонического: `#11998e` (teal), `#eb3349` (cherry-red), `#fa709a` (pink), `#4facfe` (sky‑blue) — НИ ОДИН не из палитры variables.css (`--success: #16a34a`, `--danger: #ef4444`). Затем `dark-theme-fixes.css:248-271` снова переопределяет alerts на правильные цвета через `!important`. Тройное переопределение. **Редизайн**: удалить alert‑правила из «модерн» блока components.css.

- [ ] **U3-09** [components.css:1763-1771](IESA_ROOT/IESA_ROOT/static/css/components.css#L1763-L1771) — **`.benefit-card-discount` использует `#f5576c` (peach‑pink)** для «скидка» — снова чужой цвет. **Редизайн**: `var(--success)` (зелёный) для positive economic value, или `var(--primary)` для бренда.

- [ ] **U3-10** [components.css:1437-1444 + 1457-1466](IESA_ROOT/IESA_ROOT/static/css/components.css#L1437-L1444) — **`.btn-primary:hover { opacity: 0.9 }` И `.btn-danger:hover { opacity: 0.9 }`** — снижение opacity вместо изменения цвета. На тёмном фоне opacity делает кнопку «выцветшей», а не «активной». **Редизайн**: использовать `--primary-hover`, `--danger-hover` через `background`.

- [ ] **U3-11** [Каждая страница со своим `:root`] — homepage, member_cabinet, partner_dashboard, login, register **ВСЕ переопределяют `:root` локально** с разными значениями `--bg0`, `--bg1`, `--card`, `--text`, `--muted`, `--r` (border-radius). Между страницами одинаковые слова означают разное. **Редизайн**: вынести в `variables.css` единые `--surface-0..3`, `--card-bg`, `--card-radius`, использовать ТОЛЬКО их.

- [ ] **U3-12** [components.css:1297, 1320-1347](IESA_ROOT/IESA_ROOT/static/css/components.css#L1320-L1347) — **Партнёрские badge-категории** имеют 5 разных gradient цветов (`#fbbf24→#f59e0b` sponsor, `#8b5cf6→#7c3aed` media, `#3b82f6→#2563eb` tech, `#10b981→#059669` venue, `#6b7280→#4b5563` default). На тёмной теме затем перекрываются однообразным серым в `dark-theme-fixes.css:165-173`. Двойная работа, разноцветные «лейблы» полностью теряются на тёмной теме. **Редизайн**: вернуть цветовую дифференциацию в тёмной теме, использовать subtle бэкграунды (`rgba(*, 0.15)`) с цветным текстом — это работает в тёмной теме.

- [ ] **U3-13** [base.html:104-150](IESA_ROOT/IESA_ROOT/templates/base.html#L104-L150) — **47-строчный `<style>` блок прямо в `<head>` базового шаблона** для `.prof-nav-drop`. Не кэшируется, тянется на КАЖДОЙ странице. **Редизайн**: вынести в `static/css/profile-dropdown.css` или включить в `components.css`.

- [ ] **U3-14** [base.html:65-71](IESA_ROOT/IESA_ROOT/templates/base.html#L65-L71) — **Mojibake (битая Cyrillic)** в комментариях CSS-architecture v2.0 — следы повреждённой кодировки UTF-8 → Windows-1252. Комментарий v2 уже не актуален (есть v3 ниже), нужно удалить. Аналогично base.html:412-432 (HTMX скрипт). **Редизайн**: удалить v2-комментарий целиком, починить русские комментарии HTMX‑скрипта (или перевести их на английский).

### 🟠 ВЫСОКИЙ ПРИОРИТЕТ

- [ ] **U3-15** [components.css:1869-1898](IESA_ROOT/IESA_ROOT/static/css/components.css#L1869-L1898) — **`.table` из «модерн» блока: `background: white !important`, `.table thead { background: var(--primary-gradient) }`** — таблица всегда белая с красным header. На тёмной теме `dark-theme-fixes.css:215-223` перекрывает на тёмный. **Редизайн**: удалить из «модерн» блока, оставить только тёмную версию.

- [ ] **U3-16** [variables.css:113-124](IESA_ROOT/IESA_ROOT/static/css/variables.css#L113-L124) — **Алиасы `--color-gray-50..900` дублируют `--gray-*`** (`--color-gray-50: var(--gray-50)`). Это «костыль для homepage, использующего другое имя». Удвоение токенов запутывает дизайнера. **Редизайн**: переименовать использования в `homepage.css`, удалить алиасы.

- [ ] **U3-17** [variables.css + components.css 1361-1376] — **Целый параллельный набор имён тоже существует**: `--primary-color` (вместо `--primary`), `--primary-dark` (вместо `--primary-active`), `--primary-light: #fecaca` (новое значение!). 3 имени для одной концепции. **Редизайн**: убить `--primary-color`, `--primary-dark` из «модерн» блока.

- [ ] **U3-18** [member_cabinet.html (locally):25-28](IESA_ROOT/IESA_ROOT/users/templates/users/member_cabinet.html#L25-L28) — **Каждая страница придумывает свой radius (`--r: 20px`, `--r: 16px`)** — `variables.css` уже имеет `--radius-card: 1.25rem` (=20px), `--radius-2xl: 1rem` (=16px). Не используются. **Редизайн**: использовать существующие токены вместо новых имён.

- [ ] **U3-19** [responsive.css:124, 207, 218, 411, 506](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L124) — **`color: rgba(255,255,255,0.65)` повторяется ~30 раз в разных правилах** вместо `var(--text-secondary)`. При смене палитры нужно искать все 30 мест. **Редизайн**: заменить на токены.

- [ ] **U3-20** [components.css:1985-1992](IESA_ROOT/IESA_ROOT/static/css/components.css#L1985-L1992) — **`.btn { padding: 0.625rem 1rem; font-size: 0.95rem }` на <576px** — но другие правила в responsive.css задают `padding: 0.55rem 1rem`. Какая выиграет — зависит от порядка загрузки. **Редизайн**: один источник правды.

- [ ] **U3-21** [pages.css:30](IESA_ROOT/IESA_ROOT/static/css/pages.css#L30) — **`.profile-edit-card { background: var(--card-bg, #fff) }`** — дефолт `#fff` ломает тёмную тему, если `--card-bg` не определён. На самом деле `dark-theme-fixes.css:8` определил `--card-bg: var(--bg-surface)` — но опять же, `--bg-surface` через base.css:407 = `#fff`. Цикл! **Редизайн**: жёстко задать `--card-bg: #111118` в variables.css в тёмной теме, и не использовать fallback значения с белым.

- [ ] **U3-22** [pages.css:49](IESA_ROOT/IESA_ROOT/static/css/pages.css#L49) — **`.edit-card-header { border-bottom: 2px solid #fecaca }`** — pink-pastel hardcode. На тёмной теме pink выглядит инородно. **Редизайн**: `border-bottom: 1px solid var(--border-color)`.

- [ ] **U3-23** [partials/admin_appeal_form.html](IESA_ROOT/IESA_ROOT/templates/partials/admin_appeal_form.html) — **`<style>` в partial template** — стили загружаются на КАЖДОЙ странице, где этот partial included (главная — имеет appeal form в footer? Если да — стили грузятся всегда). **Редизайн**: вынести в `static/css/admin-appeal.css`, подключать только на нужных страницах.

- [ ] **U3-24** [components.css:1646-1657](IESA_ROOT/IESA_ROOT/static/css/components.css#L1646-L1657) — **`.product-card-image { height: 200px; background: var(--primary-gradient) }`** — фолбэк для product без изображения = красная заливка. Минимум для тёмной темы — нейтральный `var(--gray-100)`. **Редизайн**: `background: var(--gray-100)` с центрированной иконкой `fa-image`.

- [ ] **U3-25** [components.css:1738-1745](IESA_ROOT/IESA_ROOT/static/css/components.css#L1738-L1745) — **`.benefit-card-title { color: #2d3748 }` хардкод gray-900**. На тёмной теме невидим (тёмный текст на тёмном фоне), пока `dark-theme-fixes.css:67` не перекрывает. **Редизайн**: `color: var(--text-primary)`.

- [ ] **U3-26** [layout.css:159-167](IESA_ROOT/IESA_ROOT/static/css/layout.css#L159-L167) — **`.dropdown-item { color: rgba(255,255,255,.65) }`** — в `dark-theme-fixes.css:392` снова переопределяется на `rgba(255,255,255,.85)`. Конфликт. **Редизайн**: удалить из layout.css, оставить в одной точке.

- [ ] **U3-27** [Целая папка `static/css`] — **15 CSS-файлов суммарно ~6000 строк** содержат **1157 `!important`**. Это **в среднем 1 `!important` каждые 5 строк**. Невозможно найти источник стилей. **Редизайн**: радикальное сокращение — переход на BEM или CSS Modules, удаление `!important` через ревизию специфичности.

### 🟡 СРЕДНИЙ ПРИОРИТЕТ

- [ ] **U3-28** [responsive.css:1238-1249](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L1238-L1249) — **`@media print` отключает hover‑transforms через `transform: none !important`**, но сохраняет `box-shadow` — на печати тени видны как чернильные пятна. **Редизайн**: добавить `box-shadow: none !important` в print.

- [ ] **U3-29** [variables.css:43-48](IESA_ROOT/IESA_ROOT/static/css/variables.css#L43-L48) — **`--warning: #d97706`** vs `--warning-light: #fffbeb` — разница 12 шагов в сате. На тёмной теме `--warning-light` (почти белый) выглядит ярко-белым blob. **Редизайн**: добавить `--warning-dark-light: rgba(217,119,6,.1)` для тёмной темы.

- [ ] **U3-30** [components.css:1599-1606](IESA_ROOT/IESA_ROOT/static/css/components.css#L1599-L1606) — **`.hero::before` декоративный круг 400×400 с `animation: float 6s`** — потенциальный jank на старых телефонах (60fps animation на blur-radial-gradient). **Редизайн**: использовать `will-change: transform` или отключать `prefers-reduced-motion`.

- [ ] **U3-31** [base.html:48](IESA_ROOT/IESA_ROOT/templates/base.html#L48) — **Google Fonts тянется напрямую без `font-display: swap`** — пользователь видит invisible text 200-2000мс пока шрифт грузится. **Редизайн**: добавить `&display=swap` в URL и `<link rel="preconnect" href="https://fonts.googleapis.com">`.

- [ ] **U3-32** [base.html:50-60](IESA_ROOT/IESA_ROOT/templates/base.html#L50-L60) — **4 внешних CDN‑зависимости** (Bootstrap CSS, Font Awesome, Bootstrap Icons, Lightbox CSS) без integrity SRI. Поставщик скомпрометирован → XSS на сайте. **Редизайн**: добавить `integrity="sha384-..."` или хостить self-served в `static/`.

- [ ] **U3-33** [base.html:158](IESA_ROOT/IESA_ROOT/templates/base.html#L158) — **`<i class="bi bi-tools" style="font-size:.75rem;">`** — inline font-size в иконке dev-banner. **Редизайн**: класс `.dev-banner-icon`.

- [ ] **U3-34** [responsive.css:1191-1213](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L1191-L1213) — **`@media (hover: none)` отключает все hover-эффекты, включая `box-shadow: inherit !important`** — но `inherit` от родителя вернёт shadow родителя, не `none`. Логическая ошибка. **Редизайн**: `box-shadow: none !important` или специфичные значения для каждого селектора.

- [ ] **U3-35** [animations.css + components.css + pages.css + responsive.css] — **5+ keyframes-блоков `fadeIn`, `pulse`, `spin`** разбросаны по файлам. Уже частично исправлено в B4-04/B4-05 но `slideInDown`, `float`, `shimmer`, `progress-animation` всё ещё дублируются между файлами. **Редизайн**: финальная консолидация в `animations.css`.

- [ ] **U3-36** [Все файлы CSS] — **Mixed comment styles**: в одном файле русский, в другом английский, в третьем — mojibake. Это фронтенд — разные люди писали и не подчищали. **Редизайн**: единый стандарт (английский для библиотечных файлов, русский в шаблонах допустим).

- [ ] **U3-37** [base.html:529](IESA_ROOT/IESA_ROOT/templates/base.html#L529) — **Лишний `</div>`** — partner modal закрывается на 528, но 529 даёт ещё одно `</div>` без открытия. HTML невалидный. **Редизайн**: удалить лишний тег (проверить W3C-валидатором).

- [ ] **U3-38** [base.html:444-487](IESA_ROOT/IESA_ROOT/templates/base.html#L444-L487) — **Два разных `<script>` блока с `DOMContentLoaded`-инициализацией** в base.html. Один на 452, другой на 533. Оба добавляют listeners и могут конфликтовать. **Редизайн**: один объединённый блок инициализации.

- [ ] **U3-39** [base.html dev-banner] — **`background: rgba(8,8,14,0.97)` совпадает с цветом header** — visually it merges, но dev-banner идёт ВЫШЕ header (z-index больше), и при scroll-down скрытии header (header-hide-on-scroll.js) banner остаётся видимым. Inconsistent. **Редизайн**: либо banner тоже скрывается со scroll, либо чётко контрастный фон.

---

## БЛОК 4: КОМПОНЕНТЫ (Навигация, Футер, Карточки)

### 🔴 КРИТИЧЕСКИЕ

- [ ] **U4-01** [layout.css:148-156 + 461-465 + 659-664 + components.css:1904-1908 + dark-theme-fixes.css:187-191](IESA_ROOT/IESA_ROOT/static/css/layout.css#L148) — **`.modal-content` определён в ПЯТИ местах**: `layout.css:461` (без bg), `layout.css:659` (тёмный bg), `components.css:1904` («модерн» bg none), `dark-theme-fixes.css:187` (`!important` тёмный). Каждое определение конфликтует. **Редизайн**: один источник правды в `components.css`, удалить остальные.

- [ ] **U4-02** [base.html:165-339](IESA_ROOT/IESA_ROOT/templates/base.html#L165-L339) — **Header содержит 175 строк HTML** — главный navbar с brand, основным меню, search, notifications, profile dropdown, language picker. Никакого component-extract — нельзя переиспользовать в админке/спец. странице. **Редизайн**: вынести в `templates/partials/_navbar.html`, подключать через `{% include %}`.

- [ ] **U4-03** [base.html:365-402](IESA_ROOT/IESA_ROOT/templates/base.html#L365-L402) — **Аналогично — footer 38 строк inline**. Нельзя переопределить (например, упрощённый footer на error pages). **Редизайн**: `templates/partials/_footer.html`.

- [ ] **U4-04** [layout.css:284-288](IESA_ROOT/IESA_ROOT/static/css/layout.css#L284-L288) — **`.footer-enhanced { background: var(--bg-dark); margin-top: auto }`** — `var(--bg-dark) = #111827` (gray-900), а body — `#0e0e18` (другой тёмный). Footer чуть-чуть светлее body — visual inconsistency. **Редизайн**: использовать `var(--bg-body)` или единый `--bg-deep: #0a0a14`.

- [ ] **U4-05** [base.html footer mobile](IESA_ROOT/IESA_ROOT/templates/base.html#L365) — **На мобиле bottom-nav фиксированный, footer уезжает за bottom-nav** — пользователь должен сильно скроллить чтобы увидеть footer. responsive.css:1097 даёт `padding-bottom: calc(80px + safe-area)`. **Редизайн**: на мобиле возможно скрыть footer/упростить (только copyright + privacy link).

- [ ] **U4-06** [base.html bottom-nav 605-647](IESA_ROOT/IESA_ROOT/templates/base.html#L605-L647) — **Bottom-nav имеет 4 пункта для авторизованных: Home, Posts, Alerts, Profile**, но **отсутствуют важные**: Events (центральный для community-сайта), Benefits (key value prop), Search. Пользователь должен лезть в burger‑меню. **Редизайн**: 5 пунктов с центральной "+" для quick action (создать пост/RSVP), либо сделать «More» как 5-й пункт.

- [ ] **U4-07** [base.html:241-265](IESA_ROOT/IESA_ROOT/templates/base.html#L241-L265) — **Notifications dropdown имеет `max-height: 400px; overflow-y: auto`** (layout.css:614-616), но **на мобиле при открытии** клавиатуры (если фокус на input) или iOS bouncy scroll — всё «ломается». **Редизайн**: на <768px открывать как `position: fixed; top:0; height: 100dvh` (slide-over).

- [ ] **U4-08** [layout.css:553-554](IESA_ROOT/IESA_ROOT/static/css/layout.css#L553-L554) — **Search dropdown `min-width: 360px`** — превышает iPhone SE viewport (320px). На таких устройствах либо обрезается с горизонтальным скроллом, либо `responsive.css:776` максит `100vw - 1rem` через `!important`. **Редизайн**: `min-width: min(360px, calc(100vw - 1rem))`.

- [ ] **U4-09** [base.html:174-194](IESA_ROOT/IESA_ROOT/templates/base.html#L174-L194) — **Главное меню desktop: Home, About, Benefits, Gallery, Community(dropdown)**. На <992px всё это сворачивается в burger, и Community-dropdown превращается во вложенный список. UX-проблема: «Posts», «Events», «Products», «Partners», «Members» — это 5 крупных функций спрятаны на 2 уровне. **Редизайн**: на мобиле развернуть community в 5 отдельных пунктов либо сделать tabs.

- [ ] **U4-10** [Партнёрские карточки vs Member карточки vs Event карточки](IESA_ROOT/IESA_ROOT/static/css/components.css#L1258) — **Каждый тип карточки имеет свой border-radius**: `partner-card-compact: 12px`, `benefit-card: 16px`, `event-card: 14px (на mobile)`, `card: 20px`. Inconsistent. **Редизайн**: единый `--radius-card: 16px` (или 14px) по всему сайту.

### 🟠 ВЫСОКИЙ ПРИОРИТЕТ

- [ ] **U4-11** [base.html lang-picker 199-219](IESA_ROOT/IESA_ROOT/templates/base.html#L199-L219) — **Custom language picker с inline JS-handler (base.html:649-674)** дублирует возможности Bootstrap dropdown. Зачем custom? **Редизайн**: использовать `bootstrap.Dropdown` через стандартный API, удалить кастомный JS.

- [ ] **U4-12** [base.html language picker](IESA_ROOT/IESA_ROOT/templates/base.html#L211) — **`{{ lang.1|slice:":3" }}` показывает первые 3 буквы названия** ("Eng" вместо "English"). На многих языках (как Русский→"Рус") выглядит ОК, но "Deutsch"→"Deu" грубо. **Редизайн**: ISO‑код 2 буквы в верхнем регистре (`{{ lang.0|upper }}`) или флаги emoji.

- [ ] **U4-13** [layout.css:613-617](IESA_ROOT/IESA_ROOT/static/css/layout.css#L613-L617) — **`.notifications-dropdown { min-width: 320px; max-height: 400px }`** — на устройствах с сайдбаром (iPad horizontal) этого хватает, но на iPhone это 100% ширины. На мобиле `responsive.css:776` ограничивает `calc(100vw - 1rem)`, но тогда **min-width 320 > max-width 311 на iPhone SE → конфликт**. **Редизайн**: убрать `min-width` на мобиле через media‑query.

- [ ] **U4-14** [Footer copyright 371](IESA_ROOT/IESA_ROOT/templates/base.html#L371) — **`&copy; {{ "now"|date:"Y" }}` использует текущий год** — корректно, но если страница была закэширована Cloudflare на год — год неактуальный. **Редизайн**: либо `meta http-equiv="cache-control" content="public, max-age=86400"`, либо хардкод года для footer.

- [ ] **U4-15** [Footer Social 392-398](IESA_ROOT/IESA_ROOT/templates/base.html#L392-L398) — **`{% for sn in social_networks %}` иконки соцсетей** — если context_processor `social_networks` отсутствует на конкретной странице — секция пустая. **Редизайн**: всегда передавать через `core/context_processors.py` (TemplateContextProcessor).

- [ ] **U4-16** [Profile dropdown 268-331](IESA_ROOT/IESA_ROOT/templates/base.html#L268-L331) — **Меню профиля содержит 4 пункта: My Cabinet, PIN Cabinet (опц), Edit Profile, Partner Portal (опц)**. Нет пункта **«Logout»** — он отдельной кнопкой справа. На мобиле в burger‑menu — кнопки в столбик. UX: пользователь ожидает logout в profile-меню (стандарт). **Редизайн**: добавить divider + Logout в profile dropdown.

- [ ] **U4-17** [Карточки на разных страницах] — **Hover‑эффект разный**:
  - `.card:hover { transform: translateY(-2px) }` (responsive.css:1173)
  - `.card:hover { transform: translateY(-4px); box-shadow: var(--shadow-lg) }` (components.css:1406)
  - `.benefit-card:hover { transform: translateY(-8px) }` (components.css:1716)
  - `.product-card:hover { transform: translateY(-8px) }` (components.css:1641)
  - `.partner-card-compact:hover { transform: translateY(-2px) }` (components.css:1265)
  
  5 разных значений! **Редизайн**: единый `--card-hover-lift: -3px`.

- [ ] **U4-18** [Иконки в карточках 1721-1729](IESA_ROOT/IESA_ROOT/static/css/components.css#L1721-L1729) — **`.benefit-card-icon { height: 100px }` фиксированная высота** — на мобиле 100px-блок занимает много пространства, теряется content. **Редизайн**: `height: clamp(60px, 15vw, 100px)`.

- [ ] **U4-19** [Footer текст 736-739](IESA_ROOT/IESA_ROOT/static/css/layout.css#L736-L739) — **`.footer-about-text { max-width: 360px }`** — но контейнер col-lg-4 шире. На больших экранах текст обрывается на 360px при свободном пространстве 400+. **Редизайн**: убрать max-width, использовать `line-height` для оптимального чтения.

- [ ] **U4-20** [Mobile bottom-nav badges](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L132-L143) — **`.mbn-badge { top: 2px; right: 10px; min-width: 16px }`** — 99+ уведомлений вылезают за иконку. **Редизайн**: `font-size` адаптивный + `99+` если >99.

- [ ] **U4-21** [Notifications dropdown content](IESA_ROOT/IESA_ROOT/notifications/templates/notifications/notification_list.html) — **Content загружается через HTMX `hx-trigger="load"`** на каждой странице — даже если дропдаун не открывается (см. U2-10). **Редизайн**: `hx-trigger="click from:#notificationsToggle"`.

- [ ] **U4-22** [base.html:243-253](IESA_ROOT/IESA_ROOT/templates/base.html#L243-L253) — **Notification badge `{% if unread_notifications_count > 0 %}` рендерится server-side**, и обновляется через `hx-get every 60s` на скрытом div (line 590). После HTMX swap **бэдж в navbar НЕ обновляется** — он остаётся со старым значением до перезагрузки страницы. **Редизайн**: HTMX target-ить непосредственно в navbar badge, или использовать SSE.

- [ ] **U4-23** [base.html:585-596](IESA_ROOT/IESA_ROOT/templates/base.html#L585-L596) — **`<div hx-get="..." hx-target="#unreadMessagesCount">` но `#unreadMessagesCount` НЕ ВИДЕН на странице** (не находится в base.html текстом). Это либо мёртвый код, либо элемент в чужом partial. **Редизайн**: проверить и удалить если мёртвый.

### 🟡 СРЕДНИЙ ПРИОРИТЕТ

- [ ] **U4-24** [base.html notifications dropdown 261-264](IESA_ROOT/IESA_ROOT/templates/base.html#L261-L264) — **«Loading...» plain text** при загрузке notifications. **Редизайн**: skeleton-loader (3 «карточки‑заглушки»), не текст.

- [ ] **U4-25** [Search results spinner](IESA_ROOT/IESA_ROOT/templates/base.html#L236) — **`<i class="fas fa-spinner fa-spin"></i>` без размера/цвета** — может выглядеть микроскопическим на retina. **Редизайн**: `font-size: 1.25rem; color: var(--primary)`.

- [ ] **U4-26** [Avatar fallback 774-778](IESA_ROOT/IESA_ROOT/static/css/components.css#L774-L778) — **`.avatar-fallback { background: var(--gradient-primary) }`** — все пользователи без аватара получают одинаковый красный gradient. UI: невозможно различить юзеров визуально. **Редизайн**: hash username → один из 6 цветов (red/blue/green/amber/purple/pink) через CSS-trick `background-color: hsl(calc(var(--user-hash) * 137deg), 60%, 50%)`.

- [ ] **U4-27** [Avatar sizes](IESA_ROOT/IESA_ROOT/static/css/variables.css#L310-L316) — **6 размеров `--avatar-xs..2xl` (24-160px)**, но в шаблонах используются конкретные числа:`width="22px"` (base.html:628), `width: 36px` (search-avatar). **Редизайн**: всегда применять токены.

- [ ] **U4-28** [layout.css:543-549](IESA_ROOT/IESA_ROOT/static/css/layout.css#L543-L549) — **`.navbar-btn .avatar { width: 26px !important; height: 26px !important }`** — `!important` нужен потому что `.avatar-sm = 28px` (variables.css:312). **Редизайн**: использовать `--avatar-sm: 28px` как канон.

- [ ] **U4-29** [Footer social 327-344](IESA_ROOT/IESA_ROOT/static/css/layout.css#L327-L344) — **Hover эффект `transform: translateY(-2px)` без `prefers-reduced-motion: reduce`** — для пользователей с motion-чувствительностью. **Редизайн**: обернуть `@media (prefers-reduced-motion: no-preference)`.

- [ ] **U4-30** [base.html notifications HTMX 257-260](IESA_ROOT/IESA_ROOT/templates/base.html#L257-L260) — **`hx-swap="innerHTML show:no-scroll"`** — `show:no-scroll` это нестандартный HTMX modifier (не существует в `htmx.min.js` 1.x). Возможно typo, должно быть `scroll:no` или `swap:none scroll:false`. **Редизайн**: проверить документацию HTMX и исправить.

- [ ] **U4-31** [Mobile bottom-nav active state](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L126-L130) — **`.mbn-item.active, .mbn-item:active`** — `:active` это псевдо при тапе (мгновенный feedback), `.active` — при текущей странице. Объединены в один rule с `color: #dc2626`. На тапе кратковременно красный, потом обратно — выглядит как «мерцание». **Редизайн**: разделить, для `:active` отдельный мгновенный effect (background-pulse).

- [ ] **U4-32** [base.html partner-modal 515-528](IESA_ROOT/IESA_ROOT/templates/base.html#L515-L528) — **Partner modal с body загружаемым по HTMX**, но `aria-labelledby` отсутствует. Modal ARIA‑accessibility: assistive‑tech не знает, какой заголовок у модалки. **Редизайн**: `aria-labelledby="partnerModalTitle"` + назначить id заголовку.

- [ ] **U4-33** [Profile-dropdown caret](IESA_ROOT/IESA_ROOT/templates/base.html#L281) — **`<i class="fas fa-chevron-down pnd-caret"></i>` ротируется через `.show .pnd-caret { transform: rotate(180deg) }`** — но Bootstrap не добавляет `.show` на dropdown-toggle, а на сам `.dropdown` контейнер. **Редизайн**: убедиться селектор `.prof-nav-drop.show .pnd-caret` совпадает с DOM.

- [ ] **U4-34** [Card border-radius на мобиле](IESA_ROOT/IESA_ROOT/static/css/responsive.css#L444-L446) — **`.card { border-radius: 14px }` на мобиле**, но `partner-card-compact` остаётся 12px, `event-card` остаётся 14px. Каждый тип карточки имеет свой override на мобиле — фрагментация. **Редизайн**: единый mobile radius `--radius-card-mobile: 14px`.

- [ ] **U4-35** [Comments thread](IESA_ROOT/IESA_ROOT/blog/templates/blog/htmx/comments_section.html) — **Стилизация комментариев**: `dark-theme-fixes.css:381-382 .comment-thread .card-modern { background: rgba(255,255,255,.04) }`, при этом базовый `card-modern` = `#111118`. Вложенные comments выглядят светлее — это намеренный «depth-effect», но дальше глубже становится одинаково. **Редизайн**: явный visual-depth pattern (например, `.depth-1: rgba(255,255,255,.04)`, `.depth-2: rgba(255,255,255,.07)`, ...).

- [ ] **U4-36** [Partner modal partner_modal.html 238 строк inline `<style>`](IESA_ROOT/IESA_ROOT/templates/core/htmx/partner_modal.html) — уже зафиксировано как B4-06 и помечено `[x]`, но проверить что СRefactor выполнен (есть ли отдельный `partner-modal.css`). **Редизайн**: убедиться что вынос на самом деле произошёл.

- [ ] **U4-37** [Карточки: уровень тени](IESA_ROOT/IESA_ROOT/static/css/dark-theme-fixes.css#L45) — **`.card { box-shadow: 0 4px 20px rgba(0,0,0,0.3) }` через `!important`**. На тёмной теме (фон `#0e0e18`) тень почти невидима — нет контраста. **Редизайн**: либо тоньше тень с лёгким blue-tint, либо использовать `border` вместо тени для разделения.

- [ ] **U4-38** [Mobile bottom-nav: aria-current на active](IESA_ROOT/IESA_ROOT/templates/base.html#L606) — **`{% if request.resolver_match.url_name == 'home' %}active{% endif %}`** добавляет только класс. **Должно быть** также `aria-current="page"` для accessibility. **Редизайн**: добавить `{% if ... %}aria-current="page"{% endif %}`.

- [ ] **U4-39** [Footer ARIA-labels](IESA_ROOT/IESA_ROOT/templates/base.html#L394) — **`<a class="footer-social" title="...">`** — title работает на mouse, но не для screen-readers без aria-label. **Редизайн**: добавить `aria-label="{{ sn.get_name_display }}"` в дополнение к title.

---

## СВОДНАЯ ТАБЛИЦА ПРИОРИТЕТОВ

### Критические (блокируют UX или ломают визуал)
| Код | Файл | Тип | Влияние |
|-----|------|-----|---------|
| U1-01 | responsive.css | Touch-target | desktop tap‑zones broken |
| U1-02 | responsive.css | Mobile zoom | font‑size hack global |
| U1-03 | base.html | Inline‑style | header overlap |
| U1-04 | base.html | Avatar inline | hardcoded size |
| U1-05 | components.css | Padding | inconsistent auth |
| U1-06 | responsive.css | Dark theme | white tables on dark |
| U1-07 | layout.css vs base.html | Specificity conflict | padding broken |
| U2-01 | base.html | HTMX errors | no UX feedback on 5xx |
| U2-02 | base.html | Search debounce | spinner flickers |
| U2-03 | base.html | Dev banner | always shown |
| U2-04 | register.html | Long form | abandonment risk |
| U2-05 | layout.css | Touch target | footer-social broken |
| U2-06 | base.html | Color logic | warning vs danger |
| U2-07 | base.html | HTMX 403 | hard reload loses data |
| U2-08 | post_create | Auto-save | data loss |
| U2-09 | base.html | Dev banner overlay | hero z‑index |
| U3-01 | base.css:357 | Dark-theme root cause | 41 selectors broken |
| U3-02 | components.css :root | Tokens | shadows broken |
| U3-03 | components.css | Font override | Inter not used |
| U3-04 | components.css | Duplicate .card | radius mismatch |
| U3-05 | components.css | Duplicate .btn | no focus-visible |
| U3-06 | components.css | Brand color | purple gradient |
| U3-07 | layout.css | Brand color | purple in messaging |
| U3-08 | components.css | Alert palette | wrong colors |
| U3-09 | components.css | Color | peach for discount |
| U3-10 | components.css | Hover | opacity instead color |
| U3-11 | All pages | Local :root | 6 conflicting design systems |
| U3-12 | components.css | Badges | partner colors lost |
| U3-13 | base.html | Inline style 47 lines | profile dropdown |
| U3-14 | base.html | Mojibake | comment encoding |
| U4-01 | layout.css×2 + components.css + dark-fixes | Modal-content | 5 definitions |
| U4-02 | base.html | Header monolith | non-extracted |
| U4-03 | base.html | Footer monolith | non-extracted |
| U4-04 | layout.css | Bg color | inconsistent dark |
| U4-05 | base.html | Mobile footer | hidden by bottom-nav |
| U4-06 | base.html | Bottom-nav IA | missing key links |
| U4-07 | base.html | Notifications | not full‑screen on mobile |
| U4-08 | layout.css | Search dropdown | min-width > viewport |
| U4-09 | base.html | Community menu | nested 2 levels |
| U4-10 | components.css | Card radius | 5 different values |

### Высокий приоритет (заметные UX/Visual проблемы)
40 issues (U1-08..U1-17, U2-10..U2-20, U3-15..U3-27, U4-11..U4-23)

### Средний приоритет (полировка)
30+ issues (U1-18..U1-23, U2-21..U2-27, U3-28..U3-39, U4-24..U4-39)

> **Итого:** ~10 критических Block 1, ~9 критических Block 2, ~14 критических Block 3, ~10 критических Block 4 = **~43 критических**.
> Высокий + средний приоритет = **~80 задач**.
> **Общий объём: ~120 UI/UX-задач.**

---

## ПОРЯДОК ИСПРАВЛЕНИЙ (рекомендуемый)

### Спринт UI-1 — Корень тёмной темы (1-2 дня, drastic improvements)
1. **U3-01** Удалить блок `base.css:357-419` (41 селектор → `--bg-surface: #fff`)
2. **U3-02** Удалить дубль `:root` в components.css:1359-1378
3. **U3-04, U3-05** Слить дубли `.card` и `.btn`, оставить токены
4. **U3-11** Заменить локальные `:root` в страницах на токены variables.css
5. **U3-21** Зафиксировать `--card-bg`, `--bg-surface` без fallback на `#fff`
6. **Цель**: после этого спринта `dark-theme-fixes.css` сжимается с 485 строк до ~50

### Спринт UI-2 — Component extraction (1-2 дня)
7. **U4-02, U4-03** Вынести header и footer из base.html в partials
8. **U3-13** Вынести `<style>` блок profile-dropdown
9. **U1-10, U1-11** Вынести inline-styles из member_cabinet.html и partner_dashboard.html
10. **U3-23** Вынести `<style>` из admin_appeal_form

### Спринт UI-3 — Mobile-First Critical (1 день)
11. **U1-01, U1-02** Снять глобальные mobile-only правила с десктопа
12. **U1-03, U1-04, U1-07** Исправить header padding-top + аватары inline
13. **U1-06** Темная тема для mobile-cards
14. **U4-08** Мобильный search dropdown

### Спринт UI-4 — UX/HTMX (1-2 дня)
15. **U2-01** HTMX error handling для 5xx
16. **U2-02** Search debounce + min spinner duration
17. **U2-03** Dev banner localStorage dismissal
18. **U2-07** Soft session‑expired modal вместо reload
19. **U2-10, U2-11, U4-21** Notifications: убрать `load`-trigger, увеличить polling
20. **U4-22** HTMX обновление badge в navbar

### Спринт UI-5 — Component consistency (2 дня)
21. **U4-01** Один `.modal-content`
22. **U4-10, U4-17, U4-18** Единый card-radius и hover-lift
23. **U3-12** Вернуть цвета партнёрских badges в dark theme
24. **U3-26** Один `.dropdown-item` color
25. **U4-26, U4-27** Avatar consistency

### Спринт UI-6 — Forms & Long-form UX (2-3 дня)
26. **U2-04** Разбить регистрацию на 3 шага
27. **U2-08** Auto-save для post_create + profile_edit
28. **U2-17** Char counter + preview для post

### Спринт UI-7 — Polish (1 день)
29. **U3-31** Google Fonts swap + preconnect
30. **U3-32** SRI integrity для CDN
31. **U3-37** Удалить лишний `</div>`
32. **U3-38** Объединить два DOMContentLoaded
33. **U2-20, U4-24, U4-25** Skeleton + spinners polish

---

## ВЕРИФИКАЦИЯ (как тестировать после изменений)

1. **Lighthouse CI** — добавить в pre-commit (Performance, Accessibility, Best Practices, SEO ≥ 90).
2. **Visual regression** — Percy / BackstopJS на 5 ключевых страницах (home, blog, profile, post_detail, partner_dashboard) × 3 viewports (320, 768, 1440).
3. **W3C HTML validator** — проверить лишний `</div>` в base.html (U3-37).
4. **CSS specificity calculator** — после удаления `!important` (цель: < 100 occurrences вместо 1157).
5. **Manual touch testing** — iPhone SE (320px), iPhone 14 (390px), iPad (768px), Pixel 7 (412px).
6. **prefers-reduced-motion** — DevTools rendering tab → emulate, проверить отключение анимаций.
7. **prefers-contrast: high** — то же.
8. **Screen reader** — VoiceOver (macOS) на главной + регистрации.
9. **Dark theme audit** — поиск `#fff`, `#ffffff`, `white` в CSS (должно остаться <10 явных, для специальных light-cards).
10. **Cross-browser** — Safari (iOS 16, 17), Chrome (Android), Firefox desktop.
