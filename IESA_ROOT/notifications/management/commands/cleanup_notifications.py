"""
Management command для очистки старых прочитанных уведомлений (B2-08).

Запуск вручную:
    python manage.py cleanup_notifications
    python manage.py cleanup_notifications --days 60

Добавить в crontab (DigitalOcean App Platform → Jobs):
    0 2 * * * python manage.py cleanup_notifications
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Удаляет старые прочитанные уведомления (по умолчанию старше 90 дней)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Удалить уведомления старше N дней (default: 90)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать сколько будет удалено без реального удаления',
        )

    def handle(self, *args, **options):
        from notifications.models import Notification

        days = options['days']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(days=days)

        qs = Notification.objects.filter(
            is_read=True,
            created_at__lt=cutoff,
        )
        count = qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'[dry-run] Будет удалено {count} уведомлений старше {days} дней')
            )
            return

        deleted, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(f'✅ Удалено {deleted} прочитанных уведомлений старше {days} дней')
        )
