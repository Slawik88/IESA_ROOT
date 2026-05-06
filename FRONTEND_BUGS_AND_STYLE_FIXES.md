# FRONTEND BUGS AND STYLE FIXES — IESA ROOT
> **Аудитор:** Principal Frontend Architect  
> **Дата:** 2026-05-07  
> **Охват:** 42 шаблона · 15 CSS-файлов · 13 JS-файлов  
> **Статус:** `[ ]` — не сделано, `[x]` — выполнено

---

## 🏛 РАЗДЕЛ 0 — ЕДИНЫЙ СТИЛЬ (ЗАКОН ДИЗАЙН-СИСТЕМЫ)

Выведен на основе самых качественных компонентов проекта: страница поста, страница события, notification_list, member_cabinet. Эти правила являются **эталоном** для всех остальных страниц.

### 0.1 Цветовая палитра (токены из `variables.css`)
| Имя | Значение | Назначение |
|-----|----------|-----------|
| `--bg-body` | `#0e0e18` | Фон страницы |
| `--bg-surface` | `#111118` | Карточки, панели |
| `--bg-surface-hover` | `#1a1a24` | Ховер карточек |
| `--primary` | `#dc2626` | Красный бренд |
| `--text-primary` | `rgba(255,255,255,.87)` | Основной текст |
| `--text-secondary` | `rgba(255,255,255,.65)` | Вторичный текст |
| `--text-muted` | `rgba(255,255,255,.5)` | Вспомогательный |
| `--border-dark` | `rgba(255,255,255,.08)` | Граница карточки |

**НАРУШЕНИЯ:**
- Белые фоны `#fff`, `white` — **запрещены** везде кроме `.modal-light`
- Жёсткий цвет `#0a0a0f` (темнее body) — только для hero-section фона
- Прозрачность текста < 30% — **запрещена** (нечитаемо)

### 0.2 Архитектура страницы (шаблон)
```
PageHero (полноширинный, фиксированный pattern)
  └─ .page-hero → background: #0a0a0f + radial-gradient красный
CommandBar (опционально для blog/events)  
ContentGrid
  └─ .container-limited → max-width: 1280px
```

### 0.3 Единый border-radius
| Уровень | Значение | Токен | Применение |
|---------|----------|-------|-----------|
| XL | 20px | `--radius-card` | Основные карточки, секции |
| L | 16px | `--radius-2xl` (1rem) | Вторичные карточки |
| M | 12px | `--radius-xl` (0.75rem) | Малые элементы, badges |
| S | 8px | `--radius-lg` (0.5rem) | Кнопки, инпуты |
| Pill | 100px | `--radius-full` | Badges, chips |

### 0.4 Именование CSS-классов (обязательные префиксы)
- `.page-hero` — общий Hero для всех страниц (замена `.pl-hero`, `.ev-page-hero`, `.gal-hero`, `.prod-hero`, `.ben-hero`)
- `.cmd-*` — Command Bar (существует, НО дублируется — нужно вынести в `components.css`)
- Страничные классы: `pd-` (post detail), `ev-` (events), `evd-` (event detail), `cab-` (cabinet), `pp-` (partner portal) — **оставить, но не создавать новые похожие**

### 0.5 Кнопки (эталон)
- Primary: `background: rgba(220,38,38,.15); border: 1.5px solid rgba(220,38,38,.35); color: #f87171`
- Secondary: `background: rgba(255,255,255,.07); border: 1.5px solid rgba(255,255,255,.12); color: rgba(255,255,255,.65)`
- **НЕ использовать** отдельные `.evd-btn-*`, `.pd-btn-*` — заменить на `.btn-primary`/`.btn-secondary` из `components.css`

### 0.6 Типографика (эталонная шкала)
| Назначение | Размер | Примечание |
|-----------|--------|-----------|
| Заголовок H1 | `clamp(1.5rem,4vw,2.1rem)` | post_detail, event_detail |
| Заголовок H2 | `1.9rem / 900` | Секции |
| Подзаголовок | `1.1rem` | Описание |
| Основной текст | `1rem / line-height:1.8` | Статья |
| UI-текст | `.9rem` | Карточки |
| Метаданные | `.78rem-.82rem` | Даты, авторы |
| Micro-label | `.68-.72rem / Courier New / uppercase / letter-spacing` | Секционные лейблы |

### 0.7 Hover-поведение (унифицировано)
- Карточки: `translateY(var(--card-hover-lift)) = -3px` (из Sprint UI-5)
- Переход: `transition: border-color .2s, transform .2s, box-shadow .2s`
- На мобиле: `transform: none !important` (из `responsive.css`)

---

## 🔴 БЛОК 1 — КРИТИЧЕСКИЕ БАГИ ВЕРСТКИ

### Б1-01 Полный inline-стиль в `post_list_items.html` — **разрушает поддерживаемость**
- [ ] **Файл:** [blog/templates/blog/partials/post_list_items.html](IESA_ROOT/blog/templates/blog/partials/post_list_items.html)
- **Проблема:** Весь HTML-шаблон карточки поста написан с `style=""` атрибутами (~80 строк). Нет ни одного CSS-класса для структурных элементов. Тёмная тема, hover-эффекты, typography — всё хардкод.
- **Примеры** (строки 10-75):
  - `style="display:flex;align-items:stretch;min-height:130px;"` 
  - `style="flex-shrink:0;width:160px;min-height:130px;"` (фиксированная ширина)
  - `style="font-size:.97rem;font-weight:700;color:rgba(255,255,255,.9);"` (хардкод цвет)
  - `style="width:22px;height:22px;border-radius:50%;background:rgba(220,38,38,.2);"` (аватар)
