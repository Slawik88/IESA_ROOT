from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0011_alter_user_totp_secret'),
    ]

    operations = [
        # 1) Brute-force protection fields on User
        migrations.AddField(
            model_name='user',
            name='failed_pin_attempts',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='Failed PIN Attempts'),
        ),
        migrations.AddField(
            model_name='user',
            name='pin_lockout_until',
            field=models.DateTimeField(blank=True, null=True, verbose_name='PIN Lockout Until'),
        ),
        # 2) Status field on Visit
        migrations.AddField(
            model_name='visit',
            name='status',
            field=models.CharField(
                choices=[('ACTIVE', 'Active'), ('EDITED', 'Edited'), ('CANCELLED', 'Cancelled')],
                default='ACTIVE',
                max_length=10,
                verbose_name='Status',
            ),
        ),
        # 3) VisitAudit table
        migrations.CreateModel(
            name='VisitAudit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(
                    choices=[('EDIT', 'Edit'), ('CANCEL', 'Cancel')],
                    max_length=10,
                    verbose_name='Action',
                )),
                ('previous_service_type', models.CharField(blank=True, max_length=100, verbose_name='Previous Service Type')),
                ('previous_service_description', models.TextField(blank=True, verbose_name='Previous Description')),
                ('previous_cost', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Previous Cost')),
                ('previous_comments', models.TextField(blank=True, verbose_name='Previous Comments')),
                ('reason', models.TextField(verbose_name='Reason')),
                ('changed_at', models.DateTimeField(auto_now_add=True, verbose_name='Changed At')),
                ('changed_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='visit_audits',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Changed By',
                )),
                ('visit', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='audits',
                    to='users.visit',
                    verbose_name='Visit',
                )),
            ],
            options={
                'verbose_name': 'Visit Audit',
                'verbose_name_plural': 'Visit Audits',
                'db_table': 'users_visitaudit',
                'ordering': ['-changed_at'],
            },
        ),
    ]
