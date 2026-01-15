#!/usr/bin/env python
"""
MASSIVE FAKE DATA GENERATOR FOR IESA
=====================================
Создает полный набор тестовых данных для сайта:
- Суперюзер root
- Президент ассоциации
- Члены ассоциации
- Партнеры
- Пользователи
- Посты блога
- События
- Социальные сети

Запуск: python manage.py shell < populate_massive_data.py
Или: python populate_massive_data.py
"""

import os
import sys
import django
import random
from datetime import datetime, timedelta
from pathlib import Path

# Настройка Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import connection
from core.models import President, Partner, AssociationMember, SocialNetwork
from blog.models import Post, Event, Comment

User = get_user_model()

print("\n" + "="*70)
print("🚀 IESA MASSIVE FAKE DATA GENERATOR")
print("="*70)

# ============================================================
# УТИЛИТЫ
# ============================================================

def delete_all_data():
    """Удаление всех данных из БД (кроме миграций)"""
    print("\n🗑️  Удаляем старые данные...")
    
    # Удаляем в правильном порядке (сначала зависимые)
    models_to_clear = [
        ('Comment', Comment),
        ('Post', Post),
        ('Event', Event),
        ('SocialNetwork', SocialNetwork),
        ('AssociationMember', AssociationMember),
        ('Partner', Partner),
        ('President', President),
    ]
    
    for name, model in models_to_clear:
        try:
            count = model.objects.count()
            model.objects.all().delete()
            print(f"   ✓ {name}: удалено {count} записей")
        except Exception as e:
            print(f"   ⚠ {name}: {e}")
    
    # Удаляем всех пользователей
    try:
        count = User.objects.count()
        User.objects.all().delete()
        print(f"   ✓ Users: удалено {count} записей")
    except Exception as e:
        print(f"   ⚠ Users: {e}")

# ============================================================
# СОЗДАНИЕ СУПЕРЮЗЕРА
# ============================================================

def create_superuser():
    """Создание суперюзера root"""
    print("\n👤 Создаем суперюзера...")
    
    if User.objects.filter(username='root').exists():
        User.objects.filter(username='root').delete()
    
    user = User.objects.create_superuser(
        username='root',
        email='root@iesa.org',
        password='20041987',
        first_name='System',
        last_name='Administrator',
        is_verified=True
    )
    print(f"   ✓ Создан суперюзер: root (пароль: 20041987)")
    return user

# ============================================================
# СОЗДАНИЕ ПРЕЗИДЕНТА
# ============================================================

def create_president():
    """Создание президента ассоциации"""
    print("\n🎖️  Создаем президента...")
    
    president = President.objects.create(
        name="Dr. Alexander Volkov",
        position="President of IESA",
        description="""
        <p>As the President of the International Extreme Sports Association, I am honored to lead an organization that brings together passionate athletes, professionals, and enthusiasts from around the world.</p>
        
        <p><strong>Our mission</strong> is to promote safety, excellence, and innovation in extreme sports while building a global community that supports and inspires one another.</p>
        
        <p>Since founding IESA in 2020, we have grown to include over 50,000 members across 120 countries. Together, we are pushing the boundaries of what's possible in extreme sports.</p>
        
        <p><em>"The only limit is the one you set yourself."</em></p>
        """
    )
    print(f"   ✓ Президент: {president.name}")
    return president

# ============================================================
# СОЗДАНИЕ ЧЛЕНОВ АССОЦИАЦИИ
# ============================================================

