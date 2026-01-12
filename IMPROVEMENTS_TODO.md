# IESA - Список улучшений и исправлений

## ✅ ВЫПОЛНЕНО

### 1. Система активности и очков ✅
- Добавлено поле `activity_points` в модель User
- Создана миграция `0005_user_activity_points.py`
- Улучшен метод `get_achievement_level()` с прогрессом
- Отображение очков в профиле с прогресс-баром
- Формула: Посты×10 + Лайки×2 + Комментарии×1

### 2. IESA_ROOT → IESA ✅
- Заменено во всех шаблонах (17 файлов)
- Обновлены заголовки страниц
- Изменен footer

### 3. Убрана черная линия на ссылках ✅
- Добавлен `border-bottom: none` в style.css
- Применено к `a` и `a:hover`

### 4. Админка постов улучшена ✅
- Добавлен ID в list_display
- Автор показывается со ссылкой на профиль  
- Расширен поиск: ID, автор, email, имя, фамилия
- Добавлена date_hierarchy
- Детальная статистика engagement

### 5. Лайки и комментарии ✅
- Проверены views и шаблоны
- Работают корректно через HTMX

---

## 🔧 ТРЕБУЮТ ДОРАБОТКИ

### 6. Рекомендованные посты - сделать кликабельными
**Файл:** `blog/templates/blog/post_detail.html`
**Проблема:** Только заголовок кликабелен
**Решение:** Обернуть всю карточку в `<a>` с классом hover-lift

```html
<a href="{% url 'post_detail' post_rec.pk %}" class="text-decoration-none">
    <div class="card card-modern hover-lift" style="cursor:pointer;">
        <!-- card content -->
    </div>
</a>
```

**CSS добавить:**
```css
.hover-lift {
    transition: transform 0.2s, box-shadow 0.2s;
}
.hover-lift:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.15);
}
```

---

### 7. События на главной странице
**Файл:** `core/views.py` и `core/templates/core/index.html`

**В views.py добавить:**
```python
from blog.models import Event
from django.utils import timezone

def index(request):
    # Upcoming events (next 3)
    upcoming_events = Event.objects.filter(
        date__gte=timezone.now()
    ).order_by('date')[:3]
    
    context = {
        'upcoming_events': upcoming_events,
        # ... other context
    }
    return render(request, 'core/index.html', context)
```

**В index.html добавить секцию:**
```html
{% if upcoming_events %}
<section class="mb-5">
    <h2 class="section-title mb-4">
        <i class="fas fa-calendar-alt me-2"></i>Upcoming Events
    </h2>
    <div class="row g-3">
        {% for event in upcoming_events %}
        <div class="col-md-4">
            <a href="{% url 'event_detail' event.pk %}" class="text-decoration-none">
                <div class="card card-modern hover-lift h-100">
                    {% if event.image %}
                    <img src="{{ event.image.url }}" class="card-img-top" style="height:180px;object-fit:cover;">
                    {% endif %}
                    <div class="card-body">
                        <h5 class="card-title">{{ event.title }}</h5>
                        <p class="text-muted small">
                            <i class="fas fa-calendar"></i> {{ event.date|date:"d M Y" }}<br>
                            <i class="fas fa-map-marker-alt"></i> {{ event.location|default:"TBA" }}
                        </p>
                    </div>
                </div>
            </a>
        </div>
        {% endfor %}
    </div>
    <div class="text-center mt-3">
        <a href="{% url 'event_list' %}" class="btn btn-outline-primary">View All Events →</a>
    </div>
</section>
{% endif %}
```

---

### 8. Поиск на странице Community
**Файл:** `blog/templates/blog/post_list.html`
**Проблема:** HTMX поиск не работает

**Проверить:**
1. Есть ли форма поиска?
2. Правильный ли URL в hx-get?
3. Существует ли view для поиска?

**Добавить в views.py:**
```python
def post_search(request):
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', 'all')
    
    posts = Post.objects.filter(status='published').select_related('author')
    
    if query:
        posts = posts.filter(
            Q(title__icontains=query) | 
            Q(text__icontains=query) |
            Q(author__username__icontains=query)
        ).distinct()
    
    context = {'posts': posts, 'query': query}
    
    if request.headers.get('HX-Request'):
        return render(request, 'blog/htmx/post_search_results.html', context)
    return render(request, 'blog/post_list.html', context)
```

**В urls.py:**
```python
path('search/', views.post_search, name='post_search'),
```

