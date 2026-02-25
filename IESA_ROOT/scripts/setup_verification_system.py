"""
Quick setup script for Membership Verification System
Run this after migrations to create initial data
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

from django.contrib.auth.models import Group
from users.models import User, Partner

def setup_verification_system():
    """Initialize the membership verification system"""
    
    print("🔧 Setting up Membership Verification System...\n")
    
    # 1. Create Partners group
    print("1️⃣ Creating 'Partners' group...")
    partners_group, created = Group.objects.get_or_create(name='Partners')
    if created:
        print("   ✓ Group 'Partners' created")
    else:
        print("   ℹ Group 'Partners' already exists")
    
    # 2. Create test member (optional)
    print("\n2️⃣ Creating test member...")
    member, created = User.objects.get_or_create(
        username='test_member',
        defaults={
            'email': 'member@test.com',
            'first_name': 'Test',
            'last_name': 'Member',
            'membership_status': 'active',
            'pseudonym': 'TestMember01',
        }
    )
    if created:
        member.set_password('test123')
        member.save()
        print(f"   ✓ Test member created: {member.username}")
        print(f"   📌 Current PIN: {member.get_current_pin()}")
    else:
        print(f"   ℹ Test member already exists: {member.username}")
        print(f"   📌 Current PIN: {member.get_current_pin()}")
    
    # 3. Create test partner (optional)
    print("\n3️⃣ Creating test partner...")
    partner_user, created = User.objects.get_or_create(
        username='test_partner',
        defaults={
            'email': 'partner@test.com',
            'first_name': 'Test',
            'last_name': 'Partner',
        }
    )
    if created:
        partner_user.set_password('test123')
        partner_user.save()
        partner_user.groups.add(partners_group)
        print(f"   ✓ Test partner user created: {partner_user.username}")
    else:
        print(f"   ℹ Test partner user already exists: {partner_user.username}")
    
    # Create Partner profile
    partner_profile, created = Partner.objects.get_or_create(
        user=partner_user,
        defaults={
            'company_name': 'Test Sport Shop',
            'business_type': 'shop',
        }
    )
    if created:
        print(f"   ✓ Partner profile created: {partner_profile.company_name}")
    else:
        print(f"   ℹ Partner profile already exists: {partner_profile.company_name}")
    
    print("\n" + "="*60)
    print("✅ Setup complete!\n")
    print("📋 Test credentials:")
    print(f"   Member: username='test_member', password='test123'")
    print(f"   Partner: username='test_partner', password='test123'")
    print("\n🔗 URLs to test:")
    print(f"   Member cabinet: /auth/cabinet/")
    print(f"   Partner dashboard: /auth/partner/dashboard/")
    print(f"   Public profile: /auth/profile/{member.permanent_id}/public/")
    print("\n📌 Current member PIN: " + member.get_current_pin())
    print("="*60)

if __name__ == '__main__':
    setup_verification_system()
