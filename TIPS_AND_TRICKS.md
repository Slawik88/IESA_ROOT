# 💡 СОВЕТЫ И ТРЮКИ - IESA_ROOT

**Версия:** 1.0 | **Дата:** 28 декабря 2025 | **Назначение:** Полезные советы и хаки

---

## ⚡ БЫСТРЫЕ ХАКИ

### 1. Запуск на видимом IP (для мобильного)

```powershell
# Вместо localhost, будет доступно с других устройств
python manage.py runserver 0.0.0.0:8000

# Затем найдите IP:
ipconfig

# Открыть с другого устройства:
# http://192.168.X.X:8000
```

### 2. Запуск без просмотра логов

```powershell
# Очистить консоль при старте
cls; python manage.py runserver
```

### 3. Перезапустить сервер одной командой

```powershell
# Ctrl+C, потом вверх стрелка, Enter
# или создайте .ps1 файл:

Write-Host "Restarting server..."
Start-Sleep -Seconds 1
python manage.py runserver
```

---

## 🐛 ДЕБАГ СОВЕТЫ

### 1. Просмотр SQL запросов

```python
# В views.py добавьте:
from django.db import connection
from django.db import reset_queries

def my_view(request):
    reset_queries()
    # Ваш код
    for query in connection.queries:
        print(query['sql'])
        print(f"Time: {query['time']}ms")
```

### 2. Вывод переменных в шаблон

```html
<!-- В templates -->
DEBUG:
{{ my_variable }}
<pre>{{ my_variable|pprint }}</pre>
```

### 3. Логирование в файл

```python
# В views.py
import logging
logger = logging.getLogger(__name__)

logger.debug("Это дебаг сообщение")
logger.error("Это ошибка")

# Смотрите в logs/ папке
```

### 4. Точки останова (Breakpoints)

```python
# В views.py
import pdb

def my_view(request):
    pdb.set_trace()  # Точка останова
    # Консоль остановится здесь
```

---

## 🎨 CSS ТРЮКИ

### 1. Быстро добавить градиент

```css
/* Скопируйте в style.css */
.my-gradient {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
```

### 2. Быстро добавить тень

```css
/* Скопируйте в style.css */
.my-shadow {
    box-shadow: 0 12px 28px rgba(13, 110, 253, 0.15);
}
```

### 3. Быстро добавить анимацию

```css
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

.my-animate {
    animation: fadeIn 0.5s ease-in;
}
```

### 4. Отладка CSS (покажи все элементы)

```css
/* Временно добавьте в style.css для видимости всех границ */
* {
    border: 1px solid red !important;
}
```

---

## 🌐 HTMX ТРЮКИ

### 1. Простой AJAX запрос

```html
<!-- Загрузить контент на кнопку -->
<button hx-get="/api/data/" hx-target="#result">
    Загрузить
</button>
<div id="result"></div>
```

### 2. Автоматическое обновление

```html
<!-- Обновлять каждые 5 секунд -->
<div hx-get="/api/time/" hx-trigger="every 5s">
    Текущее время будет здесь
</div>
```

### 3. Показать загрузку

```html
<!-- Показать "Loading..." пока идет запрос -->
<button hx-get="/api/slow/" 
        hx-indicator="#loading">
    Долгий запрос
</button>
<img id="loading" class="htmx-indicator" src="/spinner.gif">
```

---

## 📱 АДАПТИВНЫЙ ДИЗАЙН

### 1. Проверить на мобильном (DevTools)

```
F12 → Ctrl+Shift+M
или просто F12 → Device Toolbar
```

### 2. Быстро добавить отзывчивость

```css
/* Bootstrap классы (уже в проекте) */
.col-12           /* 1 столбец на мобильном */
.col-md-6         /* 2 столбца на планшете */
.col-lg-4         /* 3 столбца на ПК */

/* В HTML: -->
<div class="row">
    <div class="col-12 col-md-6 col-lg-4">
        Адаптивно!
    </div>
</div>
```

### 3. Скрывать элементы на мобильном

```css
/* Скрыть на мобильном */
@media (max-width: 768px) {
    .desktop-only {
        display: none;
    }
}
```

---

## 🔍 ПОИСК ОШИБОК

### 1. Проверка 404 ошибок

```powershell
# В консоли браузера смотрите Network tab
# Клик по запросу → Response

# Или в Django логах
# Server должен показать: "GET /url/ 404"
```

### 2. CSRF ошибка

```html
<!-- Убедитесь что в форме есть: -->
{% csrf_token %}
```