MEMBERS_DATA = [
    {
        "name": "Maria Rodriguez",
        "position": "Vice President",
        "description": "Former Olympic snowboarder with 15 years of competitive experience. Maria oversees all sporting programs and athlete development initiatives at IESA. She has won 3 World Championships and continues to mentor young athletes worldwide."
    },
    {
        "name": "James Chen",
        "position": "Chief Technology Officer",
        "description": "MIT graduate and tech entrepreneur. James leads IESA's digital transformation, developing cutting-edge platforms for athlete tracking, event management, and community engagement. Previously worked at Google and SpaceX."
    },
    {
        "name": "Sophie Anderson",
        "position": "Director of Communications",
        "description": "Award-winning journalist and former ESPN correspondent. Sophie manages IESA's global media presence, partnerships with broadcasters, and social media strategy. She has covered extreme sports events in over 40 countries."
    },
    {
        "name": "Ahmed Hassan",
        "position": "Head of Safety & Standards",
        "description": "Dr. Hassan brings 20 years of experience in sports medicine and safety protocols. He develops and enforces safety standards for all IESA-sanctioned events, ensuring athlete welfare remains our top priority."
    },
    {
        "name": "Emma Thompson",
        "position": "Events Director",
        "description": "Professional event organizer with experience managing the X Games and Red Bull events. Emma coordinates IESA's calendar of 200+ annual events worldwide, from local competitions to international championships."
    },
    {
        "name": "Lucas Fernandez",
        "position": "Community Manager",
        "description": "Former professional skateboarder and social media influencer with 2M followers. Lucas builds and nurtures IESA's global community, organizing meetups, online challenges, and grassroots initiatives."
    },
    {
        "name": "Yuki Tanaka",
        "position": "International Relations",
        "description": "Diplomat and sports administrator. Yuki manages IESA's relationships with national federations, government bodies, and international sports organizations. Fluent in 5 languages."
    },
    {
        "name": "David Miller",
        "position": "Finance Director",
        "description": "CPA with 18 years in sports finance. David oversees IESA's $50M annual budget, sponsorship agreements, and financial sustainability programs. Previously CFO at two major sports leagues."
    },
]

def create_members():
    """Создание членов ассоциации"""
    print("\n👥 Создаем членов ассоциации...")
    
    members = []
    for data in MEMBERS_DATA:
        member = AssociationMember.objects.create(**data)
        members.append(member)
        print(f"   ✓ {member.name} - {member.position}")
    
    return members

# ============================================================
# СОЗДАНИЕ ПАРТНЕРОВ
# ============================================================

PARTNERS_DATA = [
    {
        "name": "Red Bull",
        "description": "Global energy drink company and major extreme sports sponsor. Partner since 2021.",
        "link": "https://www.redbull.com",
        "category": "sponsor"
    },
    {
        "name": "GoPro",
        "description": "Official action camera partner. Providing equipment for all IESA events and athletes.",
        "link": "https://www.gopro.com",
        "category": "tech"
    },
    {
        "name": "Nike",
        "description": "Athletic apparel and footwear sponsor. Exclusive provider of IESA team gear.",
        "link": "https://www.nike.com",
        "category": "sponsor"
    },
    {
        "name": "ESPN",
        "description": "Official broadcast partner for major IESA events and championships.",
        "link": "https://www.espn.com",
        "category": "media"
    },
    {
        "name": "Monster Energy",
        "description": "Energy drink sponsor supporting athlete nutrition and event catering.",
        "link": "https://www.monsterenergy.com",
        "category": "sponsor"
    },
    {
        "name": "Burton Snowboards",
        "description": "Premium snowboard equipment partner for winter sports programs.",
        "link": "https://www.burton.com",
        "category": "tech"
    },
    {
        "name": "X Games",
        "description": "Strategic partnership for co-hosting major extreme sports competitions.",
        "link": "https://www.xgames.com",
        "category": "media"
    },
    {
        "name": "Oakley",
        "description": "Eyewear and protective gear sponsor for IESA athletes worldwide.",
        "link": "https://www.oakley.com",
        "category": "tech"
    },
    {
        "name": "Marriott Hotels",
        "description": "Official accommodation partner for IESA events and athlete housing.",
        "link": "https://www.marriott.com",
        "category": "venue"
    },
    {
        "name": "DJI",
        "description": "Drone technology partner for aerial coverage of events.",
        "link": "https://www.dji.com",
        "category": "tech"
    },
    {
        "name": "Vans",
        "description": "Skateboarding and BMX footwear and apparel sponsor.",
        "link": "https://www.vans.com",
        "category": "sponsor"
    },
    {
        "name": "Eurosport",
        "description": "European broadcast partner for IESA events.",
        "link": "https://www.eurosport.com",
        "category": "media"
    },
]

def create_partners():
    """Создание партнеров"""
    print("\n🤝 Создаем партнеров...")
    
    partners = []
    for data in PARTNERS_DATA:
        partner = Partner.objects.create(**data)
        partners.append(partner)
        print(f"   ✓ {partner.name} ({partner.get_category_display()})")
    
    return partners

# ============================================================
# СОЗДАНИЕ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

