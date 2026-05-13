# IESA Sport — UX/UI Аудит и план улучшений
> **Роль**: Lead Product Designer, UX/UI Эксперт & Frontend Архитектор  
> **Цель**: сделать сайт удобнее, продуктивнее и приятнее для каждого типа пользователя.  
> **Стратегия**: один блок → тест → галочка → следующий блок.

---

## Обозначения
- `[ ]` — не сделано  
- `[x]` — выполнено  
- ⚡ высокий приоритет / видимый импакт  
- 💅 UI/визуал / микровзаимодействие  
- 🚀 новая фича  
- 📱 специфично для мобильного  
- ♿ доступность  

---

## Что УЖЕ хорошо (не трогаем)
- ✅ **PWA**: manifest + service worker + shortcuts + share target → сайт устанавливается как приложение
- ✅ **Тёмная тема**: glassmorphism-дизайн, красивые токены, консистентный `#dc2626`
- ✅ **HTMX**: лайки, подписки, поиск, уведомления — без перезагрузки страницы
- ✅ **Bottom nav** на мобиле: 5 пунктов, 44px touch-targets, safe-area insets
- ✅ **Skeleton loaders** в дропдауне уведомлений
- ✅ **Toast-система** в base.html с auto-dismiss
- ✅ **Responsive**: mobile-first, 5 брейкпоинтов, viewport-height iOS fix
- ✅ **Анимации**: scroll-reveal, card-hover, magnetic buttons (отключаются на touch)
- ✅ **Доступность**: skip-to-main, ARIA labels, semantic HTML, font-size ≥ 16px на touch
- ✅ **Real-time поиск**: debounced HTMX (400–500ms) с spinner

---

## BLOCK 1 — Онбординг: первый день пользователя ⚡💅 ✅ DONE
> **Проблема**: после регистрации новый пользователь видит пустой профиль и не понимает, что делать. Нет подсказок, нет целей, нет приветствия. Отток на этом этапе максимальный.

### 1a — Welcome-экран после первой регистрации ⚡
- [x] Добавить поле `User.onboarded = BooleanField(default=False)` + миграция 0027
- [x] При `onboarded=False` → welcome-modal: 🏔️ + 3 буллета (карта/PIN/Telegram) + CTA «Let's go» + Skip
- [x] POST `/auth/onboarded/` → `onboarded=True` без перезагрузки; Escape/backdrop-click закрывают
- [x] CSS: backdrop blur + pop-in spring animation + hide-animation при закрытии

### 1b — Progress-бар заполнения профиля ⚡💅 ✅
- [x] `User.profile_completeness` property: 5 шагов (avatar, name, phone, telegram, dob)
- [x] Бар: цвет red→amber→green, анимация fill с delay 400ms, toggle-шевроны для раскрытия шагов
- [x] Скрывается при 100% заполнении; каждый шаг — кликабельная ссылка на нужный раздел

### 1c — Contextual tooltips для новых юзеров 💅 ✅
- [x] CSS `[data-onb-tip]` pseudo-element tooltips на PIN-карточке и QR-карточке
- [x] Показываются только пока `show_quick_actions=True` (до 3 визитов)

### 1d — «Быстрые действия» после онбординга 💅 ✅
- [x] Горизонтальный scroll-carousel (до `total_visits < 3`): Telegram / Add Photo / Find Partner / Write Post / How it works
- [x] Выполненные шаги (Telegram/фото) — зелёный «✓ done» badge вместо ссылки
- [x] Tooltip-подсказки `[data-onb-tip]` на каждой карточке

### 1e — Страница «Как это работает» для новых членов ✅
- [x] `/auth/how-it-works/` — 4 шага с зеркальным layout, scroll-reveal, benefits grid, CTA
- [x] Ссылка в navbar для гостей (между поиском и Sign In)
- [x] Ссылка «How it works» в quick-actions carousel

---

## BLOCK 2 — Навигация: меньше кликов ⚡💅 ✅ DONE
> **Проблема**: до частых действий (написать пост, записаться к партнёру, проверить PIN) нужно 2–3 клика. Нет breadcrumbs в сложных разделах.

