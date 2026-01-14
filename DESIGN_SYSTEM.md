# 🎨 IESA Modern Design System

## Обзор

Полностью переработанная система дизайна с фокусом на мобильные устройства, современный UX и доступность.

## 📁 Структура файлов

### CSS Файлы

- **`modern-design.css`** (1100+ строк) - Основная система дизайна
  - CSS переменные для всех токенов
  - Компоненты (кнопки, карточки, формы, модалы)
  - Утилиты и помощники
  - Анимации и переходы

- **`mobile-enhanced.css`** (600+ строк) - Мобильная оптимизация
  - Touch интерфейсы (44px минимум)
  - Адаптивная типографика
  - Мобильное меню
  - Safe area support (iPhone notch)
  - Специфичные мобильные компоненты

- **`components.css`** (500+ строк) - Дополнительные компоненты
  - Back-to-top кнопка
  - Toast уведомления
  - Loading состояния
  - Аватары и пустые состояния

### JavaScript Файлы

- **`mobile-interactions.js`** - Интерактивные функции
  - Мобильное меню
  - Модальные окна
  - Lazy loading
  - Smooth scroll
  - Accessibility helpers

## 🎨 Система дизайна

### Цветовая палитра

```css
--color-primary: #ef4444;       /* Красный акцент */
--color-secondary: #6b7280;     /* Серый */
--color-success: #10b981;       /* Зеленый */
--color-warning: #f59e0b;       /* Оранжевый */
--color-danger: #dc2626;        /* Красный */
--color-info: #3b82f6;          /* Синий */

/* Градации серого (10 оттенков) */
--color-gray-50: #f9fafb;
--color-gray-900: #111827;
```

### Типографика

```css
/* Размеры текста */
--text-xs: 0.75rem;    /* 12px */
--text-sm: 0.875rem;   /* 14px */
--text-base: 1rem;     /* 16px */
--text-lg: 1.125rem;   /* 18px */
--text-xl: 1.25rem;    /* 20px */
--text-2xl: 1.5rem;    /* 24px */
--text-3xl: 1.875rem;  /* 30px */
--text-4xl: 2.25rem;   /* 36px */
--text-5xl: 3rem;      /* 48px */
```

### Отступы

```css
--space-1: 0.25rem;    /* 4px */
--space-2: 0.5rem;     /* 8px */
--space-3: 0.75rem;    /* 12px */
--space-4: 1rem;       /* 16px */
--space-6: 1.5rem;     /* 24px */
--space-8: 2rem;       /* 32px */
--space-12: 3rem;      /* 48px */
--space-16: 4rem;      /* 64px */
--space-24: 6rem;      /* 96px */
```

### Тени

```css
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
--shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1);
--shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1);
--shadow-xl: 0 20px 25px rgba(0, 0, 0, 0.15);
```

### Радиусы скругления

```css
--radius-sm: 0.25rem;  /* 4px */
--radius-md: 0.5rem;   /* 8px */
--radius-lg: 0.75rem;  /* 12px */
--radius-xl: 1rem;     /* 16px */
--radius-full: 9999px; /* Круг */
```

## 📱 Мобильная оптимизация

### Минимальные размеры для touch

- **Кнопки**: 44x44px (Apple HIG стандарт)
- **Ссылки**: 44px минимальная высота
- **Чекбоксы/радио**: 24x24px

### Адаптивная типографика

- **Desktop**: 16px base
- **Mobile**: 14px base
- **Заголовки**: масштабируются пропорционально

### Safe Area Support

```css
padding-bottom: env(safe-area-inset-bottom);
```

Поддержка iPhone с вырезом (notch) и Dynamic Island.

### Responsive Breakpoints

```css
/* Mobile First */
@media (min-width: 640px)  { /* sm - большие телефоны */ }
@media (min-width: 768px)  { /* md - планшеты */ }
@media (min-width: 1024px) { /* lg - ноутбуки */ }
@media (min-width: 1280px) { /* xl - десктоп */ }
```

## 🧩 Компоненты

### Кнопки

```html
<!-- Primary -->
<button class="btn btn-primary">Кнопка</button>

<!-- Secondary -->
<button class="btn btn-secondary">Кнопка</button>

<!-- Outline -->
<button class="btn btn-outline">Кнопка</button>

<!-- Ghost -->
<button class="btn btn-ghost">Кнопка</button>

<!-- Размеры -->
<button class="btn btn-primary btn-sm">Маленькая</button>
<button class="btn btn-primary btn-lg">Большая</button>

<!-- Мобильный full-width -->
<button class="btn btn-primary mobile-block">На всю ширину</button>
```

