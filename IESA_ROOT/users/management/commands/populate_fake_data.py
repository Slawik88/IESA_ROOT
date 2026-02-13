"""
Populate database with fake high-quality data for development and testing.
Focused on extreme sports, boxing, kitesurfing in Egypt, and sauna culture.
"""

from django.core.management.base import BaseCommand
from faker import Faker
import random
from datetime import timedelta
from django.utils import timezone

from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile

from users.models import User
from blog.models import Post, Event
from products.models import Product
from core.models import Partner, AssociationMember, President

fake = Faker(['en_US', 'de_DE', 'fr_FR'])


def create_fake_image(filename, width=600, height=400, color=(73, 109, 137)):
    """Create a simple in-memory image for demo content."""
    image = Image.new('RGB', (width, height), color=color)
    image_io = BytesIO()
    image.save(image_io, format='PNG')
    image_io.seek(0)
    return InMemoryUploadedFile(
        image_io, None, filename, 'image/png', image_io.getbuffer().nbytes, None
    )


def set_translations(obj, field, en, uk, fr, de):
    setattr(obj, field, en)
    setattr(obj, f"{field}_en", en)
    setattr(obj, f"{field}_uk", uk)
    setattr(obj, f"{field}_fr", fr)
    setattr(obj, f"{field}_de", de)


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

            # Create About IESA (President + Members)
            self.stdout.write(self.style.WARNING('👥 Creating About IESA section data...'))
            self.create_about_iesa()
            self.stdout.write(self.style.SUCCESS('✅ Created About IESA data\n'))

            # Create Partners
            self.stdout.write(self.style.WARNING('🤝 Creating partners...'))
            self.create_partners()
            self.stdout.write(self.style.SUCCESS('✅ Created partners\n'))

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
        Event.objects.all().delete()
        events = []
        
        templates = [
            {
                'title': {
                    'en': 'IESA Extreme Camp: Red Sea Edition',
                    'uk': 'IESA Екстрим-табір: видання Червоного моря',
                    'fr': 'Camp extrême IESA : Édition Mer Rouge',
                    'de': 'IESA-Extremcamp: Rotes-Meer-Edition',
                },
                'location': {
                    'en': 'Red Sea Coast, Egypt',
                    'uk': 'Узбережжя Червоного моря, Єгипет',
                    'fr': 'Côte de la mer Rouge, Égypte',
                    'de': 'Rotes Meer Küste, Ägypten',
                },
            },
            {
                'title': {
                    'en': 'Urban Boxing Bootcamp',
                    'uk': 'Міський боксерський буткемп',
                    'fr': 'Bootcamp de boxe urbaine',
                    'de': 'Urbanes Box-Bootcamp',
                },
                'location': {
                    'en': 'Geneva, Switzerland',
                    'uk': 'Женева, Швейцарія',
                    'fr': 'Genève, Suisse',
                    'de': 'Genf, Schweiz',
                },
            },
            {
                'title': {
                    'en': 'Adventure Week: Desert & Sea',
                    'uk': 'Тиждень пригод: пустеля і море',
                    'fr': 'Semaine d’aventure : désert et mer',
                    'de': 'Abenteuerwoche: Wüste & Meer',
                },
                'location': {
                    'en': 'Sinai Desert, Egypt',
                    'uk': 'Синайська пустеля, Єгипет',
                    'fr': 'Désert du Sinaï, Égypte',
                    'de': 'Sinai-Wüste, Ägypten',
                },
            },
            {
                'title': {
                    'en': 'IESA Leadership & Team Summit',
                    'uk': 'Саміт лідерства та команди IESA',
                    'fr': 'Sommet leadership & équipe IESA',
                    'de': 'IESA Leadership- & Team-Gipfel',
                },
                'location': {
                    'en': 'Zurich, Switzerland',
                    'uk': 'Цюрих, Швейцарія',
                    'fr': 'Zurich, Suisse',
                    'de': 'Zürich, Schweiz',
                },
            },
            {
                'title': {
                    'en': 'Coastal Water Sports Weekend',
                    'uk': 'Вікенд водних видів спорту на узбережжі',
                    'fr': 'Week-end sports nautiques',
                    'de': 'Wassersport-Wochenende an der Küste',
                },
                'location': {
                    'en': 'Soma Bay, Egypt',
                    'uk': 'Сома-Бей, Єгипет',
                    'fr': 'Soma Bay, Égypte',
                    'de': 'Soma Bay, Ägypten',
                },
            },
        ]

        lorem = {
            'en': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer posuere lorem at neque hendrerit, nec volutpat justo gravida.',
            'uk': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer posuere lorem at neque hendrerit, nec volutpat justo gravida.',
            'fr': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer posuere lorem at neque hendrerit, nec volutpat justo gravida.',
            'de': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer posuere lorem at neque hendrerit, nec volutpat justo gravida.',
        }

        for i in range(count):
            template = templates[i % len(templates)]
            title_en = template['title']['en']
            location_en = template['location']['en']
            if i >= len(templates):
                title_en = f"{title_en} #{i // len(templates) + 1}"

            start_date = timezone.now() + timedelta(days=random.randint(1, 120))
            event = Event.objects.create(
                title=title_en,
                description=lorem['en'],
                location=location_en,
                date=start_date,
                end_date=start_date + timedelta(days=random.randint(1, 7)),
                status='upcoming',
                image=create_fake_image(f"event_{i+1}.png", 1000, 600, color=(40, 90, 140))
            )
            set_translations(event, 'title', title_en, template['title']['uk'], template['title']['fr'], template['title']['de'])
            set_translations(event, 'description', lorem['en'], lorem['uk'], lorem['fr'], lorem['de'])
            set_translations(event, 'location', location_en, template['location']['uk'], template['location']['fr'], template['location']['de'])
            event.save()
            events.append(event)

        return events

    def create_about_iesa(self):
        """Create President and Association Members for About IESA section"""
        President.objects.all().delete()
        AssociationMember.objects.all().delete()

        lorem_en = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        lorem_uk = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        lorem_fr = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        lorem_de = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'

        president = President.objects.create(
            name='Alex Morgan',
            photo=create_fake_image('president.png', 600, 600, color=(80, 80, 120)),
            position='President',
            description=lorem_en,
        )
        set_translations(president, 'position', 'President', 'Президент', 'Président', 'Präsident')
        set_translations(president, 'description', lorem_en, lorem_uk, lorem_fr, lorem_de)
        president.save()

        members = [
            {
                'name': 'Sofia Laurent',
                'position': {'en': 'Operations Director', 'uk': 'Директор з операцій', 'fr': 'Directrice des opérations', 'de': 'Operationsleiterin'},
            },
            {
                'name': 'Daniel Weber',
                'position': {'en': 'Programs Lead', 'uk': 'Керівник програм', 'fr': 'Responsable des programmes', 'de': 'Programmleiter'},
            },
            {
                'name': 'Mila Kovalenko',
                'position': {'en': 'Community Manager', 'uk': 'Менеджер спільноти', 'fr': 'Responsable communauté', 'de': 'Community-Managerin'},
            },
            {
                'name': 'Noah Schmidt',
                'position': {'en': 'Partnerships Lead', 'uk': 'Керівник партнерств', 'fr': 'Responsable partenariats', 'de': 'Leiter Partnerschaften'},
            },
        ]

        for idx, member in enumerate(members, start=1):
            assoc = AssociationMember.objects.create(
                name=member['name'],
                photo=create_fake_image(f"member_{idx}.png", 600, 800, color=(90, 90, 140)),
                position=member['position']['en'],
                description=lorem_en,
            )
            set_translations(assoc, 'position', member['position']['en'], member['position']['uk'], member['position']['fr'], member['position']['de'])
            set_translations(assoc, 'description', lorem_en, lorem_uk, lorem_fr, lorem_de)
            assoc.save()

    def create_partners(self):
        """Create partners with translated descriptions"""
        Partner.objects.all().delete()

        lorem_en = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Curabitur vitae lorem ipsum, sit amet luctus ipsum.'
        lorem_uk = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Curabitur vitae lorem ipsum, sit amet luctus ipsum.'
        lorem_fr = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Curabitur vitae lorem ipsum, sit amet luctus ipsum.'
        lorem_de = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Curabitur vitae lorem ipsum, sit amet luctus ipsum.'

        partners = [
            {'name': 'AquaEdge Sports', 'category': 'sponsor', 'link': 'https://aquaedge.example.com'},
            {'name': 'PeakFlow Media', 'category': 'media', 'link': 'https://peakflow.example.com'},
            {'name': 'NorthLine Tech', 'category': 'tech', 'link': 'https://northline.example.com'},
            {'name': 'Summit Arena', 'category': 'venue', 'link': 'https://summitarena.example.com'},
            {'name': 'ActivePulse Foundation', 'category': 'other', 'link': 'https://activepulse.example.com'},
        ]

        for idx, partner in enumerate(partners, start=1):
            p = Partner.objects.create(
                name=partner['name'],
                description=lorem_en,
                link=partner['link'],
                category=partner['category'],
                logo=create_fake_image(f"partner_{idx}.png", 400, 240, color=(60, 120, 160))
            )
            set_translations(p, 'description', lorem_en, lorem_uk, lorem_fr, lorem_de)
            p.save()