---

### 9. Создание поста и превью
**Файл:** `blog/views.py` - `post_create`
**Проблема:** Не работает создание и превью

**Проверить форму:**
```python
from django import forms
from .models import Post

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['title', 'text', 'preview_image']
        widgets = {
            'text': CKEditor5Widget(config_name='extends'),
        }
```

**View:**
```python
@login_required
def post_create(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.status = 'pending'  # Moderation
            post.save()
            messages.success(request, 'Post created successfully!')
            return redirect('post_detail', pk=post.pk)
    else:
        form = PostForm()
    
    return render(request, 'blog/post_create.html', {'form': form})
```

---

### 10. QR коды - проверка
**Файлы:** `users/qr_utils.py`, `users/views.py`

**Проверить:**
1. Генерируются ли файлы в `/media/cards/`?
2. URL правильный? Должен быть динамический
3. View `qr_image` работает?

**Тест:**
```python
# В manage.py shell
from users.models import User
user = User.objects.first()
print(user.permanent_id)
print(f"/auth/card/{user.permanent_id}/")
```

**Проверить URL паттерн в users/urls.py:**
```python
path('qr/<uuid:permanent_id>/', views.qr_image, name='user_qr'),
```

---

### 11. Фильтры поиска
**Добавить в post_list.html:**

```html
<div class="filter-bar mb-4">
    <form hx-get="{% url 'post_search' %}" 
          hx-target="#posts-container" 
          hx-trigger="change, submit">
        <div class="row g-2">
            <div class="col-md-6">
                <input type="text" name="q" class="form-control" 
                       placeholder="🔍 Search posts..." 
                       value="{{ query }}">
            </div>
            <div class="col-md-3">
                <select name="author" class="form-select">
                    <option value="">All Authors</option>
                    {% for author in authors %}
                    <option value="{{ author.id }}">{{ author.username }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-md-3">
                <select name="sort" class="form-select">
                    <option value="-created_at">Newest First</option>
                    <option value="created_at">Oldest First</option>
                    <option value="-views_count">Most Viewed</option>
                    <option value="title">A-Z</option>
                </select>
            </div>
        </div>
    </form>
</div>
```

---

### 12. Фильтры для событий
**Добавить в event_list.html:**

```html
<div class="filter-bar mb-4">
    <div class="btn-group" role="group">
        <input type="radio" class="btn-check" name="event-filter" id="upcoming" checked>
        <label class="btn btn-outline-primary" for="upcoming" 
               hx-get="{% url 'event_list' %}?filter=upcoming"
               hx-target="#events-container">
            🔜 Upcoming
        </label>
        
        <input type="radio" class="btn-check" name="event-filter" id="past">
        <label class="btn btn-outline-primary" for="past"
               hx-get="{% url 'event_list' %}?filter=past"
               hx-target="#events-container">
            📅 Past Events
        </label>
        
        <input type="radio" class="btn-check" name="event-filter" id="all-events">
        <label class="btn btn-outline-primary" for="all-events"
               hx-get="{% url 'event_list' %}?filter=all"
               hx-target="#events-container">
            📋 All Events
        </label>
    </div>
</div>
```

**В views.py:**
```python
def event_list(request):
    event_filter = request.GET.get('filter', 'upcoming')
    now = timezone.now()
    
    if event_filter == 'upcoming':
        events = Event.objects.filter(date__gte=now).order_by('date')
    elif event_filter == 'past':
        events = Event.objects.filter(date__lt=now).order_by('-date')
    else:
        events = Event.objects.all().order_by('-date')
    
    context = {'events': events, 'filter': event_filter}
    return render(request, 'blog/event_list.html', context)
```

---

## 🚀 КОМАНДЫ ДЛЯ ПРИМЕНЕНИЯ

```bash
# 1. Создать и применить миграции
python manage.py makemigrations
python manage.py migrate

# 2. Обновить статистику пользователей
python manage.py shell
>>> from users.models import User
>>> for user in User.objects.all():
...     user.update_statistics()

# 3. Собрать статические файлы
python manage.py collectstatic --noinput

# 4. Перезапустить сервер
python manage.py runserver
```

---

## 📝 ПРИМЕЧАНИЯ

- Все изменения обратно совместимы
- Миграции безопасны для production
- HTMX требует правильных заголовков
- Проверить CSRF токены в формах
- Тестировать на разных разрешениях экрана