- **Исправление:** Создать CSS-классы `.post-card`, `.post-card__image`, `.post-card__body`, `.post-card__title`, `.post-card__meta`, `.post-card__author`, `.post-card__stats` в `static/css/pages.css` или отдельном `blog-cards.css`. Заменить все inline styles на классы.

### Б1-02 Белые секции на тёмном сайте в `index.html`
- [ ] **Файл:** [core/templates/core/index.html](IESA_ROOT/core/templates/core/index.html) строки 114, 118, 139, 178
- **Проблема:** 
  - `#hp-offers { background: #fff }` — секция "Offers" белая
  - `.offer-card-v2 { background: #fff }` — карточки белые  
  - `#hp-mission { background: #fff }` — секция "Mission" белая
  - `.iesa-do-item { background: #fff }` — карточки "What We Do" белые
  - `.mission-panel { border: 1.5px solid var(--border-color) }` — `--border-color` = `#e5e7eb` (светлый, ломается на тёмном фоне)
- **Причина:** Эти секции задуманы как "light sections" на тёмном сайте. Но после Sprint UI-1 `dark-theme-fixes.css` исправляет их через `!important`. Конфликт источников.
- **Исправление:** Заменить `background: #fff` → `background: var(--bg-surface)` во всех указанных местах. Текстовые цвета (`var(--text-primary)`, `var(--text-secondary)`) уже работают корректно через токены.

### Б1-03 `.offer-num` — нечитаемый при тёмном фоне
- [ ] **Файл:** [core/templates/core/index.html](IESA_ROOT/core/templates/core/index.html) строка 124
- **Проблема:** `.offer-num { color: rgba(0,0,0,.04) }` — почти прозрачный чёрный на тёмном фоне. На белом фоне это декоративный subtlety, на тёмном — исчезает полностью.
- **Исправление:** `color: rgba(255,255,255,.04)` при тёмном фоне.

### Б1-04 DEBUG-комментарий в продакшн-коде
- [ ] **Файл:** [blog/templates/blog/htmx/post_search_results.html](IESA_ROOT/blog/templates/blog/htmx/post_search_results.html) строка 29-31
- **Проблема:**
  ```html
  <!-- DEBUG INFO (remove in production) -->
  <!-- Query: '{{ query }}' | Users: ... | Posts: ... -->
  ```
  Раскрывает структуру поиска. Нарушение информационной безопасности.
- **Исправление:** Удалить 3 строки.

### Б1-05 XSS-потенциал: `|safe` на пользовательских данных в search results
- [ ] **Файл:** [users/templates/users/search_results.html](IESA_ROOT/users/templates/users/search_results.html) строки 75-76
- **Проблема:**
  ```html
  <small class="text-muted">@{{ item.username_html|safe }}</small>
  {{ item.email_html|safe }} • <code>{{ item.permanent_id_html|safe }}</code>
  ```
  `|safe` применяется к полям `username_html`, `email_html`, `permanent_id_html`. Если сервер не гарантирует эскейпинг HTML в этих полях — XSS.
- **Исправление:** Проверить `views.py` — поля должны содержать только `<mark>...</mark>` теги подсветки. Добавить явную sanitization в Python-коде через `bleach.clean()` или `mark_safe(html.escape(value).replace(...))`.

### Б1-06 Emoji вместо иконок в поиске — нарушает консистентность
- [ ] **Файл:** [blog/templates/blog/htmx/post_search_results.html](IESA_ROOT/blog/templates/blog/htmx/post_search_results.html) строка 54, 80
- **Проблема:** `👤 {{ user.get_full_name }}`, `📝 {{ post.title }}`, `📅 {{ event.title }}` — emoji вместо Font Awesome иконок. Несогласованно с остальным сайтом.
- **Исправление:**
  ```html
  <i class="fas fa-user me-1 text-muted"></i>{{ user.get_full_name }}
  <i class="fas fa-newspaper me-1 text-muted"></i>{{ post.title }}
  ```

### Б1-07 `<style>` в HTMX-партиале перезагружается при каждом запросе
- [ ] **Файл:** [blog/templates/blog/htmx/comments_section.html](IESA_ROOT/blog/templates/blog/htmx/comments_section.html) строки 3-40
- **Проблема:** `<style>` блок с `.cm-card`, `.cm-body`, `.cm-btn` и т.д. находится в HTMX-партиале (загружается при каждом открытии/обновлении комментариев). CSS-правила дублируются в DOM на каждый swap.
- **Исправление:** Вынести в `static/css/blog-comments.css` (или добавить в `pages.css`), подключить в `extra_css` блоке `post_detail.html`.

