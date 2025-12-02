from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings
import os

from users.qr_utils import generate_qr_code_for_user


class Command(BaseCommand):
    help = 'Check QR files for all users with card_active=True. Use --fix to generate missing QR files.'

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true', help='Generate missing QR files')

    def handle(self, *args, **options):
        User = get_user_model()
        missing = []
        for u in User.objects.filter(card_active=True):
            filename = os.path.join(settings.MEDIA_ROOT, 'cards', f"{str(u.permanent_id)}.png")
            if not os.path.exists(filename):
                missing.append((u.username, str(u.permanent_id)))

        if not missing:
            self.stdout.write(self.style.SUCCESS('All QR files present for active cards.'))
            return

        self.stdout.write(self.style.WARNING(f'Found {len(missing)} missing QR file(s):'))
        for username, pid in missing:
            self.stdout.write(f' - {username} ({pid})')

        if options.get('fix'):
            self.stdout.write('Generating missing QR files...')
            for username, pid in missing:
                try:
                    u = User.objects.get(permanent_id=pid)
                    generate_qr_code_for_user(u)
                    self.stdout.write(self.style.SUCCESS(f' Generated for {username}'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f' Failed for {username}: {e}'))
            self.stdout.write(self.style.SUCCESS('Done.'))
