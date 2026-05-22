# IESA Sport — UX/UI Аудит и Рефакторинг (v2.0)
> **Роль**: Lead Product Designer · UX/UI Эксперт · Frontend Архитектор
> **Цель**: упростить, разгрузить и починить интерфейс — особенно личный профиль, партнёрский дашборд и мобильную вёрстку.
> **Принцип**: «Меньше — это больше». Каждая страница должна иметь **один** главный CTA и **одну** главную задачу.

---

## Обозначения

- `[ ]` — не сделано · `[x]` — выполнено
- ⚡ — высокий приоритет / сломанная вёрстка
- 📱 — мобильная адаптивность
- 🧹 — очистка / минимализм / разгрузка
- 🎨 — визуальная консистентность

---

## КРАТКАЯ СВОДКА ПРОБЛЕМ (TL;DR)

**Что обнаружено:**
1. **Профиль перегружен** — 13 карточек, 3 места «Quick Actions», ACR-форма на 200+ строк, дубли PIN-блока
2. **Партнёрский портал использует ДВЕ дизайн-системы** одновременно: `dash-*` (sidebar) и `pp-wrap` (top-tabs) — выглядит как два разных продукта
3. **CSS-архитектура развалена**: 23 файла, 14 356 строк, **445 `!important`** (242 в responsive, 160 в dark-theme, 43 в ui-ux), 7+ дублирующих дизайн-систем (cab-*, dash-*, pp-*, pd-*, reg-*, auth-*, acr-*, ucal-*)
4. **На главной hero-desc на ФРАНЦУЗСКОМ** — захардкоженный msgid не переводится
5. **На мобиле** sidebar партнёра пропадает полностью, таблицы скроллятся горизонтально, нет mobile-навигации внутри дашборда
6. **Inline `<style>` блоки** — profile.html (4 блока, ~500 строк CSS внутри HTML), partner_analytics.html (52 строки inline), log_visit/edit_visit/cancel_visit — каждый дублирует pp-wrap систему
7. **Visit History и My Posts** — таблицы с `overflow-x:auto` на мобиле = пользователь должен скроллить горизонтально
8. **Hero профиля**: avatar + name + 4 badges + 4 кнопок + ещё 3 quick-actions кнопки = слишком плотно

---

# 📋 ПЛАН РЕФАКТОРИНГА ПО БЛОКАМ

## BLOCK 1 — Глобальные основы: design tokens, типографика, mobile-first reset 🎨📱⚡

> **Цель блока**: создать единый источник правды для дизайна, убрать каскадный бардак (445 `!important`), починить базовую mobile-вёрстку.

### 1a — Унификация дизайн-токенов 🎨⚡
- [ ] Перенести ВСЕ повторяющиеся `rgba(220,38,38,.12)`, `rgba(255,255,255,.4)` и т.п. в CSS-переменные в `variables.css`
  - Палитра поверхностей: `--surface-0 / --surface-1 / --surface-2 / --surface-3`
  - Палитра бордеров: `--border-faint / --border-soft / --border-strong`
  - Палитра primary с alpha: `--primary-a8 / --primary-a12 / --primary-a25 / --primary-a40`
- [ ] Зафиксировать 4 размера радиусов: `--r-sm (8px) / --r-md (12px) / --r-lg (16px) / --r-xl (20px)` — заменить хаос `border-radius: 10px / 12px / 14px / 16px / 18px / 20px`
- [ ] **Где исправлять**: `variables.css` + поиск/замена inline-стилей в шаблонах

### 1b — Чистка CSS-каскада (убрать 445 `!important`) 🧹⚡
- [ ] **`dark-theme-fixes.css` (160 !important)** — это анти-паттерн. Корректные стили должны быть в `components.css`/`pages.css`. План:
  - Удалить файл полностью, перенести нужные правила выше по каскаду
  - Удалить из base.html: `<link ... dark-theme-fixes.css>`
- [ ] **`responsive.css` (242 !important)** — частая причина: дубли правил из других CSS. Аудит каждого правила:
  - Если правило уникально мобильное → оставить без !important (mobile-first)
  - Если перебивает другой файл → передвинуть правило туда