### Б1-08 Inline avatar-стили в comments_section
- [ ] **Файл:** [blog/templates/blog/htmx/comments_section.html](IESA_ROOT/blog/templates/blog/htmx/comments_section.html) строки 51-53, 70-76
- **Проблема:** У каждого аватара комментария хардкод:
  ```html
  style="width:30px;height:30px;border-radius:50%;object-fit:cover;border:1.5px solid rgba(255,255,255,.12);flex-shrink:0;"
  style="color:rgba(255,255,255,.88);font-size:.87rem;"
  style="color:rgba(255,255,255,.3);font-size:.74rem;margin-left:auto;"
  ```
  Для reply-аватаров другие размеры: `width:24px;height:24px`.
- **Исправление:** CSS-классы `.cm-avatar` (30px) и `.cm-reply-avatar` (24px), `.cm-author-name`, `.cm-time`.

---

## 🟠 БЛОК 2 — ДУБЛИРОВАНИЕ КОДА

### Д2-01 `.cmd-bar` CSS дублируется в двух шаблонах слово в слово
- [ ] **Файлы:**
  - [blog/templates/blog/post_list.html](IESA_ROOT/blog/templates/blog/post_list.html) строки 24-226 (~202 строки)
  - [blog/templates/blog/event_list.html](IESA_ROOT/blog/templates/blog/event_list.html) строки 23-200 (~178 строк)
- **Проблема:** Полный дубликат CSS для `.cmd-bar`, `.cmd-bar__inner`, `.cmd-tabs`, `.cmd-tab`, `.cmd-tab::after`, `.cmd-tab__dot`, `.cmd-sep`, `.cmd-search`, `.cmd-lbl`, `.cmd-input`, `.cmd-filter-group`, `.cmd-select`, `.cmd-cta` — один в один.
- **Исправление:** Создать `static/css/cmd-bar.css`, подключить в `base.html`. Из шаблонов удалить дублирующие `<style>` блоки.

### Д2-02 Hero-section шаблон повторяется в 5 файлах
- [ ] **Файлы:**
  - [blog/templates/blog/post_list.html](IESA_ROOT/blog/templates/blog/post_list.html) — `.pl-hero`
  - [blog/templates/blog/event_list.html](IESA_ROOT/blog/templates/blog/event_list.html) — `.ev-page-hero`
  - [gallery/templates/gallery/gallery.html](IESA_ROOT/gallery/templates/gallery/gallery.html) — `.gal-hero`
  - [products/templates/products/product_list.html](IESA_ROOT/products/templates/products/product_list.html) — `.prod-hero`
  - [core/templates/core/benefits.html](IESA_ROOT/core/templates/core/benefits.html) — `.ben-hero`
- **Проблема:** Все 5 классов содержат идентичный CSS:
  ```css
  background: #0a0a0f;
  padding: 5.5rem 0 4.5rem;
  text-align: center;
  position: relative;
  overflow: hidden;
  /* ::before — identical radial-gradient overlay */
  ```
- **Исправление:** Единый класс `.page-hero` в `layout.css` или `pages.css`. В шаблонах заменить все `.pl-hero`, `.ev-page-hero`, `.gal-hero`, `.prod-hero`, `.ben-hero` на `<div class="page-hero">`.

### Д2-03 `:root` переопределяется в 4 страничных шаблонах
- [ ] **Файлы:**
  - [users/templates/users/profile.html](IESA_ROOT/users/templates/users/profile.html) строки 15-29 (`:root { --bg0, --bg1, --card, --bdr... }`)
  - [users/templates/users/profile_public.html](IESA_ROOT/users/templates/users/profile_public.html) строки 8-9 (`.pp-page { background: #0e0e18 }`)
  - [users/templates/users/member_cabinet.html](IESA_ROOT/users/templates/users/member_cabinet.html) — `member-cabinet.css` уже вынесен, но там `:root` переопределяет глобальные переменные
  - [users/templates/users/partner_dashboard.html](IESA_ROOT/users/templates/users/partner_dashboard.html) — `partner-dashboard.css` тоже
- **Проблема:** `html, body { background: var(--bg0) !important }` — переопределение `:root` в inline `<style>` заставляет ГЛОБАЛЬНЫЕ переменные вести себя по-разному на разных страницах.
- **Исправление:** 
  - В `member-cabinet.css` и `partner-dashboard.css` — уже сделана область видимости через `.cab-page { --bg0: ... }`. Проверить что `html, body` не глобализируется.
  - В `profile.html` — убрать `:root` override, использовать `.cab-page {}` скопинг или глобальные токены напрямую.

### Д2-04 Секционный лейбл `.cab-label` / `.pd-section-label` / `.evd-section-label` / `.pp-card-title` — один паттерн
- [ ] **Файлы:**
  - [users/templates/users/profile.html](IESA_ROOT/users/templates/users/profile.html)
  - [blog/templates/blog/post_detail.html](IESA_ROOT/blog/templates/blog/post_detail.html) `.pd-section-label`
  - [blog/templates/blog/event_detail.html](IESA_ROOT/blog/templates/blog/event_detail.html) `.evd-section-label`
  - [users/templates/users/profile_public.html](IESA_ROOT/users/templates/users/profile_public.html) `.pp-card-title`
- **Проблема:** Все используют идентичный CSS:
  ```css
  font-size: .72-.75rem; font-weight: 800; text-transform: uppercase; 
  letter-spacing: .1em; color: #dc2626; display: block;
  ```
- **Исправление:** Единый класс `.section-eyebrow` в `layout.css` (уже есть `.section-title` — использовать его).

