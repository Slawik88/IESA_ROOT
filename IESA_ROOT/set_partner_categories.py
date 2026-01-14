#!/usr/bin/env python
"""Set partner categories based on names"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')

import django
django.setup()

from core.models import Partner

categories = {
    'SportTech Solutions': 'tech',
    'Elite Fitness Co': 'sponsor',
    'Performance Nutrition': 'sponsor',
    'Global Sports Media': 'media',
    'Youth Academy Fund': 'sponsor',
}

for partner in Partner.objects.all():
    if partner.name in categories:
        partner.category = categories[partner.name]
        partner.save()
        print(f"✅ {partner.name} → {partner.category}")
    else:
        print(f"⏭️  {partner.name} (not in mapping)")

print("\nFinal state:")
for partner in Partner.objects.all():
    print(f"  - {partner.name}: {partner.category}")
