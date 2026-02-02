# Гайд по использованию обновлённой админ-панели

## 🎯 Для администраторов

### Где всё находится

#### CSS файлы
- **Admin styling**: `static/css/admin-enhanced.css` (355 строк)
- **Profile styling**: `static/css/pages.css` (раздел profile-edit-page)

#### Python файлы
- **Custom admin**: `core/admin_site.py` (CustomAdminSite класс)
- **Admin config**: `core/admin.py` (форма с CKEditor и подсказками)
- **URL config**: `IESA_ROOT/urls.py` (применение CustomAdminSite)

#### Шаблоны
- **Profile edit**: `users/templates/users/profile_edit.html` (с примерами ссылок)

## 🎨 Цветовая схема

Всегда используйте эти цвета для новых элементов:

```
Основной:    #dc2626 (bright red)
Тёмный:      #991b1b (dark accent)
Светлый:     #fecaca (borders & light backgrounds)
Фон 1:       #fef2f2 (very light red)
Фон 2:       #fee2e2 (light red)
```

## 📝 Как добавить новые поля в админку

### Пример 1: Простой текстовой field

```python
from django import forms
from django.contrib import admin

class MyModelAdminForm(forms.ModelForm):
    description = forms.CharField(
        widget=forms.Textarea,
        help_text='Используйте форматирование для красивого текста'
    )
    
    class Meta:
        model = MyModel
        fields = ['name', 'description']

class MyModelAdmin(admin.ModelAdmin):
    form = MyModelAdminForm
```

**Результат**: текстовое поле автоматически получит красную тему!

### Пример 2: Rich text editor (CKEditor)

```python
from django_ckeditor_5.widgets import CKEditor5Widget
from django import forms

class MyForm(forms.ModelForm):
    content = forms.CharField(
        widget=CKEditor5Widget(
            attrs={'class': 'django-ckeditor-widget'}
        )
    )
    
    class Meta:
        model = MyModel
        fields = ['content']
```

**Результат**: полноценный WYSIWYG редактор с красным toolbar!

### Пример 3: Поле с подсказками (help_text)

```python
from django.utils.html import format_html

class BenefitAdminForm(forms.ModelForm):
    icon = forms.CharField(
        help_text=format_html(
            '<strong>Выберите иконку:</strong><br>'
            '<i class="fas fa-star"></i> star - звезда<br>'
            '<i class="fas fa-heart"></i> heart - сердце<br>'
            '<i class="fas fa-gift"></i> gift - подарок'
        )
    )
```

**Результат**: красиво отформатированная подсказка с иконками!

## 📋 Поддерживаемые социальные сети в профиле

| Платформа | URL пример | Иконка |
|-----------|-----------|--------|
| GitHub | https://github.com/username | fab fa-github |
| Website | https://example.com | fas fa-globe |
| Telegram | https://t.me/username | fab fa-telegram |
| Discord | https://discord.com/users/123456 | fab fa-discord |
| LinkedIn | https://linkedin.com/in/username | fab fa-linkedin |
| Twitter | https://twitter.com/username | fab fa-twitter |
| Instagram | https://instagram.com/username | fab fa-instagram |
| YouTube | https://youtube.com/@username | fab fa-youtube |
| TikTok | https://tiktok.com/@username | fab fa-tiktok |
| Twitch | https://twitch.tv/username | fab fa-twitch |
| Medium | https://medium.com/@username | fab fa-medium |
| Reddit | https://reddit.com/u/username | fab fa-reddit |

## 🔧 Как добавить новый раздел в админке

### Шаг 1: Создайте форму

```python
# в admin.py
class MyFormadmin(forms.ModelForm):
    class Meta:
        model = MyModel
        fields = '__all__'
```

### Шаг 2: Зарегистрируйте в админе

```python
@admin.register(MyModel)
class MyModelAdmin(admin.ModelAdmin):
    form = MyFormdmin
    list_display = ['name', 'created_at']
    search_fields = ['name']
```

### Шаг 3: ВСЁ! 🎉

Admin-enhanced.css автоматически применится ко всем полям!

## 💡 Полезные CSS классы

Если нужно кастомизировать под свои нужды:

```css
/* Красное поле */
.form-control:focus {
    border-color: #dc2626;
    box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.1);
}

/* Красная кнопка */
.btn-primary {
    background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);
}

/* Красный заголовок */
h1, h2, h3 {
    color: #dc2626;
}

/* Красная граница */
border: 2px solid #fecaca;

/* Красный фон */
background: #fef2f2;
```

## 🚀 Развёртывание изменений

Если вы добавили новый CSS:

```bash
# 1. Соберите статику
python manage.py collectstatic --noinput

# 2. Закоммитьте
git add -A
git commit -m "feat: Add new styling"

# 3. Отправьте
git push origin master

# Production (DigitalOcean) автоматически обновится!
```

## ⚠️ Важные замечания

1. **CKEditor toolbar** - красный градиент уже встроен
2. **Все input поля** - получат красные фокусные состояния автоматически
3. **Кнопки** - используют красный градиент по умолчанию
4. **Help text** - отображаются с красной левой границей

## ❓ Часто задаваемые вопросы

**Q: Как изменить цвет?**
A: Замените все `#dc2626` на нужный цвет в `admin-enhanced.css`

**Q: Как добавить новый язык в админке?**
A: Используйте параметр `help_text` в форме

**Q: Почему профиль выглядит красиво?**
A: `pages.css` содержит профессиональный дизайн для profile-edit-page

**Q: Как тестировать локально?**
A: `python manage.py runserver` → http://localhost:8000/admin

## 📞 Поддержка

- Git repo: https://github.com/Slawik88/IESA_ROOT
- Main branch: master
- Production: DigitalOcean App Platform

---

**Версия**: 1.0
**Последнее обновление**: 2024
**Статус**: ✅ Production Ready