### 2a — Быстрые действия в шапке профиля ⚡ ✅
- [x] В хедере профиля (рядом с «Edit Profile») — кнопки быстрых действий в один клик:
  - ✏️ «Написать пост» (только для авторизованных)
  - 📅 «Мой календарь» (если есть встречи)
  - 🛡️ «Страховой агент» (если нет заявки)
- [x] На мобиле (< 600px) — только иконка (`span { display:none }`), текст в `title` tooltip; CSS в `profile-page.css`

### 2b — Breadcrumbs в партнёрском портале 💅 ✅
- [x] Добавить breadcrumbs на страницы с 3+ уровнями вложенности:
  - Партнёрский портал → Журнал визитов → Редактировать визит
  - Партнёрский портал → Аналитика
  - Партнёрский портал → История клиента (Имя)
- [x] Стиль: `>` (`fa-chevron-right`) разделитель, последний элемент без ссылки — в `_breadcrumbs.html`
- [x] HTML: `<nav aria-label="{% trans 'Breadcrumb' %}">` — уже в `_breadcrumbs.html`

### 2c — Sticky «быстрые действия» на партнёрском дашборде ⚡ ✅
- [x] В правом нижнем углу дашборда — FAB (Floating Action Button):
  - Основная кнопка: ✚ (красный круг)
  - По клику — разворачивается веер из 3 кнопок: «Записать визит», «Новая встреча», «Пригласить клиента»
  - Анимация: spring expand с задержкой 50ms между кнопками
- [x] На мобиле: FAB над bottom nav с `bottom: calc(80px + env(safe-area-inset-bottom, 0px))` — в `dashboard.css`

### 2d — Сокращение пути «Найти партнёра → записать визит» ⚡ ✅
- [x] На странице поиска пользователей (`/auth/search/`) у партнёров — добавить кнопку «Записать визит» прямо в карточке результата
  - Только если `request.user.is_partner`
  - Ведёт на `/auth/partner/visit/{user_id}/`

### 2e — «Вернуться» по Swipe на мобиле 📱 ✅
- [x] swipe-right 80px от левого края → `history.back()` на внутренних страницах
- [x] Красный индикатор на левом краю экрана при свайпе
- [x] Добавлен в `touch-gestures.js`; отключён на root-страницах

### 2f — Умная кнопка «Назад» в навбаре 💅 ✅
- [x] На мобиле (`< 992px`) при `history.length > 1` — кнопка `←` перед логотипом
- [x] На root-страницах логотип остаётся нетронутым

---

## BLOCK 3 — Формы и Интерактивность 💅⚡ ✅ DONE
> **Проблема**: формы только с HTML5-валидацией, нет live-feedback, нет автозаполнения, нет масок ввода. Пользователь узнаёт об ошибке только после отправки.

### 3a — Live-валидация при регистрации ⚡💅 ✅
- [x] Username: debounced 500ms → `check-username/?u=` → ✅/✗ icon + цветное сообщение
- [x] Email: format regex + `check-email/?e=` → доступность в реальном времени
- [x] Password: strength bar (4 критерия: длина/uppercase/число/спецсимвол), 4 уровня (red→amber→green→emerald)
- [x] Password confirm: мгновенный `Passwords match / do not match`
- [x] Новый эндпоинт `/auth/check-email/`

### 3b — Автокомплит в форме поиска участника (партнёрский портал) ⚡💅 ✅
- [x] HTMX autocomplete: debounce 300ms, `member-autocomplete/?q=` → HTML dropdown
  - Debounce 300ms, минимум 2 символа
  - Показывает аватар + имя + username + статус (active/inactive)
  - Клавиатурная навигация (↑↓ Enter)
  - Выбор члена заполняет скрытый `member_id` инпут
  - «Не найден» → ссылка «Найти в общем поиске»
- [x] Реализован как HTMX кастомный dropdown (`.mac-dropdown`) с клавиатурной навигацией