### Д2-05 Кнопка Back (`evd-btn-back` / аналоги) дублируется на каждой странице
- [ ] **Файлы:** `event_detail.html`, `post_detail.html`, `partner_access_denied.html`, `cancel_visit.html`
- **Проблема:** Каждая страница определяет свою "back button" с одинаковыми значениями:
  ```css
  background: rgba(255,255,255,.07); border: 1.5px solid rgba(255,255,255,.12);
  color: rgba(255,255,255,.65); border-radius: 10px;
  ```
- **Исправление:** Это и есть `.btn-secondary` из `components.css`. Удалить дублирующие классы, использовать `<a class="btn btn-secondary">`.

### Д2-06 `.search-results <style>` в HTMX-партиале
- [ ] **Файл:** [blog/templates/blog/htmx/post_search_results.html](IESA_ROOT/blog/templates/blog/htmx/post_search_results.html) строки 2-26
- **Проблема:** `<style>` блок с `.search-results *` стилями грузится при КАЖДОМ нажатии клавиши в поиске.
- **Исправление:** Эти стили уже есть в `dark-theme-fixes.css` (строки 328-343). Удалить `<style>` из партиала.

---

## 🟠 БЛОК 3 — НЕСОГЛАСОВАННОСТЬ BORDER-RADIUS

### Б3-01 8 разных значений border-radius для "карточек"
- [ ] **Файлы:** Все шаблоны
- **Проблема:**

| Значение | Где используется | Должно быть |
|----------|-----------------|-------------|
| `10px` | `.cmd-bar`, кнопки | `var(--radius-lg)` → 8px |
| `12px` | `.pd-rec-card__no-img`, notification mobile | `var(--radius-xl)` → 12px ✓ |
| `14px` | `.cm-card`, `.pd-rec-card` | `var(--radius-2xl)` → 16px ❌ |
| `16px` | `.evd-desc-card`, `.notification-item`, `.pp-card-dark` | `var(--radius-2xl)` → 16px ✓ |
| `18px` | `.tl-card`, `.evd-hero-img`, `.gallery-thumb` | ❌ нет токена |
| `20px` | `.pd-article`, `.pd-comments-wrap`, `.ben-card`, `.offer-card-v2` | `var(--radius-card)` → 20px ✓ |
| `24px` | `.reg-card`, `.prod-empty` | ❌ нет токена |
| `100px` | `.pl-counter-chip`, badges | `var(--radius-full)` ✓ |

- **Исправление:**
  - Добавить `--radius-3xl: 1.5rem` (24px) в `variables.css`
  - Добавить `--radius-card-alt: 1.125rem` (18px) в `variables.css` ИЛИ унифицировать на 16px/20px
  - Заменить все хардкодированные значения на токены

### Б3-02 Несогласованный border-width
- [ ] Используются: `1px`, `1.5px`, `2px` для одинаковых типов границ в карточках
- **Исправление:** Ввести `--border-width-card: 1.5px` в `variables.css`.

---

## 🟠 БЛОК 4 — НЕСОГЛАСОВАННОСТЬ ТИПОГРАФИКИ

### Т4-01 Отсутствие типографической шкалы в страничных стилях
- [ ] **Файлы:** Все inline `<style>` в шаблонах
- **Проблема:** Используется ~20 разных font-size значений без системы:
  `.58rem`, `.62rem`, `.65rem`, `.68rem`, `.7rem`, `.72rem`, `.74rem`, `.75rem`, `.78rem`, `.82rem`, `.84rem`, `.85rem`, `.87rem`, `.88rem`, `.875rem`, `.9rem`, `.95rem`
- **Исправление:** Допустимые значения из `variables.css`:
  - `.68-.72rem` → `var(--text-xs)` (0.75rem) 
  - `.82-.88rem` → `var(--text-sm)` (0.875rem)
  - `.95-1rem` → `var(--text-base)` (1rem)

### Т4-02 Прозрачность текста ниже 30% — нечитаемо
- [ ] **Файлы:** Множество шаблонов
- **Проблема:**
  - `rgba(255,255,255,.25)` — `post_list_items.html` строка 48 (excerpt текст)
  - `rgba(255,255,255,.28)` — `comments_section.html` строка 75 (время реплая)
  - `rgba(255,255,255,.3)` — Многие места
  - Минимальный контраст по WCAG AA: 4.5:1 → rgba(255,255,255,.45) минимум
- **Исправление:** Все значения `rgba(255,255,255,X)` где X < 0.4 → заменить на `var(--text-muted)` (= 0.5) или `var(--text-light)` (= 0.38, минимально допустимо).

### Т4-03 `Courier New, monospace` hardcode вместо `var(--font-mono)`
- [ ] **Файлы:** `post_list.html`, `event_list.html`, `member_cabinet.html`, `partner_dashboard.html`, `log_visit.html`, `edit_visit.html`
- **Проблема:** `font-family: 'Courier New', monospace` хардкодировано ~20+ раз.
- **Исправление:** Везде заменить на `font-family: var(--font-mono)`.

---

## 🟠 БЛОК 5 — НАРУШЕНИЯ ПАТТЕРНА АВАТАРОВ

