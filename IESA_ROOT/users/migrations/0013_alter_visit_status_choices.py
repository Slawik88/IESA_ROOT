import django.db.models.deletion
import django.utils.translation
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Align field verbose_name / choices with model definitions.

    Migration 0012 was hand-written with plain-string labels, but the models
    use gettext_lazy wrappers (_()).  Django's migration consistency check
    detects the mismatch and emits a warning on every deploy.

    This migration re-declares all affected fields so that the migration
    state matches what Django derives from models.py.

    Fields touched:
        User.failed_pin_attempts   — verbose_name plain → lazy
        User.pin_lockout_until     — verbose_name plain → lazy
        Visit.status               — choices + verbose_name plain → lazy
        VisitAudit (whole model)   — choices + verbose_names plain → lazy
    """

    dependencies = [
        ('users', '0012_visit_status_visitaudit_user_pinlockout'),
    ]

    operations = [
        # ── User ──────────────────────────────────────────────────────────
        migrations.AlterField(
            model_name='user',
            name='failed_pin_attempts',
            field=models.PositiveSmallIntegerField(
                default=0,
                verbose_name=django.utils.translation.gettext_lazy('Failed PIN Attempts'),
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='pin_lockout_until',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name=django.utils.translation.gettext_lazy('PIN Lockout Until'),
            ),
        ),

        # ── Visit.status ─────────────────────────────────────────────────
        migrations.AlterField(
            model_name='visit',
            name='status',
            field=models.CharField(
                choices=[
                    ('ACTIVE', django.utils.translation.gettext_lazy('Active')),
                    ('EDITED', django.utils.translation.gettext_lazy('Edited')),
                    ('CANCELLED', django.utils.translation.gettext_lazy('Cancelled')),
                ],
                default='ACTIVE',
                max_length=10,
                verbose_name=django.utils.translation.gettext_lazy('Status'),
            ),
        ),

        # ── VisitAudit — re-declare with lazy strings ─────────────────────
        migrations.AlterModelOptions(
            name='visitaudit',
            options={
                'verbose_name': django.utils.translation.gettext_lazy('Visit Audit'),
                'verbose_name_plural': django.utils.translation.gettext_lazy('Visit Audits'),
                'db_table': 'users_visitaudit',
                'ordering': ['-changed_at'],
            },
        ),
        migrations.AlterField(
            model_name='visitaudit',
            name='action',
            field=models.CharField(
                choices=[
                    ('EDIT', django.utils.translation.gettext_lazy('Edit')),
                    ('CANCEL', django.utils.translation.gettext_lazy('Cancel')),
                ],
                max_length=10,
                verbose_name=django.utils.translation.gettext_lazy('Action'),
            ),
        ),
        migrations.AlterField(
            model_name='visitaudit',
            name='changed_at',
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name=django.utils.translation.gettext_lazy('Changed At'),
            ),
        ),
        migrations.AlterField(
            model_name='visitaudit',
            name='changed_by',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='visit_audits',
                to=settings.AUTH_USER_MODEL,
                verbose_name=django.utils.translation.gettext_lazy('Changed By'),
            ),
        ),
        migrations.AlterField(
            model_name='visitaudit',
            name='previous_comments',
            field=models.TextField(
                blank=True,
                verbose_name=django.utils.translation.gettext_lazy('Previous Comments'),
            ),
        ),
        migrations.AlterField(
            model_name='visitaudit',
            name='previous_cost',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name=django.utils.translation.gettext_lazy('Previous Cost'),
            ),
        ),
        migrations.AlterField(
            model_name='visitaudit',
            name='previous_service_description',
            field=models.TextField(
                blank=True,
                verbose_name=django.utils.translation.gettext_lazy('Previous Description'),
            ),
        ),
        migrations.AlterField(
            model_name='visitaudit',
            name='previous_service_type',
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name=django.utils.translation.gettext_lazy('Previous Service Type'),
            ),
        ),
        migrations.AlterField(
            model_name='visitaudit',
            name='reason',
            field=models.TextField(
                verbose_name=django.utils.translation.gettext_lazy('Reason'),
            ),
        ),
        migrations.AlterField(
            model_name='visitaudit',
            name='visit',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='audits',
                to='users.visit',
                verbose_name=django.utils.translation.gettext_lazy('Visit'),
            ),
        ),
    ]