### 3c — Маски ввода для контактных полей 💅 ✅
- [x] Swiss phone mask Vanilla JS в base.html (global `_applyPhoneMask`): `+41 79 000 00 00`
- [x] Applied: `id_phone_number` (profile_edit) + `ins-phone` (insurance_agent)

### 3d — Умная форма расписания встречи 💅 ✅
- [x] «Today» / «Tomorrow» / «Clear» quick-select кнопки под date-полем
- [x] End time = start + 1h (auto-fill при выборе start_time)
- [x] Duration label («1h 30min») рядом с END label
- [x] Предупреждение «Date is in the past» при выборе прошедшей даты

### 3e — Inline-сохранение профиля 💅 ✅
- [x] `/auth/profile/field-save/` POST endpoint; 8 разрешённых полей
  - «Автосохранение...» → «Сохранено ✓» анимированный текст под полем
  - Fallback: обычная кнопка «Сохранить» если HTMX-запрос упал
- [x] `password` и `email` не в `ALLOWED` set в `profile_field_save` view — исключены

### 3f — Форма поста: smart CKEditor 💅 ✅
- [x] Draft autosave to localStorage (2s debounce + 10s interval + beforeunload guard)
- [x] Draft restore on page load (7-day TTL, merges with Quill/CKEditor/textarea)
- [x] `_iesa_quill_hook` для интеграции с динамически инициализированным Quill

### 3g — Drag-and-drop загрузка аватара 💅📱 ✅
- [x] Drop zone в profile_edit: красная рамка при drag-over, превью после выбора
- [x] Mobile: `<input type="file" accept="image/*">` на невидимом overlay (tap→gallery/camera)
- [x] File → real Django `id_avatar` input через DataTransfer API
- [x] Размер и имя файла показываются под зоной

---

## BLOCK 4 — Пустые состояния ⚡💅 ✅ DONE
> **Проблема**: когда нет данных — пользователь видит либо пустой контейнер, либо простой текст. Хорошие empty states направляют к действию и не демотивируют.

### 4a — Partner Dashboard — нет визитов сегодня 💅 ✅
- [x] Текущее: пустая таблица → Новое: 🏃 emoji + заголовок + subtitle + кнопка «Log a Visit» → #search-section
- [x] Анимация float-icon (3s ease-in-out)

### 4b — Calendar — нет встреч на выбранный день 💅 ✅
- [x] JS-overlay `.cal-no-meetings` поверх почасовой сетки: 📅 + заголовок + subtitle + кнопка «Schedule Meeting»
- [x] `toggleEmptyOverlay()` вызывается в DOMContentLoaded: показывает overlay если `MEETINGS.length === 0`
- [x] Клик на кнопку — разворачивает форму + скроллит к #add-meeting

### 4c — Analytics — нет данных за период 💅 ✅
- [x] `{% if total_30 == 0 %}` — вместо пустых графиков: 📊 + заголовок + subtitle + CTA «Log First Visit»
- [x] Пунктирная рамка (dashed border), анимация float-icon

### 4d — Blog — фильтр вернул 0 результатов 💅 ✅
- [x] В `posts_list_fragment.html` `{% else %}`: 🔍 + «No posts found for your query» + кнопка «Reset Filters»
- [x] Кнопка очищает поля input/select через JS + hx-get на базовый URL

### 4e — Поиск пользователей — нет результатов 💅 ✅
- [x] `{% empty %}` в `search_results.html`: 👤 + «No results for "query"» + subtitle + кнопка «Invite to IESA Sport»
- [x] Кнопка → `{% url 'users:invite_generate' %}` (только авторизованным)

### 4f — Уведомления — все прочитаны 💅 ✅
- [x] `total_count` добавлен в контекст view `notification_list`
- [x] Два отдельных empty state: `total_count > 0` → «All caught up! ✅» ; `total_count == 0` → «No notifications yet 🔔»

### 4g — Галерея — нет фотографий 💅 ✅
- [x] Анимированная пунктирная рамка (dash-border keyframe: red↔white 3s)
- [x] 📸 emoji + «Your first shot goes here»
- [x] Staff → кнопка «Upload Photos» → `/admin/gallery/photo/add/`
- [x] Обычный юзер → кнопка «Explore Community» → blog:post_list

