# Production Setup Commands for DigitalOcean

## Проблема: Не работает админка и медиа файлы

### Решение:

## 1. Применить миграции в production

В консоли DigitalOcean App Platform (Console tab):

```bash
python IESA_ROOT/manage.py migrate
```

## 2. Создать суперпользователя

```bash
python IESA_ROOT/manage.py createsuperuser
```

Введите:
- Username: admin (или ваш username)
- Email: your@email.com
- Password: (надежный пароль)

## 3. Собрать статические файлы (если нужно)

```bash
python IESA_ROOT/manage.py collectstatic --noinput
```

## 4. Проверить что база данных существует

```bash
ls -la IESA_ROOT/db.sqlite3
```

## Альтернативный способ через App Spec:

Добавьте в DigitalOcean App Settings → Components → Run Command (Build):

```yaml
run:
  - python IESA_ROOT/manage.py migrate
```

## Важно:

⚠️ SQLite в production - временное решение! Данные могут быть потеряны при рестарте.

### Рекомендации для продакшена:

1. **База данных**: Подключите PostgreSQL (DigitalOcean Managed Database)
2. **Media файлы**: Используйте DigitalOcean Spaces (S3-совместимое хранилище)
3. **Static файлы**: WhiteNoise уже настроен ✅

### Как подключить PostgreSQL:

1. В DigitalOcean создайте Database → PostgreSQL
2. В App Settings → Environment Variables добавьте:
   - `DATABASE_URL` (автоматически подключится из Managed Database)
3. Settings.py уже настроен для автоматического подключения PostgreSQL!

### Как подключить DigitalOcean Spaces для media:

1. Установите пакеты:
```bash
pip install django-storages boto3
```

2. Добавьте в settings.py:
```python
# Digital Ocean Spaces for media files
if not DEBUG:
    AWS_ACCESS_KEY_ID = os.getenv('SPACES_KEY')
    AWS_SECRET_ACCESS_KEY = os.getenv('SPACES_SECRET')
    AWS_STORAGE_BUCKET_NAME = os.getenv('SPACES_BUCKET')
    AWS_S3_ENDPOINT_URL = os.getenv('SPACES_ENDPOINT', 'https://fra1.digitaloceanspaces.com')
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
    AWS_LOCATION = 'media'
    AWS_DEFAULT_ACL = 'public-read'
    
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
```

3. В Environment Variables добавьте:
   - `SPACES_KEY` - Access Key из Spaces
   - `SPACES_SECRET` - Secret Key из Spaces
   - `SPACES_BUCKET` - название bucket
   - `SPACES_ENDPOINT` - https://fra1.digitaloceanspaces.com

## Текущее состояние:

✅ Static files (CSS/JS) - работают через WhiteNoise
⚠️ Media files - временно через Django (работает, но не оптимально)
⚠️ Database - SQLite (временно, данные могут быть потеряны)
✅ CSRF настроен для DigitalOcean домена
✅ ALLOWED_HOSTS настроен
