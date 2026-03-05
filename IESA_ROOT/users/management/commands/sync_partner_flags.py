"""
Management command to sync is_partner boolean flag with partner_profile FK.

Fixes inconsistent state where a user has a Partner profile but
is_partner=False (or vice versa). Run once after deploy.

Usage:
    python manage.py sync_partner_flags
    python manage.py sync_partner_flags --dry-run
"""
from django.core.management.base import BaseCommand
from users.models import Partner, User


class Command(BaseCommand):
    help = 'Sync is_partner flag with Partner profile FK relationship'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making DB changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        prefix = '[DRY RUN] ' if dry_run else ''

        # --- Case 1: has partner_profile but is_partner=False ---
        needs_flag_true = (
            User.objects.filter(is_partner=False, partner_profile__isnull=False)
            if hasattr(User, 'partner_profile')
            else User.objects.filter(is_partner=False).filter(
                pk__in=Partner.objects.values_list('user_id', flat=True)
            )
        )
        count_true = needs_flag_true.count()
        if count_true:
            self.stdout.write(
                self.style.WARNING(
                    f'{prefix}Found {count_true} user(s) with partner_profile but is_partner=False'
                )
            )
            for u in needs_flag_true:
                self.stdout.write(f'  → {u.username} (id={u.pk})')
            if not dry_run:
                needs_flag_true.update(is_partner=True)
                self.stdout.write(self.style.SUCCESS(f'✅ Set is_partner=True for {count_true} user(s)'))
        else:
            self.stdout.write('✅ No users with partner_profile + is_partner=False found')

        # --- Case 2: is_partner=True but NO partner_profile ---
        partner_user_ids = set(Partner.objects.values_list('user_id', flat=True))
        orphan_flags = User.objects.filter(is_partner=True).exclude(pk__in=partner_user_ids)
        count_false = orphan_flags.count()
        if count_false:
            self.stdout.write(
                self.style.WARNING(
                    f'{prefix}Found {count_false} user(s) with is_partner=True but no partner_profile'
                )
            )
            for u in orphan_flags:
                self.stdout.write(f'  → {u.username} (id={u.pk})')
            if not dry_run:
                orphan_flags.update(is_partner=False)
                self.stdout.write(self.style.SUCCESS(f'✅ Cleared is_partner for {count_false} user(s)'))
        else:
            self.stdout.write('✅ No orphan is_partner=True flags found')

        if dry_run:
            self.stdout.write(self.style.NOTICE('Dry run complete — no changes made'))
        else:
            self.stdout.write(self.style.SUCCESS('Sync complete'))
