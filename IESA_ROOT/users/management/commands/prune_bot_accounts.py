"""Find (and optionally delete) accounts that look like leftovers of bot sign-ups.

An account is a candidate only if ALL of these hold:
  * e-mail never confirmed, and no social-provider login,
  * older than --days (default 14),
  * not staff / superuser / partner, and has no partner profile or invites,
  * has never posted, commented, liked, registered for an event, logged a visit,
    subscribed, or filed any request.

The default is a dry run that only prints what it WOULD remove.

    python manage.py prune_bot_accounts                 # list
    python manage.py prune_bot_accounts --days 30       # stricter age
    python manage.py prune_bot_accounts --delete        # actually delete
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import User


class Command(BaseCommand):
    help = 'List (dry run) or delete never-confirmed, never-active sign-ups older than --days.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=14, help='Minimum account age in days (default 14).')
        parser.add_argument('--delete', action='store_true', help='Really delete. Without it nothing changes.')
        parser.add_argument('--show', type=int, default=25, help='How many sample rows to print.')

    def candidates(self, days):
        cutoff = timezone.now() - timedelta(days=days)
        return (
            User.objects
            .filter(
                is_active=True, is_staff=False, is_superuser=False, is_partner=False,
                email_verified_at__isnull=True, date_joined__lt=cutoff,
                socialaccount__isnull=True,
                partner_profile__isnull=True, created_invites__isnull=True,
                blog_posts__isnull=True, comments_authored__isnull=True,
                commentlike__isnull=True, like__isnull=True, event_registrations__isnull=True, visits__isnull=True,
                blog_subscriptions__isnull=True, subscribers__isnull=True,
                account_change_requests__isnull=True, insurance_requests__isnull=True,
                admin_appeals__isnull=True, created_events__isnull=True,
            )
            .distinct()
            .order_by('date_joined')
        )

    def handle(self, *args, **opts):
        qs = self.candidates(opts['days'])
        total = qs.count()
        self.stdout.write(f'{total} account(s) match (unconfirmed e-mail, no activity, older than {opts["days"]} days).')
        for user in qs[:opts['show']]:
            self.stdout.write(f'  #{user.pk:<6} {user.date_joined:%Y-%m-%d}  {user.username:<28} {user.email}')
        if total > opts['show']:
            self.stdout.write(f'  ... and {total - opts["show"]} more')

        if not opts['delete']:
            self.stdout.write(self.style.WARNING('Dry run — nothing deleted. Add --delete to remove them.'))
            return
        ids = list(qs.values_list('pk', flat=True))
        deleted, _ = User.objects.filter(pk__in=ids).delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {len(ids)} account(s) ({deleted} rows incl. dependants).'))
