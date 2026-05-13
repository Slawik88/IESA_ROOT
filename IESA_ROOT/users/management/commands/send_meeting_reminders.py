"""
7g: Management command — рассылка напоминаний о встречах.

Запуск (Heroku Scheduler или cron):
    python manage.py send_meeting_reminders
    python manage.py send_meeting_reminders --hours 1

По умолчанию отправляет напоминания о встречах завтра (24ч).
С --hours 1 — о встречах через 1 час.
"""
import logging
from datetime import date, timedelta, datetime, time

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.translation import gettext as _

from notifications.models import Notification
from users.models import Meeting

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send meeting reminder notifications (24h and/or 1h before)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Send reminders for meetings this many hours ahead (default: 24)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending',
        )

    def handle(self, *args, **options):
        hours    = options['hours']
        dry_run  = options['dry_run']
        now      = timezone.localtime()
        target   = now + timedelta(hours=hours)
        t_date   = target.date()
        t_hour   = target.hour

        self.stdout.write(
            f"[send_meeting_reminders] hours={hours} target={target.strftime('%Y-%m-%d %H:%M')} dry_run={dry_run}"
        )

        # Встречи в целевой час (+/- 30 мин)
        meetings = Meeting.objects.filter(
            date=t_date,
            status__in=['scheduled', 'confirmed'],
            start_time__isnull=False,
        ).select_related('partner', 'member', 'partner__user')

        sent = 0
        for m in meetings:
            # Проверяем что встреча в нужном временном окне
            mt = datetime.combine(t_date, m.start_time)
            diff_min = abs((mt - target.replace(tzinfo=None)).total_seconds() / 60)
            if diff_min > 30:
                continue

            time_str  = m.start_time.strftime('%H:%M')
            title_str = m.title or _('Meeting')
            partner_name = m.partner.company_name

            if hours >= 12:
                msg_member  = _(f"Reminder: tomorrow at {time_str} you have \"{title_str}\" at {partner_name}")
                msg_partner = _(f"Reminder: tomorrow at {time_str} — \"{title_str}\" with {m.member.get_full_name() or m.member.username}")
            else:
                msg_member  = _(f"In {hours}h at {time_str}: \"{title_str}\" at {partner_name}")
                msg_partner = _(f"In {hours}h at {time_str}: \"{title_str}\" with {m.member.get_full_name() or m.member.username}")

            if dry_run:
                self.stdout.write(f"  DRY: member={m.member.username} → {msg_member}")
                self.stdout.write(f"  DRY: partner={m.partner.user.username} → {msg_partner}")
            else:
                # In-site notifications
                Notification.objects.get_or_create(
                    recipient=m.member,
                    notification_type='event_reminder',
                    message=msg_member,
                    defaults={'link': f'/auth/my-calendar/'},
                )
                Notification.objects.get_or_create(
                    recipient=m.partner.user,
                    notification_type='event_reminder',
                    message=msg_partner,
                    defaults={'link': f'/auth/partner/calendar/?day={t_date}'},
                )

                # Telegram уведомление если привязан
                self._send_tg(m.member, f"📅 {msg_member}")
                self._send_tg(m.partner.user, f"📅 {msg_partner}")

            sent += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. {'Would send' if dry_run else 'Sent'} reminders for {sent} meeting(s)."
        ))

    def _send_tg(self, user, text):
        """Отправляет TG-сообщение если у пользователя привязан chat_id."""
        if not getattr(user, 'telegram_chat_id', None):
            return
        try:
            from users.telegram_bot import send_message
            send_message(user.telegram_chat_id, text)
        except Exception as e:
            logger.warning("TG reminder failed for user %s: %s", user.pk, e)