---

## BLOCK 5 — Обратная связь и Микровзаимодействия ⚡💅 ✅ DONE
> **Проблема**: система тостов есть, но Django-messages рендерятся как `<div class="alert">` (не как тосты). Некоторые действия не дают никакой обратной связи.

### 5a — Унификация Django messages → Toast ⚡💅 ✅
- [x] Удалён дублирующий `{% if messages %}` блок из `base.html` — `toast_container.html` уже рендерит Django messages как Bootstrap toasts

### 5b — Состояния кнопок при ожидании ⚡💅 ✅
- [x] HTMX: `htmx:beforeRequest/afterRequest` → `opacity .65; cursor: wait; disabled` на триггере
- [x] Vanilla-формы: глобальный `submit` listener → spinner в кнопке, `pageshow` восстанавливает

### 5c — Skeleton loaders для автокомплита 💅 ✅
- [x] 3 skeleton-строки в `#mac-skeleton` в partner_dashboard; показываются при `htmx:beforeRequest`, скрываются после

### 5d — Анимация лайка 💅 ✅
- [x] `@keyframes heart-pop`: scale 1→1.45→0.9→1 (0.45s) в `like_button.html`
- [x] Класс `.heart-pop` добавляется в onclick до HTMX swap

### 5e — Конфетти после логирования визита 💅🚀 ✅
- [x] `log_visit.html`: CSS `@keyframes confetti-fall` + 30 частиц на submit (8 цветов, случайные позиции)
- [x] `navigator.vibrate(200)` haptic feedback при submit

### 5f — Copy-to-clipboard PIN → Toast + haptic 💅 ✅
- [x] PIN copy в `profile.html`: `window._iesa_showToast('PIN скопирован ✓', 'success')`
- [x] `navigator.vibrate(50)` лёгкий тик при копировании

### 5g — Pull-to-refresh на мобиле 📱 ✅
- [x] `touch-gestures.js`: `[data-pull-refresh]` attribute → pull-down 70px → красный spinner → `location.reload()` или HTMX trigger
- [x] Добавлен на `post_list.html` (`#posts-container`) и `notification_list.html`

---

## BLOCK 6 — Мобильный опыт ⚡📱💅 ✅ DONE
> **Проблема**: базово мобиль уже хорош, но есть точки трения при интенсивном использовании (партнёр логирует 10+ визитов в день, юзер проверяет PIN в спортзале).

### 6a — PIN-экран как полноэкранный «карточный» вид 📱⚡ ✅
- [x] Кнопка «Full» видима только на мобиле (< 992px), управляется JS resize-listener
- [x] Fullscreen overlay: `background:#050510`, `z-index:10000`, flex-center
- [x] PIN крупным шрифтом (`clamp(3.5rem,14vw,6rem)`, monospace, `#f87171`)
- [x] SVG circular countdown (r=14, stroke-dasharray=87.96), синхронизирован через MutationObserver на `#pin-cnt`
- [x] Кнопка «Copy PIN» → clipboard + showToast + vibrate(50)
- [x] Закрыть: ✕ кнопка / Escape / swipe-down 100px
- [x] `navigator.wakeLock.request('screen')` для яркости экрана

### 6b — QR-код — быстрый доступ 📱⚡ ✅
- [x] В bottom nav: круглая красная кнопка QR (только `membership_status == 'active'`)
- [x] Fullscreen overlay белым фоном (`background:#fff`) — максимальный контраст для сканирования
- [x] `navigator.wakeLock` при открытии
- [x] Закрыть: кнопка / swipe-down 80px / Escape

### 6c — Партнёр: быстрое логирование через мобиль ⚡📱 ✅
- [x] Кнопка «Visit» в bottom nav (только для `is_partner=True`)
- [x] Bottom sheet: HTMX autocomplete поиск → клик → redirect на `/auth/partner/visit/{id}/`
- [x] Ссылка «Open full dashboard» для развёрнутого флоу