- [ ] **`ui-ux-improvements.css` (43 !important)** — мерж в `components.css`, удалить файл-«заплатку»

### 1c — Сокращение CSS-файлов с 23 до 8 ⚡🧹
**Текущее**: variables, base, layout, components, pages, utilities, animations, product-cards, homepage, touch-gestures, responsive, dark-theme-fixes, ui-ux-improvements, profile-page, dashboard, partner-dashboard, admin-enhanced, admin-appeal, cmd-bar, events-timeline, lightbox-custom, style, bootstrap.min
**Целевая структура (8 файлов)**:
- [ ] `variables.css` — токены (как сейчас)
- [ ] `base.css` — reset + base typography + accessibility
- [ ] `components.css` — все переиспользуемые компоненты (кнопки, карточки, badges, formы, modals, dropdowns, tabs)
- [ ] `layout.css` — navbar, footer, bottom-nav, container, sidebar
- [ ] `pages.css` — page-specific (hero homepage, blog, profile)
- [ ] `partner.css` — единая партнёрская система (см. Block 2)
- [ ] `responsive.css` — все @media запросы в одном месте
- [ ] `bootstrap.min.css` (внешний)

### 1d — Inline `<style>` блоки → во внешние CSS 🧹
- [ ] `profile.html` (4 `<style>` блока) → новый `profile-page.css` (расширить существующий)
- [ ] `partner_analytics.html` (52 строки inline) → новый `partner.css`
- [ ] `log_visit.html`, `edit_visit.html`, `cancel_visit.html`, `partner_member_visits.html`, `partner_profile_edit.html` → используют ОДНУ и ту же `.pp-wrap` систему inline. Вынести в `partner.css`
- [ ] `register.html`, `login.html` → объединить в `auth.css`
- [ ] `user_calendar.html` → перенести в `profile-page.css`

### 1e — Типографика: убрать `Courier New` из партнёра 🎨
- [ ] Партнёрские страницы используют `font-family:'Courier New',monospace` для всех label-ов → это выглядит как два разных продукта на одном сайте
- [ ] **Решение**: оставить mono только для PIN-кода и UUID. Для label-ов — обычный шрифт с `letter-spacing: .08em; text-transform: uppercase`

### 1f — Глобальные mobile-first ремонты 📱⚡
- [ ] `html, body { overflow-x: hidden }` уже есть — проверить, что не ломает sticky
- [ ] iOS zoom предотвращение (`input { font-size: 16px }` на мобиле) уже есть
- [ ] Минимальный touch-target 44×44 — есть, но проверить FAB, dropdowns, bottom-nav badges
- [ ] **Hero на главной**: исправить msgid с французского на английский (`hero-desc` строка 526 в `index.html`)
- [ ] Тестировать на 320px (iPhone SE 1st gen) — самый узкий случай

### 1g — Унификация bottom-nav active-state 📱
- [ ] Сейчас Profile-таб не подсвечивается активным внутри `/auth/dashboard/` и `/auth/my-calendar/`
- [ ] Расширить логику `request.resolver_match.url_name` → проверять префикс пути

---

## BLOCK 2 — Рефакторинг Партнёрского портала ⚡🧹🎨📱

> **Цель блока**: одна дизайн-система, нормальная мобильная навигация, карточки вместо таблиц, **один** главный CTA «Записать визит».

### 2a — Объединение двух дизайн-систем (`dash-*` + `pp-wrap`) ⚡🎨
**Сейчас** партнёрский флоу выглядит так:
- `/partner/dashboard/` — sidebar layout (`dash-*`, тёмный sidebar 240px слева)
- `/partner/analytics/` — top-nav layout (`pp-wrap`, горизонтальные tabs)
- `/partner/calendar/` — sidebar layout (`dash-*`)
- `/partner/visit/<id>/` (log_visit) — `pp-wrap`
- `/partner/visit/<id>/edit/` — `pp-wrap`
- `/partner/member/<id>/` — `pp-wrap`
- `/partner/profile/` — `pp-wrap`

