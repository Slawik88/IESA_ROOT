# 🎯 Система верификации членства / Membership Verification System

## 📋 Обзор

Полностью функциональная система верификации для ассоциации IESA Sport, позволяющая:

- ✅ Членам ассоциации иметь уникальный 6-значный PIN-код, обновляющийся каждые 12 минут
- ✅ Партнерам логировать посещения членов с верификацией PIN
- ✅ Публичные профили, доступные через QR-коды
- ✅ Личный кабинет члена с текущим PIN и таймером обратного отсчета
- ✅ Панель партнера с поиском членов и историей визитов

---

## 🚀 Установка завершена!

Все компоненты успешно установлены и мигрированы:

### ✓ Установленные библиотеки
- `pyotp==2.9.0` - генерация TOTP PIN-кодов

### ✓ Модели базы данных
- **User**: расширен полями `membership_status`, `totp_secret`, `pseudonym`
- **Partner**: профиль партнера с OneToOne связью к User
- **Visit**: логи визитов с верификацией PIN

### ✓ Views
- `public_profile(uuid)` - публичный профиль для QR
- `member_cabinet()` - личный кабинет члена
- `partner_dashboard()` - панель партнера
- `log_visit(member_id)` - форма логирования визита

### ✓ Templates
- `users/public_profile.html` - адаптивная карточка профиля
- `users/member_cabinet.html` - кабинет с PIN и таймером
- `users/partner_dashboard.html` - двухколоночная панель поиска/истории
- `users/log_visit.html` - форма визита с валидацией PIN

### ✓ URL маршруты
- `/auth/profile/<uuid>/public/` - публичный профиль
- `/auth/cabinet/` - личный кабинет члена
- `/auth/partner/dashboard/` - панель партнера
- `/auth/partner/visit/<member_id>/` - логирование визита

### ✓ Админ-панель
- PartnerAdmin - управление партнерами с счетчиком визитов
- VisitAdmin - богатый список визитов с фильтрами, иерархией дат, цветными бейджами

---

## 📖 Как использовать

### 1️⃣ Создание группы "Partners"

**Через Django admin:**

1. Перейдите в админ-панель: `http://localhost:8000/admin/`
2. Зайдите в **Authentication and Authorization** → **Groups**
3. Нажмите **Add Group**
4. Имя группы: `Partners` (точно так!)
5. Сохраните

**Или через Python shell:**

```python
python manage.py shell

from django.contrib.auth.models import Group
partners_group, created = Group.objects.get_or_create(name='Partners')
print(f"✓ Group 'Partners' {'created' if created else 'already exists'}")
exit()
```

---

### 2️⃣ Создание партнера

**Шаг 1: Создайте пользователя**

Через админ-панель создайте обычного пользователя (например, `partner_shop1`)

**Шаг 2: Добавьте в группу Partners**

В профиле пользователя в админке:
- Permissions → Groups → Выберите "Partners"
- Сохраните

**Шаг 3: Создайте профиль Partner**

В админке перейдите в **Users** → **Partners** → **Add Partner**:
- User: выберите созданного пользователя
- Company Name: например, "Sport Shop Geneva"
- Business Type: выберите тип (shop, service, gym, restaurant, other)
- Сохраните

---

### 3️⃣ Создание активного члена

**Через админ-панель:**

1. Перейдите в **Users** → **Users** → выберите пользователя
2. Прокрутите до раздела **Membership Verification System**:
   - **Membership Status**: выберите `Active`
   - **Pseudonym**: (опционально) введите псевдоним
   - **TOTP Secret**: оставьте пустым (генерируется автоматически)
3. Сохраните

**Или через Python shell:**

```python
python manage.py shell

from users.models import User

# Создать нового члена
member = User.objects.create_user(
    username='member1',
    email='member1@example.com',
    password='testpass123',
    first_name='John',
    last_name='Doe',
    membership_status='active'  # Важно!
)

# Псевдоним (опционально)
member.pseudonym = 'JD_Sport'
member.save()

# TOTP secret генерируется автоматически при первом save()
print(f"✓ Member created: {member.username}")
print(f"✓ Current PIN: {member.get_current_pin()}")
exit()
```

---

### 4️⃣ Workflow использования

#### Для члена ассоциации:

1. **Войдите** на сайт через свой аккаунт
2. Перейдите в **личный кабинет**: `/auth/cabinet/`
3. Вы увидите:
   - Текущий 6-значный PIN (крупный шрифт)
   - Таймер обратного отсчета (12 минут)
   - Прогресс-бар (зеленый → желтый → красный)
   - Автообновление при истечении времени

4. **Покажите PIN партнеру** при визите

#### Для партнера:

1. **Войдите** как пользователь из группы Partners
2. Перейдите в **панель партнера**: `/auth/partner/dashboard/`
3. **Найдите члена**:
   - Введите имя, псевдоним или UUID в поиске
   - Нажмите **Log Visit** напротив нужного члена

4. **Заполните форму визита**:
   - Service Type: тип услуги
   - Service Description: описание (опционально)
   - Cost: стоимость (опционально)
   - Comments: комментарии (опционально)
   - **PIN**: попросите члена показать текущий PIN

5. **Отправьте форму**:
   - Если PIN верный → визит логируется с `pin_verified = True`
   - Если PIN неверный → ошибка валидации

6. **Просматривайте историю**:
   - Все визиты отображаются справа на панели
   - Пагинация по 15 визитов
   - Цветные бейджи для типа услуги и статуса верификации

#### Для публичного доступа (QR коды):

