"""
Management command to create Partners group and set up permissions
Run: python manage.py setup_partners_group
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from users.models import User, Partner, Visit


class Command(BaseCommand):
    help = 'Create Partners group and assign necessary permissions'

    def handle(self, *args, **options):
        # Create or get Partners group
        partners_group, created = Group.objects.get_or_create(name='Partners')
        
        if created:
            self.stdout.write(self.style.SUCCESS('✅ Created "Partners" group'))
        else:
            self.stdout.write(self.style.WARNING('⚠️ "Partners" group already exists'))
        
        # Get content types
        visit_ct = ContentType.objects.get_for_model(Visit)
        partner_ct = ContentType.objects.get_for_model(Partner)
        user_ct = ContentType.objects.get_for_model(User)
        
        # Define permissions partners should have
        permissions_to_add = [
            # Visit permissions
            Permission.objects.get(content_type=visit_ct, codename='add_visit'),
            Permission.objects.get(content_type=visit_ct, codename='view_visit'),
            # Partner permissions (view own profile)
            Permission.objects.get(content_type=partner_ct, codename='view_partner'),
            # User permissions (search members)
            Permission.objects.get(content_type=user_ct, codename='view_user'),
        ]
        
        # Add permissions to group
        for perm in permissions_to_add:
            partners_group.permissions.add(perm)
            self.stdout.write(f'  Added permission: {perm.codename}')
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Partners group configured with {len(permissions_to_add)} permissions'))
        self.stdout.write(self.style.SUCCESS('✅ Partners can now log visits and search members'))
