"""
Script to populate the database with fake data for testing
Run with: python manage.py shell < populate_fake_data.py
"""

import os
import django
from io import BytesIO
from PIL import Image

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

from django.contrib.auth import get_user_model
from blog.models import Post, Comment, Event, Like, EventRegistration
from core.models import Partner, AssociationMember
from products.models import Product
from gallery.models import Photo
from notifications.models import Notification
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

def create_fake_image(filename, width=200, height=200):
    """Create a fake image for testing"""
    image = Image.new('RGB', (width, height), color=(73, 109, 137))
    image_io = BytesIO()
    image.save(image_io, format='PNG')
    image_io.seek(0)
    return InMemoryUploadedFile(image_io, None, filename, 'image/png', image_io.getbuffer().nbytes, None)

print("Starting fake data population...")

# Create regular users
users_data = [
    ('alice', 'Alice Smith', 'alice@example.com', 'password123'),
    ('bob', 'Bob Johnson', 'bob@example.com', 'password123'),
    ('charlie', 'Charlie Brown', 'charlie@example.com', 'password123'),
    ('diana', 'Diana Prince', 'diana@example.com', 'password123'),
    ('evan', 'Evan Lee', 'evan@example.com', 'password123'),
]

users = {}
for username, full_name, email, password in users_data:
    if not User.objects.filter(username=username).exists():
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=full_name.split()[0],
            last_name=full_name.split()[1] if len(full_name.split()) > 1 else '',
            is_verified=True
        )
        users[username] = user
        print(f"✓ Created user: {username}")

# Get root user
root = User.objects.get(username='root')

# Create Partners
partners_data = [
    {
        'name': 'SportTech Solutions',
        'description': 'Leading technology provider for sports analytics and management platforms. We help sports organizations streamline operations and improve athlete performance through innovative tech solutions.',
        'link': 'https://sporttech.example.com'
    },
    {
        'name': 'Elite Fitness Co',
        'description': 'Premium fitness equipment manufacturer specializing in high-performance gym equipment for professional athletes and training facilities.',
        'link': 'https://elitefitness.example.com'
    },
    {
        'name': 'Performance Nutrition',
        'description': 'Nutritional supplements and sports drinks designed specifically for athletes. Certified and trusted by sports associations worldwide.',
        'link': 'https://perfnutrition.example.com'
    },
    {
        'name': 'Global Sports Media',
        'description': 'International sports broadcasting network covering major sporting events across multiple continents and platforms.',
        'link': 'https://globalsportsmedia.example.com'
    },
    {
        'name': 'Youth Academy Fund',
        'description': 'Non-profit organization dedicated to funding youth sports programs and developing the next generation of athletic talent.',
        'link': 'https://youthacademyfund.example.com'
    },
]

for partner_data in partners_data:
    if not Partner.objects.filter(name=partner_data['name']).exists():
        partner = Partner.objects.create(
            name=partner_data['name'],
            description=partner_data['description'],
            link=partner_data['link'],
            logo=create_fake_image(f"{partner_data['name'].lower().replace(' ', '_')}_logo.png", 200, 200)
        )
        print(f"✓ Created partner: {partner_data['name']}")

# Create Association Members
members_data = [
    {
        'name': 'Dr. John Anderson',
        'position': 'Vice President',
        'description': 'Former Olympic coach with 20+ years of experience in athletic development and international sports management.'
    },
    {
        'name': 'Prof. Maria Garcia',
        'position': 'Secretary General',
        'description': 'Sports scientist and researcher with expertise in sports sociology and organizational development.'
    },
    {
        'name': 'James Chen',
        'position': 'Treasurer',
        'description': 'Financial expert specializing in sports business and international federation management.'
    },
    {
        'name': 'Sophie Martin',
        'position': 'Communications Director',
        'description': 'PR professional with extensive experience in sports marketing and media relations.'
    },
]

for member_data in members_data:
    if not AssociationMember.objects.filter(name=member_data['name']).exists():
        member = AssociationMember.objects.create(
            name=member_data['name'],
            position=member_data['position'],
            description=member_data['description'],
            photo=create_fake_image(f"{member_data['name'].lower().replace(' ', '_')}_photo.png", 300, 400)
        )
        print(f"✓ Created member: {member_data['name']}")

# Create Products
products_data = [
    {
        'name': 'Professional Training Bundle',
        'description': 'Complete training program for beginners including coaching materials, nutrition guide, and progress tracking tools.',
        'price': 49.99
    },
    {
        'name': 'Advanced Analytics Dashboard',
        'description': 'Real-time performance analytics platform for sports teams with detailed statistics and player comparisons.',
        'price': 199.99
    },
    {
        'name': 'Elite Certification Course',
        'description': 'Comprehensive online certification course for sports professionals covering coaching, nutrition, and injury prevention.',
        'price': 299.99
    },
    {
        'name': 'Community Membership',
        'description': 'Annual membership providing access to exclusive events, networking opportunities, and member-only resources.',
        'price': 99.99
    },
]

for product_data in products_data:
    if not Product.objects.filter(name=product_data['name']).exists():
        product = Product.objects.create(
            name=product_data['name'],
            description=product_data['description'],
            price=product_data['price'],
            image=create_fake_image(f"{product_data['name'].lower().replace(' ', '_')}.png", 400, 300)
        )
        print(f"✓ Created product: {product_data['name']}")

