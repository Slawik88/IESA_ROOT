"""
Drop orphaned messaging_* tables that remain from the removed 'messaging' app.
The messaging app was uninstalled but its tables stayed in PostgreSQL, causing
ForeignKeyViolation when deleting users via Django admin.

Uses database-specific SQL: CASCADE for PostgreSQL, plain DROP for SQLite.
"""
from django.db import migrations, connection


def drop_messaging_tables(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute("DROP TABLE IF EXISTS messaging_message CASCADE;")
            cursor.execute("DROP TABLE IF EXISTS messaging_chat CASCADE;")
        else:
            # SQLite не поддерживает CASCADE — таблицы могут отсутствовать в dev
            cursor.execute("DROP TABLE IF EXISTS messaging_message;")
            cursor.execute("DROP TABLE IF EXISTS messaging_chat;")


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0028_add_partner_map_fields'),
    ]

    operations = [
        migrations.RunPython(drop_messaging_tables, migrations.RunPython.noop),
    ]