### А5-01 Аватар-fallback с хардкодом красного цвета
- [ ] **Файлы:**
  - `post_list_items.html` строка 61: `background:rgba(220,38,38,.2);color:#f87171`
  - `comments_section.html` строка 53: `background:rgba(220,38,38,.18);color:#f87171`
  - `comments_section.html` строка 72: `background:rgba(255,255,255,.08);color:rgba(255,255,255,.5)` — другой цвет для reply
  - `profile_public.html` строка 32: `background: linear-gradient(135deg, #dc2626, #7f1d1d)`
- **Проблема:** 4 варианта дизайна для одного компонента "аватар-инициалы". Нет единого класса.
- **Исправление:** Использовать `.avatar-fallback[data-avatar-seed]` с CSS переменной `--avatar-hue` (уже реализовано в Sprint UI-5). Заменить все inline fallback-аватары на:
  ```html
  <span class="avatar avatar-sm avatar-fallback" data-avatar-seed="{{ user.username }}">
      {{ user.username|slice:":1"|upper }}
  </span>
  ```

### А5-02 Размер аватаров не использует CSS-классы
- [ ] **Файлы:** `post_list_items.html`, `comments_section.html`
- **Проблема:** `width:22px;height:22px` (post_list), `width:30px;height:30px` (comments), `width:24px;height:24px` (replies) — всё inline.
- **Исправление:** Использовать `.avatar-xs` (24px), `.avatar-sm` (28px), `.cm-avatar` (30px) из `components.css`.

---

## 🟡 БЛОК 6 — HOMEPAGE АРХИТЕКТУРНЫЕ ПРОБЛЕМЫ

### Г6-01 Секция Offers — белые карточки на тёмном сайте
- [ ] **Файл:** [core/templates/core/index.html](IESA_ROOT/core/templates/core/index.html) строки 114-134
- **Проблема:**
  ```css
  #hp-offers { background: #fff; }
  .offer-card-v2 { background: #fff; }
  .iesa-do-item { background: #fff; }
  ```
  Белые секции нарушают единую тёмную тему. `dark-theme-fixes.css` только частично патчит их через `!important`.
- **Исправление:** 
  ```css
  #hp-offers { background: var(--bg-body); }
  .offer-card-v2 { background: var(--bg-surface); border-color: var(--border-dark); }
  .iesa-do-item { background: var(--bg-surface); border-color: var(--border-dark); }
  ```
  Все текстовые цвета уже используют `var(--text-primary/secondary/muted)` — они корректны.

### Г6-02 Секция Mission — белый фон
- [ ] **Файл:** [core/templates/core/index.html](IESA_ROOT/core/templates/core/index.html) строки 178-189
- **Проблема:** `#hp-mission { background: #fff }`, `.mission-panel { border: 1.5px solid var(--border-color) }` (светлая граница).
- **Исправление:** `#hp-mission { background: var(--bg-body) }`, `.mission-panel { border-color: var(--border-dark) }`.

### Г6-03 `var(--primary-light)` — розовый цвет (#fecaca) в светлой теме
- [ ] **Файл:** [core/templates/core/index.html](IESA_ROOT/core/templates/core/index.html) строки 126, 147
- **Проблема:** `.offer-icon-v2 { background: var(--primary-light) }` — `--primary-light` = `#fecaca` (розовый). На тёмном фоне выглядит неуместно.
- **Исправление:** `background: var(--primary-100)` (= `rgba(220,38,38,.08)`) для тёмной темы.

### Г6-04 `.stat-unit`, `.offer-num` — неправильные цвета для тёмного фона
- [ ] **Файл:** [core/templates/core/index.html](IESA_ROOT/core/templates/core/index.html) строки 124, 172
- **Проблема:**
  - `.offer-num { color: rgba(0,0,0,.04) }` — невидимо на тёмном
  - `.stat-unit { color: rgba(255,255,255,.35) }` — граница читаемости
- **Исправление:** `.offer-num { color: rgba(255,255,255,.04) }`, `.stat-unit { color: var(--text-muted) }`.

---

## 🟡 БЛОК 7 — СТРАНИЦЫ БЛОГА

### Б7-01 `post_detail.html` — `{{ post.text|safe }}` без заголовка формата
- [ ] **Файл:** [blog/templates/blog/post_detail.html](IESA_ROOT/blog/templates/blog/post_detail.html) строка 159-161
- **Проблема:** `{{ post.text|safe }}` рендерит HTML из Quill-редактора. Стили для внутренних элементов (`.pd-content h1`, `.pd-content p`, `.pd-content img`) определены, но:
  - Нет `h1` внутри `.pd-content` (это создаст два H1 на странице)
  - `pd-content img { max-width: 100%; border-radius: 10px }` — OK
  - **Нет** обёртки для overflow на мобиле — длинные URL/код могут ломать лейаут
- **Исправление:** Добавить `overflow-wrap: break-word; word-break: break-word` к `.pd-content`.

### Б7-02 `post_detail.html` — likes_count и comments_count вызывают N+1
- [ ] **Файл:** [blog/templates/blog/post_detail.html](IESA_ROOT/blog/templates/blog/post_detail.html) строки 213-215
- **Проблема:** `{{ post_rec.likes.count }}`, `{{ post_rec.comments.count }}` в recommended posts loop — N+1 query.
- **Исправление:** В view передавать annotated queryset с `likes_count`, `comments_count` аннотациями.

