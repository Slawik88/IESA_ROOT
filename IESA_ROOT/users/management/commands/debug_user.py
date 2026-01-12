"""
Debug user data
"""
from django.core.management.base import BaseCommand
from users.models import User


class Command(BaseCommand):
    help = 'Debug user data with "root"'

    def handle(self, *args, **options):
        users = User.objects.filter(username__icontains='root')
        
        self.stdout.write(f'Found {users.count()} users with "root":')
        for u in users:
            self.stdout.write(f'  ID={u.id}')
            self.stdout.write(f'    username="{u.username}"')
            self.stdout.write(f'    type={type(u.username)}')
            self.stdout.write(f'    repr={repr(u.username)}')
            self.stdout.write(f'    len={len(u.username) if u.username else "None"}')
            self.stdout.write(f'    is_string={isinstance(u.username, str)}')
            self.stdout.write(f'    strip_len={len(u.username.strip()) if u.username else "None"}')
            
            # Test validation
            if u.username and isinstance(u.username, str) and len(u.username.strip()) > 0:
                self.stdout.write(self.style.SUCCESS('    ✓ PASS validation'))
            else:
                self.stdout.write(self.style.ERROR('    ✗ FAIL validation'))
