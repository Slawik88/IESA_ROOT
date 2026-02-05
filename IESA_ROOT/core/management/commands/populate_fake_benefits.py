"""
Django management command для создания фейковых бенефитов.
Используется: python manage.py populate_fake_benefits
"""

from django.core.management.base import BaseCommand
from core.models import MemberBenefit


class Command(BaseCommand):
    help = 'Создает фейковые бенефиты для членов ассоциации'
    
    def handle(self, *args, **options):
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.WARNING("СОЗДАНИЕ ФЕЙКОВЫХ БЕНЕФИТОВ ДЛЯ ЧЛЕНОВ АССОЦИАЦИИ"))
        self.stdout.write("=" * 80)
        
        # Шаг 1: Удалить текущие
        self.stdout.write("\n📋 Шаг 1: Удаление текущих бенефитов...")
        deleted_count, _ = MemberBenefit.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f"✅ Удалено {deleted_count} бенефитов"))
        
        # Шаг 2: Создать новые
        self.stdout.write("\n📋 Шаг 2: Создание новых фейковых бенефитов...\n")
        
        benefits_data = [
            {
                'title': 'Premium Insurance Package',
                'category': 'medical',
                'description': 'Comprehensive health insurance with coverage up to €500,000. Includes dental care, vision coverage, and emergency evacuation.',
                'discount_info': 'Up to 35% savings on premium',
                'icon': 'fas fa-heart',
                'color': 'danger',
                'partner_info': 'Allianz Switzerland & Swiss Medical',
                'terms': 'Available for all active members. Coverage starts immediately after enrollment.',
                'order': 1,
            },
            {
                'title': 'Luxury Hotel Network',
                'category': 'travel',
                'description': 'Exclusive access to 5-star hotels worldwide. Enjoy curated travel experiences at member-only rates in over 150 countries.',
                'discount_info': '30-45% off room rates',
                'icon': 'fas fa-hotel',
                'color': 'info',
                'partner_info': 'Luxury Hotel Group & Marriott Bonvoy',
                'terms': 'Book through the member portal. Complimentary room upgrades available.',
                'order': 2,
            },
            {
                'title': 'Executive Business Lounge Access',
                'category': 'events',
                'description': 'Priority access to exclusive networking events and business lounges. Monthly VIP events with industry leaders and celebrities.',
                'discount_info': 'Free access + 2 guest passes',
                'icon': 'fas fa-crown',
                'color': 'warning',
                'partner_info': 'Global Business Club',
                'terms': 'Valid membership card required. Reservations can be made 30 days in advance.',
                'order': 3,
            },
            {
                'title': 'Financial Advisory Services',
                'category': 'services',
                'description': 'Personalized wealth management and investment advisory from certified financial professionals. Portfolio optimization and tax planning included.',
                'discount_info': '50% off advisory fees',
                'icon': 'fas fa-chart-line',
                'color': 'success',
                'partner_info': 'Rothschild & Co Private Banking',
                'terms': 'Minimum €100,000 portfolio. Quarterly reviews and unlimited consultations.',
                'order': 4,
            },
            {
                'title': 'Premium Shopping & Retail Discounts',
                'category': 'shopping',
                'description': 'Exclusive partnerships with luxury brands and major retailers. Get premium products at exceptional prices with personal shopping assistance.',
                'discount_info': '20-50% off selected items',
                'icon': 'fas fa-shopping-bag',
                'color': 'primary',
                'partner_info': 'Luxury Brands Alliance & Department Stores',
                'terms': 'Show member card at checkout. Online shopping also eligible with promo code.',
                'order': 5,
            },
            {
                'title': 'Advanced Professional Education',
                'category': 'education',
                'description': 'Access to exclusive online courses and certifications from leading universities. Master new skills with world-class instructors.',
                'discount_info': 'Free access to premium courses',
                'icon': 'fas fa-graduation-cap',
                'color': 'info',
                'partner_info': 'Stanford Online, MIT OpenCourseWare, Coursera Pro',
                'terms': 'Unlimited course access. Certificates available upon completion.',
                'order': 6,
            },
            {
                'title': 'Concierge Service 24/7',
                'category': 'services',
                'description': 'Round-the-clock personal assistant service. Restaurant reservations, travel arrangements, event planning, and emergency support.',
                'discount_info': 'Complimentary service',
                'icon': 'fas fa-concierge-bell',
                'color': 'secondary',
                'partner_info': 'Elite Concierge International',
                'terms': 'Call or email anytime. Priority response within 4 hours.',
                'order': 7,
            },
            {
                'title': 'Automotive Privilege Program',
                'category': 'shopping',
                'description': 'Special discounts on luxury vehicles, maintenance, and insurance. Exclusive access to test drives and automotive events.',
                'discount_info': '15-25% off services',
                'icon': 'fas fa-car',
                'color': 'dark',
                'partner_info': 'Mercedes-Benz, BMW, Porsche Switzerland',
                'terms': 'Valid for authorized dealerships. Additional discounts for new members.',
                'order': 8,
            },
            {
                'title': 'Wellness & Spa Membership',
                'category': 'services',
                'description': 'Unlimited access to premium fitness centers, spas, and wellness retreats. Personal training and nutrition consultations included.',
                'discount_info': '40% off memberships',
                'icon': 'fas fa-spa',
                'color': 'success',
                'partner_info': 'Swiss Wellness Centers & Spa Resorts',
                'terms': 'Annual membership. Facilities available worldwide in partner locations.',
                'order': 9,
            },
            {
                'title': 'Legal Protection Plan',
                'category': 'medical',
                'description': 'Comprehensive legal advice and representation. Cover for civil disputes, inheritance planning, and contract review.',
                'discount_info': '60% off legal fees',
                'icon': 'fas fa-gavel',
                'color': 'info',
                'partner_info': 'Swiss Law Associates',
                'terms': 'Initial consultation free. Subsequent services at member rates.',
                'order': 10,
            },
            {
                'title': 'Tech & Digital Innovation Access',
                'category': 'education',
                'description': 'Early access to new technology products and innovation labs. Exclusive tech summits and beta testing opportunities.',
                'discount_info': 'Free premium tech subscriptions',
                'icon': 'fas fa-laptop',
                'color': 'primary',
                'partner_info': 'Apple, Microsoft, Google Switzerland',
                'terms': 'Product availability varies. Pre-order access 30 days early.',
                'order': 11,
            },
            {
                'title': 'Wine & Gastronomy Collection',
                'category': 'other',
                'description': 'Monthly curated wine selections and exclusive access to Michelin-starred restaurants. Private dining experiences available.',
                'discount_info': '25% off wine purchases',
                'icon': 'fas fa-wine-glass',
                'color': 'warning',
                'partner_info': 'Premium Vineyard Alliance & Michelin Restaurants',
                'terms': 'Subscription available. Exclusive dinners require 2 weeks advance booking.',
                'order': 12,
            },
        ]
        
        for benefit_data in benefits_data:
            benefit = MemberBenefit.objects.create(**benefit_data)
            self.stdout.write(f"  ✅ {benefit.title}")
        
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS(f"✨ ГОТОВО! Всего создано {len(benefits_data)} премиум-бенефитов"))
        self.stdout.write("=" * 80)