### Б7-03 `post_list.html` — `animation:pf-float` в empty state inline
- [ ] **Файл:** [blog/templates/blog/partials/post_list_items.html](IESA_ROOT/blog/templates/blog/partials/post_list_items.html) строки 78-85
- **Проблема:** `style="animation:pf-float 3s ease-in-out infinite;"` — animation name `pf-float` нигде не определена в CSS файлах проекта. Empty state не анимируется.
- **Исправление:** Добавить `@keyframes pf-float` в `pages.css` или использовать существующий `@keyframes float`.

### Б7-04 Comment form — `hero-btn-p` класс в неподходящем контексте
- [ ] **Файл:** [blog/templates/blog/post_detail.html](IESA_ROOT/blog/templates/blog/post_detail.html) строка 181
- **Проблема:** `<button class="btn hero-btn-p btn-sm">Send comment</button>` — `hero-btn-p` определён в `homepage.css` как кнопка героя главной страницы. Семантически неверное переиспользование.
- **Исправление:** Заменить на `<button class="btn btn-primary btn-sm">`.

---

## 🟡 БЛОК 8 — СТРАНИЦЫ СОБЫТИЙ

### Е8-01 `event_list_items.html` — `<style>` в HTMX-партиале
- [ ] **Файл:** [blog/templates/blog/partials/event_list_items.html](IESA_ROOT/blog/templates/blog/partials/event_list_items.html) строки 1-200+
- **Проблема:** Весь CSS для timeline-событий (`.tl-item`, `.tl-card`, `.tl-capacity-fill`, `.tl-countdown` и т.д.) определён внутри `<style>` тега в HTMX-партиале, который загружается при каждом swap.
- **Исправление:** Вынести в `static/css/events-timeline.css`, подключить в `extra_css` блоке `event_list.html`.

### Е8-02 Анимация `.tl-dot--upcoming` использует хардкод цвета
- [ ] **Файл:** [blog/templates/blog/partials/event_list_items.html](IESA_ROOT/blog/templates/blog/partials/event_list_items.html) строки 48-61
- **Проблема:** `background: #f87171; border: 2px solid rgba(248,113,113,.35); box-shadow: 0 0 0 4px rgba(248,113,113,.12)` — хардкод светлого красного вместо токена.
- **Исправление:** `background: var(--primary); border: 2px solid rgba(220,38,38,.35); box-shadow: 0 0 0 4px var(--primary-100)`.

### Е8-03 `.tl-item` transform: `translateX(-18px)` может вызывать горизонтальный скролл
- [ ] **Файл:** [blog/templates/blog/partials/event_list_items.html](IESA_ROOT/blog/templates/blog/partials/event_list_items.html) строки 9-20
- **Проблема:** `transform: translateX(-18px)` на входящей анимации. Если элемент у левого края контейнера без `overflow: hidden` на родителе — небольшой горизонтальный скролл.
- **Исправление:** Добавить `overflow: hidden` на родительский контейнер событий или изменить анимацию на `translateY`.

---

## 🟡 БЛОК 9 — ПРОФИЛЬ И ЛИЧНЫЙ КАБИНЕТ

### П9-01 `profile.html` — 500+ строк inline `<style>`, включая `:root` override
- [ ] **Файл:** [users/templates/users/profile.html](IESA_ROOT/users/templates/users/profile.html) строки 15-550+
- **Проблема:** Весь CSS личного кабинета в `extra_css` inline. Дублирует `member-cabinet.css` (уже вынесен в Sprint UI-2). При этом `profile.html` и `member_cabinet.html` — РАЗНЫЕ страницы с разным контентом, оба переопределяют `:root`.
- **Исправление:** Аналогично Sprint UI-2 — вынести в `static/css/profile-page.css`, подключить через `<link>` в `extra_css`.

### П9-02 `profile_public.html` — дублирует стили из `profile.html`
- [ ] **Файлы:**
  - [users/templates/users/profile.html](IESA_ROOT/users/templates/users/profile.html)
  - [users/templates/users/profile_public.html](IESA_ROOT/users/templates/users/profile_public.html)
- **Проблема:** Публичный профиль (`.pp-*` классы) и личный кабинет (`.cab-*` классы) имеют идентичные паттерны: hero-strip, stat-chips, badge level, progress bars. CSS написан дважды.
- **Исправление:** Объединить общие компоненты в `static/css/profile-common.css`.

### П9-03 `profile.html` — `html, body { background: var(--bg0) !important }` в inline стиле
- [ ] **Файл:** [users/templates/users/profile.html](IESA_ROOT/users/templates/users/profile.html) строка 30
- **Проблема:** Глобальный override `html, body` через `!important` в страничном `<style>`. Это ломает переходы между страницами (HTMX pushState) — тело страницы остаётся с другим фоном.
- **Исправление:** Убрать `html, body` глобальный override. Использовать `.cab-page { background: var(--bg0); min-height: 100vh; }` как уже сделано в `member-cabinet.css`.

---

## 🟡 БЛОК 10 — JS АРХИТЕКТУРА

