"""
Скрипт для создания тестовых данных
"""
from django.contrib.auth import get_user_model
from blog.models import Post, Event
from datetime import datetime, timedelta

User = get_user_model()

# Создаём тестового пользователя
test_user, created = User.objects.get_or_create(
    username='testuser',
    defaults={
        'email': 'test@test.com',
        'first_name': 'Test',
        'last_name': 'User'
    }
)
if created:
    test_user.set_password('testpass123')
    test_user.save()
    print(f'✅ Created user: {test_user.username}')
else:
    print(f'ℹ️ User exists: {test_user.username}')

# Создаём тестовые посты
posts_data = [
    {'title': 'Kitesurfing in Egypt', 'text': 'Amazing kitesurfing experience in Dahab!'},
    {'title': 'Boxing Training', 'text': 'New boxing training schedule for beginners'},
    {'title': 'Sauna Benefits', 'text': 'Health benefits of regular sauna sessions'},
]

for data in posts_data:
    post, created = Post.objects.get_or_create(
        title=data['title'],
        author=test_user,
        defaults={
            'text': data['text'],
            'status': 'published'
        }
    )
    if created:
        print(f'✅ Created post: {post.title}')
    else:
        print(f'ℹ️ Post exists: {post.title}')

# Создаём тестовые события
events_data = [
    {'title': 'Kitesurf Camp', 'description': 'Join us for a week of kitesurfing!'},
    {'title': 'Boxing Tournament', 'description': 'Annual boxing championship'},
]

for data in events_data:
    event, created = Event.objects.get_or_create(
        title=data['title'],
        created_by=test_user,
        defaults={
            'description': data['description'],
            'date': datetime.now() + timedelta(days=30),
            'location': 'IESA Sports Center'
        }
    )
    if created:
        print(f'✅ Created event: {event.title}')
    else:
        print(f'ℹ️ Event exists: {event.title}')

print('\n📊 Summary:')
print(f'Users: {User.objects.count()}')
print(f'Published Posts: {Post.objects.filter(status="published").count()}')
print(f'Events: {Event.objects.count()}')
