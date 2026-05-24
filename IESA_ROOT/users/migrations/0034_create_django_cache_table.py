"""audit v5: создать таблицу django_cache_table для DatabaseCache backend.
Заменяет LocMemCache — теперь cache shared между всеми воркерами через PostgreSQL."""
from django.db import migrations


def create_cache_table(apps, schema_editor):
    from django.core.management import call_command
    try:
        call_command('createcachetable', 'django_cache_table', verbosity=0)
    except Exception:
        # Если таблица уже существует — игнорируем
        pass


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0033_accountchangerequest_rejection_reason_and_more'),
    ]

    operations = [
        migrations.RunPython(create_cache_table, reverse_noop),
    ]
