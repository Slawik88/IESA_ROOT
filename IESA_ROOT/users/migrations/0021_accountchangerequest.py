"""
Миграция 0021: создаёт модель AccountChangeRequest — заявки на смену типа аккаунта.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0020_partner_type_invite_token'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccountChangeRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('desired_type', models.CharField(
                    choices=[
                        ('partner',           'External Partner'),
                        ('association_staff', 'Association Staff (IESA)'),
                    ],
                    max_length=50,
                    verbose_name='Desired Account Type',
                )),
                ('reason', models.TextField(
                    verbose_name='Reason / Description of Activity',
                    help_text='Describe why you want to change your account type and what you do.',
                )),
                ('status', models.CharField(
                    choices=[
                        ('pending',  'Pending Review'),
                        ('reviewed', 'Reviewed'),
                        ('rejected', 'Rejected'),
                    ],
                    default='pending',
                    max_length=20,
                    verbose_name='Status',
                )),
                ('admin_note', models.TextField(
                    blank=True,
                    verbose_name='Admin Note',
                    help_text='Internal note for the administrator (not shown to user).',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='account_change_requests',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='User',
                )),
            ],
            options={
                'verbose_name': 'Account Change Request',
                'verbose_name_plural': 'Account Change Requests',
                'db_table': 'users_accountchangerequest',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='accountchangerequest',
            index=models.Index(fields=['status', '-created_at'], name='acr_status_date_idx'),
        ),
        migrations.AddIndex(
            model_name='accountchangerequest',
            index=models.Index(fields=['user', 'status'], name='acr_user_status_idx'),
        ),
    ]