USERS_DATA = [
    {"username": "john_rider", "first_name": "John", "last_name": "Rider", "email": "john@example.com"},
    {"username": "sarah_snow", "first_name": "Sarah", "last_name": "Snow", "email": "sarah@example.com"},
    {"username": "mike_skater", "first_name": "Mike", "last_name": "Peters", "email": "mike@example.com"},
    {"username": "emma_wings", "first_name": "Emma", "last_name": "Williams", "email": "emma@example.com"},
    {"username": "alex_extreme", "first_name": "Alex", "last_name": "Johnson", "email": "alex@example.com"},
    {"username": "nina_surf", "first_name": "Nina", "last_name": "Garcia", "email": "nina@example.com"},
    {"username": "tom_climb", "first_name": "Tom", "last_name": "Baker", "email": "tom@example.com"},
    {"username": "lisa_dive", "first_name": "Lisa", "last_name": "Chen", "email": "lisa@example.com"},
    {"username": "marcus_bmx", "first_name": "Marcus", "last_name": "Brown", "email": "marcus@example.com"},
    {"username": "anna_ski", "first_name": "Anna", "last_name": "Mueller", "email": "anna@example.com"},
]

def create_users():
    """Создание тестовых пользователей"""
    print("\n👤 Создаем пользователей...")
    
    users = []
    for data in USERS_DATA:
        user = User.objects.create_user(
            username=data["username"],
            email=data["email"],
            password="testpass123",
            first_name=data["first_name"],
            last_name=data["last_name"],
            is_verified=random.choice([True, True, True, False]),  # 75% verified
            activity_points=random.randint(50, 5000),
            total_posts=random.randint(0, 50),
            total_likes_received=random.randint(0, 500),
        )
        users.append(user)
        print(f"   ✓ {user.username} ({user.first_name} {user.last_name})")
    
    return users

# ============================================================
# СОЗДАНИЕ ПОСТОВ
# ============================================================

POSTS_DATA = [
    {
        "title": "My First BASE Jump Experience",
        "text": """
        <p>Last week, I finally took the plunge and completed my first BASE jump! After years of skydiving and months of specific BASE training, I was ready.</p>
        
        <p>The location was a 300-meter cliff in Norway. The view was breathtaking, but nothing compared to the feeling of stepping off the edge. Those 4 seconds of freefall felt like an eternity.</p>
        
        <h3>What I Learned</h3>
        <ul>
            <li>Mental preparation is just as important as physical training</li>
            <li>Trust your equipment and training</li>
            <li>The community support is incredible</li>
        </ul>
        
        <p>Can't wait for my next jump! 🪂</p>
        """
    },
    {
        "title": "Essential Gear for Mountain Biking",
        "text": """
        <p>After 10 years of downhill mountain biking, I've compiled my essential gear list for beginners.</p>
        
        <h3>Must-Have Equipment</h3>
        <ol>
            <li><strong>Full-face helmet</strong> - Non-negotiable for safety</li>
            <li><strong>Knee and elbow pads</strong> - You will fall, protect yourself</li>
            <li><strong>Quality gloves</strong> - Better grip, less fatigue</li>
            <li><strong>Proper shoes</strong> - Flat pedal or clipless, your choice</li>
        </ol>
        
        <p>Remember: good gear doesn't make you a good rider, but it keeps you safe while you learn!</p>
        """
    },
    {
        "title": "Surfing the Monster Waves of Nazaré",
        "text": """
        <p>Nazaré, Portugal. Home to some of the biggest waves on Earth. Last month, I had the opportunity to surf there during a swell that produced 50-foot faces.</p>
        
        <p>The preparation for big wave surfing is intense. Physical conditioning, breath-hold training, and mental fortitude all play crucial roles. But nothing truly prepares you for the moment when you're paddling into a wave that towers above you like a building.</p>
        
        <p>Respect the ocean. It will humble you.</p>
        """
    },
    {
        "title": "Wingsuit Flying: The Ultimate Freedom",
        "text": """
        <p>Flying. Actual human flight. That's what wingsuit flying feels like.</p>
        
        <p>I started skydiving 8 years ago, and wingsuit flying was always my goal. After 500+ jumps, I finally earned my wingsuit certification. The first flight changed everything I knew about the sport.</p>
        
        <h3>The Feeling</h3>
        <p>Imagine gliding through the air at 120 mph, feeling the wind support your body, with complete control over your direction. It's indescribable.</p>
        
        <p>If you're a skydiver dreaming of wingsuits - keep jumping, keep learning, your time will come.</p>
        """
    },
    {
        "title": "Ice Climbing in the Alps",
        "text": """
        <p>This winter, I tackled some of the most challenging ice routes in the French Alps. Here's what I learned.</p>
        
        <h3>Technical Challenges</h3>
        <p>Ice climbing requires a completely different skill set than rock climbing. The texture, temperature, and consistency of ice change constantly. What was solid in the morning might be unstable by afternoon.</p>
        
        <h3>Essential Skills</h3>
        <ul>
            <li>Reading ice conditions</li>
            <li>Efficient crampon technique</li>
            <li>Ice screw placement</li>
            <li>Managing cold and fatigue</li>
        </ul>
        
        <p>The Alps offer incredible ice climbing, but always respect the mountain and check conditions before climbing.</p>
        """
    },
    {
        "title": "Skateboarding at 40: Never Too Late",
        "text": """
        <p>I picked up a skateboard for the first time at 38. Two years later, I'm landing kickflips and competing in amateur events.</p>
        
        <p>Age is just a number. Yes, I heal slower than the teenagers at the park. Yes, I stretch more and take more breaks. But the joy of landing a new trick? That's ageless.</p>
        
        <h3>Tips for Older Beginners</h3>
        <ol>
            <li>Wear ALL the protective gear</li>
            <li>Progress slowly but consistently</li>
            <li>Find a supportive community</li>
            <li>Don't compare yourself to others</li>
        </ol>
        
        <p>It's never too late to pursue your passion!</p>
        """
    },
    {
        "title": "Training for Extreme Endurance Events",
        "text": """
        <p>Ultra-marathons, multi-day adventure races, extreme obstacle courses - these events push human limits. Here's my training philosophy.</p>
        
        <h3>The Four Pillars</h3>
        <ol>
            <li><strong>Physical conditioning</strong> - Build your base slowly</li>
            <li><strong>Mental toughness</strong> - Practice discomfort regularly</li>
            <li><strong>Nutrition strategy</strong> - Learn to fuel during effort</li>
            <li><strong>Recovery protocol</strong> - Rest is when you get stronger</li>
        </ol>
        
        <p>The body can handle far more than the mind believes. Train both.</p>
        """
    },
    {
        "title": "Safety First: Lessons from a Near-Miss",
        "text": """
        <p>Last month, I almost had a serious accident while paragliding. This post is about what went wrong and what I learned.</p>
        
        <p>I got complacent. After hundreds of flights, I started cutting corners on pre-flight checks. One day, I almost launched with a tangled line. My ground handler caught it just in time.</p>
        
        <h3>Never Skip</h3>
        <ul>
            <li>Pre-flight equipment checks</li>
            <li>Weather assessment</li>
            <li>Communication with ground crew</li>
            <li>Emergency procedure review</li>
        </ul>
        
        <p>Complacency kills. Stay vigilant, stay safe.</p>
        """
    },
]