# Create Blog Posts
posts_data = [
    {
        'title': 'The Future of Sports Technology',
        'text': '<h2>Introduction</h2><p>Sports technology is revolutionizing how athletes train and compete. From wearables to AI analytics, innovations are transforming the industry.</p><h2>Key Trends</h2><ul><li>Artificial Intelligence in coaching</li><li>Wearable performance tracking</li><li>Virtual reality training</li><li>Real-time biometric monitoring</li></ul><p>These technologies are making sports more competitive and data-driven than ever before.</p>',
        'author': root,
    },
    {
        'title': 'Youth Development Best Practices',
        'text': '<h2>Building Champions</h2><p>Developing young athletes requires a comprehensive approach combining technical training, mental preparation, and proper nutrition.</p><h2>Key Principles</h2><p>1. Start with fundamentals</p><p>2. Personalize training programs</p><p>3. Focus on injury prevention</p><p>4. Develop mental resilience</p>',
        'author': users.get('alice') or root,
    },
    {
        'title': 'Nutrition Guide for Athletes',
        'text': '<h2>Fueling Performance</h2><p>Proper nutrition is essential for athletic performance and recovery. Here\'s what athletes need to know.</p><h2>Macronutrients</h2><p><strong>Carbohydrates:</strong> Primary energy source</p><p><strong>Proteins:</strong> Muscle repair and growth</p><p><strong>Fats:</strong> Hormone production and energy</p>',
        'author': users.get('bob') or root,
    },
    {
        'title': 'Breaking Records: Mental Strategies',
        'text': '<h2>The Mental Game</h2><p>Elite athletes understand that success is 90% mental. Here are proven strategies for peak performance.</p><h2>Techniques</h2><p>- Visualization and mental rehearsal</p><p>- Goal setting and motivation</p><p>- Stress management and focus</p>',
        'author': users.get('charlie') or root,
    },
    {
        'title': 'Global Sports Events Calendar 2025',
        'text': '<h2>Major Events Coming Up</h2><p>2025 promises to be an exciting year for sports around the world. Mark your calendars for these major events.</p><p>From international championships to continental tournaments, athletes and fans have much to look forward to.</p>',
        'author': root,
    },
]

posts = []
for post_data in posts_data:
    if not Post.objects.filter(title=post_data['title']).exists():
        post = Post.objects.create(
            title=post_data['title'],
            text=post_data['text'],
            author=post_data['author'],
            status='published',
            preview_image=create_fake_image(f"{post_data['title'].lower()[:20].replace(' ', '_')}.png", 600, 400)
        )
        posts.append(post)
        print(f"✓ Created post: {post_data['title']}")

# Create Events
events_data = [
    {
        'title': 'Annual Sports Summit 2025',
        'description': 'Join us for the annual international sports summit featuring keynote speakers, workshops, and networking opportunities.',
        'location': 'Geneva Convention Center',
        'date': timezone.now() + timedelta(days=30)
    },
    {
        'title': 'Youth Championship Finals',
        'description': 'Exciting finals of the youth championship tournament showcasing the best young athletes from around the world.',
        'location': 'Olympic Stadium',
        'date': timezone.now() + timedelta(days=45)
    },
    {
        'title': 'Advanced Coaching Masterclass',
        'description': 'Exclusive masterclass with Olympic coaches on advanced training techniques and athlete development.',
        'location': 'Training Academy',
        'date': timezone.now() + timedelta(days=20)
    },
]

for event_data in events_data:
    if not Event.objects.filter(title=event_data['title']).exists():
        event = Event.objects.create(
            title=event_data['title'],
            description=event_data['description'],
            location=event_data['location'],
            date=event_data['date'],
            image=create_fake_image(f"{event_data['title'].lower()[:20].replace(' ', '_')}.png", 800, 400)
        )
        print(f"✓ Created event: {event_data['title']}")

# Create Comments on posts
if posts:
    comment_texts = [
        "Great insights! This really helped me understand the topic better.",
        "Excellent article. Looking forward to more posts like this!",
        "Very informative and well-written. Thank you for sharing!",
        "This is exactly what I was looking for. Highly recommended!",
        "Well explained with great examples. Keep up the good work!",
    ]
    
    for i, post in enumerate(posts[:3]):
        for j, user in enumerate([users.get('alice'), users.get('bob'), users.get('charlie')]):
            if user and j < len(comment_texts):
                if not Comment.objects.filter(post=post, author=user).exists():
                    Comment.objects.create(
                        post=post,
                        author=user,
                        text=comment_texts[j]
                    )
                    print(f"✓ Created comment by {user.username} on '{post.title}'")

# Create Likes on posts
for post in posts:
    for user in [users.get('alice'), users.get('bob'), users.get('diana')]:
        if user:
            if not Like.objects.filter(post=post, user=user).exists():
                Like.objects.create(post=post, user=user)
                print(f"✓ {user.username} liked '{post.title}'")

# Update user statistics
for user in list(users.values()) + [root]:
    user.update_statistics()
    print(f"✓ Updated statistics for {user.username} - Level: {user.get_achievement_level()}")

print("\n" + "="*50)
print("Fake data population completed successfully!")
print("="*50)
print("\nSummary:")
print(f"✓ Created {len(users_data)} users")
print(f"✓ Created {Partner.objects.count()} partners")
print(f"✓ Created {AssociationMember.objects.count()} members")
print(f"✓ Created {Product.objects.count()} products")
print(f"✓ Created {Post.objects.count()} blog posts")
print(f"✓ Created {Event.objects.count()} events")
print(f"✓ Created {Comment.objects.count()} comments")
print(f"✓ Created {Like.objects.count()} likes")
print("\nSuper user: root / 20041987")
print("\nYou can now log in to the admin panel at /admin/")