### 6d — Bottom sheet компонент 💅📱 ✅
- [x] CSS: `position:fixed; bottom:0; border-radius:20px 20px 0 0; transform:translateY(100%); transition .35s cubic-bezier`
- [x] `.bs-handle` drag handle + swipe-down > 100px → close
- [x] `.bs-backdrop` с `backdrop-filter:blur(3px)`
- [x] `window.IESABottomSheet.open(id)` / `.close(id)` API

### 6e — Оффлайн-режим 📱🚀 ✅
- [x] `service-worker.js` полностью переписан: cache-first для /static/, network-first для HTML, stale-while-revalidate для профилей/уведомлений
- [x] STATIC_ASSETS список исправлен (убраны несуществующие файлы — причина падения install)
- [x] `/offline/` страница + Django view + URL
- [x] NO_CACHE_PATTERNS: admin, api, login, logout, partner portal — никогда не кэшируются

### 6f — Haptic feedback на мобиле 📱💅 ✅
- [x] Успешный визит: `vibrate(200)` при submit (log_visit.html)
- [x] Ошибка PIN: `vibrate([100,50,100])` — двойная вибрация при наличии `errorlist` в PIN-поле
- [x] Copy PIN: `vibrate(50)` лёгкий тик (profile.html + fullscreen)

---

## BLOCK 7 — Партнёрский портал: профессиональный инструмент ⚡💅 ✅ DONE
> **Проблема**: партнёры используют портал ежедневно для бизнес-операций. Интерфейс должен быть максимально быстрым, информативным и не требовать думать.

### 7a — Dashboard: real-time счётчики ⚡💅 ✅
- [x] `.dash-stat-grid` оборачивает весь grid с `hx-get="partner_today_stats" hx-trigger="every 60s" hx-swap="outerHTML"`
- [x] `partner_today_stats` view возвращает partial `partner_today_stats.html` (full grid)
- [x] Пульсирующая зелёная точка `.stat-pulse-dot` если был визит за последние 30 минут

### 7b — История визитов: умные фильтры 💅 ✅
- [x] Новый view `partner_visit_history` + partial `partner_visit_history.html`
- [x] Pill-фильтры: All / Today / This week / This month (period) + All / PIN verified / Cancelled (status_f)
- [x] История загружается при `hx-trigger="load"` в `#visit-history-wrap`, фильтры меняют содержимое через HTMX без перезагрузки
- [x] Пагинация с сохранением фильтров в параметрах запроса

### 7c — Inline статус визита 💅 ✅
- [x] `.vh-status-badge[data-tooltip]::after` CSS tooltip при hover
- [x] ACTIVE → «Confirmed via PIN», EDITED → «Was edited...», CANCELLED → «причина если есть»

### 7d — Карточка клиента на дашборде 💅 ✅
- [x] `.rc-item` + `.rc-link` с data-атрибутами (id, name, visits, last, status)
- [x] `#rc-popup`: fixed position, показывается при mouseenter с setTimeout, скрывается при mouseleave
- [x] Popup содержит: имя, статус (●ACTIVE/INACTIVE), счётчик визитов, последний визит, кнопки «Log» и «History»
- [x] JS mouseenter/mouseleave с задержкой 150-200ms для плавного UX

### 7e — Экспорт данных 🚀 ✅
- [x] `partner_visits_csv` view: `StreamingHttpResponse` с `csv.writer(Echo())`, Content-Disposition attachment
- [x] Кнопка «CSV» в заголовке блока истории, рядом с «Analytics →»

### 7f — Calendar: drag-to-create встречу 🚀💅 ✅
- [x] `mousedown/mousemove/mouseup` на `.cal-hour-content` в `partner_calendar.html`
- [x] `.cal-drag-block` с dashed border показывает временной диапазон в реальном времени
- [x] При mouseup (≥15 мин) — заполняет start/end + открывает форму + focus на title
- [x] Курсор `crosshair` при наведении на свободную ячейку

