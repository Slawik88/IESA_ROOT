# IESA i18n Audit — Непереведённые строки

> **Дата аудита:** 27 февраля 2026  
> **Всего файлов с проблемами:** ~32  
> **Всего непереведённых строк:** ~300+  

---

## 🔴 ПРИОРИТЕТ 1 — Видимый UI (пользователь видит на сайте)

### 1. `users/views_verification.py` — ~30 строк
Все `messages.success/error/warning()` — чистые строки без `_()`:
- `'⚠️ System error: Database migration required. Contact administrator.'`
- `'Your membership is inactive. Contact administrator...'`
- `'⚠️ TOTP secret not configured. Contact administrator.'`
- `'PIN system not initialized...'`, `'⚠️ Unable to generate PIN...'`
- `'⚠️ Partner profile not configured...'`
- `'Partner profile not found.'`
- `'⚠️ Warning: ... membership is currently inactive.'`
- `'🔒 PIN entry locked for this member...'`
- `'⚠️ Member PIN system not configured...'`
- `'ℹ️ Duplicate detected: identical visit already logged...'`
- `'✅ Visit logged! Member: ...'`
- `'🔒 Too many wrong PINs. PIN locked for ... minutes.'`
- `'❌ Invalid PIN. ... attempt(s) remaining before lockout.'`
- `'⏰ Edit window expired...'`, `'❌ Cancelled visits cannot be edited.'`
- `'✅ Visit updated. Member notified via Telegram.'`
- `'⏰ Edit window expired...'` (cancel), `'This visit is already cancelled.'`
- `'✅ Visit cancelled. Member notified via Telegram.'`
- `"Доступ только для администраторов."` (hardcoded Russian)
- `"Код должен состоять из 6 цифр."` (hardcoded Russian)
- `"Код недействителен или истёк..."` (hardcoded Russian)
- `"Этот Telegram уже привязан..."` (hardcoded Russian)
- `"✅ Telegram успешно привязан!"` (hardcoded Russian)
- `"Telegram отвязан от вашего аккаунта."` (hardcoded Russian)
- `"Проверка подписи Telegram не пройдена."` (hardcoded Russian)
- `"Запрос Telegram устарел..."` (hardcoded Russian)
- `"Не удалось получить ID от Telegram."` (hardcoded Russian)

### 2. `users/views.py` — 4 строки
- `'Профиль успешно обновлён! ✨'` (hardcoded Russian)
- `'❌ Please enter your password to confirm account deactivation.'`
- `'❌ Incorrect password. Account deactivation cancelled.'`
- `'✅ Your account has been deactivated...'`

### 3. `blog/views/posts.py` — 1 строка
- `'Ваш пост успешно отправлен на модерацию! 🎉'` (hardcoded Russian)

### 4. `blog/views/comments.py` — 2 строки
- `'Method Not Allowed. Use POST.'`
- `'Forbidden'`

### 5. `notifications/utils.py` — 12 строк (все уведомления)
- `'Post Approved! 🎉'` / `'Your post "..." has been approved...'`
- `'Post Needs Review'` / `'Your post "..." was not approved...'`
- `'New Comment'` / `'{username} commented on your post...'`
- `'New Reply'` / `'{username} replied to your comment'`
- `'New Like ❤️'` / `'{username} liked your post...'`
- `'Event Reminder 📅'` / `'Reminder: "..." is coming up...'`

### 6. `notifications/views.py` — 1 строка
- `'All notifications marked as read'` (HTMX response)

### 7. `core/mixins.py` — 5 строк (toast titles)
- `'Успешно'`, `'Ошибка'`, `'Внимание'`, `'Информация'`, `'Уведомление'` (hardcoded Russian)

---

## 🟠 ПРИОРИТЕТ 2 — Формы (labels, placeholders, help_text, errors)

### 8. `users/forms.py` — ~12 строк
- `'Дата рождения'` (label, 2 раза — hardcoded Russian)
- `'GitHub профиль'`, `'Discord'`, `'Telegram'`, `'Веб-сайт'`, `'Другие ссылки'` (labels)
- `'Введите полную ссылку на ваш GitHub профиль'`, `'Введите ваше имя в Discord'` и т.д. (help_text)
- `'Search by name, pseudonym, or UUID...'` (placeholder)

### 9. `users/forms_verification.py` — ~15 строк
- `'🔍 Start typing name, username, or UUID...'` (placeholder)
- `'🔑 Member PIN Code (6 digits)'` (label)
- `'⚠️ Ask member to show their current PIN...'` (help_text)
- `'📋 Service Type *'`, `'📝 Service Description (Optional)'` и т.д. (labels)
- `'❌ PIN must be exactly 6 digits...'`, `'❌ Cost cannot be negative'` (ValidationError)
- `'📝 Reason for Edit *'`, `'📝 Reason for Cancellation *'` (labels)
- Все `placeholder` attrs: `'Example: Massage therapy...'`, `'Enter amount...'` и т.д.

