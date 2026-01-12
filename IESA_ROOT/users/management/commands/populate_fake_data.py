"""
Populate database with fake high-quality data for development and testing.
Focused on extreme sports, boxing, kitesurfing in Egypt, and sauna culture.
"""

from django.core.management.base import BaseCommand
from faker import Faker
import random
from datetime import timedelta
from django.utils import timezone

from users.models import User
from blog.models import Post, Event
from products.models import Product

fake = Faker(['en_US', 'de_DE', 'fr_FR'])


class Command(BaseCommand):
    help = 'Populate database with fake data for development'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=10, help='Number of users to create')
        parser.add_argument('--posts', type=int, default=15, help='Number of blog posts to create')
        parser.add_argument('--products', type=int, default=20, help='Number of products to create')
        parser.add_argument('--events', type=int, default=12, help='Number of events to create')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Starting data population...\n'))
        
        num_users = options['users']
        num_posts = options['posts']
        num_products = options['products']
        num_events = options['events']

        try:
            # Create users
            self.stdout.write(self.style.WARNING(f'👥 Creating {num_users} users...'))
            users = self.create_users(num_users)
            self.stdout.write(self.style.SUCCESS(f'✅ Created {len(users)} users\n'))

            # Create blog posts
            self.stdout.write(self.style.WARNING(f'📝 Creating {num_posts} blog posts...'))
            posts = self.create_posts(num_posts, users)
            self.stdout.write(self.style.SUCCESS(f'✅ Created {len(posts)} posts\n'))

            # Create products
            self.stdout.write(self.style.WARNING(f'🛍️ Creating {num_products} products...'))
            products = self.create_products(num_products)
            self.stdout.write(self.style.SUCCESS(f'✅ Created {len(products)} products\n'))

            # Create events
            self.stdout.write(self.style.WARNING(f'📅 Creating {num_events} events...'))
            events = self.create_events(num_events)
            self.stdout.write(self.style.SUCCESS(f'✅ Created {len(events)} events\n'))

            self.stdout.write(self.style.SUCCESS('\n✨ Data population completed successfully!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error: {str(e)}'))
            import traceback
            traceback.print_exc()

    def create_users(self, count):
        """Create fake users"""
        users = []
        
        for i in range(count):
            username = f"athlete_{i+1}"
            if User.objects.filter(username=username).exists():
                users.append(User.objects.get(username=username))
                continue

            user = User.objects.create_user(
                username=username,
                email=fake.email(),
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                is_staff=False
            )

            user.bio = random.choice([
                "Passionate kitesurfer from Egypt 🪁",
                "Professional boxer and fitness enthusiast 🥊",
                "Adventure traveler and extreme sports lover 🚀",
                "Sauna culture enthusiast from Nordic region 🧖",
                "Multi-sport athlete and community organizer 💪",
            ])
            user.country = random.choice(['Egypt', 'Switzerland', 'Germany', 'France', 'UK'])
            user.location = random.choice(['Red Sea', 'Geneva', 'Berlin', 'Paris', 'Cairo'])
            user.save()
            users.append(user)

        return users

    def create_posts(self, count, users):
        """Create fake blog posts"""
        posts = []
        
        topics = [
            ('Best Kitesurfing Spots in Egypt\'s Red Sea', '<p>Discover Egypt\'s top kitesurfing locations from Dahab to Soma Bay.</p>'),
            ('Boxing Training Essentials', '<p>Master the fundamentals of boxing with our comprehensive guide.</p>'),
            ('Sauna Culture Across Europe', '<p>Explore authentic sauna traditions from Finland to Russia.</p>'),
            ('Ultimate Egypt Adventure Guide', '<p>Beyond the pyramids - explore Egypt\'s adventure sports scene.</p>'),
            ('Women in Extreme Sports', '<p>Celebrating female athletes pushing boundaries worldwide.</p>'),
            ('Professional Boxing Techniques', '<p>Advanced techniques from professional fighters.</p>'),
            ('Kitesurfing Wave Riding Guide', '<p>Master advanced wave selection and positioning techniques.</p>'),
            ('Health Benefits of Sauna Use', '<p>Scientific research on sauna benefits for physical health.</p>'),
            ('Multi-Sport Adventure Trips', '<p>Combine kitesurfing, hiking and diving perfectly.</p>'),
            ('Building Global Sports Communities', '<p>How IESA connects athletes worldwide.</p>'),
        ]

        for i in range(count):
            title, content = topics[i % len(topics)]
            if i >= len(topics):
                title = f"{title} - Part {i // len(topics) + 1}"
            
            if Post.objects.filter(title=title).exists():
                posts.append(Post.objects.get(title=title))
                continue

            post = Post.objects.create(
                title=title,
                text=content,
                author=random.choice(users),
                status='published',
                created_at=timezone.now() - timedelta(days=random.randint(1, 60))
            )
            posts.append(post)

        return posts

    def create_products(self, count):
        """Create fake products"""
        products = []
        
        items = [
            ('Professional Kitesurfing Board', 600),
            ('Kitesurfing Kite 17m', 900),
            ('Neoprene Wetsuit 3mm', 180),
            ('Professional Boxing Gloves', 130),
            ('Heavy Bag 100lb', 300),
            ('IESA Athletic Hoodie', 75),
            ('Compression Sports Shorts', 50),
            ('Technical Running Tee', 35),
            ('Sauna Essential Oils Kit', 60),
            ('Recovery Foam Roller', 65),
            ('Massage Gun Pro', 220),
            ('Carbon Fiber Kite Board', 750),
        ]

        for i in range(count):
            name, base_price = items[i % len(items)]
            if i >= len(items):
                name = f"{name} - Edition {i // len(items) + 1}"
            
            if Product.objects.filter(name=name).exists():
                products.append(Product.objects.get(name=name))
                continue

            product = Product.objects.create(
                name=name,
                description=f'High-quality {name} for athletes and enthusiasts.',
                price=base_price + random.uniform(-50, 150)
            )
            products.append(product)

        return products

    def create_events(self, count):
        """Create fake events"""
        events = []
        
        templates = [
            ('Egypt Kitesurfing Championship 2024', 'Red Sea, Egypt'),
            ('International Boxing Tournament', 'Geneva, Switzerland'),
            ('Nordic Sauna Culture Workshop', 'Helsinki, Finland'),
            ('Summer Extreme Sports Festival', 'Multiple Locations'),
            ('Boxing Training Camp - Advanced', 'Berlin, Germany'),
            ('Desert Adventure Expedition', 'Egyptian Desert'),
            ('Women in Extreme Sports Conference', 'Paris, France'),
            ('Community Meetup - Beginners', 'Various Cities'),
            ('Professional Kitesurfing Seminar', 'Red Sea, Egypt'),
            ('Annual IESA Awards Gala', 'Zurich, Switzerland'),
        ]

        for i in range(count):
            title, location = templates[i % len(templates)]
            if i >= len(templates):
                title = f"{title} - Event {i // len(templates) + 1}"
            
            if Event.objects.filter(title=title).exists():
                events.append(Event.objects.get(title=title))
                continue

            start_date = timezone.now() + timedelta(days=random.randint(1, 120))
            event = Event.objects.create(
                title=title,
                description=f'{title} - Join us for an incredible experience!',
                location=location,
                date=start_date,
                end_date=start_date + timedelta(days=random.randint(1, 7))
            )
            events.append(event)

        return events
