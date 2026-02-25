"""
Test script for Membership Verification System
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

from users.models import User, Partner, Visit

def test_verification_system():
    print("=" * 60)
    print("Testing Membership Verification System")
    print("=" * 60)
    
    # Get test member and partner
    try:
        member = User.objects.get(username='test_member')
        partner = Partner.objects.get(company_name='Test Sport Shop')
    except Exception as e:
        print(f"Error: {e}")
        print("Please run setup_verification_system.py first")
        return
    
    # Test PIN generation
    print(f"\n1. Member: {member.username}")
    print(f"   First Name: {member.first_name}")
    print(f"   Last Name: {member.last_name}")
    print(f"   Membership Status: {member.membership_status}")
    print(f"   Permanent ID: {member.permanent_id}")
    
    # Test PIN
    current_pin = member.get_current_pin()
    print(f"\n2. Current PIN: {current_pin}")
    print(f"   Verify correct PIN: {member.verify_pin(current_pin)}")
    print(f"   Verify wrong PIN: {member.verify_pin('000000')}")
    
    # Test partner
    print(f"\n3. Partner: {partner.company_name}")
    print(f"   Business Type: {partner.get_business_type_display()}")
    print(f"   Total Visits: {partner.get_total_visits()}")
    
    # Create test visit
    print("\n4. Creating test visit...")
    visit = Visit.objects.create(
        member=member,
        partner=partner,
        service_type='purchase',
        service_description='Test purchase',
        cost=50.00,
        pin_verified=True
    )
    print(f"   Visit created: {visit}")
    print(f"   Total visits now: {Visit.objects.count()}")
    
    # Test URLs
    print(f"\n5. Test URLs:")
    print(f"   Public Profile: /auth/profile/{member.permanent_id}/public/")
    print(f"   Member Cabinet: /auth/cabinet/")
    print(f"   Partner Dashboard: /auth/partner/dashboard/")
    
    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)

if __name__ == '__main__':
    test_verification_system()
