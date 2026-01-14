"""Минимальный тест view"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

from django.test import Client
from blog.models import Post

client = Client()

print("\n=== ПРОВЕРКА ДАННЫХ ===")
posts = Post.objects.filter(status='published')[:3]
for p in posts:
    print(f"POST: {p.title[:40]}")

print("\n=== ТЕСТ 1: Загрузка страницы постов ===")
response = client.get('/blog/')
print(f"Status: {response.status_code}")
print(f"Template: {response.template_name if hasattr(response, 'template_name') else 'N/A'}")
if response.status_code == 200:
    content = response.content.decode('utf-8')
    if 'posts-container' in content:
        print("✓ posts-container найден")
    else:
        print("✗ posts-container НЕ найден!")
    
    if 'post_search' in content:
        print("✓ post_search форма найдена")
    else:
        print("✗ post_search форма НЕ найдена!")

print("\n=== ТЕСТ 2: Поиск через HTMX (пустой запрос) ===")
response = client.get('/blog/search/', {'q': '', 'status': '', 'sort': 'latest'})
print(f"Status: {response.status_code}")
content = response.content.decode('utf-8')
print(f"Content length: {len(content)} bytes")
print(f"Content preview:\n{content[:300]}")

print("\n=== ТЕСТ 3: Поиск 'sport' ===")
response = client.get('/blog/search/', {'q': 'sport'})
print(f"Status: {response.status_code}")
content = response.content.decode('utf-8')
print(f"Content length: {len(content)} bytes")
print(f"Content preview:\n{content[:500]}")
if 'No posts found' in content:
    print("✗ Показывает 'No posts found'")
elif 'card-modern' in content:
    print("✓ Карточки постов найдены")
else:
    print("? Непонятно что показывает")
