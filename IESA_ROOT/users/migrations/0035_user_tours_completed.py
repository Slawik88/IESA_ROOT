"""Add tours_completed JSONField to User (Tour system 2026-05-27)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0034_create_django_cache_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='tours_completed',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Tracks which interactive tours user has finished',
                verbose_name='Tours Completed',
            ),
        ),
    ]
