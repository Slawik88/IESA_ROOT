"""
Test global search query
"""
from django.core.management.base import BaseCommand
from users.models import User
from blog.models import Post, Event
from core.models import Partner
from django.db.models import Q


class Command(BaseCommand):
    help = 'Test global search query'

    def add_arguments(self, parser):
        parser.add_argument('query', type=str, help='Search query to test')

    def handle(self, *args, **options):
        normalized_q = options['query']
        
        self.stdout.write(self.style.SUCCESS(f'\n=== Testing search for: "{normalized_q}" ===\n'))
        
        # Test Users
        self.stdout.write(self.style.WARNING('--- USERS ---'))
        users = User.objects.filter(
            Q(username__icontains=normalized_q) |
            Q(first_name__icontains=normalized_q) |
            Q(last_name__icontains=normalized_q) |
            Q(email__icontains=normalized_q)
        ).exclude(
            Q(username__isnull=True) | 
            Q(username='') | 
            Q(username__regex=r'^\s*$')
        ).filter(
            username__isnull=False
        ).exclude(
            username=''
        ).order_by('-is_verified', 'username')[:20]
        
        self.stdout.write(f'Query returned {users.count()} users:')
        for user in users:
            status = '✓' if (user.username and len(user.username.strip()) > 0) else '✗'
            self.stdout.write(f'  {status} ID={user.id} username="{user.username}" email={user.email}')
        
        # Test Posts
        self.stdout.write(self.style.WARNING('\n--- POSTS ---'))
        posts = Post.objects.filter(
            Q(title__icontains=normalized_q) |
            Q(text__icontains=normalized_q),
            status='published'
        )[:10]
        
        self.stdout.write(f'Query returned {posts.count()} posts:')
        for post in posts:
            status = '✓' if (post.pk is not None and post.pk != '') else '✗'
            self.stdout.write(f'  {status} ID={post.pk} title="{post.title[:50]}"')
        
        # Test Events
        self.stdout.write(self.style.WARNING('\n--- EVENTS ---'))
        events = Event.objects.filter(
            Q(title__icontains=normalized_q) |
            Q(description__icontains=normalized_q)
        )[:10]
        
        self.stdout.write(f'Query returned {events.count()} events:')
        for event in events:
            status = '✓' if (event.pk is not None and event.pk != '') else '✗'
            self.stdout.write(f'  {status} ID={event.pk} title="{event.title[:50]}"')
        
        # Test Partners
        self.stdout.write(self.style.WARNING('\n--- PARTNERS ---'))
        partners = Partner.objects.filter(
            Q(name__icontains=normalized_q) |
            Q(description__icontains=normalized_q)
        )[:10]
        
        self.stdout.write(f'Query returned {partners.count()} partners:')
        for partner in partners:
            status = '✓' if (partner.pk is not None and partner.pk != '') else '✗'
            self.stdout.write(f'  {status} ID={partner.pk} name="{partner.name[:50]}"')
        
        self.stdout.write(self.style.SUCCESS('\n=== Test completed ===\n'))