### 7g — Напоминания о встречах ⚡🚀 ✅
- [x] `python manage.py send_meeting_reminders [--hours N] [--dry-run]`
- [x] Окно ±30 мин вокруг target datetime; idempotent через `get_or_create`
- [x] In-site Notification + TG отправка если `telegram_chat_id` привязан
- [x] Heroku Scheduler: `send_meeting_reminders --hours 24` раз в день

---

## BLOCK 8 — Блог и Сообщество 💅🚀 ✅ DONE (core items)
> **Проблема**: блог работает, но не «цепляет». Нет Reading Time, нет рекомендаций на основе активности, нет тёплых точек взаимодействия.

### 8a — Reading Time на постах 💅 ✅
- [x] `Post.read_time_minutes` property: `max(1, word_count // 200)` с `strip_tags`
- [x] Отображается в `pd-meta`: «X min read» рядом с просмотрами

### 8b — Reading Progress Bar 💅 ✅
- [x] `#reading-progress`: `position:fixed;top:0;height:2px;background:var(--primary)`, `z-index:9999`
- [x] JS scroll listener обновляет `width` с `transition:.1s linear`, passive event

### 8c — Related Posts scroll-carousel на мобиле 💅 ✅
- [x] `.pd-rec-carousel`: `overflow-x:auto; scroll-snap-type:x mandatory` на мобиле
- [x] На десктопе (≥ 768px) — `display:grid` через media query

### 8d — Comment threading collapse/expand ✅
- [x] Первые 3 ответа всегда видны, `cm-reply-hidden` скрыты по умолчанию
- [x] Кнопка «Show N more replies» / «Collapse» — чистый vanilla JS inline
- [x] Анимация `fadeInUp .25s` при раскрытии

### 8e–8g — Reactions, Bookmarks, Activity (отложено)
- [ ] Требуют новых Django моделей — в следующей итерации

---

## BLOCK 9 — Геймификация и Удержание 🚀⚡ (отложено)
> Требует создания новых моделей (Achievement, Streak) и значительной логики бэкенда.
> Запланировано в следующей итерации разработки.

---

## BLOCK 10 — Новые Фичи: Экосистема 🚀⚡ ✅ DONE (core items)
> Фичи, которых нет, но которые сделают платформу значительно более ценной для пользователей.

### 10a — Экспорт календаря встреч (.ics) 🚀⚡ ✅
- [x] `user_calendar_ics` view: RFC 5545 iCalendar, `content_type='text/calendar'`
- [x] Поддержка: `DTSTART/DTEND` с временем если задано, иначе `VALUE=DATE`
- [x] Кнопка «Export .ics» на странице «My Calendar»
- [x] Зарегистрирован URL `/auth/my-calendar/export.ics`

### 10b — Тёмная / Светлая тема (Toggle) 🚀💅 ✅
- [x] Кнопка 🌙/☀️ в navbar (`.btn-nav-icon#theme-toggle`)
- [x] `:root[data-theme="light"]` переменные: bg-body, bg-surface, text-primary, nav-bg
- [x] `localStorage.setItem('iesa-theme', ...)` сохраняет выбор
- [x] Тема применяется при загрузке страницы до рендера контента (script в `<head>` зоне)
- [x] `transition: background-color .2s, color .2s` на `:root`

### 10c — PWA Install Prompt 🚀📱 ✅
- [x] `beforeinstallprompt` event → bottom sheet через 30 секунд
- [x] Кнопка «Install» → `deferredPrompt.prompt()`
- [x] «Not now» → `localStorage.setItem('pwa-dismissed', Date.now())` — скрыть на 7 дней
- [x] Не показывать в standalone режиме (`display-mode: standalone`)

### 10d — Поиск партнёров на карте 🚀💅 ✅
- [x] `Partner.address_full`, `lat`, `lon` поля + миграция 0028
- [x] `/partners/map/` view + шаблон с Leaflet.js + OpenStreetMap (dark mode filter)
- [x] `/partners/map/data/` JSON endpoint для markers
- [x] Кастомный красный drop-pin маркер, popup: название/тип/адрес/кнопка «Visit Profile»
- [x] Геолокация: кнопка `crosshairs` → `navigator.geolocation` → синий circleMarker