**Решение**:
- [ ] Все партнёрские страницы используют **sidebar-layout** (`dash-*`)
- [ ] Sidebar содержит: Dashboard / Calendar / Visit History / Analytics / Company Profile / My Settings / Back to Cabinet
- [ ] На мобиле sidebar становится `<details>` accordion в топбаре ИЛИ bottom drawer
- [ ] Все шаблоны переходят на один extends-партиал `partials/_partner_layout.html`
- [ ] Удалить файл `partner-dashboard.css` (`pp-*` стили) после миграции

### 2b — Мобильная навигация дашборда 📱⚡
**Сейчас** на мобиле sidebar полностью скрывается → пользователь не может попасть в Analytics/Calendar/Company Profile из дашборда (только через bottom nav, где их нет)

**Решение**:
- [ ] Добавить sticky top-bar на мобиле партнёрских страниц с горизонтальным scroll-меню (pills): Dashboard · Calendar · History · Analytics · Profile
- [ ] Или вариант B: drawer-меню с тапом на hamburger в топбаре дашборда (специфичном для дашборда)
- [ ] **Рекомендация**: pills с horizontal scroll — проще и привычнее

### 2c — История визитов: таблица → карточки на мобиле 📱⚡🧹
**Сейчас** `partner_visit_history.html` (partials) — таблица с `overflow-x:auto`. На мобиле пользователь скроллит горизонтально, видит 1.5 колонки → плохо.

**Решение**:
- [ ] **Desktop**: оставить таблицу
- [ ] **Mobile (< 768px)**: каждая строка → карточка вида:
  ```
  ┌─────────────────────────────────────┐
  │ [✓] Иван Петров          15.05 12:30│
  │     Тренировка · 50 CHF             │
  │     PIN verified                    │
  │     [edit] [cancel]                 │
  └─────────────────────────────────────┘
  ```
- [ ] CSS: `display:none` для `<table>` на мобиле, генерировать `<div class="vh-card">` отдельным `{% if request.is_mobile %}` или через CSS-grid (рекомендуется второе — без бэка)
- [ ] **Где**: `users/templates/users/partials/partner_visit_history.html`

### 2d — Дашборд: убрать дублирование «Log Visit» CTA 🧹
**Сейчас** на дашборде «Log Visit» появляется 4 раза:
1. В sidebar (главная кнопка)
2. В topbar (зелёная кнопка справа)
3. В пустом состоянии Today's Visits («Log a Visit»)
4. Через FAB в правом нижнем углу
5. Bottom nav центральная (для партнёров)

**Решение**:
- [ ] Оставить только: **#search-section** (главная зона поиска) + **FAB на мобиле** + **bottom-nav center**
- [ ] Убрать topbar-кнопку (дублирует sidebar)
- [ ] Убрать sidebar-кнопку (есть пункт меню)
- [ ] Пустое состояние Today's Visits — оставить, но переименовать в «Записать первый визит» (т.к. это onboarding-state)

### 2e — Stats-карточки на мобиле: 4 колонки → 2 колонки → горизонтальный scroll 📱🧹
**Сейчас** на 360px stats grid пытается влезть в 2 колонки → числа маленькие, отступы плотные

**Решение**:
- [ ] Mobile (< 480px): **горизонтальный scroll** карточек stats (как Apple Health rings)
- [ ] Каждая карточка фиксированной ширины 140px
- [ ] Snap-points через `scroll-snap-type: x mandatory`

### 2f — «Today's Visits» + «Recent Clients» — упрощение мобиль 📱🧹
- [ ] На мобиле — табы вместо двух колонок: `[Today's Visits] [Recent Clients]`
- [ ] Активная таб содержит контент, другая — скрыта (не нужно дублировать вертикально)

### 2g — Календарь партнёра: упрощение интерфейса 🧹🎨
**Сейчас** `partner_calendar.html`:
- Двухколоночный layout 320px sidebar + main
- В sidebar: статы (2 карточки) + месячный mini-calendar + быстрый прыжок + неделя
- В main: hour-grid + список встреч + форма создания

