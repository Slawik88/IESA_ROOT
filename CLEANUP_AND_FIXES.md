# Cleanup & Fixes - 18 января 2026

## 🔴 Проблемы найденные в логах

### 1. **Ошибка 500 при создании поста**
```
django.urls.exceptions.NoReverseMatch: Reverse for 'post_list' not found
```
**Причина:** В `blog/views/posts.py` использовалось `reverse_lazy('post_list')` без namespace  
**Решение:** Изменено на `reverse_lazy('blog:post_list')`

**Файлы изменены:**
- `IESA_ROOT/blog/views/posts.py` (line 108)
- `IESA_ROOT/blog/sitemaps.py` (line 35) - обновлены все URL names с namespace

### 2. **POST 405 Method Not Allowed на /messages/2/**
```
WARNING 2026-01-18 21:38:04,279 log Method Not Allowed (POST): /messages/2/
```
**Причина:** JavaScript отправляет POST на основной URL вместо /send/ эндпоинта  
**Решение:** Конвертированы кнопки действий с HTMX на fetch API с правильными URL-ами

---

## 🧹 Очистка старых файлов

### Удалены backup файлы:
- ❌ `messaging/templates/messaging/conversation_detail.backup.html`
- ❌ `messaging/templates/messaging/partials/message_item.backup.html`
- ❌ `messaging/templates/messaging/partials/message_bubble.html` (устаревший шаблон)
- ❌ `blog/forms_new.py.backup`
- ❌ `blog/views_old.py.backup`
- ❌ `static/css/messaging.backup.css`

---

## ✅ Новые файлы

### `messaging/templates/messaging/partials/message_item_detailed.html`
Новый шаблон для `conversation_detail.html`:
- Без HTMX зависимостей
- Кнопки действий используют fetch API через JavaScript функции
- Совместим с новой архитектурой fetch-based messaging

---

## 🔧 Исправления архитектуры

### conversation_detail.html
```html
<!-- ДО: HTMX зависимости -->
{% include 'messaging/partials/message_item.html' with message=message %}

<!-- ПОСЛЕ: Новый шаблон без HTMX -->
{% include 'messaging/partials/message_item_detailed.html' with message=message %}
```

### Добавлены функции для работы с сообщениями
```javascript
window.pinMessage(messageId)      // POST /messages/message/{id}/pin/
window.editMessage(messageId)     // POST /messages/message/{id}/edit/
window.deleteMessage(messageId)   // POST /messages/message/{id}/delete/
```

---

## 📊 Статус

✅ **Django system check:** 0 issues  
✅ **Git commit:** 54181ec2  
✅ **Все старые файлы удалены**  
✅ **Миграции созданы и применены:** messaging.0003_alter_message_text_and_more  

---

## 🎯 Итоги

1. **Исправлены 500 ошибки** при создании постов
2. **Удалены все старые/backup файлы** которые могли препятствовать работе
3. **Разделены шаблоны:**
   - `message_item.html` - для `inbox.html` (с HTMX)
   - `message_item_detailed.html` - для `conversation_detail.html` (с fetch API)
4. **Все изменения закоммичены и запушены** в GitHub
5. **Система готова к использованию**
