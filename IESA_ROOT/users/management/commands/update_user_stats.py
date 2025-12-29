from django.core.management.base import BaseCommand
from users.models import User

class Command(BaseCommand):
    help = 'Update statistics for all users'

    def handle(self, *args, **options):
        users = User.objects.all()
        total = users.count()
        
        self.stdout.write(f'Updating statistics for {total} users...')
        
        for index, user in enumerate(users, 1):
            user.update_statistics()
            if index % 10 == 0:
                self.stdout.write(f'Processed {index}/{total} users')
        
        self.stdout.write(self.style.SUCCESS(f'Successfully updated statistics for {total} users'))
