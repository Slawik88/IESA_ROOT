# 🎯 Membership Verification System - Краткое руководство

## ✅ Система установлена и готова к работе!

### Что уже сделано:

1. ✅ Установлена библиотека `pyotp==2.9.0`
2. ✅ Созданы модели: User (расширенная), Partner, Visit
3. ✅ Применены миграции к базе данных
4. ✅ Созданы все views, forms, templates
5. ✅ Настроены URL маршруты
6. ✅ Настроена админ-панель
7. ✅ Создана группа "Partners"
8. ✅ Созданы тестовые пользователи
9. ✅ Обновлены TOTP секреты для всех пользователей

---

## 🧪 Быстрое тестирование

### 1. Запустите сервер

```bash
python manage.py runserver
```

### 2. Тестовые учетные данные

**Член ассоциации:**
- Username: `test_member`
- Password: `test123`
- Текущий PIN: смотрите в личном кабинете

**Партнер:**
- Username: `test_partner`
- Password: `test123`

**Суперпользователь (для админки):**
- Username: `root` (или ваш существующий)
- Password: ваш пароль

---

## 🔗 Страницы для тестирования

### Для члена ассоциации:

1. **Войдите** как `test_member`
2. **Личный кабинет**: http://localhost:8000/auth/cabinet/
   - Увидите текущий 6-значный PIN
   - Таймер обратного отсчета (12 минут)
   - Автообновление при истечении

3. **Публичный профиль**: http://localhost:8000/auth/profile/[UUID]/public/
   - Замените [UUID] на permanent_id пользователя
   - Это то, что видят при сканировании QR кода

### Для партнера:

1. **Войдите** как `test_partner`
2. **Панель партнера**: http://localhost:8000/auth/partner/dashboard/
   - Поиск членов (попробуйте "test")
   - Нажмите "Log Visit" напротив `test_member`
   
3. **Форма визита**: http://localhost:8000/auth/partner/visit/[ID]/
   - Заполните форму
   - Введите PIN из личного кабинета test_member
   - Отправьте форму

4. **Проверьте историю** на панели партнера
   - Справа увидите залогированный визит
   - Зеленый бейдж "✓ Verified" если PIN был верный

### Для администратора:

1. **Войдите** в админку: http://localhost:8000/admin/
2. **Users → Users** - управление пользователями
   - Измените `membership_status` на "Active" для тестирования
3. **Users → Partners** - управление партнерами
4. **Users → Visits** - просмотр всех визитов
   - Фильтры по типу услуги, статусу верификации, дате
   - Цветные бейджи для быстрого визуального поиска

---

## 🔄 Workflow тестирования

### Полный цикл:

1. **Откройте 2 браузера** (или режим инкогнито + обычный):
   - Browser 1: войдите как `test_member`
   - Browser 2: войдите как `test_partner`

2. **Browser 1** (член):
   - Перейдите в `/auth/cabinet/`
   - **Запомните текущий PIN** (например, 123456)
   - Оставьте страницу открытой - увидите таймер

3. **Browser 2** (партнер):
   - Перейдите в `/auth/partner/dashboard/`
   - В поиске введите "test"
   - Найдите `test_member`, нажмите "Log Visit"

4. **Заполните форму визита**:
   - Service Type: Purchase
   - Service Description: "Купил спортивную обувь"
   - Cost: 150.00
   - PIN: введите PIN из Browser 1
   - Submit

5. **Проверьте результат**:
   - Вас перенаправит на dashboard
   - Справа увидите новый визит с зеленым бейджем "✓ Verified"
   - Время, тип услуги, стоимость

6. **Тест неверного PIN**:
   - Повторите шаг 3-4, но введите неверный PIN (например, 000000)
   - Увидите ошибку: "PIN must be exactly 6 digits" или "Invalid PIN"

7. **Проверьте таймер**:
   - Вернитесь в Browser 1
   - Наблюдайте за обратным отсчетом
   - При истечении 12 минут PIN обновится автоматически
   - Страница перезагрузится

---

## 🎨 Что тестировать

### Функциональность:

- ✅ Генерация PIN (каждые 12 минут новый)
- ✅ Валидация PIN (верный/неверный)
- ✅ Поиск членов
- ✅ Логирование визитов
- ✅ История визитов
- ✅ Публичные профили
- ✅ Права доступа (только Partners могут логировать)

### UI/UX:

