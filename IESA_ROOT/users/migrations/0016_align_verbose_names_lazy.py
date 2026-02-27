"""
Align verbose_name (and verbose_name_plural) on User
fields that were originally written with plain-string labels but
have since been updated to gettext_lazy in models.py.

Affected fields / objects:
    User.permanent_id    — 'Permanent ID'       → gettext_lazy('Permanent ID')
    User.card_active     — 'Card active'         → gettext_lazy('Card active')
    User.card_issued_at  — 'Card issued at'      → gettext_lazy('Card issued at')
    User.membership_status — verbose_name plain  → lazy
    User.pseudonym       — 'Pseudonym'           → gettext_lazy('Pseudonym')
    User.totp_secret     — 'TOTP Secret'         → gettext_lazy('TOTP Secret')
"""

import django.utils.translation
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0015_alter_user_telegram_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='permanent_id',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name=django.utils.translation.gettext_lazy('Permanent ID'),
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='card_active',
            field=models.BooleanField(
                default=False,
                verbose_name=django.utils.translation.gettext_lazy('Card active'),
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='card_issued_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name=django.utils.translation.gettext_lazy('Card issued at'),
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='membership_status',
            field=models.CharField(
                choices=[('active', 'Active'), ('inactive', 'Inactive')],
                default='inactive',
                max_length=20,
                verbose_name=django.utils.translation.gettext_lazy('Membership Status'),
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='pseudonym',
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name=django.utils.translation.gettext_lazy('Pseudonym'),
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='totp_secret',
            field=models.CharField(
                blank=True,
                help_text='Base32-encoded secret for PIN generation',
                max_length=64,
                verbose_name=django.utils.translation.gettext_lazy('TOTP Secret'),
            ),
        ),
    ]