### Карточки

```html
<!-- Стандартная карточка -->
<div class="card">
  <div class="card-body">
    <h5 class="card-title">Заголовок</h5>
    <p>Контент</p>
  </div>
</div>

<!-- Компактная карточка -->
<div class="card card-compact">
  <div class="card-body">Контент</div>
</div>

<!-- Плоская карточка (без тени) -->
<div class="card card-flat">
  <div class="card-body">Контент</div>
</div>
```

### Формы

```html
<div class="form-group">
  <label class="form-label">Email</label>
  <input type="email" class="form-control" placeholder="email@example.com">
</div>

<!-- С валидацией -->
<input class="form-control is-valid">
<input class="form-control is-invalid">
<div class="form-error">Ошибка</div>
<div class="form-success">Успешно</div>
```

### Grid System

```html
<!-- 4 колонки на desktop, 2 на планшете, 1 на мобильном -->
<div class="grid grid-cols-4">
  <div>Колонка 1</div>
  <div>Колонка 2</div>
  <div>Колонка 3</div>
  <div>Колонка 4</div>
</div>
```

### Badges

```html
<span class="badge badge-primary">Primary</span>
<span class="badge badge-success">Success</span>
<span class="badge badge-warning">Warning</span>
<span class="badge badge-danger">Danger</span>
<span class="badge badge-info">Info</span>
<span class="badge badge-secondary">Secondary</span>
```

### Alerts

```html
<div class="alert alert-success">Успех!</div>
<div class="alert alert-warning">Предупреждение</div>
<div class="alert alert-danger">Ошибка</div>
<div class="alert alert-info">Информация</div>
```

### Модальные окна

```html
<div class="modal" id="myModal">
  <div class="modal-content">
    <div class="modal-header">
      <h3>Заголовок</h3>
      <button class="modal-close" onclick="closeModal('myModal')">×</button>
    </div>
    <div class="modal-body">
      Контент модального окна
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('myModal')">Отмена</button>
      <button class="btn btn-primary">Сохранить</button>
    </div>
  </div>
</div>

<!-- Открыть модальное окно -->
<button onclick="openModal('myModal')">Открыть</button>
```

### Bottom Sheets (Мобильные)

```html
<div class="bottom-sheet" id="mySheet">
  <div class="bottom-sheet-handle"></div>
  <div class="bottom-sheet-content">
    <h3>Заголовок</h3>
    <p>Контент bottom sheet</p>
  </div>
</div>

<!-- Открыть -->
<button onclick="openBottomSheet('mySheet')">Открыть</button>
```

## 🎭 Утилиты

### Текст

```html
<p class="text-left">Слева</p>
<p class="text-center">По центру</p>
<p class="text-right">Справа</p>

<p class="text-primary">Основной цвет</p>
<p class="text-muted">Приглушенный</p>

<p class="text-truncate">Обрезанный текст...</p>
<p class="line-clamp-2">Максимум 2 строки...</p>
```

### Отступы

```html
<div class="mt-4">Margin-top</div>
<div class="mb-4">Margin-bottom</div>
<div class="mx-auto">Центрирование</div>
```

### Flex

```html
<div class="d-flex">
  <div>Item 1</div>
  <div>Item 2</div>
</div>

<div class="d-flex justify-content-center">Центрированный</div>
<div class="d-flex align-items-center">Вертикальное выравнивание</div>
<div class="d-flex flex-column">Вертикальный flex</div>
<div class="d-flex gap-3">С отступами между элементами</div>
```

### Видимость

```html
<!-- Скрыть на мобильных -->
<div class="hide-mobile">Только на desktop</div>

<!-- Показать только на мобильных -->
<div class="show-mobile-only">Только на мобильных</div>

<!-- Full width на мобильных -->
<button class="btn mobile-block">Кнопка</button>
```

## 🎬 Анимации

### Встроенные анимации

```css
.fadeIn { animation: fadeIn 0.3s ease-out; }
.slideUp { animation: slideUp 0.3s ease-out; }
```

### Анимации при скролле (через JS)

```javascript
// Автоматически применяется к элементам с классом .animate-on-scroll
```

## ♿ Доступность

### Keyboard Navigation

- Tab - переход между элементами
- Enter/Space - активация кнопок
- Escape - закрытие модальных окон

### Screen Readers

```html
<button aria-label="Закрыть">×</button>
<div role="alert">Важное уведомление</div>
<nav aria-label="Основная навигация">...</nav>
```

### Focus States

Все интерактивные элементы имеют четкий focus state с outline.

### Skip Links