def create_posts(users, admin):
    """Создание постов"""
    print("\n📝 Создаем посты...")
    
    posts = []
    all_authors = users + [admin]
    
    for data in POSTS_DATA:
        author = random.choice(all_authors)
        post = Post.objects.create(
            title=data["title"],
            text=data["text"],
            author=author,
            status='published',
            views_count=random.randint(50, 2000),
        )
        posts.append(post)
        print(f"   ✓ '{post.title[:40]}...' by {author.username}")
    
    return posts

# ============================================================
# СОЗДАНИЕ СОБЫТИЙ
# ============================================================

EVENTS_DATA = [
    {
        "title": "IESA World Championship 2026",
        "description": "The biggest extreme sports competition of the year! Athletes from 50+ countries will compete in skateboarding, BMX, surfing, and snowboarding disciplines.",
        "location": "Los Angeles, USA",
        "status": "upcoming",
        "max_participants": 500
    },
    {
        "title": "European Snowboard Cup",
        "description": "Annual snowboard competition featuring halfpipe, slopestyle, and big air events. Prize pool: $100,000.",
        "location": "Zermatt, Switzerland",
        "status": "upcoming",
        "max_participants": 200
    },
    {
        "title": "Asia Pacific Surf Championship",
        "description": "Premier surfing event in the Asia Pacific region. Come witness the best surfers battle epic waves.",
        "location": "Gold Coast, Australia",
        "status": "upcoming",
        "max_participants": 150
    },
    {
        "title": "Urban Skateboarding Festival",
        "description": "Street skateboarding competition + music festival + art exhibition. A celebration of skate culture!",
        "location": "Barcelona, Spain",
        "status": "upcoming",
        "max_participants": 300
    },
    {
        "title": "Mountain Bike World Tour - Stage 3",
        "description": "Downhill mountain biking at its finest. 5km of technical trails with 800m elevation drop.",
        "location": "Whistler, Canada",
        "status": "upcoming",
        "max_participants": 100
    },
    {
        "title": "Paragliding Safety Workshop",
        "description": "Free safety workshop for all IESA members. Topics: emergency procedures, weather assessment, equipment maintenance.",
        "location": "Online (Zoom)",
        "status": "upcoming",
        "max_participants": None
    },
    {
        "title": "BASE Jumping Symposium",
        "description": "Annual gathering of BASE jumping community. Talks, workshops, and networking.",
        "location": "Oslo, Norway",
        "status": "upcoming",
        "max_participants": 250
    },
    {
        "title": "IESA Annual Gala",
        "description": "Celebrate the year's achievements! Awards ceremony, live entertainment, and networking with industry leaders.",
        "location": "Monaco",
        "status": "upcoming",
        "max_participants": 400
    },
]