### 10e — Real-time Уведомления (SSE) 🚀⚡ ✅
- [x] `/notifications/stream/` StreamingHttpResponse, `text/event-stream`, keepalive comment
- [x] Client: `EventSource`, event `badge` обновляет `#navbar-notif-badge`
- [x] `X-Accel-Buffering: no` для nginx; timeout 50s (< Heroku 55s)
- [x] Fallback: `es.onerror → es.close()`, hx polling продолжает работать

### 10f — Умный поиск с подсказками 🚀💅 ✅
- [x] `localStorage` «Recent searches» (5 записей) показываются при фокусе
- [x] Кнопка «Clear history»; сохранение при Enter и клике на результат
- [x] `#search-suggestions` показывает список при пустом поле

### 10g — Open Graph превью 🚀 ✅
- [x] `profile.html`: OG type=profile, og:title=fullname, og:image=avatar, og:description=level
- [x] `profile_public.html`: аналогично для публичного профиля
- [x] `post_detail.html`: уже был реализован ранее

### 10h — Страница достижений (отложено)
- [ ] Требует создания модели Achievement — в следующей итерации

---

## Приоритизация по матрице Impact × Effort

### Сделать сразу (высокий impact, низкий effort)
| № | Улучшение | Блок | Effort |
|---|-----------|------|--------|
| 1 | Django messages → Toast | 5a | 2ч |
| 2 | Skeleton loaders для HTMX | 5c | 3ч |
| 3 | Empty states партнёрский дашборд | 4a, 4b | 2ч |
| 4 | Reading Time для постов | 8a | 1ч |
| 5 | Reading Progress Bar | 8b | 2ч |
| 6 | Кнопки submit → loading state | 5b | 2ч |
| 7 | PIN fullscreen на мобиле | 6a | 4ч |
| 8 | Live-валидация регистрации (username check) | 3a | 3ч |
| 9 | Copy PIN → toast (не alert) | 5f | 1ч |
| 10 | PWA Install Prompt | 10c | 4ч |

### Следующие спринт (высокий impact, средний effort)
| № | Улучшение | Блок | Effort |
|---|-----------|------|--------|
| 11 | Welcome-модал для новых | 1a | 6ч |
| 12 | Progress-бар профиля | 1b | 4ч |
| 13 | Autocomplete поиск участника | 3b | 6ч |
| 14 | Экспорт календаря .ics | 10a | 4ч |
| 15 | Bottom sheet логирования | 6c, 6d | 8ч |
| 16 | Ачивки (3 начальных) | 9a | 8ч |

### Стратегические (высокий impact, высокий effort)
| № | Фича | Блок | Effort |
|---|------|------|--------|
| 17 | Тёмная/светлая тема toggle | 10b | 16ч |
| 18 | SSE уведомления | 10e | 12ч |
| 19 | Карта партнёров | 10d | 16ч |
| 20 | Streak + Leaderboard | 9b, 9c | 12ч |
| 21 | Activity Feed | 8g | 20ч |

---

## Текущий UX-долг ✅ DONE
- [x] ♿ aria-label на иконках navbar (QR, уведомления, поиск, профиль, тема)
- [x] 💅 Notification dropdown: eager-load через 1.5с при загрузке страницы
- [x] 💅 Форма логина: `autofocus` на поле username
- [x] 💅 Форма регистрации: `tabindex` 1-4 на полях (username→email→pw1→pw2)
- [x] 💅 404-страница: кнопка «Go back» с `history.back()` при `history.length > 1`
- [x] 💅 Модальные: Bootstrap поддерживает Escape нативно; кастомные (PIN/QR) — добавлен Escape listener
- [x] 💅 Navbar search: `hide.bs.dropdown` очищает поле и результаты
- [x] 📱 `#meta-theme-color` обновляется динамически при смене темы (dark→`#0e0e18`, light→`#f4f6fb`)
- [x] 💅 `@media (hover: hover)` уже есть в `card-animations.css` — верифицировано

---

*Создан: 2026-05-13 | Исполнитель: Claude Sonnet 4.6 (Lead Product Designer mode)*