### 3. Шаблон не обновляется

```powershell
# Очистить кэш браузера:
Ctrl + Shift + Delete

# Или:
Ctrl + F5 (жесткая перезагрузка)
```

---

## 📊 ОПТИМИЗАЦИЯ БД

### 1. Смотреть кол-во запросов

```python
# В views.py добавьте:
from django.template.defaulttags import register

def my_view(request):
    from django.db import connection
    import time
    
    start = time.time()
    # Ваш код
    end = time.time()
    
    print(f"Запросов: {len(connection.queries)}")
    print(f"Время: {end - start}s")
```

### 2. Использовать select_related

```python
# ❌ ПЛОХО: N+1 запросов
posts = Post.objects.all()
for post in posts:
    print(post.author.username)  # +1 запрос на каждый пост

# ✅ ХОРОШО: 1+1 запросов
posts = Post.objects.select_related('author')
for post in posts:
    print(post.author.username)  # Уже загружено
```

### 3. Использовать prefetch_related

```python
# ✅ ХОРОШО для many-to-many
posts = Post.objects.prefetch_related('comments')
```

### 4. Кэширование результатов

```python
from django.views.decorators.cache import cache_page

@cache_page(60 * 15)  # Кэш на 15 минут
def my_view(request):
    # Результат будет кэширован
    posts = Post.objects.all()
    return render(request, 'template.html', {'posts': posts})
```

---

## 🔐 БЕЗОПАСНОСТЬ

### 1. Никогда не выкладывайте это

```python
# НИКОГДА в settings.py:
SECRET_KEY = "ваш-ключ"  # ❌ Никогда!
DEBUG = True              # ❌ Никогда в продакшене!
ALLOWED_HOSTS = []        # ❌ Добавьте вашу доменов!
```

### 2. Используйте .env файл

```python
# settings.py
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG') == 'True'
```

### 3. SQL Injection защита (через ORM)

```python
# ✅ ХОРОШО
users = User.objects.filter(username=username)

# ❌ ПЛОХО (НИКОГДА!)
User.objects.raw(f"SELECT * FROM users WHERE username='{username}'")
```

### 4. XSS защита (автоматическая в Django)

```html
<!-- Автоматически экранирует вредоносный HTML -->
{{ user_input }}  <!-- Безопасно! -->

<!-- Если НУЖНО HTML (редко): -->
{{ user_input|safe }}  <!-- ⚠️ Только для доверенного контента! -->
```

---

## 🎯 ФУНКЦИОНАЛЬНОСТЬ

### 1. Добавить новое поле в модель

```python
# 1. Модель (users/models.py)
class User(models.Model):
    new_field = models.CharField(max_length=100)

# 2. Миграция
python manage.py makemigrations

# 3. Применить
python manage.py migrate

# 4. Шаблон (profile.html)
{{ user.new_field }}

# 5. Форма (forms.py)
class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['new_field']
```

### 2. Добавить новый URL

```python
# urls.py
urlpatterns = [
    path('new-page/', views.new_page, name='new_page'),
]

# views.py
def new_page(request):
    return render(request, 'new_page.html')

# templates/new_page.html
{% extends 'base.html' %}
{% block content %}
    <h1>Новая страница</h1>
{% endblock %}
```

### 3. Добавить валидацию

```python
# models.py
from django.core.validators import MinValueValidator

class Product(models.Model):
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )

# forms.py
class ProductForm(forms.ModelForm):
    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price < 0:
            raise forms.ValidationError("Цена не может быть отрицательной")
        return price
```

---

## 📝 ТЕСТИРОВАНИЕ

### 1. Простой тест

```python
# tests.py
from django.test import TestCase

class UserTestCase(TestCase):
    def setUp(self):
        User.objects.create_user(username="test", password="pass")
    
    def test_user_created(self):
        user = User.objects.get(username="test")
        self.assertEqual(user.username, "test")

# Запуск:
python manage.py test
```

### 2. Тест API

```python
from django.test import Client

class ViewTestCase(TestCase):
    def test_home_page(self):
        client = Client()
        response = client.get('/')
        self.assertEqual(response.status_code, 200)
```

---

## 🚀 ДЕПЛОЙ

### 1. Перед деплоем чеклист

```python
# settings.py
DEBUG = False                              # ✅
ALLOWED_HOSTS = ['yourdomain.com']        # ✅
SECRET_KEY = os.getenv('SECRET_KEY')      # ✅ Из .env
SECURE_SSL_REDIRECT = True                # ✅
SESSION_COOKIE_SECURE = True              # ✅
CSRF_COOKIE_SECURE = True                 # ✅
```