- ✅ Адаптивность (откройте на мобильном)
- ✅ Таймер и прогресс-бар
- ✅ Цветные бейджи
- ✅ Миниатюры аватаров
- ✅ Пагинация истории визитов

### Безопасность:

- ✅ Неавторизованный доступ (logout и попытка открыть /auth/cabinet/)
- ✅ Партнер не может видеть чужой PIN
- ✅ Обычный пользователь не может открыть /auth/partner/dashboard/
- ✅ Член может видеть только свой PIN

---

## 📊 Примеры данных

### Создать больше тестовых данных:

```bash
python manage.py shell
```

```python
from users.models import User, Partner, Visit
from django.contrib.auth.models import Group

# Создать члена
member = User.objects.create_user(
    username='anna_ski',
    password='test123',
    first_name='Anna',
    last_name='Ski',
    membership_status='active',
    pseudonym='SkiQueen'
)
print(f"PIN: {member.get_current_pin()}")

# Создать партнера
partner_user = User.objects.create_user(
    username='gym_partner',
    password='test123',
    first_name='Gym',
    last_name='Owner'
)
partner_user.groups.add(Group.objects.get(name='Partners'))
partner = Partner.objects.create(
    user=partner_user,
    company_name='Geneva Fitness Center',
    business_type='gym'
)

# Создать визит
visit = Visit.objects.create(
    member=member,
    partner=partner,
    service_type='training',
    service_description='Персональная тренировка 60 минут',
    cost=80.00,
    pin_verified=True
)
print(f"Visit created: {visit}")

exit()
```

---

## 🐛 Устранение неполадок

### Проблема: "User is not a partner"

**Решение:** Убедитесь, что пользователь:
1. Добавлен в группу "Partners" (админка → Users → выбрать пользователя → Groups)
2. Имеет профиль Partner (админка → Partners → создать для этого User)

### Проблема: "Invalid PIN"

**Причины:**
1. PIN истек (прошло больше 12 минут)
2. Член неактивен (membership_status != 'active')
3. Опечатка в PIN

**Решение:** Обновите страницу личного кабинета члена, скопируйте новый PIN

### Проблема: "Non-base32 digit found"

**Причина:** Старые пользователи с hex-секретами

**Решение:** Запустите:
```bash
python update_totp_secrets.py
```

### Проблема: Таймер не работает

**Причина:** JavaScript отключен или ошибка в консоли

**Решение:** 
1. Откройте DevTools (F12)
2. Проверьте Console на ошибки
3. Обновите страницу

---

## 📈 Следующие шаги

### Для продакшена:

1. **Создайте реальных партнеров**:
   - Через админку создайте пользователей для реальных бизнесов
   - Добавьте их в группу "Partners"
   - Создайте профили Partner с реальными названиями

2. **Активируйте членов**:
   - Установите `membership_status='active'` для платных членов
   - Добавьте псевдонимы (опционально)

3. **Настройте QR коды**:
   - Используйте существующую систему QR (qr_utils.py)
   - Печатайте карты с QR → `/auth/profile/<permanent_id>/public/`

4. **Безопасность**:
   - Включите HTTPS (обязательно для production!)
   - Настройте ALLOWED_HOSTS
   - Установите SESSION_COOKIE_SECURE = True

5. **Мониторинг**:
   - Регулярно проверяйте админку → Visits
   - Экспортируйте отчеты (добавьте CSV export при необходимости)

---

## 📞 Полезные команды

```bash
# Проверить систему
python manage.py check

# Создать суперпользователя
python manage.py createsuperuser

# Запустить setup
python setup_verification_system.py

# Обновить TOTP секреты
python update_totp_secrets.py

# Shell для тестов
python manage.py shell

# Миграции (если изменили модели)
python manage.py makemigrations
python manage.py migrate
```

---

## ✅ Чеклист для production

- [ ] Все тестовые аккаунты удалены или пароли изменены
- [ ] Созданы реальные партнеры
- [ ] Активированы члены с `membership_status='active'`
- [ ] HTTPS включен
- [ ] SESSION_COOKIE_SECURE = True
- [ ] ALLOWED_HOSTS настроен
- [ ] DEBUG = False
- [ ] Секретный ключ изменен
- [ ] База данных на production сервере
- [ ] Логи настроены
- [ ] Backup стратегия определена

---

**Готово к использованию!** 🎉

Подробная документация: `MEMBERSHIP_VERIFICATION_SYSTEM.md`