```html
<a href="#main-content" class="skip-to-main">Перейти к контенту</a>
```

## 🚀 JavaScript API

### Toast Notifications

```javascript
showToast('Сохранено успешно!', 'success', 3000);
showToast('Произошла ошибка', 'danger', 5000);
showToast('Обратите внимание', 'warning');
```

### Модальные окна

```javascript
openModal('modalId');
closeModal('modalId');
```

### Bottom Sheets

```javascript
openBottomSheet('sheetId');
closeBottomSheet('sheetId');
```

## 📊 Производительность

### Оптимизации

- **GPU Acceleration**: `transform: translate3d()`
- **Will-change hints**: для анимированных элементов
- **Lazy Loading**: IntersectionObserver для изображений
- **Debounced Events**: поиск с задержкой 400ms
- **Reduced Motion**: отключение анимаций по запросу пользователя

### Bundle Size

- modern-design.css: ~35KB (до сжатия)
- mobile-enhanced.css: ~18KB (до сжатия)
- components.css: ~12KB (до сжатия)
- mobile-interactions.js: ~15KB (до сжатия)

**Итого**: ~80KB CSS + ~15KB JS (до сжатия и минификации)

## 🎯 Best Practices

### Мобильный дизайн

1. ✅ Всегда используйте `mobile-block` для кнопок на мобильных
2. ✅ Минимум 44px для touch элементов
3. ✅ Тестируйте на реальных устройствах
4. ✅ Используйте `env(safe-area-inset-*)` для iPhone

### Формы

1. ✅ Font-size минимум 16px для избежания zoom на iOS
2. ✅ Используйте правильные типы input (email, tel, number)
3. ✅ Добавляйте autocomplete атрибуты
4. ✅ Валидация в реальном времени

### Производительность

1. ✅ Lazy loading для изображений: `<img loading="lazy">`
2. ✅ Используйте CSS вместо JS для анимаций когда возможно
3. ✅ Debounce для частых событий (scroll, resize, input)
4. ✅ Минимизируйте DOM манипуляции

## 🔄 Миграция со старого дизайна

### Замены классов

```html
<!-- Старый -->
<button class="btn-primary btn-modern">Кнопка</button>

<!-- Новый -->
<button class="btn btn-primary">Кнопка</button>
```

```html
<!-- Старый -->
<div class="card card-modern">

<!-- Новый -->
<div class="card">
```

### Старые файлы (можно удалить)

- `unified-design.css` - заменен на `modern-design.css`
- Встроенные стили в шаблонах - перенесены в CSS файлы

## 📖 Примеры использования

### Страница с карточками

```html
<div class="container-limited">
  <h1 class="text-center mb-5">Наши услуги</h1>
  
  <div class="grid grid-cols-3">
    <div class="card">
      <div class="card-body">
        <i class="fas fa-rocket text-primary mb-3" style="font-size: 2rem;"></i>
        <h3 class="card-title">Быстрый старт</h3>
        <p class="text-muted">Начните за считанные минуты</p>
      </div>
    </div>
    
    <!-- Еще карточки... -->
  </div>
</div>
```

### Форма с валидацией

```html
<form class="card p-4">
  <h2 class="mb-4">Регистрация</h2>
  
  <div class="form-group">
    <label class="form-label">Email</label>
    <input type="email" class="form-control" required>
  </div>
  
  <div class="form-group">
    <label class="form-label">Пароль</label>
    <input type="password" class="form-control" required>
  </div>
  
  <button type="submit" class="btn btn-primary mobile-block">
    Зарегистрироваться
  </button>
</form>
```

## 🐛 Troubleshooting

### Проблема: Стили не применяются

**Решение**: Проверьте порядок подключения CSS файлов в base.html:
1. modern-design.css
2. mobile-enhanced.css
3. components.css

### Проблема: Модальные окна не работают

**Решение**: Убедитесь что подключен `mobile-interactions.js` и он загружается после HTML.

### Проблема: Кнопки слишком маленькие на мобильных

**Решение**: Добавьте класс `mobile-block` для full-width на мобильных.

## 📞 Поддержка

При возникновении проблем с новым дизайном:

1. Проверьте консоль браузера на ошибки
2. Убедитесь что все CSS/JS файлы загружены
3. Проверьте что используете правильные классы
4. Тестируйте в разных браузерах

## 🎉 Готово!

Новая система дизайна полностью готова к использованию. Все основные страницы уже обновлены:

- ✅ Главная страница
- ✅ Список постов
- ✅ Детали поста
- ✅ Профиль пользователя
- ✅ Базовый шаблон

Наслаждайтесь современным и удобным интерфейсом! 🚀