**Решение**:
- [ ] Mobile (< 1024px): свернуть месячный mini-calendar в кнопку «📅 Выбрать дату» → открывает overlay с full-screen календарём
- [ ] Hour-grid на мобиле: компактнее (40px на час вместо 64px), показывать только 6:00–22:00 по умолчанию
- [ ] Форму «Schedule Meeting» вынести в slide-up drawer (открывается по тапу на пустую ячейку)

### 2h — FAB: пересмотр функций 🧹
**Сейчас** FAB на дашборде имеет 3 действия: New Meeting / Log Visit / Invite Client
- [ ] **Invite Client** — не используется (нет flow приглашения) → удалить
- [ ] **Log Visit** — дублирует bottom-nav центральную кнопку → удалить
- [ ] Оставить только **New Meeting** → переделать FAB в одиночную кнопку без раскрытия

### 2i — Topbar: убрать с мобиля 📱🧹
- [ ] `.dash-topbar` (заголовок «Dashboard» + «Partner since…» + Log Visit) — на мобиле занимает ценное пространство
- [ ] Mobile: скрыть topbar, переименовать страницу в `<h1>` внутри `dash-content`

### 2j — `partner_analytics.html` — мобильная типографика 📱🎨
- [ ] `pp-stats` 5 колонок → 2 на мобиле (есть, но 3×2 неравномерно — последняя одна)
- [ ] `pp-charts` Chart.js — responsive=true, проверить читаемость на 320px
- [ ] Service Breakdown таблица → cards на мобиле

---

## BLOCK 3 — Очистка Личного Профиля ⚡🧹🎨

> **Цель блока**: вместо 13 карточек на одной странице — фокус-ориентированный профиль с табами/аккордеонами.

### 3a — Убрать дублирование Quick Actions ⚡🧹
**Сейчас**:
- В hero: 3 кнопки (`hero-quick-actions`: New Post, Calendar, Insurance)
- Под hero: 6 ссылок (`cab-quick-nav`: Overview, Posts, Calendar, PIN, Partner, Settings)
- В правой колонке: 5–6 кнопок (`qa-grid`: Edit Profile, Write Post, Connect Telegram, Activity Levels, …)
- Плюс в onboarding-carousel (если новый): ещё 5 (Connect Telegram, Add Photo, etc.)

**Решение**:
- [ ] Убрать hero-quick-actions (3 кнопки) — оставить только Edit Profile + QR Code в hero
- [ ] Убрать quick-nav (`cab-quick-nav`) — мало кто использует anchor-навигацию по странице
- [ ] Сохранить ОДНУ Quick Actions карточку в правой колонке (рефакторинг — см. 3b)

### 3b — Структура профиля: переход на табы 🧹⚡
**Сейчас** профиль — длинная вертикальная страница в 1514 строк HTML с 13 карточками
**Решение**: Sticky табы вверху профиля:
- **Tab 1 «Обзор» (default)**: Hero + Activity Level + 4 stat-cards + Account Info
- **Tab 2 «Карта & PIN»**: PIN-card (большой) + QR-card + Physical Card status + 4 шага использования
- **Tab 3 «Активность»**: My Posts (карточки на мобиле!) + Visit History (карточки)
- **Tab 4 «Социальное»**: Telegram + Social Links + Onboarding completeness
- **Tab 5 «Заявка»** (только если `not is_partner`): ACR-форма для повышения статуса

- [ ] Реализация: CSS `:target` или JS hash-routing
- [ ] Mobile: табы стикятся под navbar (sticky)

### 3c — Вынести ACR-форму на отдельную страницу 🧹⚡
**Сейчас** Apply Change Role (ACR) форма — 200+ строк прямо в profile.html (50+ option-ов в одном select, 4 поля контактов, длинный textarea)
**Решение**:
- [ ] Создать страницу `/auth/account-upgrade/` (URL уже есть — `views.account_change_request_submit`)
- [ ] В профиле — только кнопка `«Подать заявку на партнёрство →»` с одной строкой описания
- [ ] Если уже подана — показать badge `«Заявка на рассмотрении»` + дата
- [ ] Удалить `acr-card / acr-form / steps-grid CSS` из profile.html, перенести в новую страницу

