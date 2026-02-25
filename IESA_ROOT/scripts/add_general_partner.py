#!/usr/bin/env python
"""Add a new general partner"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')

import django
django.setup()

from core.models import Partner

# Создаём нового обычного партнёра
partner = Partner.objects.create(
    name='Community Sports Alliance',
    category='other',
    description='Our trusted partner in community development and sports initiatives. Together we organize local events, workshops and social programs to promote healthy lifestyle and team spirit.',
    link='https://example.com/community-sports',
    contract=None
)

print(f"✅ Created new partner: {partner.name} (category: {partner.category})")

print("\n📋 All partners:")
for p in Partner.objects.all().order_by('category', 'name'):
    print(f"  - {p.name}: {p.category}")