### 10. `blog/forms.py` — 1 строка
- `'Напишите комментарий...'` (placeholder, hardcoded Russian)

---

## 🟡 ПРИОРИТЕТ 3 — Модели (verbose_name, choices, Meta)

### 11. `users/models.py` — ~25 строк
**User model:**
- verbose_name: `'Avatar'`, `'Date of Birth'`, `'Phone Number'`, `'Hide Phone Number'`, `'Last Online'`, `'Verified User'`, `'GitHub'`, `'Discord'`, `'Telegram'`, `'Website'`, `'Other links'`, `'Total Posts Published'`, `'Total Likes Received'`, `'Total Comments Made'`, `'Activity Points'`
- help_text: `'If checked, only admins can see your phone number'`, `'Base32-encoded secret...'`, `'Linked Telegram chat id...'`
- choices: `'Active'`, `'Inactive'` (membership_status)
- Meta: `'User'` / `'Users'`

**Partner model:**
- choices: `'Shop/Retail'`, `'Service Provider'`, `'Gym/Fitness'`, `'Restaurant/Cafe'`, `'Other'`

**Visit model:**
- choices: `'Purchase'`, `'Consultation'`, `'Training Session'`, `'Event Attendance'`, `'Other'`

### 12. `blog/models.py` — ~60 строк
**Post:** choices `'Черновик'`, `'На модерации'`, `'Опубликован'`, `'Отклонен'` (hardcoded Russian) + verbose_name `'Заголовок'`, `'Текст поста'`, `'Автор'` и т.д. (hardcoded Russian)
**Comment:** `'Post'`, `'Author'`, `'Comment text'`, `'Creation date'`, `'Parent comment'`
**CommentLike:** `'Comment'`, `'User'`
**Like:** `'Post'`, `'User'`
**PostView:** `'Post'`, `'User'`, `'IP Address'`, `'View date'`
**Event:** `'Upcoming'`, `'Ongoing'`, `'Completed'`, `'Cancelled'` + все verbose_name
**EventRegistration:** `'Pending'`, `'Confirmed'`, `'Cancelled'`, `'Attended'` + verbose_name
**BlogSubscription:** `'Subscriber'`, `'Author'`, `'Subscription date'`

### 13. `core/models.py` — ~80 строк
**President:** `'Full Name'`, `'Photo'`, `'Position'`, `'Bio/Message'` + `'Only one President can exist...'` (ValueError)
**Partner:** choices + verbose_name ~10 строк
**AssociationMember:** ~5 строк
**SocialNetwork:** все SOCIAL_CHOICES (~19 вариантов) + verbose_name
**CoreProduct:** ВСЕ verbose_name и help_text на русском (~15 строк hardcoded Russian)
**MemberBenefit:** ВСЕ verbose_name и help_text на русском (~20 строк hardcoded Russian) + choices (~8 вариантов)

### 14. `gallery/models.py` — 3 строки
- `'Photo'`, `'Caption'`, `'Uploaded At'`

### 15. `products/models.py` — 4 строки
- `'Product Name'`, `'Description'`, `'Price'`, `'Product Image'`

### 16. `notifications/models.py` — ~15 строк
- choices: `'Post Approved'`, `'Post Rejected'`, `'New Comment'`, `'Comment Reply'`, `'New Like'`, `'New Follower'`, `'Event Reminder'`, `'New Message'`, `'System Notification'`
- verbose_name: `'Recipient'`, `'Sender'`, `'Type'`, `'Title'`, `'Message'`, `'Link'`, `'Read'`, `'Created at'`, `'Read at'`

---

## 🔵 ПРИОРИТЕТ 4 — Админка

### 17. `users/admin.py` — ~20 строк
- Filter titles: `'Card Status'`, `'Verification Status'`
- Filter lookups: `'Card Active'`, `'Card Inactive'`, `'Never Issued'`, `'Verified'`, `'Unverified'`
- Fieldset titles (mixed): `'Персональная информация'`, `'Membership'`, `'Card QR & Actions'`, `'Разрешения'`, `'Важные даты'`, `'Card'`, `'Basic Information'`, `'Metadata'`, `'Visit Information'`, `'Service Details'`, `'Verification'`
- Action messages & descriptions (all Russian): `'✅ Перегенерирован QR код...'`, `'🔄 Перегенерировать QR код...'`, `'🆕 Новый permanent_id...'`, `'✓ Выдать карту...'`, `'✗ Отозвать карту...'` и т.д.

### 18. `blog/admin.py` — ~10 строк
- Action descriptions: `'✅ Publish selected posts'`, `'❌ Reject selected posts'`, `'📝 Move to draft'`
- Action messages: `'{count} post(s) published successfully.'` и т.д.
- Fieldset titles: `'Post Information'`, `'Publishing'`, `'Statistics'`, `'Event Information'`, `'Date & Time'`, `'Location & Capacity'`, `'System'`
- `'Not published'` (preview_link)

