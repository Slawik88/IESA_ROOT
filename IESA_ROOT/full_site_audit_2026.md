# IESA Full Site Audit — Март 2026

> Полный аудит сайта: дизайн, UX, код, безопасность, производительность.
> Референс дизайна: **index.html** (homepage IESA REDESIGN 2026).

---

## СОДЕРЖАНИЕ

1. [Дизайн-система — Референс (homepage)](#1-дизайн-система)
2. [Telegram — Привязка для всех пользователей](#2-telegram)
3. [Страницы, нуждающиеся в редизайне](#3-страницы-нуждающиеся-в-редизайне)
4. [Частичные шаблоны (partials) с устаревшим стилем](#4-partials)
5. [CSS проблемы](#5-css-проблемы)
6. [JavaScript проблемы](#6-javascript)
7. [UX / навигация / доступность](#7-ux)
8. [Производительность](#8-производительность)
9. [Безопасность](#9-безопасность)
10. [Сводная таблица файлов для редизайна](#10-сводная-таблица)

---

## 1. ДИЗАЙН-СИСТЕМА

### Референс: `core/templates/core/index.html` (971 строк)

Homepage задаёт стандарт:

#### Цвета
| Переменная | Значение | Применение |
|---|---|---|
| Фон тёмных секций | `#0a0a0f` | Hero, Stats, About, Donate |
| Фон светлых секций | `#f2f2f8` / `#eeeef6` / `#f5f5fb` | Offers, Mission, Products, Events, Partners |
| Карточки | `#ffffff` | Поверх тонированных секций |
| Акцент (primary) | `#dc2626` | Кнопки, иконки, градиенты |
| Glow-эффекты | `rgba(220,38,38,.12-.22)` | Radial-gradient облака на тёмных секциях |
| Текст основной | `var(--text-primary)` | Заголовки на светлом |
| Текст вторичный | `var(--text-muted)` / `var(--text-secondary)` | Описания |
| Текст на тёмном | `#fff` / `rgba(255,255,255,.4-.65)` | Всё на #0a0a0f секциях |

#### Типографика
| Элемент | Стиль |
|---|---|
| Section label | `.hp-label` — 0.72rem, uppercase, 0.2em spacing, с линиями `::before/::after` |
| Section heading | `.hp-h2` — `clamp(2rem, 4vw, 3.2rem)`, weight 900, letter-spacing -.03em |
| Section sub | `.hp-sub` — 1.05rem, color muted, max-width 540px |
| Section divider | `.hp-divider` — 48px × 3px красная полоска |
| Container | `.hp-container` — max-width 1200px |

#### Карточки
| Свойство | Значение |
|---|---|
| Border radius | `16px` – `24px` |
| Border | `1.5px solid var(--border-color)` |
| Hover border | `var(--primary)` |
| Hover transform | `translateY(-3px...-5px)` |
| Hover shadow | `0 12px-24px 40px-60px rgba(...)` |
| Background overlay | `::before` с `linear-gradient(135deg, rgba(220,38,38,.04)...)` |

#### Анимации
| Система | Реализация |
|---|---|
| Scroll reveal | `[data-reveal]` + IntersectionObserver → `.revealed` |
| Stagger delay | `[data-delay="1-5"]` → transition-delay .1s-.5s |
| 3D tilt | `.tilt3d` — `perspective(600px) rotateY/rotateX` на mousemove |
| Magnetic buttons | `.mag-btn` — translate на mousemove |
| Counter animation | `animCnt()` — cubic ease-out числовой подсчёт |
| Word swap | `.dynamic-word` — skewY анимация входа/выхода |
| Canvas particles | `#hp-hero-canvas` — 75 точек с линиями соединения |
| Donation bar | `.don-fill.animated` — width transition 1.6s |

#### Секции homepage (10 штук)
1. **Hero** — full-height, canvas, word swap, stats counter, scroll indicator
2. **Offers** — 2×2 grid, numbered cards (01-04), icon hover rotate
3. **Stats Band** — dark, 4-cell grid, emoji + text, hover underline
4. **Mission** — split layout (text + 3 panels), check-mark list
5. **Products** — 2-col grid, image aspect-ratio 16/9, tags, features
6. **Events** — 3-col grid, date badge, foot arrow transition
7. **About/Team** — president hero card, members 2-col grid, dark modal
8. **Partners** — marquee track + 3-col grid, category badges, HTMX modal
9. **Benefits** — 4-col grid, icon rotate hover, gradient ::after overlay
10. **Donate** — dark split layout, progress bar, donation pillars

---

## 2. TELEGRAM — ПРИВЯЗКА ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ

### ✅ Исправлено в этой сессии

**Было**: Telegram привязка технически доступна всем, но:
- После привязки редирект шёл на `member_cabinet` (требует активного членства)
- `telegram_login_callback_view` не имел `@login_required`
- Early-return пути в `member_cabinet` не передавали telegram-переменные

**Стало**:
- Все redirect'ы из `connect_telegram_code_view`, `disconnect_telegram_view`, `telegram_login_callback_view` → `users:profile`
- `telegram_login_callback_view` защищён `@login_required`
- Early-return пути в `member_cabinet` передают `telegram_linked`, `telegram_bot_configured`, `telegram_bot_name`
- `profile.html` показывает полный блок Telegram: CTA если не привязан, статус + кнопка отвязки если привязан

### Файлы затронутые
| Файл | Изменение |
|---|---|
| `users/views_verification.py` | Redirect → profile, @login_required, telegram vars в early-return |
| `users/templates/users/profile.html` | Telegram connected/not-connected блок с disconnect кнопкой |

---

## 3. СТРАНИЦЫ, НУЖДАЮЩИЕСЯ В РЕДИЗАЙНЕ

### Критерий: страница extends base.html, видна пользователям, но использует OLD Bootstrap стиль (белые карточки, bg-primary, btn-outline-*, card shadow-sm, нет dark theme)

---

### 3.1 ❌ `users/templates/users/partner_dashboard.html` (353 строк)
**Что это**: Дашборд партнёра — статистика, поиск участников, таблица визитов  
**Текущий стиль**: Белые `card shadow-sm`, цветные gradient карточки (`linear-gradient(135deg, #f093fb, #f5576c)`), `table-light`, `badge bg-success`, `btn-light`  
**Что нужно**:
- Тёмный фон страницы (`#0e0e18`)
- Hero-band с `hp-label` + `hp-h2` стилем
- Stat-карточки в стиле homepage stats band (тёмные ячейки с hover)
- Поисковая карточка: тёмный фон `#111118`, `1.5px border rgba(255,255,255,.08)`
- Таблица: тёмная (`background: rgba(255,255,255,.03)`, row borders `.06`)
- Badges: полупрозрачные на тёмном фоне
- Кнопки: `hero-btn-p` / ghost стиль

---

### 3.2 ❌ `users/templates/users/log_visit.html` (129 строк)
**Что это**: Форма записи визита участника (для партнёра)  
**Текущий стиль**: Белый `card shadow-sm`, `card-header bg-primary text-white`, `badge bg-success`, стандартные Bootstrap формы  
**Что нужно**:
- Тёмная страница `#0e0e18`
- Карточка участника: `background: rgba(255,255,255,.03)`, 16px радиус, 1.5px border
- Аватар: красная рамка как в homepage team section
- Форма: тёмные inputs (`#1a1a24`), red focus glow, labels uppercase 0.72rem
- Сабмит кнопка: `hero-btn-p` стиль
- Back link: ghost button стиль

---

### 3.3 ❌ `users/templates/users/edit_visit.html` (117 строк)
**Что это**: Редактирование визита с обратным отсчётом  
**Текущий стиль**: `card shadow-sm`, `bg-warning bg-opacity-25`, розовый gradient header  
**Что нужно**:
- Тёмная страница
- Alert → тёмный с amber/warning иконкой (`rgba(245,158,11,.12)`)
- Карточка визита: тёмная, 16px радиус
- Форма: тёмные inputs, красный submit
- Countdown: крупные числа, как hero-stat-num

---

### 3.4 ❌ `users/templates/users/cancel_visit.html` (115 строк)
**Что это**: Подтверждение отмены визита  
**Текущий стиль**: `card shadow-sm`, `bg-danger bg-opacity-25`, красный gradient header  
**Что нужно**:
- Тёмная страница
- Danger alert: тёмный с красной иконкой (`rgba(239,68,68,.12)`)
- Confirm кнопка: красный gradient как hero-btn-p но с иконкой ⚠️
- Cancel кнопка: ghost стиль

---

### 3.5 ❌ `users/templates/users/member_scan_card.html` (80 строк)
**Что это**: Публичный профиль при сканировании QR-кода  
**Текущий стиль**: Полностью белый Bootstrap — `card shadow-sm`, `bg-secondary` аватар, `badge bg-success`, `alert alert-success/info`  
**Что нужно**:
- Тёмная страница `#0e0e18`
- Стиль как `profile_public.html` — hero strip с radial glow
- Аватар: 100px, красная рамка + ring shadow
- Badge: полупрозрачный зелёный на тёмном
- Card info: тёмная карточка с border `rgba(255,255,255,.08)`
- "For Partners" инфо-блок: тёмный alert с blue accent

---

### 3.6 ❌ `users/templates/users/profile_deactivate_confirm.html` (81 строка)
**Что это**: Подтверждение деактивации аккаунта  
**Текущий стиль**: `card border-danger`, `bg-danger text-white` header, `alert alert-warning`, стандартные формы  
**Что нужно**:
- Тёмная страница
- Warning карточка: тёмная с красной границей (`rgba(239,68,68,.3)`)
- Список последствий: иконки + текст rgba(255,255,255,.65)
- Password input: тёмный (#1a1a24) с красным focus
- Danger кнопка: красный gradient
- Cancel: ghost стиль

---

### 3.7 ❌ `templates/core/htmx/partner_modal.html` (197 строк)
**Что это**: HTMX модалка деталей партнёра (загружается с homepage)  
**Текущий стиль**: `background: #fff`, `border: 2px solid #f0f4ff`, light pastel цвета  
**Что нужно**:
- IMPORTANT: Модалка загружается в разных контекстах — на homepage НЕ тёмная, но на partnerModal контент должен быть нейтральным
- Использовать CSS переменные: `var(--bg-surface)`, `var(--text-primary)`
- Или: добавить класс `.partner-modal-dark` и стилизовать через него
- Border: `1.5px solid var(--border-color)`
- Logo placeholder: gradient фон вместо `#f0f4ff`
- Кнопки: `hero-btn-p` / `hero-btn-g` стиль

---

### 3.8 ❌ `templates/blog/partners.html` (170 строк)
**Что это**: Include-partial для отображения партнёров (не на homepage)  
**Текущий стиль**: `background: linear-gradient(180deg, #f8fbff, #f0f6ff)`, `border: 2px solid #e3ecf5`  
**Что нужно**:
- Переделать на тёмную тему
- Или удалить если не используется (homepage имеет свою секцию партнёров)
- Если используется — карточки в стиле `pc-v2` с homepage

---

## 4. PARTIALS С УСТАРЕВШИМ СТИЛЕМ

### 4.1 ⚠️ `blog/templates/blog/partials/post_list_items.html` (83 строки)
**Проблема**: `text-dark` на ссылке (строка 23) — Bootstrap `text-dark` расставляет `color: #212529 !important`, невидим на тёмном фоне  
**Что нужно**:
- Заменить `text-dark` → убрать или заменить на CSS-переменную
- `card card-modern` → проверить что `.card-modern` из components.css рендерит правильно на тёмном фоне (ответ: да, `.card-modern` использует `var(--gradient-card)`)
- `badge bg-primary-subtle` → проверить цвет на тёмном
- `bg-secondary` аватар fallback → `rgba(255,255,255,.08)` для тёмной темы

### 4.2 ⚠️ `blog/templates/blog/htmx/comments_section.html` (142 строки)
**Проблема**: Использует `card card-modern`, `btn btn-sm btn-outline-primary btn-modern`, `btn-outline-secondary`, `btn-primary`  
**Что нужно**:
- `btn-outline-primary` → ghost button стиль (`border: 1px solid rgba(...)`, color: var(--primary))
- `btn-outline-secondary` → ghost стиль
- `btn-primary` → `hero-btn-p` стиль для submit
- Comment card: убедиться что `.card-modern` работает (работает — использует CSS vars)
- Reply card: отступ + немного темнее фон

### 4.3 ⚠️ `blog/templates/blog/htmx/comment_like_button.html`
**Проблема**: `btn btn-sm btn-outline-secondary` + `text-primary`  
**Что нужно**: Заменить на engage-chip стиль (как like_button.html)

### 4.4 ⚠️ `blog/templates/blog/htmx/post_search_results.html` (blog)
**Проблема**: `list-group`, `list-group-item-action`, `text-muted`, emoji-prefix  
**Что нужно**: Тёмные list items (`rgba(255,255,255,.03)` hover), убрать emoji, добавить иконки Font Awesome

### 4.5 ⚠️ `templates/blog/htmx/post_search_results.html` (global)
**Проблема**: Аналогично — `list-group`, `text-dark`, `fw-bold`  
**Что нужно**: Универсальная тёмная стилизация

### 4.6 ⚠️ `users/templates/users/partials/partner_search_results.html`
**Проблема**: `border: 2px solid #e9ecef`, `color: #495057`, light pink gradient empty state  
**Что нужно**: Тёмная стилизация (`rgba(...)` borders, light text)

---

## 5. CSS ПРОБЛЕМЫ

### 5.1 `static/css/pages.css` — ~35 hardcoded белых цветов
**Проблема**: `background: #fff`, `background: white !important`, `border: N solid white`, пастельные фоны (`#fff5f5`, `#fff8ed`)  
**Примеры строк**: 30, 114, 174, 437, 465, 469, 500, 527, 575, 604, 606, 633, 1303, 1432, 1444, 1453, 1465, 1500, 1518, 1533  
**Что нужно**: Заменить на CSS переменные: `var(--card-bg)` / `var(--bg-surface)` / `var(--bg-body)`

### 5.2 `templates/base.html` строка 15 — theme-color
**Проблема**: `<meta name="theme-color" content="#ffffff">` — браузер показывает белую полоску на тёмном сайте  
**Что нужно**: Изменить на `#0e0e18` (или dynamic через Django)

### 5.3 Inline styles в шаблонах
**Проблема**: Многие шаблоны (index.html, profile.html, member_cabinet.html) используют обильные inline `style=""` вместо классов  
**Что нужно**: Не критично для работы, но затрудняет maintenance. При редизайне страниц — выносить в `<style>` / `{% block extra_css %}`

---

## 6. JAVASCRIPT

### 6.1 ⏳ Три системы lazy-loading
**Файлы**: `performance-optimization.js` (initLazyLoading), `partner-card-effects.js` (lazyLoadLogos), `mobile-optimization.js`  
**Что нужно**: Консолидировать в одну систему или использовать нативный `loading="lazy"`

### 6.2 `member_scan_card.html` — нет JS для dark theme
**Проблема**: Standalone карточка не подключает homepage-JS (canvas, tilt, reveal)  
**Что нужно**: Как минимум `[data-reveal]` observer если добавляем анимации

---

## 7. UX / НАВИГАЦИЯ

### 7.1 Mobile bottom nav — active state
**Проблема**: Нижняя навигация на мобильных не подсвечивает текущий раздел  
**Что нужно**: JS-определение текущего URL и добавление `.active` класса

### 7.2 Body-lock sync
**Проблема**: При открытии hamburger-меню body не лочится (можно скроллить фон)  
**Что нужно**: `document.body.style.overflow = 'hidden'` при открытии menu

### 7.3 Breadcrumbs
**Текущее**: Нет breadcrumbs ни на одной странице  
**Что нужно**: Добавить на inner pages (post_detail, event_detail, profile, gallery) в стиле тёмной темы

### 7.4 Partner Dashboard — нет пагинации визитов
**Проблема**: Все визиты в одной таблице, нет пагинации
**Что нужно**: Пагинация или infinite scroll с HTMX

---

## 8. ПРОИЗВОДИТЕЛЬНОСТЬ

### 8.1 `members` query в IndexView не ограничен
**Файл**: `core/views.py` — `AssociationMember.objects.all()`  
**Что нужно**: `.order_by('order')[:12]` или подобное ограничение

### 8.2 N+1 в post_detail
**Файл**: `blog/views.py` — комментарии и лайки не prefetch'атся  
**Что нужно**: `select_related('author')`, `prefetch_related('likes', 'replies__author')`

### 8.3 Homepage загружает ~15 JS файлов
**Что нужно**: Bundle homepage-specific JS отдельно от global

---

## 9. БЕЗОПАСНОСТЬ

### 9.1 `{{ post.text|safe }}` в post_detail.html
**Проблема**: XSS если CKEditor не санитизирует серверную сторону  
**Что нужно**: Верифицировать что CKEditor 5 sanitizes HTML. Или добавить bleach

### 9.2 `{{ member.description|safe }}` в index.html
**Проблема**: Данные в data-attribute → innerHTML в JS модалке  
**Что нужно**: Sanitize на сервере или escape в JS

---

## 10. СВОДНАЯ ТАБЛИЦА ФАЙЛОВ ДЛЯ РЕДИЗАЙНА

### Приоритет 1 — Полный редизайн страниц (видны пользователям)

| # | Файл | Строк | Сложность | Описание |
|---|------|-------|-----------|----------|
| 1 | `users/templates/users/partner_dashboard.html` | 353 | 🔴 Высокая | Stat cards, search, table, modals |
| 2 | `users/templates/users/log_visit.html` | 129 | 🟡 Средняя | Карточка участника + форма |
| 3 | `users/templates/users/edit_visit.html` | 117 | 🟡 Средняя | Countdown + форма |
| 4 | `users/templates/users/cancel_visit.html` | 115 | 🟡 Средняя | Summary + confirm |
| 5 | `users/templates/users/member_scan_card.html` | 80 | 🟡 Средняя | Публичный QR-профиль |
| 6 | `users/templates/users/profile_deactivate_confirm.html` | 81 | 🟢 Низкая | Confirm form |

### Приоритет 2 — Partials / модалки (компоненты внутри страниц)

| # | Файл | Строк | Описание |
|---|------|-------|----------|
| 7 | `templates/core/htmx/partner_modal.html` | 197 | Partner detail modal |
| 8 | `templates/blog/partners.html` | 170 | Partners include |
| 9 | `blog/templates/blog/partials/post_list_items.html` | 83 | Post cards |
| 10 | `blog/templates/blog/htmx/comments_section.html` | 142 | Comments + replies |
| 11 | `blog/templates/blog/htmx/comment_like_button.html` | ~20 | Like button |
| 12 | `blog/templates/blog/htmx/post_search_results.html` | ~60 | Blog search dropdown |
| 13 | `templates/blog/htmx/post_search_results.html` | ~80 | Global search dropdown |
| 14 | `users/templates/users/partials/partner_search_results.html` | ~60 | Partner search results |

### Приоритет 3 — CSS рефакторинг

| # | Файл | Описание |
|---|------|----------|
| 15 | `static/css/pages.css` | ~35 hardcoded #fff → CSS vars |
| 16 | `templates/base.html` L15 | theme-color #ffffff → #0e0e18 |

---

## ДИЗАЙН-ПРАВИЛА ДЛЯ РЕДИЗАЙНА

При редизайне каждой страницы следовать этим принципам:

### Структура страницы
```
{% block extra_css %}
<style>
/* Все стили страницы здесь */
</style>
{% endblock %}

{% block container_wrap_start %}{% endblock %}
{% block container_wrap_end %}{% endblock %}

{% block content %}
<!-- Dark page wrapper -->
<div class="page-name" style="background:#0e0e18;min-height:100vh;color:rgba(255,255,255,.87);">
  
  <!-- Hero band (optional) -->
  <div style="background:#0a0a0f;padding:3rem 0;position:relative;overflow:hidden;">
    <!-- Radial glow -->
    <div style="position:absolute;top:-100px;left:-100px;width:400px;height:400px;background:radial-gradient(circle,rgba(220,38,38,.15),transparent 70%);pointer-events:none;"></div>
    <div class="hp-container">
      <p class="hp-label">Section Label</p>
      <h1 class="hp-h2">Page <span>Title</span></h1>
    </div>
  </div>
  
  <!-- Content -->
  <div class="hp-container" style="padding:3rem 1.5rem;">
    <!-- Cards, forms, tables here -->
  </div>
</div>
{% endblock %}
```

### Карточки
```css
.page-card {
  background: rgba(255,255,255,.03);
  border: 1.5px solid rgba(255,255,255,.08);
  border-radius: 16px;
  padding: 1.5rem;
  transition: border-color .3s, transform .3s;
}
.page-card:hover {
  border-color: rgba(220,38,38,.3);
  transform: translateY(-2px);
}
```

### Формы (inputs)
```css
.dark-input {
  background: #1a1a24;
  border: 1.5px solid rgba(255,255,255,.1);
  border-radius: 10px;
  color: rgba(255,255,255,.87);
  padding: .75rem 1rem;
}
.dark-input:focus {
  border-color: rgba(220,38,38,.5);
  box-shadow: 0 0 0 3px rgba(220,38,38,.12);
  outline: none;
}
.dark-input::placeholder {
  color: rgba(255,255,255,.3);
}
```

### Кнопки
```css
/* Primary */
.btn-dark-primary {
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 12px;
  padding: .75rem 1.5rem;
  font-weight: 700;
  transition: box-shadow .25s, transform .25s;
}
.btn-dark-primary:hover {
  box-shadow: 0 8px 32px rgba(220,38,38,.4);
  transform: translateY(-1px);
}

/* Ghost */
.btn-dark-ghost {
  background: transparent;
  color: rgba(255,255,255,.7);
  border: 1.5px solid rgba(255,255,255,.15);
  border-radius: 12px;
  padding: .75rem 1.5rem;
  font-weight: 700;
  transition: border-color .25s, color .25s;
}
.btn-dark-ghost:hover {
  border-color: rgba(255,255,255,.4);
  color: #fff;
}
```

### Таблицы
```css
.dark-table {
  background: rgba(255,255,255,.02);
  border-radius: 16px;
  overflow: hidden;
  border: 1.5px solid rgba(255,255,255,.06);
}
.dark-table thead {
  background: rgba(255,255,255,.04);
}
.dark-table th {
  color: rgba(255,255,255,.5);
  font-size: .72rem;
  text-transform: uppercase;
  letter-spacing: .1em;
  font-weight: 700;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid rgba(255,255,255,.06);
}
.dark-table td {
  color: rgba(255,255,255,.75);
  padding: 1rem 1.25rem;
  border-bottom: 1px solid rgba(255,255,255,.04);
}
.dark-table tr:hover {
  background: rgba(220,38,38,.04);
}
```

### Alerts
```css
/* Info */
.dark-alert-info {
  background: rgba(59,130,246,.08);
  border: 1px solid rgba(59,130,246,.2);
  border-radius: 12px;
  color: rgba(147,197,253,.9);
  padding: 1rem 1.25rem;
}
/* Warning */
.dark-alert-warning {
  background: rgba(245,158,11,.08);
  border: 1px solid rgba(245,158,11,.2);
  border-radius: 12px;
  color: rgba(253,224,71,.9);
  padding: 1rem 1.25rem;
}
/* Danger */
.dark-alert-danger {
  background: rgba(239,68,68,.08);
  border: 1px solid rgba(239,68,68,.2);
  border-radius: 12px;
  color: rgba(252,165,165,.9);
  padding: 1rem 1.25rem;
}
/* Success */
.dark-alert-success {
  background: rgba(34,197,94,.08);
  border: 1px solid rgba(34,197,94,.2);
  border-radius: 12px;
  color: rgba(134,239,172,.9);
  padding: 1rem 1.25rem;
}
```

### Badges
```css
.dark-badge {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  padding: .25rem .65rem;
  border-radius: 50px;
  font-size: .7rem;
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.dark-badge-success { background: rgba(34,197,94,.12); color: #4ade80; }
.dark-badge-warning { background: rgba(245,158,11,.12); color: #fbbf24; }
.dark-badge-danger  { background: rgba(239,68,68,.12); color: #f87171; }
.dark-badge-info    { background: rgba(59,130,246,.12); color: #60a5fa; }
```

---

## ИТОГО

| Категория | Кол-во файлов | Статус |
|-----------|---------------|--------|
| Полный редизайн страниц | **6** | Не начато |
| Партиалы/модалки обновить | **8** | Не начато |
| CSS рефакторинг | **2** | Не начато |
| Telegram для юзеров | — | ✅ Готово |
| Бот: приветствие новых участников | — | ✅ Готово |
| JS консолидация | 2-3 | Частично (из прошлых сессий) |

---

## ПЛАН РАБОТЫ — 3 ЗАПРОСА

### ЗАПРОС 1 — Мелкие страницы + CSS исправления

**CSS / base.html (быстрые фиксы)**
- `templates/base.html` — `theme-color` `#ffffff` → `#0e0e18`
- `static/css/pages.css` — заменить ~35 hardcoded `#fff`/`white` на CSS vars (партиями)
- `blog/templates/blog/partials/post_list_items.html` — `text-dark` → убрать
- `blog/templates/blog/htmx/comments_section.html` — `btn-outline-*` → тёмные кнопки
- `blog/templates/blog/htmx/comment_like_button.html` — `btn-outline-secondary` → engage-chip

**Страницы (простые)**
1. `users/templates/users/profile_deactivate_confirm.html` (81 строка) — полный редизайн
2. `users/templates/users/cancel_visit.html` (115 строк) — полный редизайн
3. `users/templates/users/log_visit.html` (129 строк) — полный редизайн

---

### ЗАПРОС 2 — Средние страницы + Партиалы

**Страницы**
1. `users/templates/users/edit_visit.html` (117 строк) — полный редизайн
2. `users/templates/users/member_scan_card.html` (80 строк) — полный редизайн

**Партиалы / Модалки**
3. `templates/core/htmx/partner_modal.html` (197 строк) — редизайн модалки
4. `templates/blog/partners.html` (170 строк) — редизайн
5. `blog/templates/blog/htmx/post_search_results.html` — тёмные list items
6. `templates/blog/htmx/post_search_results.html` — тёмные list items (global)
7. `users/templates/users/partials/partner_search_results.html` — тёмные результаты поиска

---

### ЗАПРОС 3 — Главная сложная страница + Производительность

**Главная страница для редизайна**
1. `users/templates/users/partner_dashboard.html` (353 строки) — ПОЛНЫЙ редизайн
   - Stat cards → тёмные ячейки в стиле Stats Band с homepage
   - Search form → тёмный фон, dark inputs
   - Visits table → dark-table стиль
   - Action buttons → hero-btn-p / ghost стиль

**Производительность**
2. `core/views.py` — огнраничить `members = AssociationMember.objects.all()` → `[:12]`
3. `blog/views.py` — добавить `select_related` / `prefetch_related` для комментариев
4. `static/css/pages.css` — финальная волна замены hardcoded цветов

---

## TELEGRAM БОТ — ПОЛНЫЙ ФУНКЦИОНАЛ (March 2026)

### Статус: ✅ АКТИВЕН (`BOT_ACTIVE = True`)
- Токен: `TELEGRAM_BOT_TOKEN` (env var в DigitalOcean)
- Webhook secret: `TELEGRAM_WEBHOOK_SECRET` (env var)
- Бот: `@IESA_Administrator_bot`
- Endpoint: `/auth/telegram/webhook/<secret>/`
- Страница настройки (staff): `/auth/partner/test-telegram/`

### Команды бота (slash commands)
| Команда | Описание |
|---------|----------|
| `/start` | Главное меню — приветствие с кнопками |
| `/link` | Получить 6-значный код привязки аккаунта |
| `/status` | Проверить статус членства |
| `/help` | Справка по функционалу |
| `/id` | Показать свой Telegram chat_id |
| `/unlink` | Отвязать Telegram от аккаунта |

### InlineKeyboard callbacks
| callback_data | Действие |
|---|---|
| `cb:link` | Сгенерировать код привязки |
| `cb:help` | Показать справку |
| `cb:status` | Обновить статус членства |
| `cb:new_code` | Перевыпустить код привязки |
| `cb:unlink_ask` | Запрос подтверждения отвязки |
| `cb:unlink_yes` | Подтвердить отвязку |
| `cb:cancel` | Отмена |

### Уведомления из Django (notify.py)
| Функция | Триггер | Получатель |
|---|---|---|
| `notify_visit_confirmed(visit)` | Партнёр записывает визит | Пользователь (DM) |
| `notify_visit_edited(visit, audit)` | Партнёр редактирует визит | Пользователь (DM) |
| `notify_visit_cancelled(visit, audit)` | Партнёр отменяет визит | Пользователь (DM) |
| `notify_membership_activated(user)` | Активация членства | Пользователь (DM) |

### Методы привязки Telegram
**Метод A — 6-значный код (основной)**
1. Пользователь пишет `/link` боту
2. Бот генерирует 6-значный код (TTL 10 минут, в Redis/cache)
3. Пользователь вводит код в личном кабинете на сайте (`/auth/cabinet/` или `/auth/profile/`)
4. Код проверяется, `user.telegram_chat_id` сохраняется

**Метод B — Telegram Login Widget**
1. Кнопка "Войти через Telegram" на странице
2. Telegram возвращает подписанный hash
3. Django проверяет hash (`verify_telegram_auth`), сохраняет chat_id

### ✅ НОВОЕ: Приветствие новых участников канала
**Добавлено 01.03.2026**
- При вступлении нового пользователя в канал бот отправляет **публичное приветствие в канал**
- Приветствие тегает пользователя через `<a href="tg://user?id=...">Имя</a>`
- Включает кнопки: "Сайт IESA Sport" + "Привязать аккаунт"
- Боты игнорируются (не приветствуются)
- Требует: `TELEGRAM_CHANNEL_ID` в env vars (например `@iesasport` или `-1001234567890`)
- Триггер: `chat_member` update (old_status `left/kicked` → new_status `member/administrator`)

**Важно**: После добавления нужно пересетить вебхук через `/auth/partner/test-telegram/` — новый `allowed_updates` включает `"chat_member"`. Без этого Telegram не будет слать event'ы о новых участниках.

### Архитектура файлов
| Файл | Назначение |
|---|---|
| `users/telegram/__init__.py` | Публичный API пакета |
| `users/telegram/config.py` | `token()`, `bot_name()`, `channel_id()`, `BOT_ACTIVE` |
| `users/telegram/client.py` | HTTP клиент (sync + async), `set_webhook`, `send_message` |
| `users/telegram/handlers.py` | Обработчики команд и `handle_new_channel_member()` |
| `users/telegram/dispatcher.py` | Роутинг updates → handlers |
| `users/telegram/link.py` | Генерация/проверка кодов привязки |
| `users/telegram/notify.py` | Notify-функции для визитов и членства |
| `users/telegram_notify.py` | Backwards-compat shim (старые импорты) |
| `users/views_verification.py` | Django views: webhook, connect, disconnect, test page |
