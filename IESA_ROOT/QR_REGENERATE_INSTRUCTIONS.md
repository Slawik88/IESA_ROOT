# Инструкция: Регенерация QR кодов

## Проблема
QR коды были созданы до исправления S3 хранилища и могут быть некорректными.

## Решение: Пересоздание QR кодов

### Вариант 1: Через Django shell (локально)
```bash
cd IESA_ROOT
python manage.py shell < regenerate_qr_codes.py
```

### Вариант 2: На DigitalOcean App Platform

1. Зайди в консоль приложения DigitalOcean
2. Выполни:
```bash
python manage.py shell
```

3. В интерпретаторе Python выполни:
```python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

from users.models import User
from users.qr_utils import generate_qr_code_for_user
import boto3

# Initialize S3
s3 = boto3.client(
    's3',
    endpoint_url='https://fra1.digitaloceanspaces.com',
    aws_access_key_id=os.getenv('SPACES_KEY'),
    aws_secret_access_key=os.getenv('SPACES_SECRET'),
    region_name='fra1'
)

bucket = os.getenv('SPACES_BUCKET', 'iesa-bucket')

# Delete old QR codes
print("Deleting old QR codes...")
response = s3.list_objects_v2(Bucket=bucket, Prefix='media/cards/')
if 'Contents' in response:
    for obj in response['Contents']:
        s3.delete_object(Bucket=bucket, Key=obj['Key'])
        print(f"Deleted: {obj['Key']}")

# Generate new QR codes
print("\nGenerating new QR codes...")
users = User.objects.filter(permanent_id__isnull=False).exclude(permanent_id='')
for user in users:
    try:
        qr_path = generate_qr_code_for_user(user)
        s3.put_object_acl(Bucket=bucket, Key=f'media/cards/{user.permanent_id}.png', ACL='public-read')
        print(f"✓ {user.username}")
    except Exception as e:
        print(f"✗ {user.username}: {e}")

print("\n✅ Done!")
```

## Что изменилось в QR кодах

Старая версия:
- ❌ Могли быть сохранены с неправильной путём
- ❌ ACL мог быть приватным
- ❌ Возможны проблемы с S3 хранилищем

Новая версия:
- ✅ Правильный путь: `media/cards/{permanent_id}.png`
- ✅ ACL: `public-read` (доступны всем)
- ✅ S3 хранилище: DigitalOcean Spaces
- ✅ Генерируются автоматически при регистрации пользователя

## После регенерации

QR коды будут:
1. Удалены из старых путей
2. Пересоздены с правильным путём
3. Установлены как публичные
4. Доступны через CDN

Проверь в профиле - QR код должен загружаться корректно!