### 19. `core/admin.py` — ~10 строк
- Form labels: `'Описание'` (×3), `'Особенности'`, `'Условия'` (hardcoded Russian)
- Fieldset titles: `'Основная информация'`, `'Детали программы'`, `'Настройки отображения'`, `'Служебная информация'`, `'Дизайн'`, `'Дополнительно'`

### 20. `core/admin_site.py` — 3 строки
- `"IESA Administration"`, `"IESA Admin"`, `"Welcome to IESA Admin Panel"`

### 21. `notifications/admin.py` — 2 строки
- Fieldset titles: `'Notification Info'`, `'Status'`

---

## 🟣 ПРИОРИТЕТ 5 — Email и Telegram уведомления

### 22. `users/email_service.py` — ~15 строк
- Subjects: `'✅ Visit confirmed at ...'`, `'📝 Visit record updated...'`, `'❌ Visit cancelled...'`, `'✅ IESA Sport — Test Email'`
- Bodies: все HTML строки (`'Visit Confirmed'`, `'Hello, ...'`, `'Previous values:'`, `'New values:'`, `'Reason for edit:'`, `'Reason for cancellation:'`, `'This is a test email...'`)

### 23. `users/telegram/notify.py` — ~4 блока (hardcoded Russian)
- `'✅ Визит подтверждён'` + детали
- `'📝 Визит изменён'` + детали
- `'❌ Визит отменён'` + детали
- `'🎉 Членство активировано!'` + детали

### 24. `users/telegram/handlers.py` — ~20 строк (all hardcoded Russian)
- Все сообщения бота: `'С возвращением, ...'`, `'Привет! Это бот IESA Sport.'`
- Все кнопки: `'Мой статус'`, `'Помощь'`, `'Личный кабинет'`, `'Отвязать Telegram'`, `'Привязать аккаунт'`
- Help text, link code messages, status messages, unlink messages

---

## ⚪ ПРИОРИТЕТ 6 — Прочее

### 25. `users/constants.py` — activity levels (~5 блоков)
- Названия уровней: `'Beginner'`, `'Intermediate'`, `'Advanced'`, `'Expert'`, `'Legend'`
- Все `description` и `tips` массивы

### 26. `IESA_ROOT/protected_media_views.py` — 1 строка
- `"You don't have permission to access this file"`

---

## 🔧 ШАБЛОНЫ (Templates)

### 27. `core/templates/core/index.html` — 3 строки
- `'IESA — Extreme Sports Association'` (page title)
- JS sport words array: `'Kitesurfing','Diving','Climbing',...`
- `'CHF 4,500 / 10,000'` (donation goal)

### 28. `blog/templates/blog/post_create.html` — 4 строки
- `'Post preview'` (modal title)
- `'Close'` (modal button)
- JS fallbacks: `'Please enter a post title'`, `'Please enter post content'`

### 29. `templates/base.html` — ⚠️ БАГИ
- **BROKEN TAG:** `aria-label="{% trans "Open search menu" "}"` — "}" вместо %}

### 30. `templates/blog/htmx/post_search_results.html` — 1 строка
- `title="Verified"` (icon title attr)

### 31. `users/templates/users/profile_edit.html` — 1 строка
- `alt="Current avatar"`

### 32. `users/templates/users/profile_public.html` — ~5 строк
- `'pts'`, `'max'`, `alt="QR"`, brand names (`GitHub`, `Telegram`, `Discord`)

### 33. `users/templates/users/member_cabinet.html` — 1 строка
- `'Email:'` label

### 34. `users/templates/users/partner_dashboard.html` — ~6 строк
- JS button states: `'Sending…'`, `'✅ Sent!'`, `'Error'`, `'Network error'`, `'✉️ Test Email'`
- `'CHF'` (×2 occurrences, bare)

### 35. `users/templates/users/edit_visit.html` — 3 строки
- `'⏰ Edit window expired'`, `'CHF'`, `'N/A'`

### 36. `users/templates/users/cancel_visit.html` — 3 строки
- `'⏰ Cancellation window expired'`, `'CHF'`, `'N/A'`

### 37. Кросс-файловая проблема: `aria-label="Close"` — 7 мест
- `base.html` (×2), `event_detail.html`, `post_create.html`, `partners.html`, `register.html`, `login.html`

---

## 📊 Итого по приоритетам

| Приоритет | Файлов | Строк | Описание |
|-----------|--------|-------|----------|
| 🔴 1 | 7 | ~55 | Views messages, notifications, toasts |
| 🟠 2 | 3 | ~28 | Forms labels/placeholders/errors |
| 🟡 3 | 6 | ~190 | Models verbose_name/choices/Meta |
| 🔵 4 | 5 | ~45 | Admin fieldsets/actions/filters |
| 🟣 5 | 3 | ~40 | Email + Telegram messages |
| ⚪ 6 | 2 | ~15 | Constants + misc |
| 🔧 templ | 10 | ~30 | Templates |
| **ИТОГО** | **~32** | **~300+** | |