### JS10-01 `sections-interactions.js` — CSS-эффекты через JavaScript
- [ ] **Файл:** [static/js/sections-interactions.js](IESA_ROOT/IESA_ROOT/static/js/sections-interactions.js)
- **Проблема:** Hover-эффекты на карточках (scale, boxShadow, transform) реализованы через JavaScript mousemove/mouseleave обработчики вместо CSS `:hover`.
- **Исправление:** Перенести все эффекты в CSS:
  ```css
  .si-card:hover { transform: translateY(-4px); box-shadow: var(--shadow-card-hover); }
  ```

### JS10-02 `premium-sections-interactions.js` — hardcoded rgba в JS
- [ ] **Файл:** [static/js/premium-sections-interactions.js](IESA_ROOT/IESA_ROOT/static/js/premium-sections-interactions.js) строка 58
- **Проблема:** `this.style.boxShadow = '0 8px 20px rgba(248, 113, 113, 0.3)'` — жёсткий цвет в JS.
- **Исправление:** `this.style.boxShadow = 'var(--shadow-primary)'` или CSS `:hover`.

### JS10-03 `scroll-animations.js` — потенциально не используется
- [ ] **Файл:** [static/js/scroll-animations.js](IESA_ROOT/IESA_ROOT/static/js/scroll-animations.js)
- **Проблема:** Файл присутствует, но не подключён в `base.html`. Мёртвый код.
- **Исправление:** Проверить использование. Если не нужен — удалить из `static/js/`.

### JS10-04 `member-modal.js` — потенциально дублирует Bootstrap Modal
- [ ] **Файл:** [static/js/member-modal.js](IESA_ROOT/IESA_ROOT/static/js/member-modal.js)
- **Проблема:** Кастомный modal handler. В `base.html` есть комментарий "Modal Handler Script - DISABLED (conflicts with Bootstrap 5.3.3)". `member-modal.js` может быть пережитком.
- **Исправление:** Проверить необходимость. Если не используется — удалить.

---

## 🟡 БЛОК 11 — УВЕДОМЛЕНИЯ И ПОИСК

### У11-01 `notification_list.html` и `dropdown_list.html` — дублирование стилей
- [ ] **Файлы:**
  - [notifications/templates/notifications/notification_list.html](IESA_ROOT/notifications/templates/notifications/notification_list.html)
  - [notifications/templates/notifications/dropdown_list.html](IESA_ROOT/notifications/templates/notifications/dropdown_list.html)
- **Проблема:** Оба файла определяют схожие `.notification-*` классы в `<style>` блоках.
- **Исправление:** Вынести в `static/css/notifications.css`.

### У11-02 `search_results.html` — `<style>` в середине `{% block content %}`
- [ ] **Файл:** [users/templates/users/search_results.html](IESA_ROOT/users/templates/users/search_results.html) строки 31-59
- **Проблема:** `<style>` блок внутри `{% block content %}`, а не в `{% block extra_css %}`. CSS инжектируется в body, что технически невалидно.
- **Исправление:** Переместить в `{% block extra_css %}` или вынести в CSS-файл.

### У11-03 `animation-delay-{{ forloop.counter0 }}` — несуществующий класс
- [ ] **Файлы:** `search_results.html` (строка 64), `post_search_results.html` (строка 43)
- **Проблема:** Класс `animation-delay-0`, `animation-delay-1` и т.д. нигде не определён в CSS.
- **Исправление:** Добавить в `components.css` или использовать inline `transition-delay`.

---

## 🟡 БЛОК 12 — 404 И 500 СТРАНИЦЫ

### О12-01 `404.html` и `500.html` — не расширяют `base.html`
- [ ] **Файлы:**
  - [templates/404.html](IESA_ROOT/IESA_ROOT/templates/404.html)
  - [templates/500.html](IESA_ROOT/IESA_ROOT/templates/500.html)
- **Проблема:** Обе страницы полностью standalone — не используют `base.html`, не имеют navbar, footer, bottom nav. Загружают Bootstrap и Font Awesome независимо. Полностью выбиваются из стиля сайта.
- **Исправление:** Рефакторинг для использования `{% extends "base.html" %}` с override `container_wrap_start/end`. Сохранить полноэкранный layout через `{% block content %}`.

### О12-02 `500.html` — жёсткий цвет фона `#1a0a0a`
- [ ] **Файл:** [templates/500.html](IESA_ROOT/IESA_ROOT/templates/500.html) строка 18
- **Проблема:** `background: linear-gradient(135deg, #1a0a0a 0%, #2d0c0c 40%, #450a0a 100%)` — не соответствует палитре. Должно быть что-то ближе к `--bg-body` с красным оттенком.
- **Исправление:** `background: linear-gradient(135deg, #0e0e18 0%, #1a0a0a 50%, #0e0e18 100%)`.

---

## 🟢 БЛОК 13 — МЕЛКИЕ ДОРАБОТКИ (POLISH)

### М13-01 Отсутствие `loading="lazy"` на части изображений
- [ ] **Файл:** [blog/templates/blog/event_detail.html](IESA_ROOT/blog/templates/blog/event_detail.html) строка 110
- **Исправление:** Добавить `loading="lazy" decoding="async"` к `<img src="{{ event.image.url }}">`.

### М13-02 Emoji в empty states вместо консистентных иконок
- [ ] **Файлы:** `post_list_items.html` (📝), `event_list_items.html` (📅), `product_list.html` (ProductEmoji)
- **Проблема:** `style="font-size:3rem;animation:pf-float..."` с emoji — не соответствует Font Awesome стилю.
- **Исправление:** Заменить emoji на `<i class="fas fa-..." style="font-size:3rem;color:rgba(255,255,255,.1);">`.

