"""
Скрипт для тестирования поиска
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

from blog.views.search import post_search, global_search
from django.test import RequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()

# Создаём фабрику запросов
factory = RequestFactory()

print("\n" + "="*80)
print("ТЕСТ ПОИСКА ПОСТОВ")
print("="*80)

# Тест 1: Пустой запрос
print("\n1. Тестируем пустой запрос:")
request = factory.get('/blog/search/', {'q': '', 'status': '', 'sort': 'latest'})
response = post_search(request)
print(f"   Status code: {response.status_code}")
print(f"   Content preview: {response.content[:200]}")

# Тест 2: Поиск по слову "test"
print("\n2. Тестируем поиск 'test':")
request = factory.get('/blog/search/', {'q': 'test', 'status': 'published', 'sort': 'latest'})
response = post_search(request)
print(f"   Status code: {response.status_code}")
print(f"   Content preview: {response.content[:500]}")

# Тест 3: Поиск по слову "sport"
print("\n3. Тестируем поиск 'sport':")
request = factory.get('/blog/search/', {'q': 'sport', 'status': '', 'sort': 'latest'})
response = post_search(request)
print(f"   Status code: {response.status_code}")
print(f"   Content length: {len(response.content)}")

print("\n" + "="*80)
print("ТЕСТ ГЛОБАЛЬНОГО ПОИСКА")
print("="*80)

# Тест 4: Глобальный поиск
print("\n4. Тестируем глобальный поиск 'test':")
user = User.objects.first()
request = factory.get('/blog/search/global/', {'q': 'test'})
request.user = user if user else None
response = global_search(request)
print(f"   Status code: {response.status_code}")
print(f"   Content preview: {response.content[:500]}")

print("\n" + "="*80)
print("ПРОВЕРКА ДАННЫХ В БД")
print("="*80)

from blog.models import Post, Event
from core.models import Partner

print(f"\nВсего постов: {Post.objects.count()}")
print(f"Опубликованных: {Post.objects.filter(status='published').count()}")
print(f"Событий: {Event.objects.count()}")
print(f"Партнёров: {Partner.objects.count()}")
print(f"Пользователей: {User.objects.count()}")

# Показываем несколько постов
print("\nПервые 3 поста:")
for post in Post.objects.all()[:3]:
    print(f"  - [{post.status}] {post.title[:50]}")

print("\n" + "="*80)