def create_events(admin):
    """Создание событий"""
    print("\n📅 Создаем события...")
    
    events = []
    now = timezone.now()
    
    for i, data in enumerate(EVENTS_DATA):
        # Разные даты в будущем
        event_date = now + timedelta(days=random.randint(30, 365))
        reg_deadline = event_date - timedelta(days=14)
        
        event = Event.objects.create(
            title=data["title"],
            description=data["description"],
            location=data["location"],
            date=event_date,
            end_date=event_date + timedelta(days=random.randint(1, 5)),
            status=data["status"],
            max_participants=data["max_participants"],
            registration_deadline=reg_deadline if data["max_participants"] else None,
            created_by=admin,
        )
        events.append(event)
        print(f"   ✓ '{event.title}' - {event.date.strftime('%d %b %Y')}")
    
    return events

# ============================================================
# СОЗДАНИЕ СОЦИАЛЬНЫХ СЕТЕЙ
# ============================================================

SOCIAL_NETWORKS = [
    {"name": "facebook", "url": "https://facebook.com/iesa.official"},
    {"name": "instagram", "url": "https://instagram.com/iesa_official"},
    {"name": "twitter", "url": "https://x.com/IESA_Sports"},
    {"name": "youtube", "url": "https://youtube.com/@IESASports"},
    {"name": "linkedin", "url": "https://linkedin.com/company/iesa-sports"},
    {"name": "telegram", "url": "https://t.me/iesa_community"},
    {"name": "discord", "url": "https://discord.gg/iesa"},
    {"name": "tiktok", "url": "https://tiktok.com/@iesa_sports"},
]

def create_social_networks():
    """Создание социальных сетей"""
    print("\n🌐 Создаем социальные сети...")
    
    networks = []
    for i, data in enumerate(SOCIAL_NETWORKS):
        network = SocialNetwork.objects.create(
            name=data["name"],
            url=data["url"],
            is_active=True,
            order=i
        )
        networks.append(network)
        print(f"   ✓ {network.get_name_display()}: {network.url}")
    
    return networks

# ============================================================
# MAIN
# ============================================================

def main():
    """Основная функция"""
    print("\n⚡ Начинаем генерацию данных...")
    
    # 1. Удаляем старые данные
    delete_all_data()
    
    # 2. Создаем суперюзера
    admin = create_superuser()
    
    # 3. Создаем президента
    president = create_president()
    
    # 4. Создаем членов ассоциации
    members = create_members()
    
    # 5. Создаем партнеров
    partners = create_partners()
    
    # 6. Создаем пользователей
    users = create_users()
    
    # 7. Создаем посты
    posts = create_posts(users, admin)
    
    # 8. Создаем события
    events = create_events(admin)
    
    # 9. Создаем социальные сети
    networks = create_social_networks()
    
    # Итоги
    print("\n" + "="*70)
    print("✅ ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print("="*70)
    print(f"""
    📊 СТАТИСТИКА:
    ├── Суперюзер: root (пароль: 20041987)
    ├── Президент: 1
    ├── Члены ассоциации: {len(members)}
    ├── Партнеры: {len(partners)}
    ├── Пользователи: {len(users)}
    ├── Посты: {len(posts)}
    ├── События: {len(events)}
    └── Социальные сети: {len(networks)}
    """)
    print("="*70)
    print("🎉 Данные успешно созданы!")
    print("   Логин: root")
    print("   Пароль: 20041987")
    print("="*70 + "\n")

if __name__ == '__main__':
    main()
