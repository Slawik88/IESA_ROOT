"""
Миграция 0020: добавляет partner_type к Partner и создаёт модель InviteToken.
"""
import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0019_alter_user_avatar_visitaudit_audit_visit_time_idx_and_more'),
    ]

    operations = [
        # 1. Добавляем partner_type к Partner
        migrations.AddField(
            model_name='partner',
            name='partner_type',
            field=models.CharField(
                choices=[
                    ('partner', 'External Partner'),
                    ('association_staff', 'Association Staff'),
                ],
                default='partner',
                help_text=(
                    'External Partner — внешний бизнес; '
                    'Association Staff — сотрудник ассоциации (юрист, бухгалтер). '
                    'Сотрудники НЕ получают is_staff=True.'
                ),
                max_length=50,
                verbose_name='Partner Type',
            ),
        ),

        # 2. Создаём таблицу InviteToken
        migrations.CreateModel(
            name='InviteToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('token', models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name='Token')),
                ('partner_type', models.CharField(
                    choices=[
                        ('partner', 'External Partner'),
                        ('association_staff', 'Association Staff'),
                    ],
                    default='partner',
                    help_text='Роль, которую получит зарегистрировавшийся по этой ссылке.',
                    max_length=50,
                    verbose_name='Partner Type',
                )),
                ('company_name', models.CharField(
                    blank=True, max_length=255,
                    verbose_name='Pre-filled Company Name',
                    help_text='Необязательно. Предзаполнит поле "Компания" в форме регистрации.',
                )),
                ('note', models.CharField(
                    blank=True, max_length=255,
                    verbose_name='Internal Note',
                    help_text='Внутренняя заметка (например: "Инвайт для FitnessPro Geneva").',
                )),
                ('used_at', models.DateTimeField(blank=True, null=True, verbose_name='Used At')),
                ('expires_at', models.DateTimeField(verbose_name='Expires At')),
                ('is_active', models.BooleanField(default=True, verbose_name='Is Active')),
                ('max_uses', models.PositiveSmallIntegerField(
                    default=1,
                    verbose_name='Max Uses',
                    help_text='Сколько раз можно использовать ссылку. Обычно 1.',
                )),
                ('use_count', models.PositiveSmallIntegerField(default=0, verbose_name='Use Count')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_invites',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Created By',
                )),
                ('used_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='used_invite',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Used By',
                )),
            ],
            options={
                'verbose_name': 'Invite Token',
                'verbose_name_plural': 'Invite Tokens',
                'db_table': 'users_invitetoken',
                'ordering': ['-created_at'],
            },
        ),

        # 3. Индексы для InviteToken
        migrations.AddIndex(
            model_name='invitetoken',
            index=models.Index(fields=['token'], name='invite_token_idx'),
        ),
        migrations.AddIndex(
            model_name='invitetoken',
            index=models.Index(fields=['is_active', 'expires_at'], name='invite_active_exp_idx'),
        ),
    ]