### М13-03 `mark` стиль в `search_results.html` дублирует глобальный
- [ ] **Файл:** [users/templates/users/search_results.html](IESA_ROOT/users/templates/users/search_results.html) строки 40-43
- **Проблема:** Стиль для `<mark>` определён локально. Должен быть глобальный в `components.css`.
- **Исправление:** Добавить `mark { background: rgba(220,38,38,.22); color: #fca5a5; font-weight: 500; padding: 1px 3px; border-radius: 2px; }` в `components.css`.

### М13-04 `event_detail.html` — телефон захардкожен в шаблоне
- [ ] **Файл:** [blog/templates/blog/event_detail.html](IESA_ROOT/blog/templates/blog/event_detail.html) (проверить)
- **Проблема:** Если телефон организатора хардкодирован в HTML — нужно брать из модели.

### М13-05 `benefits.html` — `.ben-card[data-glow]` использует нестандартные цвета
- [ ] **Файл:** [core/templates/core/benefits.html](IESA_ROOT/core/templates/core/benefits.html) строки 75-78
- **Проблема:** `rgba(86,171,47,.08)`, `rgba(235,51,73,.08)`, `rgba(240,147,251,.08)` — не из палитры `variables.css`.
- **Исправление:** `rgba(22,163,74,.08)` (= success), `rgba(220,38,38,.08)` (= danger), `rgba(245,158,11,.08)` (= warning).

### М13-06 `.pl-auth-notice color: #e5e7eb` — хардкод
- [ ] **Файл:** [blog/templates/blog/post_list.html](IESA_ROOT/blog/templates/blog/post_list.html) строка 208
- **Исправление:** `color: var(--text-primary)`.

### М13-07 `gallery.html` — `.gallery-thumb` border-radius 18px без токена
- [ ] **Файл:** [gallery/templates/gallery/gallery.html](IESA_ROOT/gallery/templates/gallery/gallery.html) строка 47
- **Исправление:** `border-radius: var(--radius-card)` (= 20px) или добавить токен `--radius-card-alt: 1.125rem`.

### М13-08 `product_list.html` — `prod-empty` использует emoji в анимации
- [ ] **Файл:** [products/templates/products/product_list.html](IESA_ROOT/products/templates/products/product_list.html) строки 36-39
- **Проблема:** `class="prod-emoji"` с `animation: prod-bounce` — keyframe определён локально в `<style>`.
- **Исправление:** Использовать `@keyframes float` из `animations.css`.

---

## ПРИОРИТИЗИРОВАННЫЙ ПЛАН ИСПРАВЛЕНИЙ

### Спринт A — Критические (ломают визуал сейчас)
| Задача | Файл | Сложность |
|--------|------|-----------|
| Б1-02 Белые секции homepage | `index.html` | Низкая |
| Б1-04 Удалить DEBUG comment | `post_search_results.html` | Минуты |
| Б1-07 Вынести style из comments | `comments_section.html` | Средняя |
| Д2-01 Вынести cmd-bar CSS | `post_list.html` + `event_list.html` | Средняя |
| Б1-01 Рефакторинг post_list_items | `post_list_items.html` | Высокая |
| Г6-01/02/03 Тёмная тема homepage | `index.html` | Средняя |

### Спринт B — Высокий приоритет (архитектура)
| Задача | Файл | Сложность |
|--------|------|-----------|
| Д2-02 Единый .page-hero | 5 шаблонов | Средняя |
| А5-01 Унификация avatar-fallback | Все шаблоны | Средняя |
| Е8-01 Вынести events-timeline CSS | `event_list_items.html` | Средняя |
| П9-01 Вынести profile-page CSS | `profile.html` | Высокая |
| О12-01 Рефакторинг 404/500 | `404.html`, `500.html` | Средняя |

### Спринт C — Полировка (Typography & Colors)
| Задача | Файл | Сложность |
|--------|------|-----------|
| Т4-01 Унификация font-size | Все шаблоны | Средняя |
| Т4-02 Минимальная прозрачность .38+ | Все шаблоны | Средняя |
| Т4-03 var(--font-mono) | Все шаблоны | Низкая |
| Б3-01 Токены border-radius | variables.css + шаблоны | Средняя |
| М13-03 .mark в components.css | `search_results.html` | Низкая |
| М13-06 Хардкодированный цвет | `post_list.html` | Минуты |

---

## СТАТИСТИКА АУДИТА

| Категория | Кол-во проблем | Критических |
|-----------|---------------|-------------|
| Критические баги верстки | 8 | 8 |
| Дублирование кода | 6 | 0 |
| Несогласованность border-radius | 2 | 0 |
| Несогласованность типографики | 3 | 0 |
| Паттерн аватаров | 2 | 0 |
| Homepage белые секции | 4 | 3 |
| Страницы блога | 4 | 0 |
| Страницы событий | 3 | 0 |
| Профиль/Кабинет | 3 | 1 |
| JS архитектура | 4 | 0 |
| Уведомления/Поиск | 3 | 0 |
| 404/500 | 2 | 0 |
| Мелкие доработки | 8 | 0 |
| **ИТОГО** | **56** | **12** |
