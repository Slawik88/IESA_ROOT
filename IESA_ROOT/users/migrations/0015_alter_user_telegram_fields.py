"""Align telegram field definitions with current models.py.

0014 used plain-string verbose_name and a shorter help_text.
Models.py now uses gettext_lazy verbose_name and a longer help_text,
so Django's consistency check emits a warning on every deploy.
"""
import django.utils.translation
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0014_user_telegram_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="telegram_chat_id",
            field=models.BigIntegerField(
                blank=True,
                null=True,
                unique=True,
                verbose_name=django.utils.translation.gettext_lazy("Telegram Chat ID"),
                help_text=(
                    "Linked Telegram chat id (set automatically when user "
                    "connects via bot or widget)"
                ),
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="telegram_linked_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name=django.utils.translation.gettext_lazy("Telegram Linked At"),
            ),
        ),
    ]
