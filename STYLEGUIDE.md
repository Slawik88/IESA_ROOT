# IESA Sport — Design System & Style Guide

> Последнее обновление: 2026-05-22  
> Версия CSS: v2.0 (post–UX audit refactor)

---

## Содержание

1. [CSS Архитектура](#css-архитектура)
2. [Design Tokens](#design-tokens)
3. [Цвета](#цвета)
4. [Типографика](#типографика)
5. [Отступы](#отступы)
6. [Радиусы](#радиусы)
7. [Тени](#тени)
8. [Transitions](#transitions)
9. [Компоненты](#компоненты)
10. [Naming Conventions](#naming-conventions)
11. [Доступность](#доступность)
12. [Playground](#playground)

---

## CSS Архитектура

### Порядок загрузки (cascade order — строго соблюдать)

```
variables.css       → дизайн-токены (source of truth)
base.css            → reset + базовая типографика + focus states
layout.css          → navbar, footer, bottom-nav, containers
components.css      → переиспользуемые компоненты (btn, card, form, badge...)
pages.css           → page-specific стили (hero, blog, profile...)
utilities.css       → утилиты (op-*, gap-*, d-flex...)
animations.css      → @keyframes
product-cards.css   → карточки продуктов
homepage.css        → блоки главной страницы
touch-gestures.css  → mobile swipe/gesture стили
responsive.css      → @media breakpoints
dark-theme-fixes.css → последний файл; финальные override-ы (touch-safe hover, gallery focus)
partner-dashboard.css → дашборд партнёра (pp-wrap, pmv-wrap системы)
```

**Правило**: каждый последующий файл может переопределять предыдущие. `dark-theme-fixes.css` загружается **последним** намеренно.

### Breakpoints

| Имя       | Значение   | Применение              |
|-----------|------------|-------------------------|
| `xs`      | < 480px    | iPhone SE, узкие экраны |
| `sm`      | < 576px    | Мобильные               |
| `md`      | < 768px    | Планшеты, мобильные     |
| `lg`      | < 992px    | Планшеты горизонтально  |
| `xl`      | < 1200px   | Десктоп                 |
| `xxl`     | ≥ 1400px   | Широкий десктоп         |

---

## Design Tokens

Все токены определены в `variables.css`. **Никогда не хардкодь цвета/размеры — используй переменные.**

### Как использовать

```css
/* ✅ Правильно */
color: var(--text-primary);
border-radius: var(--r-lg);
transition: all var(--transition-smooth);

/* ❌ Неправильно */
color: rgba(255,255,255,0.92);
border-radius: 20px;
transition: all 0.3s ease;
```

---

## Цвета

### Основная палитра

| Переменная        | Значение    | Применение                     |
|-------------------|-------------|--------------------------------|
| `--primary`       | `#dc2626`   | CTA, акценты, иконки действий  |
| `--primary-hover` | `#b91c1c`   | Hover-состояние primary        |
| `--secondary`     | `#2563eb`   | Вторичные действия, ссылки     |
| `--success`       | `#16a34a`   | Успех, подтверждение           |
| `--warning`       | `#d97706`   | Предупреждение                 |
| `--danger`        | `#ef4444`   | Ошибки, деструктивные действия |
| `--info`          | `#0284c7`   | Информационные сообщения       |

### Surface Scale (тёмная тема)

| Переменная    | Hex       | Применение              |
|---------------|-----------|-------------------------|
| `--surface-0` | `#0e0e18` | Фон страницы            |
| `--surface-1` | `#111118` | Карточки, модалки       |
| `--surface-2` | `#1a1a24` | Hover-поверхность       |
| `--surface-3` | `#232334` | Приподнятые элементы    |

### Текст (WCAG AA проверено)

| Переменная        | Opacity | Контраст | Применение                  |
|-------------------|---------|----------|-----------------------------|
| `--text-primary`  | 0.92    | 14:1     | Заголовки, основной текст   |
| `--text-secondary`| 0.72    | 9.5:1    | Описания, подписи           |
| `--text-muted`    | 0.58    | 6.2:1    | Метаданные, мелкий текст    |
| `--text-light`    | 0.42    | 4.6:1    | Декоративный (min WCAG AA)  |

### Границы

| Переменная       | Применение                            |
|------------------|---------------------------------------|
| `--border-faint` | `rgba(255,255,255,.06)` — едва видима |
| `--border-soft`  | `rgba(255,255,255,.10)` — карточки    |
| `--border-strong`| `rgba(255,255,255,.18)` — hover/focus |

### Primary с прозрачностью

| Переменная      | Применение                      |
|-----------------|---------------------------------|
| `--primary-a8`  | Очень тонкий фон (hover hint)   |
| `--primary-a12` | Фон активного состояния         |
| `--primary-a25` | Бордер активного элемента       |
| `--primary-a40` | Акцентный оверлей               |

---

## Типографика

### Семейство шрифтов

```css
--font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
--font-mono: 'Courier New', Courier, monospace;  /* только для PIN/UUID/кодов */
```

### Шкала размеров

| Переменная    | rem     | px  |
|---------------|---------|-----|
| `--text-xs`   | 0.75rem | 12  |
| `--text-sm`   | 0.875rem| 14  |
| `--text-base` | 1rem    | 16  |
| `--text-lg`   | 1.125rem| 18  |
| `--text-xl`   | 1.25rem | 20  |
| `--text-2xl`  | 1.5rem  | 24  |
| `--text-3xl`  | 1.875rem| 30  |
| `--text-4xl`  | 2.25rem | 36  |
| `--text-5xl`  | 3rem    | 48  |

---

## Отступы

Шаг = 4px (`--space-1 = 0.25rem`):

```
--space-1: 0.25rem (4px)
--space-2: 0.5rem  (8px)
--space-3: 0.75rem (12px)
--space-4: 1rem    (16px)
--space-5: 1.25rem (20px)
--space-6: 1.5rem  (24px)
--space-8: 2rem    (32px)
--space-10: 2.5rem (40px)
--space-12: 3rem   (48px)
--space-16: 4rem   (64px)
```

---

## Радиусы

### 4 семантических уровня (использовать эти в первую очередь)

| Переменная | Значение | Применение               |
|------------|----------|--------------------------|
| `--r-sm`   | 12px     | Теги, инпуты, мелкие UI  |
| `--r-md`   | 14px     | Кнопки                   |
| `--r-lg`   | 20px     | Карточки, модалки        |
| `--r-xl`   | 24px     | Hero-блоки, bottom sheets|

### Специфичные алиасы (совместимость)

```
--radius-card: 1.25rem  (20px) — карточки
--radius-btn:  0.875rem (14px) — кнопки
--radius-input:0.75rem  (12px) — инпуты
--radius-badge:0.5rem   (8px)  — бейджи
--radius-full: 9999px          — pills, аватары
```

---

## Тени

```
--shadow-card:       0 4px 16px rgba(0,0,0,.06)   — карточка (default)
--shadow-card-hover: 0 8px 24px rgba(0,0,0,.10)   — карточка (hover)
--shadow-card-lg:    более заметная тень
--shadow-primary:    0 4px 14px rgba(239,68,68,.25) — primary кнопка
```

---

## Transitions

| Переменная            | Значение                          | Применение                     |
|-----------------------|-----------------------------------|--------------------------------|
| `--transition-fast`   | `150ms ease`                      | Hover micro-interactions       |
| `--transition-base`   | `200ms ease`                      | Стандартный переход            |
| `--transition-slow`   | `300ms ease`                      | Плавные переходы               |
| `--transition-smooth` | `300ms cubic-bezier(.4,0,.2,1)`   | Карточки, кнопки (Material-like)|
| `--transition-bounce` | `300ms cubic-bezier(.68,-.55,.265,1.55)` | Bounce-эффекты         |

---

## Компоненты

### Кнопки

```html
<!-- Primary -->
<button class="btn hero-btn-p">Primary Action</button>

<!-- Secondary / Ghost -->
<button class="btn hero-btn-g">Secondary</button>

<!-- Danger -->
<button class="btn btn-danger">Delete</button>

<!-- Partner (pp-wrap система) -->
<button class="pp-btn">Partner Action</button>
<button class="pp-btn-ghost">Ghost</button>
<button class="pp-btn-danger">Delete</button>
```

### Карточки

```html
<!-- Базовая (Bootstrap-compatible) -->
<div class="card">...</div>

<!-- Partner карточка -->
<div class="pp-card">...</div>

<!-- Dashboard stat-карточка -->
<div class="dash-stat-card">...</div>
```

### Badges / Status

```html
<span class="pnd-role-badge pnd-role--member">Member</span>
<span class="pnd-role-badge pnd-role--partner">Partner</span>
<span class="pnd-role-badge pnd-role--staff">Admin</span>
```

### Bottom Sheets

```html
<!-- Открыть -->
<script>IESABottomSheet.open('my-sheet-id');</script>

<!-- Закрыть -->
<script>IESABottomSheet.close('my-sheet-id');</script>

<!-- Разметка -->
<div class="iesa-bottom-sheet" id="my-sheet-id">
    <div class="bs-handle"></div>
    <!-- Контент -->
</div>
```

### Toasts

```html
<!-- Django messages → автоматически в toast_container.html -->

<!-- JS API -->
<script>window._iesa_showToast('Сообщение', 'danger'); // danger|warning|info</script>
```

### Skeleton Loading

```html
<div class="skeleton" style="height:1rem;width:60%;border-radius:4px;"></div>
```

### HTMX Loading Indicator

```html
<!-- Спиннер, видимый во время HTMX-запроса -->
<span id="my-spinner" class="htmx-indicator" aria-hidden="true">
    <i class="fas fa-spinner fa-spin"></i>
</span>

<!-- На форме -->
<form hx-get="/url/" hx-indicator="#my-spinner">...</form>
```

---

## Naming Conventions

### CSS классы

| Паттерн       | Пример                     | Применение                         |
|---------------|----------------------------|------------------------------------|
| `dash-*`      | `dash-sidebar`, `dash-card`| Партнёрский дашборд (sidebar layout)|
| `pp-*`        | `pp-card`, `pp-btn`        | Партнёрские страницы (top-nav flow) |
| `pmv-*`       | `pmv-wrap`                 | Partner Member Visits               |
| `pmc-*`       | `pmc-header`               | Partner Member Cabinet              |
| `cab-*`       | `cab-card`, `cab-sub`      | User Cabinet (профиль)              |
| `vh-*`        | `vh-date`, `vh-service`    | Visit History items                 |
| `hp-*`        | `hp-hero`, `hp-h2`         | Homepage блоки                      |
| `pd-*`        | `pd-article`, `pd-content` | Post Detail                         |
| `cm-*`        | `cm-comment`, `cm-reply`   | Blog Comments                       |
| `cmd-*`       | `cmd-bar`, `cmd-input`     | Command Bar (blog/events filter)    |
| `mbn-*`       | `mbn-item`, `mbn-badge`    | Mobile Bottom Navigation            |
| `pnd-*`       | `pnd-item`, `pnd-label`    | Profile Nav Dropdown                |
| `af-*`        | `af-wrap`, `af-err`        | Auth Form fields                    |
| `rf-*`        | `rf-wrap`, `rf-hint`       | Register Form fields                |
| `reg-*`       | `reg-step`, `reg-grid`     | Registration flow                   |
| `sb-*`        | `sb-active`, `sb-member`   | Status Badge                        |
| `edit-*`      | `edit-tabs`, `edit-tab`    | Profile Edit tabs                   |
| `page-bc`     | `.page-bc ol li`           | Breadcrumbs (generic pages)         |

### Файловые соглашения

- Шаблоны партнёра наследуют `users/partner_base.html`
- Частичные шаблоны: `templates/partials/_name.html` (underscore prefix)
- HTMX-фрагменты: `blog/templates/blog/htmx/name.html`

### JavaScript API

```javascript
// Bottom Sheet
IESABottomSheet.open('sheet-id');
IESABottomSheet.close('sheet-id');

// Toast
window._iesa_showToast('текст', 'danger|warning|info');

// Copy to clipboard
<button class="copy-id" data-copy="#element-selector">
```

---

## Доступность

### Обязательные правила

1. **Иконки рядом с текстом** → `aria-hidden="true"` на `<i>`
2. **Иконки без текста** → `aria-label="..."` И `title="..."` на контейнере
3. **Ошибки форм** → `role="alert"` на error div, `aria-invalid="true"` + `aria-describedby="err-fieldname"` на input
4. **Live регионы** → `aria-live="polite"` на dynamic content areas (статус проверки username/email)
5. **Декоративные canvas** → `aria-hidden="true"`
6. **Focus visible** → не убирай `outline` без замены на `box-shadow` (3px solid `--focus-ring-color`)
7. **Touch hover** → все `:hover` трансформации задублированы в `@media (hover:none),(pointer:coarse)` блоке в `dark-theme-fixes.css`

### Контрастность (WCAG AA, фон #0e0e18)

| Компонент         | Минимум  | Текущее значение  |
|-------------------|----------|-------------------|
| Основной текст    | 4.5:1    | `--text-primary` 14:1  |
| Вторичный текст   | 4.5:1    | `--text-secondary` 9.5:1 |
| Мелкий текст      | 4.5:1    | `--text-muted` 6.2:1    |
| dash-stat-lbl     | 4.5:1    | rgba(255,255,255,.52) ~5.5:1 |
| vh-date           | 4.5:1    | rgba(255,255,255,.52) ~5.5:1 |

---

## Playground

Компонентный playground доступен по адресу `/dev/components/` (только для `is_staff`).

Показывает все компоненты системы в живом виде: кнопки, карточки, badges, формы, иконки, цвета, типографику.