### 3d — PIN-карточка: убрать дубль 🧹
**Сейчас** PIN отображается ДВАЖДЫ на одной странице:
1. `pin-card` в левой колонке (компактный вид)
2. `pin-section` в правой колонке (раздел «PIN & Membership Card» с 4 шагами + физическая карта)

**Решение**:
- [ ] Оставить ОДИН блок PIN — большой, с pulse-анимацией, на ВСЕЙ ширине правой колонки
- [ ] 4 шага «How to use PIN» свернуть в `<details>` («ℹ️ Как использовать PIN»)
- [ ] Physical Card status — отдельный мини-блок рядом

### 3e — Account Info → аккордеон 🧹
**Сейчас** Account Info card — 6 полей (Full name, Email, Phone, DoB, Joined, Card ID) — занимает ~250px высоты с метаданными, которые редко меняются
**Решение**:
- [ ] Свернуть в `<details>` под заголовком `«Account details»` с превью двух главных полей
- [ ] Открытое состояние — только при первом клике

### 3f — Visit History → карточки на мобиле 📱⚡
- [ ] Сейчас `vh-list` уже почти карточки — но padding большой, иконки маленькие
- [ ] Mobile: компактнее (`padding: .6rem .75rem`), иконка `28px`, partner-name truncate
- [ ] Группировка по дате: дата как divider (sticky внутри списка)

### 3g — My Posts → карточки на мобиле 📱⚡
**Сейчас** `<table class="posts-tbl">` с `table-responsive` — горизонтальный скролл на мобиле
**Решение**:
- [ ] Mobile: каждая строка → карточка вида:
  ```
  ┌────────────────────────────────────┐
  │ Заголовок поста...                 │
  │ [Published] · 15 мая · 234 views   │
  │                          [👁 view] │
  └────────────────────────────────────┘
  ```
- [ ] Где: `users/templates/users/profile.html` секция `<div class="cab-card">` с posts-tbl

### 3h — Hero: упрощение и breathing 🧹🎨
**Сейчас** hero перегружен:
- Аватар + name + email + 4 badges + 4 кнопки (Edit Profile, QR Code, Partner Dashboard, PIN & Card) + 3 quick-actions = слишком плотно

**Решение**:
- [ ] Оставить: avatar + name + 1 status badge (Member/Partner/Pending) + только 1 главная кнопка «Edit Profile»
- [ ] Email — мелким шрифтом под именем
- [ ] QR Code → перенести в Tab «Карта & PIN»
- [ ] Partner Dashboard кнопка → в табы (только при наличии партнёра)
- [ ] PIN & Card → в табы

### 3i — Welcome modal + Completeness bar + Tooltips конфликтуют 🧹
**Сейчас** для нового пользователя одновременно появляются:
- Welcome modal (`onb-backdrop` overlay)
- Completeness bar (`pcp-wrap` под hero)
- Quick actions carousel (`qa-onb-section` под bar)
- Tooltips на PIN/QR карточках (`[data-onb-tip]`)

**Решение**:
- [ ] Последовательность: Welcome modal → закрытие → Completeness bar (если < 100%) → Tooltips появляются ТОЛЬКО при наведении (а не сами по себе)
- [ ] Quick actions carousel — убрать ИЛИ заменить на 1 баннер «Ты ещё не подключил Telegram — подключить?»

### 3j — Activity Level: компактнее 🧹
**Сейчас** Activity Level card занимает ~200px: большое число очков + badge + progress bar + текст «To Expert: 18%»
**Решение**:
- [ ] Компактный вид: одна строка `🔥 Intermediate · 342 pts · → Expert (18%)`
- [ ] Прогресс-бар тонкий (2px) под этой строкой
- [ ] Полный вид — в Tab «Активность»

---