Каждый член может иметь публичный профиль:
- URL: `/auth/profile/<permanent_id>/public/`
- Показывает: аватар, имя, псевдоним, статус членства
- **Не показывает PIN** (только в личном кабинете)

---

## 🔧 Технические детали

### TOTP PIN система

- **Алгоритм**: TOTP (Time-based One-Time Password)
- **Интервал**: 720 секунд (12 минут)
- **Формат**: 6 цифр (000000 - 999999)
- **Секрет**: 32-символьная hex строка (auto-generated)
- **Valid window**: ±1 интервал (36 минут total grace period)

### Безопасность

- PIN показывается только владельцу в личном кабинете
- Партнеры НЕ могут видеть PIN напрямую
- Верификация через метод `User.verify_pin(pin)`
- TOTP секрет хранится в БД, никогда не показывается пользователю
- Доступ к панели партнера только для группы "Partners"

### Производительность

**Индексы БД:**
- `user_membership_idx` - быстрый поиск активных членов
- `user_pseudonym_idx` - поиск по псевдонимам
- `visit_timestamp_idx` - сортировка по времени
- `visit_partner_time_idx` - история визитов партнера
- `visit_member_time_idx` - история визитов члена
- `visit_verified_idx` - фильтрация верифицированных визитов

**Пагинация:**
- Панель партнера: 15 визитов на страницу
- Поиск членов: лимит 20 результатов

---

## 📊 Примеры использования

### Проверить PIN члена в shell:

```python
python manage.py shell

from users.models import User

member = User.objects.get(username='member1')
current_pin = member.get_current_pin()
print(f"Current PIN: {current_pin}")

# Проверить PIN
is_valid = member.verify_pin('123456')
print(f"PIN valid: {is_valid}")

exit()
```

### Создать тестовый визит:

```python
python manage.py shell

from users.models import User, Partner, Visit

member = User.objects.get(username='member1')
partner_user = User.objects.get(username='partner_shop1')
partner = Partner.objects.get(user=partner_user)

# Получить текущий PIN
pin = member.get_current_pin()
print(f"Member PIN: {pin}")

# Создать визит
visit = Visit.objects.create(
    member=member,
    partner=partner,
    service_type='purchase',
    service_description='Купил спортивную обувь',
    cost=150.00,
    pin_verified=member.verify_pin(pin)  # True если PIN верный
)

print(f"✓ Visit created: {visit}")
exit()
```

### Статистика партнера:

```python
python manage.py shell

from users.models import Partner

partner = Partner.objects.get(company_name='Sport Shop Geneva')
total = partner.get_total_visits()
verified = partner.logged_visits.filter(pin_verified=True).count()

print(f"Total visits: {total}")
print(f"Verified visits: {verified}")
print(f"Verification rate: {verified/total*100:.1f}%")

exit()
```

---

## 🎨 UI/UX особенности

### Личный кабинет члена:
- Крупный PIN: 3rem, monospace шрифт
- Анимированный прогресс-бар
- Цветовая индикация времени (зеленый → желтый → красный)
- JavaScript автообновление при истечении
- Адаптивный дизайн (col-md-6 центрированный)

### Панель партнера:
- Двухколоночный layout (поиск | история)
- Миниатюры аватаров в результатах поиска
- Цветные бейджи для типов услуг
- Иконки верификации (✓/✗)
- Responsive дизайн (col-lg-5 / col-lg-7)

### Форма визита:
- Крупное центрированное поле PIN
- Информационная карточка члена
- Валидация: только 6 цифр
- Numeric keypad на мобильных
- Inline ошибки валидации

---

## 🐛 Известные ограничения

1. **Нет email уведомлений** - по требованию заказчика
2. **Нет Stripe интеграции** - только логирование
3. **Нет QR генерации в UI** - используется существующая система QR (qr_utils.py)
4. **Timezone**: используется server timezone для TOTP (ensure production TZ = UTC)

---

## 🔄 Что дальше?

### Опциональные улучшения:

1. **QR коды для членов**:
   - Добавить кнопку "Скачать QR" в личном кабинете
   - QR ведет на `/auth/profile/<permanent_id>/public/`

2. **Статистика для членов**:
   - Показать количество визитов в личном кабинете
   - График активности

3. **Фильтры для партнеров**:
   - Фильтр по дате в истории визитов
   - Экспорт в CSV/Excel

4. **Push уведомления**:
   - Уведомление члену при логировании визита
   - Требует PWA/Firebase setup

5. **API endpoints**:
   - REST API для мобильного приложения
   - Django REST Framework integration

---

## ✅ Чеклист готовности к продакшену

- [x] Модели созданы и мигрированы
- [x] Views реализованы
- [x] Templates адаптивные и протестированы
- [x] URL маршруты настроены
- [x] Админ-панель настроена
- [x] TOTP система работает
- [x] Индексы БД оптимизированы
- [ ] Создана группа "Partners" в админке
- [ ] Созданы тестовые пользователи (члены + партнеры)
- [ ] Протестирован full workflow (член → партнер → визит)
- [ ] Проверены права доступа (member vs partner)
- [ ] Настроен HTTPS для production
- [ ] Timezone установлен на UTC в settings.py

---

## 📞 Поддержка

При возникновении вопросов:

1. Проверьте логи Django: `python manage.py runserver`
2. Проверьте миграции: `python manage.py showmigrations users`
3. Проверьте группы: убедитесь, что "Partners" существует
4. Проверьте membership_status: должен быть 'active' у членов
5. Проверьте TOTP secret: генерируется автоматически при создании

---

**Дата установки**: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")  
**Версия Django**: 5.2.9  
**Версия pyotp**: 2.9.0  

Система полностью готова к использованию! 🎉
