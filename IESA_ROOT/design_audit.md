# IESA Design & UX Comprehensive Audit

> **Дата**: Январь 2026  
> **Стек**: Django 5.2.9 + Bootstrap 5.3.3 + HTMX + CSS Architecture v3.0  
> **Тёмная тема**: `--bg-body: #0e0e18`  
> **Цель**: Полный аудит всех багов, дизайн-проблем, навигации, Telegram-бота — с конкретными файлами, строками и решениями.

---

## ОГЛАВЛЕНИЕ

1. [P0 — КРИТИЧЕСКИЕ БАГИ](#p0--критические-баги)
2. [P1 — TELEGRAM BOT](#p1--telegram-bot)
3. [P2 — МОБИЛЬНАЯ НАВИГАЦИЯ И UX](#p2--мобильная-навигация-и-ux)
4. [P3 — CSS КОНФЛИКТЫ И ТЕМИЗАЦИЯ](#p3--css-конфликты-и-темизация)
5. [P4 — ШАБЛОНЫ — ОШИБКИ И ДИЗАЙН](#p4--шаблоны--ошибки-и-дизайн)
6. [P5 — НАВИГАЦИЯ — ПОЛНОТА И ДОСТУНОСТЬ](#p5--навигация--полнота-и-доступность)
7. [P6 — JAVASCRIPT — ПРОБЛЕМЫ И УЛУЧШЕНИЯ](#p6--javascript--проблемы-и-улучшения)
8. [P7 — ПРОИЗВОДИТЕЛЬНОСТЬ](#p7--производительность)
9. [P8 — БЕЗОПАСНОСТЬ](#p8--безопасность)
10. [P9 — ПРЕДЛОЖЕНИЯ ПО УЛУЧШЕНИЮ ДИЗАЙНА](#p9--предложения-по-улучшению-дизайна)

---

## P0 — КРИТИЧЕСКИЕ БАГИ

### 0.1 ❌ Мобильное меню: белый текст на белом фоне

**Проблема**: При нажатии hamburger-кнопки на мобильном выпадает белая карточка, но текст ссылок остаётся белым → невидимый.

**Файлы**:
- `static/css/layout.css` строка ~130: `.navbar-nav .nav-link { color: rgba(255,255,255,.65); }` — НЕ внутри media query, применяется ВСЕГДА
- `static/css/responsive.css` строка ~210: `.navbar-nav .nav-link { color: #374151; }` — внутри `@media (max-width: 767.98px)`
- `static/css/responsive.css` строка ~200: `.navbar-collapse { background: #fff; }` — белый фон карточки

**Причина**: У обоих правил одинаковая специфичность (`.navbar-nav .nav-link` = 0,2,0). responsive.css загружается ПОСЛЕ layout.css, поэтому по каскаду responsive должен побеждать. НО layout.css также имеет отдельное правило внутри `@media (hover: hover) and (pointer: fine)` для hover-состояний, а для базового цвета проблема в том, что dropdown-item и другие элементы тоже стилизованы под тёмный навбар.

**Дополнительная проблема**: `.dropdown-menu` в layout.css строка ~147: `background: #0f0f1a` — тёмный фон dropdown внутри белой карточки collapse создаёт чёрный блок внутри белого.

**Решение**:
```css
/* responsive.css — усилить специфичность мобильного навбара */
@media (max-width: 767.98px) {
  .navbar-collapse {
    background: rgba(15, 15, 26, 0.98); /* тёмный вместо белого */
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow: 0 8px 30px rgba(0,0,0,0.4);
    backdrop-filter: blur(20px);
  }
  
  .navbar-collapse .navbar-nav .nav-link {
    color: rgba(255,255,255,0.75);
  }
  
  .navbar-collapse .navbar-nav .nav-link:hover,
  .navbar-collapse .navbar-nav .nav-link.active {
    background: rgba(220,38,38,0.12);
    color: #f87171;
  }
  
  .navbar-collapse .dropdown-menu {
    background: rgba(255,255,255,0.04);
    border-color: rgba(255,255,255,0.06);
  }
  
  .navbar-collapse .dropdown-item {
    color: rgba(255,255,255,0.65);
  }
  
  .navbar-collapse .dropdown-item:hover {
    background: rgba(220,38,38,0.1);
    color: #fff;
  }
  
  /* Toggler — тоже тёмный */
  .navbar-toggler {
    border: 1px solid rgba(255,255,255,0.15);
    background: rgba(255,255,255,0.07);
    color: rgba(255,255,255,0.7);
  }
}
```

---

### 0.2 ❌ Выделение текста невидимо на тёмном фоне

**Проблема**: При выделении текста мышью на любой тёмной странице текст становится невидимым.

**Файл**: `static/css/base.css` строки 187-189:
```css
::selection {
  background-color: var(--primary-200);  /* rgba(220, 38, 38, 0.12) — почти прозрачный! */
  color: var(--text-primary);            /* #111827 — тёмный текст */
}
```

**Причина**: `--primary-200` = `rgba(220, 38, 38, 0.12)` — это 12% непрозрачности, на тёмном `#0e0e18` фоне выделение почти невидимо. А цвет текста `#111827` (тёмный) на тёмном фоне = нечитаем.

**Решение**:
```css
::selection {
  background-color: rgba(220, 38, 38, 0.85); /* яркий красный фон */
  color: #ffffff;                              /* белый текст */
}

::-moz-selection {
  background-color: rgba(220, 38, 38, 0.85);
  color: #ffffff;
}
```

---

### 0.3 ❌ `--text-primary: #111827` на `--bg-body: #0e0e18` — глобальная невидимость

**Проблема**: CSS переменная `--text-primary` = `#111827` (тёмно-серый) — это ТЁМНЫЙ цвет, предназначенный для светлого фона. Но фон `--bg-body: #0e0e18` — ТЁМНЫЙ. Любой элемент, использующий `color: var(--text-primary)`, де-факто невидим.

**Файл**: `static/css/variables.css` строка 86: `--text-primary: #111827;`  
**Файл**: `static/css/variables.css` строка 93: `--bg-body: #0e0e18;`

**Зависимости**: Десятки мест используют `var(--text-primary)`:
- `components.css` — `.btn-secondary`, `.btn-light`, `.comment-author`, `.notification-title`, `.post-card-title`
- `pages.css` — `.profile-social-title`, `.post-detail-title`, `.member-name`, `.president-name`, `.partners-section-title`  
- Все эти элементы имеют тёмный-на-тёмном текст когда нет inline-override

**Решение** (два варианта):

**Вариант A — Переопределить переменную для body**:
```css
:root {
  --text-primary: #f0f0f5;     /* Светлый для тёмной темы */
  --text-primary-dark: #111827; /* Оригинал для элементов со светлым фоном */
}
```

**Вариант B (рекомендуемый) — Добавить body color override**:
```css
body {
  color: rgba(255, 255, 255, 0.87); /* Глобальный белый текст */
}
```
И оставить `--text-primary` как есть (для inline элементов на белых карточках). Но тогда нужно пройтись по всем `color: var(--text-primary)` в components/pages CSS и заменить на `color: inherit` или `color: rgba(255,255,255,.87)` для элементов на тёмном фоне.

---

### 0.4 ❌ Страница activity_levels_info.html — целиком СВЕТЛАЯ

**Проблема**: Страница `/auth/activity-levels/` построена полностью в светлой теме. Заголовок `<h1 class="text-primary">` = `#111827` на `#0e0e18` = невидим. `lead text-muted` = `#6b7280` на тёмном = еле видно. Карточки `.card-modern` с белым фоном создают лоскутное одеяло.

**Файл**: `users/templates/users/activity_levels_info.html`

**Решение**: Полная тёмная переделка страницы — аналогично `member_cabinet.html` (тёмные карточки, белый текст, glassmorphism).

---

### 0.5 ❌ Страница search_results.html — НЕ адаптирована под тёмную тему

**Проблема**: Заголовок использует класс `text-gray-900` (Tailwind-стиль, в Bootstrap нет такого класса = без эффекта) → наследует тёмный цвет на тёмном фоне = невидим. `.list-group-item` — белый фон Bootstrap по умолчанию. `text-muted` = `#6b7280` на тёмном = плохо видно.

**Файл**: `users/templates/users/search_results.html`

**Решение**: Полная тёмная стилизация результатов поиска.

---

### 0.6 ❌ profile_edit.html — Cломанная HTML-вёрстка

**Проблема**: Незакрытый `col-md-6` для поля `date_of_birth` (около строки 163) приводит к тому что поля `phone_number` и `is_phone_hidden` оказываются ВЛОЖЕНЫ внутрь колонки date_of_birth вместо соседних.

**Файл**: `users/templates/users/profile_edit.html` ~ строка 163

**Решение**: Проверить и закрыть `</div>` после поля `date_of_birth`.

---

### 0.7 ❌ register.html — Ошибки валидации не отображаются

**Проблема**: `{% with field_class="form-control is-invalid" %}{{ field }}{% endwith %}` — `with` задаёт переменную контекста, но `{{ field }}` рендерит виджет со своими `attrs` и игнорирует `field_class`. Класс `is-invalid` никогда не применяется.

**Файлы**: `users/templates/users/register.html` строки 152, 160

**Решение**: Использовать `{{ field|add_class:"is-invalid" }}` через custom template filter или JS для добавления класса.

---

### 0.8 ❌ benefits.html — Hero не на полную ширину

**Проблема**: Шаблон НЕ переопределяет блоки `container_wrap_start` / `container_wrap_end`. Hero-секция `.ben-hero` будет обёрнута в `<div class="container-limited">` из `base.html`, что обрежет фон hero и добавит padding.

**Файл**: `core/templates/core/benefits.html`

**Решение**: Добавить пустые блоки:
```html
{% block container_wrap_start %}{% endblock %}
{% block container_wrap_end %}{% endblock %}
```

---

## P1 — TELEGRAM BOT

### 1.1 ❌ Бот полностью выключен

**Проблема**: Master kill switch `BOT_ACTIVE = False` в конфиге. Все вызовы `is_active()` возвращают `False`, бот не работает.

**Файл**: `users/telegram/config.py` строка 43:
```python
BOT_ACTIVE = False
```

**Решение**: Изменить на `True`:
```python
BOT_ACTIVE = True
```

---

### 1.2 ❌ Переменные окружения не настроены

**Проблема**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_NAME`, `TELEGRAM_WEBHOOK_SECRET` — НЕ установлены в `.env`, `.env.example` и `app.yaml`.

**Файлы**:
- `.env` — только SECRET_KEY, DEBUG, SSL, DOMAIN
- `.env.example` — нет Telegram-переменных
- `app.yaml` — нет TELEGRAM-переменных

**Решение**:
1. В `.env` добавить:
```
TELEGRAM_BOT_TOKEN=<token от @BotFather>
TELEGRAM_BOT_NAME=IESA_Administrator_bot
TELEGRAM_WEBHOOK_SECRET=<random-secret>
```
2. В `.env.example` добавить шаблоны этих переменных
3. В `app.yaml` добавить в envs секцию

---

### 1.3 ⚠️ Кнопка Telegram доступна ТОЛЬКО в member_cabinet

**Проблема**: Единственный путь для пользователя подключить Telegram — через `member_cabinet.html` (строка 645-698). Причём:
- Карточка Telegram **скрыта** если `telegram_bot_configured = False` (т.е. если `TELEGRAM_BOT_TOKEN` пуст)
- Нет ссылки из `profile.html`, `profile_edit.html`, `profile_public.html`
- Нет ни одного CTA (call-to-action) для подключения Telegram на других страницах

**Файлы**:
- `users/templates/users/member_cabinet.html` строки 645-698
- `users/views_verification.py` строка ~125: `telegram_bot_configured: bool(_token())`

**Решение**:
1. Добавить ссылку/кнопку «Подключить Telegram» в `profile.html` (секция social links)
2. Добавить ссылку в `profile_edit.html`
3. Добавить CTA-баннер в `member_cabinet.html` если Telegram не подключен (более заметный, чем текущая карточка)
4. Добавить пункт в мобильное bottom-nav меню или профиль dropdown

---

### 1.4 ⚠️ togglePasswordVisibility не определён

**Файл**: `users/templates/users/register.html` строка 163  
**Проблема**: Функция `togglePasswordVisibility(this)` вызывается, но нигде не определена в шаблоне. Полагается на неявное подключение из другого места.

**Решение**: Определить функцию inline или в JS-файле.

---

## P2 — МОБИЛЬНАЯ НАВИГАЦИЯ И UX

### 2.1 ❌ Mobile Bottom Nav — БЕЛЫЙ на тёмном сайте

**Проблема**: `.mobile-bottom-nav` использует белый фон `rgba(255,255,255,0.97)`, иконки `#6b7280` (серые). На сайте с `bg-body: #0e0e18` это выглядит инородно.

**Файл**: `static/css/responsive.css` — стили `.mobile-bottom-nav`  
**Файл**: `templates/base.html` строки 486-530

**Решение**: Переделать на тёмную тему:
```css
.mobile-bottom-nav {
  background: rgba(14, 14, 24, 0.97);
  border-top: 1px solid rgba(255,255,255,0.06);
  backdrop-filter: blur(20px);
}

.mbn-item {
  color: rgba(255,255,255,0.5);
}

.mbn-item.active,
.mbn-item:hover {
  color: #f87171;
}

.mbn-badge {
  background: #dc2626;
  color: #fff;
}
```

---

### 2.2 ⚠️ Navbar toggler стили конфликтуют

**Проблема**: В layout.css `.navbar-toggler` задаётся тёмная тема (border: rgba(255,255,255,.15), icon с filter: invert(1) brightness(2)). В responsive.css для <768px переопределяется на СВЕТЛЫЙ (background: #f3f4f6, color: #374151). Визуально toggler то белый, то прозрачный в зависимости от загрузки стилей.

**Файлы**:
- `static/css/layout.css` строки 209-222
- `static/css/responsive.css` строки 183-190

**Решение**: Убрать светлый toggler из responsive.css, оставить тёмный из layout.css.

---

### 2.3 ⚠️ Hamburger menu body-lock: потенциальная проблема

**Файл**: `static/js/header-hide-on-scroll.js` строки 52-60
**Проблема**: `lockScroll()` устанавливает `body.style.overflow = 'hidden'` и `body.style.touchAction = 'none'`. Если пользователь закроет меню кликом вне навбара (обработчик в mobile-optimization.js), `unlockScroll` может не вызваться (разные слушатели). Двойная система закрытия (swipe + click outside + anchor) может рассинхронизироваться.

**Решение**: Унифицировать — слушать событие `hidden.bs.collapse` (уже есть в header-hide-on-scroll.js) и убедиться что ВСЕ методы закрытия вызывают `bsCollapse.hide()`.

---

### 2.4 ⚠️ Нет Products в навигации

**Проблема**: Приложение `products` подключено (`/products/` path в urls.py, `products:product_list` view), но НЕТ ссылки ни в десктопном навбаре, ни в мобильном bottom-nav, ни в Community dropdown.

**Файл**: `templates/base.html` строки 125-142 (desktop nav), 486-530 (mobile nav)

**Решение**: Добавить "Products" / "Товары" в Community dropdown:
```html
<li><a class="dropdown-item" href="{% url 'products:product_list' %}">{% trans "Products" %}</a></li>
```

---

### 2.5 ⚠️ Mobile bottom nav — слабый active-state

**Проблема**: Active-state определяется через `request.resolver_match.url_name` / `request.resolver_match.namespace` — это покрывает только прямые совпадения. Например, `/blog/42/` (post_detail) — `url_name = 'post_detail'` но проверяется `'blog' in namespace`, что работает. Однако `/products/` не отображает никакого active-state.

**Решение**: Расширить логику active-state для всех разделов.

---

### 2.6 💡 Gallery модальное окно — нет навигации клавиатурой

**Проблема**: В gallery модале (просмотр фото) нельзя переключать стрелками клавиатуры. Пользователь вынужден кликать prev/next.

**Файл**: `gallery/templates/gallery/gallery.html`

**Решение**: Добавить `keydown` event listener для ArrowLeft / ArrowRight.

---

## P3 — CSS КОНФЛИКТЫ И ТЕМИЗАЦИЯ

### 3.1 ❌ pages.css vs inline styles — война специфичности

**Проблема**: `pages.css` определяет СВЕТЛУЮ тему для профильных компонентов:
- `.profile-edit-card { background: #ffffff }` (строка ~34)
- `.info-pill { background: #fff }`
- `.stat-chip { background: #fff }`
- `.profile-links-card { background: #fff }`

Шаблоны `profile_edit.html` и `profile_public.html` переопределяют это inline `<style>` с `!important` на тёмную тему. Двойное определение = кошмар поддержки.

**Файлы**:
- `static/css/pages.css` строки 1-300, 300-700
- `users/templates/users/profile_edit.html` inline `<style>`
- `users/templates/users/profile_public.html` inline `<style>`

**Решение**: Убрать светлые стили из pages.css ИЛИ убрать inline styles из шаблонов. Выбрать ОДНО место для определения стилей профиля.

---

### 3.2 ⚠️ Hardcoded цвета вместо CSS-переменных — МАССОВАЯ проблема

**Масштаб**: Практически каждый шаблон с inline `<style>` использует hardcoded hex:
- `#0a0a0f`, `#111118`, `#1a1a24`, `#0e0e18` — различные оттенки тёмного (вместо `var(--bg-body)` или новой переменной)
- `rgba(220,38,38,...)` — вместо `var(--primary)`
- `#fff`, `#374151`, `#6b7280` — hardcoded нейтральные

**Затронутые шаблоны** (ВСЕ с inline `<style>`):
- `post_list.html`, `post_detail.html`, `event_list.html`
- `profile_edit.html`, `profile_public.html`, `member_cabinet.html`
- `connect_telegram_code.html`
- `gallery.html`
- `notification_list.html`
- `register.html`, `login.html`

**Решение**: Добавить в `variables.css` тёмные переменные:
```css
:root {
  --bg-surface: #111118;       /* карточки и поверхности */
  --bg-surface-hover: #1a1a24; /* hover-состояние */
  --bg-overlay: rgba(14,14,24,0.98); /* наложения */
  --text-on-dark: rgba(255,255,255,0.87);
  --text-on-dark-muted: rgba(255,255,255,0.55);
  --border-dark: rgba(255,255,255,0.08);
  --border-dark-hover: rgba(255,255,255,0.15);
}
```
И постепенно заменять hardcoded значения.

---

### 3.3 ⚠️ Modal стили — forced dark с !important

**Файл**: `static/css/layout.css` строка ~658:
```css
.modal-content { background: #111118 !important; color: #fff !important; border: 1px solid rgba(255,255,255,.1) !important; }
```

**Проблема**: `!important` на modal-content делает невозможным создание светлых модалов (например, подтверждение действия). Все модалы на сайте принудительно тёмные.

**Решение**: Убрать `!important`, использовать `.modal-dark .modal-content` или полагаться на каскад.

---

### 3.4 ⚠️ benefits.html — белые карточки на тёмном фоне

**Файл**: `core/templates/core/benefits.html`
**Проблема**: `.ben-card { background: #fff }` — белые карточки на тёмной странице. Выбивается из общего тёмного стиля.

**Решение**: Переделать карточки в тёмный стиль с glassmorphism.

---

### 3.5 ⚠️ gallery.html — невидимый бордер

**Файл**: `gallery/templates/gallery/gallery.html`
**Проблема**: `.gallery-thumb` имеет `border: 1.5px solid rgba(0,0,0,.06)` — почти прозрачная ЧЁРНАЯ граница на тёмном фоне = невидима.

**Решение**: `border: 1.5px solid rgba(255,255,255,0.06)` — белая прозрачная.

---

### 3.6 ⚠️ 500.html — синий градиент (off-brand)

**Файл**: `templates/500.html`
**Проблема**: Использует Bootstrap-синий `#0d6efd` → `#7aa5ff` градиент. Весь остальной сайт красный `#dc2626`. 404.html правильно — красный.

**Решение**: Заменить на красный градиент (`#ef4444` → `#dc2626`) или тёмный нейтральный стиль.

---

### 3.7 ⚠️ Login / Register — двухпанельный дизайн

**Файлы**: `users/templates/users/login.html`, `register.html`
**Проблема**: Левая панель — тёмная (маркетинг), правая — БЕЛАЯ (форма). На мобильных (< 992px) тёмная панель `display: none` — пользователь видит только белую форму на тёмном фоне сайта.  
**Не баг, но**: Белая форма на тёмном bg-body выглядит как "пятно". 

**Решение (optional)**: Рассмотреть single-column тёмную форму для мобильных, или добавить border-radius и shadow на белую панель чтобы она выглядела как осознанная карточка.

---

### 3.8 💡 `border-color-light` для тёмной темы

**Файл**: `variables.css` строка 99: `--border-color-light: rgba(0, 0, 0, 0.06);`
**Проблема**: На тёмном фоне `rgba(0,0,0,0.06)` = невидимый. Используется в `pages.css`, `components.css` для `.post-card-meta`, `.notification-item`, `.comment`.

**Решение**: `--border-color-light: rgba(255, 255, 255, 0.06);`

---

## P4 — ШАБЛОНЫ — ОШИБКИ И ДИЗАЙН

### 4.1 ❌ profile_public.html — hardcoded admin URL

**Файл**: `users/templates/users/profile_public.html` строка ~101
**Проблема**: `href="/admin/users/user/{{ user_obj.pk }}/change/"` — hardcoded URL. Если admin URL prefix изменится — ссылка сломается.

**Решение**: `{% url 'admin:users_user_change' user_obj.pk %}`

---

### 4.2 ⚠️ profile_edit.html — social links inline styles хрупкие

**Файл**: `users/templates/users/profile_edit.html`
**Проблема**: Пример social links блок использует `background: #f8f9fa`, `background: white`, `color: #333` — hardcoded. В `pages.css` есть атрибутные селекторы `[style*="background: #f8f9fa"]` для их переопределения, но если изменить пробел или формат — перестанет работать.

**Решение**: Использовать CSS-классы вместо inline styles + атрибутных селекторов.

---

### 4.3 ⚠️ post_detail.html — `{% load static %}` дублируется

**Файл**: `blog/templates/blog/post_detail.html` строки 12, 18
**Проблема**: `{% load static %}` загружается дважды (в блоках `og_image` и `twitter_image`). Не сломает ничего, но лишний код.

**Решение**: Переместить один `{% load static %}` наверх файла.

---

### 4.4 ⚠️ gallery.html — сломанная логика data-delay

**Файл**: `gallery/templates/gallery/gallery.html`
**Проблема**: `data-delay="{{ forloop.counter|add:'0'|divisibleby:'4'|yesno:'4,1,2,3' }}"` — `divisibleby:'4'` возвращает True/False, `yesno` маппит на "4" или "1,2,3" (строка!). Результат всегда "4" или литеральное "1,2,3", а не числовая последовательность задержек.

**Решение**: Использовать `{{ forloop.counter|divisibleby:4|yesno:"400,100" }}` или лучше вычислять в JS.

---

### 4.5 ⚠️ register.html — `{{ field.help_text|safe }}`

**Файл**: `users/templates/users/register.html` строка ~171
**Проблема**: `|safe` на `field.help_text` выводит неэкранированный HTML. Если кастомное поле имеет help_text с пользовательским вводом — XSS.

**Решение**: Для стандартных Django-полей это безопасно (help_text задаётся в модели). Но лучше заменить на `{{ field.help_text }}` (без `|safe`) или `{{ field.help_text|escape }}`.

---

### 4.6 ⚠️ notification_list.html — `<style>` в конце страницы

**Файл**: `notifications/templates/notifications/notification_list.html`
**Проблема**: Блок `<style>` расположен после HTML-контента. Работает, но неконвенционально — может вызвать FOUC (flash of unstyled content) при медленной загрузке.

**Решение**: Переместить в `{% block extra_css %}` или в начало контент-блока.

---

### 4.7 💡 404.html — hardcoded search URL

**Файл**: `templates/404.html`
**Проблема**: `action="/blog/search/"` — hardcoded URL формы поиска. Стоит проверить что этот endpoint существует и работает.

**Решение**: Если это standalone-страница (не extends base.html), Django tags недоступны — URL можно оставить, но убедиться что он валиден.

---

## P5 — НАВИГАЦИЯ — ПОЛНОТА И ДОСТУПНОСТЬ

### 5.1 ❌ Products отсутствует в навигации

Как описано в 2.4 — приложение зарегистрировано, view работает, но ссылки нет.

### 5.2 ⚠️ Messaging не в навигации

**Проблема**: Приложение `messaging/` существует, но URL `/messaging/` не подключён в `IESA_ROOT/urls.py`. Шаблон `messaging/templates/messaging/` существует. Кнопка messaging есть в layout.css (`.messaging-btn`), но нигде не используется в base.html.

**Решение**: Решить — подключать ли messaging или убрать код.

---

### 5.3 ⚠️ Нет кнопки "Назад" / breadcrumbs

**Проблема**: На внутренних страницах (post_detail, event_detail, profile_edit, connect_telegram) нет breadcrumbs или кнопки "Назад". Пользователь полагается на кнопку браузера.

**Решение**: Добавить breadcrumbs или back-link в `base.html` (блок `breadcrumb`) и переопределять в шаблонах.

---

### 5.4 ⚠️ Community dropdown — нет визуального разделения

**Проблема**: Items в Community dropdown (Posts, Events, Partners, Members, + Create post для авторизованных) идут сплошным списком без разделителей или группировки.

**Решение**: Добавить `<li><hr class="dropdown-divider"></li>` между основными пунктами и "Create post".

---

### 5.5 💡 Отсутствие ссылки на уведомления в десктопном навбаре

**Проблема**: В десктопной навигации (base.html) есть bell-иконка с числом уведомлений, но она может быть незаметна. В мобильном bottom-nav есть "Alerts" — хорошо. Однако для desktop стоит убедиться что bell-иконка достаточно заметна.

---

### 5.6 💡 Footer — проверить валидность ссылок

**Файл**: `templates/base.html` — footer секция  
**Проблема**: Стоит проверить что все ссылки в footer (если есть) ведут на существующие страницы.

---

## P6 — JAVASCRIPT — ПРОБЛЕМЫ И УЛУЧШЕНИЯ

### 6.1 ❌ Дублирование scroll handler 

**Проблема**: `header-hide-on-scroll.js` И `performance-optimization.js` оба добавляют scroll listener для header show/hide. Они будут конфликтовать — один показывает header, другой скрывает.

**Файлы**:
- `static/js/header-hide-on-scroll.js` строки 27-44: `hide()` / `show()` с debounce
- `static/js/performance-optimization.js` строки 97-108: `initOptimizedScrollListeners()` — тоже header show/hide с throttle

**Решение**: Удалить дубликующийся код из `performance-optimization.js`. Оставить основной в `header-hide-on-scroll.js`.

---

### 6.2 ⚠️ Дублирование IntersectionObserver для анимаций

**Проблема**: `scroll-animations.js`, `sections-interactions.js`, `premium-sections-interactions.js` — все три используют IntersectionObserver для `.card`, `.partner-card-compact`, `.member-card` и добавляют fade-in анимации. Тройное наблюдение одних и тех же элементов.

**Файлы**:
- `static/js/scroll-animations.js` — observes `.member-card`, партнёры, секции
- `static/js/sections-interactions.js` строки 38-48 — observes `.product-card, .event-card, .benefit-card, .member-card, .partner-card-compact`
- `static/js/premium-sections-interactions.js` — event cards, partner cards, member cards

**Решение**: Консолидировать в один файл (`scroll-animations.js`), удалить дубликаты из остальных.

---

### 6.3 ⚠️ Дублирование lazy-loading

**Проблема**: `mobile-optimization.js` (initLazyImages — добавляет loading="lazy"), `performance-optimization.js` (initLazyLoading — IntersectionObserver для data-src), `partner-card-effects.js` (lazyLoadLogos) — три разных системы lazy loading.

**Решение**: Оставить нативный `loading="lazy"` + IntersectionObserver fallback в ОДНОМ файле.

---

### 6.4 ⚠️ partner-card-effects.js — audio feedback

**Файл**: `static/js/partner-card-effects.js` строки 139-166
**Проблема**: Функция `addAudioFeedback()` создаёт AudioContext и проигрывает звук при hover на партнёрских карточках. Закомментирована в init, но сам код остался. Может случайно включиться. Web Audio API на hover — плохая UX практика.

**Решение**: Удалить полностью функцию `addAudioFeedback()`.

---

### 6.5 💡 Gallery — добавить keyboard navigation

**Файл**: `gallery/templates/gallery/gallery.html`

**Решение**:
```javascript
document.addEventListener('keydown', function(e) {
  if (e.key === 'ArrowRight') document.querySelector('.gallery-next-btn')?.click();
  if (e.key === 'ArrowLeft') document.querySelector('.gallery-prev-btn')?.click();
  if (e.key === 'Escape') document.querySelector('.gallery-modal .btn-close')?.click();
});
```

---

### 6.6 💡 Ripple effect подключён, но не оптимизирован

**Файл**: `static/css/components.css` строки 40-50: `.ripple` class с CSS анимацией.  
**Файл**: `partner-card-effects.js` — добавляет `.ripple-effect` (другой класс!).

**Проблема**: Два разных ripple-класса (`.ripple` в CSS, `.ripple-effect` в JS). Если JS добавляет `.ripple-effect` но CSS ожидает `.ripple` — анимация не работает.

**Решение**: Унифицировать класс ripple.

---

### 6.7 💡 Smooth Scroll конфликт

**Файл**: `static/css/animations.css` строка 10: `html { scroll-behavior: smooth; }`  
**Файл**: `static/js/sections-interactions.js` строки 132-148: `initSmoothScroll()` с `window.scrollTo`

**Проблема**: CSS smooth scroll плюс JS smooth scroll вместе — избыточно. JS-версия использует `offsetTop - 80` для учёта navbar, что полезно, но CSS `:target { scroll-margin-top: 160px }` тоже учитывает это.

**Решение**: Оставить CSS `scroll-behavior: smooth` + `scroll-margin-top`, убрать JS `initSmoothScroll()` или наоборот — выбрать одно.

---

## P7 — ПРОИЗВОДИТЕЛЬНОСТЬ

### 7.1 ⚠️ N+1 запросы в post_detail

**Файл**: `blog/templates/blog/post_detail.html` строки ~170, 214-216
**Проблема**: `{{ post.comments.count }}`, `post_rec.likes.count`, `post_rec.comments.count` — каждый обращение = SQL-запрос. Для рекомендованных постов (3-5 шт) это 6-10 дополнительных запросов.

**Решение**: Использовать `annotate(comment_count=Count('comments'), like_count=Count('likes'))` в view.

---

### 7.2 ⚠️ profile_public.html — polling каждые 30 секунд

**Файл**: `users/templates/users/profile_public.html` строка ~131
**Проблема**: `hx-trigger="load, every 30s"` для follower count — HTMX poll каждые 30 секунд. При 100 просматривающих профилей = 200 запросов/мин.

**Решение**: Увеличить интервал до 120s или убрать polling, обновлять только при действии.

---

### 7.3 ⚠️ 11 JS файлов загружаются на каждой странице

**Файлы**: Все JS подключены в `base.html`:
- htmx.min.js (77KB gzip ~28KB)
- mobile-optimization.js
- header-hide-on-scroll.js
- htmx-animation-disable.js
- performance-optimization.js
- scroll-animations.js
- sections-interactions.js
- premium-sections-interactions.js
- partner-card-effects.js
- member-modal.js
- touch-gestures.js (350 строк!)

**Проблема**: Многие из них нужны ТОЛЬКО на homepage (scroll-animations, sections-interactions, premium-sections-interactions, partner-card-effects, member-modal). Загрузка на всех страницах — лишний вес.

**Решение**: 
1. Загружать homepage-specific JS только на homepage через `{% block extra_js %}`
2. Объединить/минифицировать через Django Compressor или esbuild
3. Добавить `defer` / `async` атрибуты

---

### 7.4 💡 CSS тоже можно разделить

9 CSS файлов загружаются на каждой странице. `homepage.css` (2269 строк!) нужен только на homepage.

---

### 7.5 💡 preloadCriticalResources() — hardcoded paths

**Файл**: `performance-optimization.js` строки 170-185
**Проблема**: `href = \`/static/${href}\`` — hardcoded `/static/`. Django может использовать другой STATIC_URL (например, CDN) — ссылки будут битые.

**Решение**: Передавать `STATIC_URL` из Django в JS через data-атрибут или template variable.

---

## P8 — БЕЗОПАСНОСТЬ

### 8.1 ⚠️ post_detail.html — XSS через `{{ post.text|safe }}`

**Файл**: `blog/templates/blog/post_detail.html` строка ~162
**Проблема**: `{{ post.text|safe }}` выводит HTML без экранирования. Если пост содержит `<script>alert('xss')</script>` — это XSS. Зависит от серверной санитизации (CKEditor 5).

**Решение**: Убедиться что CKEditor 5 санитизирует HTML на сервере при сохранении. Или использовать библиотеку bleach для очистки при выводе: `{{ post.text|bleach_clean|safe }}`.

---

### 8.2 ⚠️ register.html — `{{ field.help_text|safe }}`

Описано в 4.5.

---

### 8.3 💡 CSRF в standalone 404/500

**Файлы**: `templates/404.html`, `templates/500.html`
**Проблема**: Standalone страницы — не через Django template engine с контекстом. Если формы поиска (`/blog/search/`) требуют CSRF, форма в 404.html может не иметь token.

**Решение**: Использовать `method="GET"` для поисковых форм (уже так, скорее всего).

---

## P9 — ПРЕДЛОЖЕНИЯ ПО УЛУЧШЕНИЮ ДИЗАЙНА

### 9.1 💡 Glassmorphism мобильное меню

Вместо белого/тёмного фона — blur-эффект как на desktop header:
```css
.navbar-collapse {
  background: rgba(14, 14, 24, 0.85);
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0,0,0,0.5);
}
```

---

### 9.2 💡 Animated gradient border на карточках

```css
.card-premium {
  background: #111118;
  position: relative;
  border-radius: 16px;
}

.card-premium::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 17px;
  background: linear-gradient(135deg, #dc2626, #f87171, #dc2626, #991b1b);
  background-size: 300% 300%;
  animation: gradient-border 4s ease infinite;
  z-index: -1;
}

@keyframes gradient-border {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
```

---

### 9.3 💡 Micro-interactions для hover состояний

Добавить в `animations.css`:
```css
/* Subtle glow на hover для кнопок */
@media (hover: hover) and (pointer: fine) {
  .btn-primary:hover {
    box-shadow: 0 0 20px rgba(220, 38, 38, 0.4),
                0 8px 16px rgba(0, 0, 0, 0.2);
  }
  
  /* Nav link подчёркивание снизу */
  .navbar-nav .nav-link::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 50%;
    width: 0;
    height: 2px;
    background: #f87171;
    transition: width 0.3s, left 0.3s;
  }
  
  .navbar-nav .nav-link:hover::after,
  .navbar-nav .nav-link.active::after {
    width: 80%;
    left: 10%;
  }
}
```

---

### 9.4 💡 Scroll progress indicator

Тонкая красная полоска вверху страницы показывающая прогресс скролла:
```css
.scroll-progress {
  position: fixed;
  top: 0;
  left: 0;
  height: 3px;
  background: linear-gradient(90deg, #dc2626, #f87171);
  z-index: 9999;
  transition: width 0.1s linear;
}
```
```javascript
window.addEventListener('scroll', () => {
  const winScroll = document.documentElement.scrollTop;
  const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
  const scrolled = (winScroll / height) * 100;
  document.querySelector('.scroll-progress').style.width = scrolled + '%';
});
```

---

### 9.5 💡 Улучшенные toast / flash messages

Текущие сообщения используют стандартные Bootstrap toasts. Можно добавить:
- Красный accent-border слева
- Иконку в зависимости от типа (success ✓, error ✗, info ℹ, warning ⚠)
- Анимацию slide-in справа (уже есть в animations.css)

---

### 9.6 💡 Smooth page transition indicator

При HTMX навигации — добавить top-loading-bar (как GitHub / YouTube):
```css
.htmx-request .page-loading-bar {
  display: block;
  position: fixed;
  top: 0;
  left: 0;
  height: 3px;
  background: #dc2626;
  animation: loading-bar 2s ease;
  z-index: 99999;
}

@keyframes loading-bar {
  0% { width: 0 }
  50% { width: 60% }
  100% { width: 90% }
}
```

---

### 9.7 💡 Dark-mode текстовые тени для заголовков

```css
.hp-h2, .section-title {
  text-shadow: 0 0 40px rgba(220, 38, 38, 0.15);
}
```

---

### 9.8 💡 Улучшенные переходы между страницами

`animations.css` уже содержит View Transitions API, но можно добавить morph-подобные переходы для карточек:
```css
.card, .post-card, .event-card {
  view-transition-name: card;
}
```

---

### 9.9 💡 Floating action button (FAB) для быстрых действий

На мобильных — FAB кнопка (вместо/дополнение к bottom nav) для:
- Создать пост
- Отправить сообщение
- Открыть QR-код Telegram

---

### 9.10 💡 Counter animations для статистики

На профиле / homepage — анимированные счётчики (0 → final value) при появлении в viewport:
```javascript
function animateCounter(el) {
  const target = parseInt(el.dataset.target);
  const duration = 1500;
  const start = performance.now();
  
  function update(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    el.textContent = Math.floor(eased * target);
    if (progress < 1) requestAnimationFrame(update);
  }
  
  requestAnimationFrame(update);
}
```

---

## СВОДКА: ПОРЯДОК ВЫПОЛНЕНИЯ

### Фаза 1 — Критические исправления (обязательно)
1. ✅ **[0.1]** Тёмное мобильное меню (responsive.css)
2. ✅ **[0.2]** Исправить `::selection` (base.css) 
3. ✅ **[0.3]** Решить `--text-primary` проблему (variables.css)
4. ✅ **[0.6]** Исправить HTML nesting в profile_edit.html
5. ✅ **[0.7]** Исправить error styling в register.html
6. ✅ **[0.8]** Добавить container overrides в benefits.html

### Фаза 2 — Telegram Bot
7. ✅ **[1.1]** `BOT_ACTIVE = True`
8. ✅ **[1.2]** Настроить env vars
9. ✅ **[1.3]** Добавить CTA для подключения Telegram
10. ✅ **[1.4]** Определить togglePasswordVisibility

### Фаза 3 — Мобильный UX
11. ✅ **[2.1]** Тёмный mobile bottom nav
12. ✅ **[2.2]** Унифицировать toggler стили
13. ✅ **[2.4]** Добавить Products в nav
14. ✅ **[2.6]** Gallery keyboard navigation

### Фаза 4 — CSS чистка
15. ⏳ **[3.1]** Разрешить pages.css vs inline styles (крупный рефакторинг)
16. ✅ **[3.2]** Добавить CSS-переменные для тёмной темы
17. ✅ **[3.3]** Убрать !important из modal
18. ✅ **[3.4]** Тёмные карточки benefits
19. ✅ **[3.5]** Gallery border fix
20. ✅ **[3.6]** 500.html красный градиент
21. ✅ **[3.8]** Исправить --border-color-light

### Фаза 5 — Страницы без тёмной темы
22. ✅ **[0.4]** Темизация activity_levels_info.html
23. ✅ **[0.5]** Темизация search_results.html

### Фаза 6 — JS консолидация
24. ✅ **[6.1]** Удалить дубликат scroll handler
25. ✅ **[6.2]** Консолидировать IntersectionObserver
26. ⏳ **[6.3]** Консолидировать lazy-loading (3 системы → 1)
27. ✅ **[6.4]** Удалить audio feedback
28. ✅ **[6.6]** Унифицировать ripple class
29. ✅ **[6.7]** Убрать duplicate smooth scroll

### Фаза 7 — Шаблоны
30. ✅ **[4.1]** profile_public admin URL fix
31. ✅ **[4.3]** post_detail duplicate load static
32. ✅ **[4.4]** gallery.html data-delay fix
33. ✅ **[4.5]** register.html help_text|safe removed
34. ✅ **[4.6]** notification_list.html style moved to extra_css
35. ✅ **[4.7]** 404.html hardcoded search URL → {% url %}

### Фаза 8 — Производительность
36. ⏳ **[7.1]** Исправить N+1 запросы (post_detail)
37. ✅ **[7.2]** Уменьшить polling frequency (30s→120s)
38. ⏳ **[7.3]** Разделить JS на homepage-specific и global
39. ✅ **[7.5]** preloadCriticalResources hardcoded /static/ → dynamic

### Фаза 9 — Не реализовано (требует решений / крупный рефакторинг)
- ⏳ **[2.3]** Body-lock sync
- ⏳ **[2.5]** Mobile bottom nav active state для всех секций
- ⏳ **[3.7]** Login/Register two-panel mobile
- ⏳ **[4.2]** profile_edit social links inline styles
- ⏳ **[5.2]** Messaging в навигации
- ⏳ **[5.3]** Breadcrumbs
- 💡 **[5.5]** Bell icon заметность (верифицировано — работает)
- 💡 **[5.6]** Footer ссылки (верифицировано — GET, валидно)
- ⏳ **[7.4]** CSS splitting
- 💡 **[8.1]** XSS via post.text|safe (зависит от CKEditor sanitization)
- 💡 **[8.3]** CSRF в 404/500 (формы GET — не нужен)
- ⏳ **[9.1-9.10]** Glassmorphism, gradient borders, micro-interactions, etc.

---

## ФАЙЛЫ ЗАТРОНУТЫЕ АУДИТОМ

| Файл | Проблемы |
|------|----------|
| `static/css/variables.css` | 0.3, 3.2, 3.8 |
| `static/css/base.css` | 0.2 |
| `static/css/layout.css` | 0.1, 2.2, 3.3 |
| `static/css/responsive.css` | 0.1, 2.1 |
| `static/css/pages.css` | 3.1 |
| `static/css/components.css` | 6.6 |
| `static/css/animations.css` | 6.7 |
| `templates/base.html` | 2.1, 2.4, 5.4 |
| `templates/404.html` | 4.7 |
| `templates/500.html` | 3.6 |
| `users/templates/users/profile_edit.html` | 0.6, 3.1, 4.2 |
| `users/templates/users/profile.html` | 1.3 |
| `users/templates/users/profile_public.html` | 4.1 |
| `users/templates/users/register.html` | 0.7, 1.4, 4.5 |
| `users/templates/users/login.html` | 3.7 |
| `users/templates/users/member_cabinet.html` | 1.3 |
| `users/templates/users/activity_levels_info.html` | 0.4 |
| `users/templates/users/search_results.html` | 0.5 |
| `core/templates/core/benefits.html` | 0.8, 3.4 |
| `gallery/templates/gallery/gallery.html` | 2.6, 3.5, 4.4 |
| `blog/templates/blog/post_detail.html` | 4.3, 7.1, 8.1 |
| `notifications/templates/notifications/notification_list.html` | 4.6 |
| `users/telegram/config.py` | 1.1 |
| `.env` / `.env.example` / `app.yaml` | 1.2 |
| `static/js/header-hide-on-scroll.js` | 2.3 |
| `static/js/performance-optimization.js` | 6.1, 7.5 |
| `static/js/scroll-animations.js` | 6.2 |
| `static/js/sections-interactions.js` | 6.2, 6.7 |
| `static/js/premium-sections-interactions.js` | 6.2 |
| `static/js/partner-card-effects.js` | 6.3, 6.4 |
| `static/js/mobile-optimization.js` | 6.3 |
| `static/js/touch-gestures.js` | (рассмотреть необходимость) |
| `users/views_verification.py` | 7.2 |

---

> **Итого**: 55+ задач, 32+ файлов. Готов к работе.