## BLOCK 4 — Главная страница ⚡🧹

### 4a — Hero: исправить французский текст ⚡
- [ ] `index.html:526` — `hero-desc` содержит msgid на ФРАНЦУЗСКОМ:
  `"IESA rassemble des personnes qui choisissent une vie active..."`
- [ ] Заменить на английский msgid: `"IESA brings together people who choose an active life..."` + добавить переводы в `.po` файлы

### 4b — Iesa-do-grid: 10 пунктов → 6 ⚡🧹
**Сейчас** на главной 10 пунктов в `iesa-do-grid` (Trips, Locations, Communities, Network, Events, Chess, Competitions, Points ecosystem, Member support, Health) — много для восприятия
**Решение**:
- [ ] Оставить 6 самых сильных: Trips & Experiences, New Locations, Communities, Events Management, Competitions, Health
- [ ] Остальные (Chess, Points ecosystem, Member support, Network) → отдельная секция «Что ещё мы делаем» с компактным списком БЕЗ иконок

### 4c — Hero stats: 4 числа → 3 на мобиле 📱
- [ ] На мобиле `hero-stats` с 4 колонками превращается в 2×2, что нормально
- [ ] Но на 320px цифра `hero-stat-num` 1.85rem сливается с label

### 4d — Canvas particles: совсем отключить на мобиле 📱🧹
- [ ] Уже есть фикс 75 → 28 на мобиле, но даже 28 частиц на 60fps тратят батарею
- [ ] Полностью отключать на `prefers-reduced-data` и < 480px

### 4e — Spacing: больше воздуха ✋🎨
- [ ] Между секциями homepage сейчас 5rem padding-top — можно увеличить до 6rem на десктопе, 3rem на мобиле
- [ ] Внутри секций — text-align center + max-width 720px для description

### 4f — Tilt 3D на туче карточек 🧹📱
- [ ] `tilt3d` эффект на partner cards — тяжёлый JS, на мобиле бесполезен (нет mouse)
- [ ] Отключить через `@media (hover: hover) and (pointer: fine)`

---

## BLOCK 5 — Блог и Посты 🧹🎨📱

### 5a — Post-list: cmd-bar упрощение на мобиле 📱
- [ ] Сейчас cmd-bar содержит: navigation tabs + search + 2 select-фильтра + кнопка New Post
- [ ] Mobile: оставить только search input + кнопка фильтра (открывает bottom-sheet с фильтрами)

### 5b — Post-detail: типографика читаемости 🎨
- [ ] `pd-content` уже имеет `max-width: 720px` и `line-height: 1.82` (из ui-ux-improvements.css) — хорошо
- [ ] Добавить «Reading time» в hero поста (рядом с date)
- [ ] Drop cap на первой букве первого параграфа (опционально)

### 5c — Comments: collapse + skeleton 🧹📱
- [ ] Уже есть collapse 3+ ответа (Block 8d прошлого аудита) — оставить
- [ ] Skeleton при первой загрузке комментариев (HTMX)
- [ ] Аватары в комментариях на мобиле компактнее (28px)

### 5d — Empty states: единый стиль 🎨
- [ ] Сейчас empty states по разному реализованы — иконка + текст в каждом шаблоне отдельно
- [ ] Создать партиал `partials/_empty_state.html` с параметрами icon/title/subtitle/action

---

## BLOCK 6 — Формы (Login / Register / Settings) 🎨🧹

### 6a — Login + Register: убрать декоративные orbs на мобиле 📱🧹
- [ ] `reg-orb-1`, `reg-orb-2`, `auth-orb-1`, `auth-orb-2` — large blur 110-120px radial gradients
- [ ] На мобиле они занимают много GPU и не дают пользы
- [ ] Скрывать через `display:none` на < 768px

### 6b — Register: убрать orbital эффекты, плотнее форму 📱
- [ ] 3 шага регистрации — каждый огромный (padding 2.5rem 3rem на десктопе)
- [ ] Mobile: padding 1rem, шаги компактнее

