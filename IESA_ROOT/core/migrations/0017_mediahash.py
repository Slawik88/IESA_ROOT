from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_adminappeal'),
    ]

    operations = [
        migrations.CreateModel(
            name='MediaHash',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sha256', models.CharField(db_index=True, max_length=64, unique=True, verbose_name='SHA-256')),
                ('s3_key', models.CharField(max_length=500, verbose_name='S3 key')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Created')),
            ],
            options={
                'verbose_name': 'Media hash (dedup)',
                'verbose_name_plural': 'Media hashes (dedup)',
            },
        ),
    ]