### 2. Собрать статические файлы

```powershell
python manage.py collectstatic --noinput
# Соберет все CSS, JS, IMG в папку static/
```

### 3. Создать requirements.txt

```powershell
pip freeze > requirements.txt
```

---

## 💻 КОМАНДЫ КОТОРЫЕ СПАСАЮТ

### Очистить все кэши

```powershell
python manage.py clear_cache
```

### Создать резервную копию БД

```powershell
# Windows
copy IESA_ROOT\db.sqlite3 IESA_ROOT\db_backup_$(Get-Date -Format 'yyyy-MM-dd').sqlite3

# Linux/Mac
cp IESA_ROOT/db.sqlite3 IESA_ROOT/db_backup_$(date +%Y-%m-%d).sqlite3
```

### Восстановить БД из резервной копии

```powershell
# Остановить сервер (Ctrl+C)
copy IESA_ROOT\db_backup_2025-12-28.sqlite3 IESA_ROOT\db.sqlite3
# Запустить сервер
```

### Сбросить пароль (забыли)

```powershell
python manage.py changepassword root
# Введите новый пароль
```

### Показать все пользователей

```powershell
python manage.py shell
>>> from django.contrib.auth.models import User
>>> User.objects.all()
```

---

## 🎨 ДИЗАЙН ШПАРГАЛКА

### Bootstrap классы что помнить

```html
<!-- Контейнер -->
<div class="container">
    <!-- Строка (максимум 12 столбцов) -->
    <div class="row">
        <!-- Адаптивные столбцы -->
        <div class="col-12 col-md-6 col-lg-4">
            Контент
        </div>
    </div>
</div>

<!-- Цвета -->
<div class="bg-primary">Синий</div>
<div class="bg-success">Зеленый</div>
<div class="bg-danger">Красный</div>

<!-- Padding -->
<div class="p-3">Padding все стороны</div>
<div class="pt-3">Padding сверху</div>

<!-- Margin -->
<div class="m-3">Margin все стороны</div>
<div class="mt-3">Margin сверху</div>

<!-- Кнопки -->
<button class="btn btn-primary">Основная</button>
<button class="btn btn-secondary">Вторичная</button>

<!-- Карточки -->
<div class="card">
    <div class="card-body">
        <h5 class="card-title">Заголовок</h5>
        <p class="card-text">Текст</p>
    </div>
</div>
```

---

## 🔗 ПОЛЕЗНЫЕ ССЫЛКИ

```
Django Docs: https://docs.djangoproject.com/en/5.2/
Bootstrap: https://getbootstrap.com/docs/5.3/
HTMX: https://htmx.org/docs/
Python: https://www.python.org/doc/
SQLite: https://www.sqlite.org/docs.html
```

---

## 🎯 ПРОИЗВОДИТЕЛЬНОСТЬ

### 1. Профилирование (что медленно?)

```python
# В views.py
import cProfile
import pstats
from io import StringIO

pr = cProfile.Profile()
pr.enable()

# Ваш код

pr.disable()
s = StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
ps.print_stats()
print(s.getvalue())
```

### 2. Сжимать изображения

```python
# requirements.txt добавьте: Pillow
from PIL import Image

def compress_image(image_field):
    img = Image.open(image_field)
    img.thumbnail((800, 800))
    img.save(image_field.path, quality=85)
```

---

## 🎓 ОБУЧЕНИЕ

### Чему учиться дальше?

```
✅ Если новичок в Django:
   → Django Documentation
   → Real Python Django Tutorials
   → CodeAcademy Django Course

✅ Если новичок в веб-разработке:
   → HTML/CSS basics
   → JavaScript basics
   → REST API concepts

✅ Если хочется углубиться:
   → Django REST Framework
   → Celery (async tasks)
   → Redis (caching)
   → Docker (containerization)
```

---

## 🎉 ФИНАЛЬНЫЕ СОВЕТЫ

1. **Читайте ошибки** - они часто помогают
2. **Google ошибку** - кто-то уже решал это
3. **Используйте IDE** - VS Code + Python Extension
4. **Комментируйте код** - себе благодарны будете
5. **Тестируйте на мобильном** - адаптивность важна
6. **Делайте резервные копии** - БД можно потерять
7. **Читайте документацию** - она для этого
8. **Практикуйте** - лучший способ учиться

---

**Версия:** 1.0 | **Дата:** 28 декабря 2025 | **Статус:** ✅ Полезные советы
