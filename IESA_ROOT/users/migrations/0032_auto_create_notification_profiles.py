"""BLOCK 9 (audit v4): автоматически создаёт AdminNotificationProfile для всех существующих
staff-юзеров, если у них его ещё нет. Включает все 5 событий по умолчанию (TG + site).

Это исправляет ситуацию когда signal _notify_admins срабатывает, но не находит ни одного
активного профиля → уведомления не отправляются (даже несмотря на is_staff=True у root).
"""
from django.db import migrations


ALL_EVENTS = [
    'new_account',
    'post_moderation',
    'account_upgrade',
    'insurance_request',
    'new_visit',
]


def ensure_profiles(apps, schema_editor):
    User = apps.get_model('users', 'User')
    AdminNotificationProfile = apps.get_model('users', 'AdminNotificationProfile')

    created = 0
    for user in User.objects.filter(is_staff=True):
        profile, was_created = AdminNotificationProfile.objects.get_or_create(
            admin_user=user,
            defaults={
                'telegram_events': list(ALL_EVENTS),
                'site_events':     list(ALL_EVENTS),
                'is_active': True,
            },
        )
        if was_created:
            created += 1
    print(f'  → AdminNotificationProfile: создано {created} новых профилей для staff-юзеров')


def reverse_noop(apps, schema_editor):
    """Не удаляем профили при откате — иначе админ потеряет настройки."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0031_accountchangerequest_first_name_and_more'),
    ]

    operations = [
        migrations.RunPython(ensure_profiles, reverse_noop),
    ]
