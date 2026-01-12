"""
Management command to check and fix users with invalid usernames
"""
from django.core.management.base import BaseCommand
from users.models import User


class Command(BaseCommand):
    help = 'Check and optionally fix users with invalid usernames'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Fix invalid usernames by setting default values',
        )

    def handle(self, *args, **options):
        self.stdout.write('Checking users data...\n')
        
        # Check for users with null or empty usernames
        invalid_users = User.objects.filter(
            username__isnull=True
        ) | User.objects.filter(
            username=''
        ) | User.objects.filter(
            username__regex=r'^\s*$'
        )
        
        count = invalid_users.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('✓ All users have valid usernames!'))
            return
        
        self.stdout.write(
            self.style.WARNING(f'Found {count} users with invalid usernames:\n')
        )
        
        for user in invalid_users:
            self.stdout.write(
                f'  - User ID {user.id}: '
                f'username="{user.username}" '
                f'email={user.email} '
                f'first_name={user.first_name} '
                f'last_name={user.last_name}'
            )
        
        if options['fix']:
            self.stdout.write('\nFixing invalid usernames...')
            fixed = 0
            for user in invalid_users:
                # Generate username from email or set default
                if user.email:
                    new_username = user.email.split('@')[0]
                    # Ensure unique
                    base_username = new_username
                    counter = 1
                    while User.objects.filter(username=new_username).exists():
                        new_username = f"{base_username}{counter}"
                        counter += 1
                else:
                    # Use user ID
                    new_username = f"user{user.id}"
                
                user.username = new_username
                user.save(update_fields=['username'])
                fixed += 1
                self.stdout.write(f'  ✓ Fixed user {user.id}: username -> "{new_username}"')
            
            self.stdout.write(
                self.style.SUCCESS(f'\n✓ Fixed {fixed} users!')
            )
        else:
            self.stdout.write(
                self.style.WARNING('\nRun with --fix flag to automatically fix these users')
            )