### 6c — Profile edit: единая страница с табами 🧹
- [ ] Сейчас `profile_edit.html` — простой form со всеми полями вертикально
- [ ] Группировать: «Личные данные» / «Контакты» / «Безопасность» / «Аватар»
- [ ] Использовать секции (`<fieldset>` с легендой) вместо длинного списка

### 6d — Insurance Agent: упрощение 🧹
- [ ] Сейчас `insurance_agent.html` — форма с 1-2 полями (нужно проверить)
- [ ] Возможно, объединить с ACR-формой (она тоже про обращение к админу)

---

## BLOCK 7 — Навигация (Navbar + Bottom Nav + Breadcrumbs) ⚡📱🎨

### 7a — Mobile bottom-nav: улучшения 📱⚡
- [ ] Сейчас 5 элементов: Home, Posts, [QR/Visit/+], Alerts, Profile — хорошо
- [ ] **Проблема**: центральная кнопка для USER (не member, не partner) — `+ Create post` — но эта функция не понятна без подсказки. Лучше «Меню действий» (показывает bottom-sheet с действиями для гостя/обычного user-а)
- [ ] **Profile-tab** на странице `/auth/dashboard/` НЕ активен → расширить логику
- [ ] **Badge на Notifications** — нужна синхронизация с navbar-notif-badge через SSE/polling (уже есть)

### 7b — Navbar mobile: hamburger содержимое 📱🧹
- [ ] Сейчас в hamburger: Home, About, Benefits, Gallery, Community + (для гостей) How it works, Register
- [ ] Это дублирует bottom-nav (Home, Posts)
- [ ] Решение: hamburger содержит только то, чего НЕТ в bottom-nav: About, Benefits, Gallery, Community submenu

### 7c — Breadcrumbs: использовать везде ⚡
- [ ] Сейчас breadcrumbs есть только в партнёрском портале
- [ ] Добавить на: post_detail (Blog → Post title), profile_edit (Profile → Edit), invite_register (Invite → Confirmation)

### 7d — Navbar avatar dropdown: лишние пункты 🧹
- [ ] Сейчас в profile dropdown: My Cabinet / PIN & Card / Partner Portal / Insurance Agent / Edit Profile / Logout
- [ ] **PIN & Card** дублирует «My Cabinet» (он же ведёт в profile с PIN-секцией)
- [ ] **Insurance Agent** — это специфическое действие, не должно быть в menu основном
- [ ] Оставить: My Cabinet · Edit Profile · Partner Portal (if partner) · Logout — 4 пункта

---

## BLOCK 8 — Микро-интеракции и Feedback 🎨🧹

### 8a — Loading states: skeleton везде, где HTMX 📱🎨
- [ ] Уведомления (dropdown + page) — есть
- [ ] Member autocomplete — есть
- [ ] Visit history — есть
- [ ] **Добавить**:
  - [ ] Search results на blog
  - [ ] Like button (hx-swap анимация)
  - [ ] Comments при первой загрузке

### 8b — Tooltips на иконках без текста 🧹
- [ ] Все «icon-only» кнопки должны иметь `title="…"` ИЛИ `aria-label="…"`
- [ ] Проверить: bottom-nav, navbar icons, FAB, table action icons

### 8c — Toast vs Alert: единая система 🎨
- [ ] Уже сделано (`toast_container.html`), проверить все Django messages → toast

### 8d — Hover: только pointer:fine 🎨📱
- [ ] CSS правила с `:hover` должны быть внутри `@media (hover: hover)`
- [ ] Сейчас на touch-устройствах при тапе hover-стиль «прилипает» и не исчезает

### 8e — Transitions: единая `--transition-smooth` 🎨
- [ ] Сейчас разнобой: `.15s`, `.2s`, `.25s`, `.3s`, `ease`, `cubic-bezier(.22,1,.36,1)`, `cubic-bezier(.4,0,.2,1)`
- [ ] Унифицировать: 3 значения — `--transition-fast (.15s)`, `--transition-base (.2s)`, `--transition-smooth (.3s cubic-bezier(.22,1,.36,1))`

---

