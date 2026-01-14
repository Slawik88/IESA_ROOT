#!/usr/bin/env python
"""Populate social networks with demo data"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')

import django
django.setup()

from core.models import SocialNetwork

# Очистим существующие
SocialNetwork.objects.all().delete()

# Создаём популярные соц сети
social_networks = [
    {'name': 'facebook', 'url': 'https://facebook.com/iesasport', 'order': 1},
    {'name': 'instagram', 'url': 'https://instagram.com/iesasport', 'order': 2},
    {'name': 'linkedin', 'url': 'https://linkedin.com/company/iesasport', 'order': 3},
    {'name': 'youtube', 'url': 'https://youtube.com/@iesasport', 'order': 4},
    {'name': 'telegram', 'url': 'https://t.me/iesasport', 'order': 5},
    {'name': 'twitter', 'url': 'https://twitter.com/iesasport', 'order': 6},
    {'name': 'discord', 'url': 'https://discord.gg/iesasport', 'order': 7},
    {'name': 'tiktok', 'url': 'https://tiktok.com/@iesasport', 'order': 8},
    {'name': 'github', 'url': 'https://github.com/iesasport', 'order': 9, 'is_active': False},
    {'name': 'reddit', 'url': 'https://reddit.com/r/iesasport', 'order': 10, 'is_active': False},
]

created_count = 0
for sn_data in social_networks:
    sn, created = SocialNetwork.objects.get_or_create(
        name=sn_data['name'],
        defaults={
            'url': sn_data['url'],
            'order': sn_data['order'],
            'is_active': sn_data.get('is_active', True)
        }
    )
    if created:
        print(f"✅ Created: {sn.get_name_display()} - {sn.get_icon()}")
        created_count += 1
    else:
        print(f"⏭️  Already exists: {sn.get_name_display()}")

print(f"\n📊 Total: {created_count} new social networks created")
print(f"🌐 Active networks: {SocialNetwork.objects.filter(is_active=True).count()}")
print("\n📋 All social networks:")
for sn in SocialNetwork.objects.all():
    status = "✓" if sn.is_active else "✗"
    print(f"  {status} {sn.get_name_display()}: {sn.url} (icon: {sn.get_icon()})")
