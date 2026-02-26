from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_alter_visit_status_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='telegram_chat_id',
            field=models.BigIntegerField(
                blank=True,
                null=True,
                unique=True,
                verbose_name='Telegram Chat ID',
                help_text='Linked Telegram chat id',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='telegram_linked_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Telegram Linked At',
            ),
        ),
    ]