## BLOCK 9 — Доступность (A11Y) ♿

### 9a — Focus states видимость ♿
- [ ] Есть в `base.css` глобальный `:focus-visible` — проверить, что не перебивается inline `outline:none`

### 9b — Контрастность по WCAG AA ♿
- [ ] Уже улучшено в прошлом аудите (`--text-muted: 0.5 → 0.58`)
- [ ] **Дополнительно проверить**:
  - [ ] `cab-sub` (rgba 0.5) — описание под именем в hero
  - [ ] `vh-date`, `vh-service` (rgba 0.4-0.42)
  - [ ] `dash-stat-lbl` — мелкие label-ы в дашборде

### 9c — Screen reader hints ♿
- [ ] Иконки-only кнопки → `aria-label`
- [ ] `<canvas>` particles → `aria-hidden="true"`
- [ ] Decorative icons → `aria-hidden="true"`

### 9d — Form labels and errors ♿
- [ ] Все `<input>` имеют `<label for="…">` или `aria-label`
- [ ] Ошибки валидации связаны с input через `aria-describedby`

---

## BLOCK 10 — Документация и Onboarding для разработчиков 📝

> Не критично, но полезно после рефакторинга

### 10a — Создать `STYLEGUIDE.md` 📝
- [ ] Описать design tokens, основные классы, naming conventions

### 10b — Создать playground страницу `/dev/components/` 📝
- [ ] Видеть все компоненты (кнопки, badges, cards, forms) на одной странице — debug-tool для дизайнера

---

# 📊 ИТОГ И ПРИОРИТЕТЫ

## Самые критичные проблемы (фиксить первыми)

| # | Проблема | Где | Блок | Effort |
|---|----------|-----|------|--------|
| 1 | Французский текст на главной hero | `index.html:526` | 4a | 5 мин |
| 2 | Две дизайн-системы партнёра (pp-wrap + dash) | весь partner flow | 2a | 1–2 дня |
| 3 | Профиль перегружен (13 карточек) | `profile.html` | 3b | 1 день |
| 4 | ACR-форма 200 строк в profile.html | `profile.html` | 3c | 2 часа |
| 5 | Visit history таблица на мобиле | `partials/partner_visit_history.html` | 2c | 3 часа |
| 6 | My Posts таблица в профиле на мобиле | `profile.html` | 3g | 2 часа |
| 7 | 445 `!important` в CSS | весь CSS | 1b | 1 день |
| 8 | dark-theme-fixes.css антипаттерн (160 !important) | `dark-theme-fixes.css` | 1b | 4 часа |
| 9 | Дубли Quick Actions (3 места) | `profile.html` | 3a | 1 час |
| 10 | Mobile партнёр: нет навигации внутри дашборда | `_partner_layout.html` | 2b | 4 часа |

## Метрики «до/после»

| Метрика | До | Цель |
|---------|----|------|
| CSS файлов | 23 | 8 |
| CSS строк | 14 356 | < 9 000 |
| `!important` | 445 | < 50 |
| Inline `<style>` блоков | ~15 | 0 |
| Дизайн-систем в партнёре | 2 (dash + pp) | 1 |
| Карточек на профиле | 13 | 5 (через табы) |
| Дубликатов Quick Actions | 3 места | 1 |
| Таблиц с overflow-x на мобиле | 3 | 0 (карточки) |

---

## ⚙️ ПОРЯДОК ВЫПОЛНЕНИЯ

> Идём строго по блокам, по команде «Делаем Блок N». После каждого — тестируем и фиксим что сломалось.

1. **Блок 1** — фундамент (без него остальное упадёт от каскадных конфликтов)
2. **Блок 4a** (быстрый фикс) — французский текст на главной (5 минут)
3. **Блок 3** — профиль (видимый импакт для всех пользователей)
4. **Блок 2** — партнёрский портал (импакт для бизнес-пользователей)
5. **Блок 5–7** — постепенно
6. **Блок 8–10** — финальная полировка

---

> **Готов к команде «Делаем Блок 1». Жду! 🚀**
