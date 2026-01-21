"""
Update existing users with valid base32 TOTP secrets
Run this once to fix any users created before the base32 fix
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

import secrets
import base64
from users.models import User

def update_totp_secrets():
    """Update all users with invalid TOTP secrets to use base32"""
    
    print("🔄 Updating TOTP secrets for all users...\n")
    
    users = User.objects.all()
    updated_count = 0
    
    for user in users:
        # Check if totp_secret is empty or invalid hex format
        needs_update = False
        
        if not user.totp_secret:
            needs_update = True
        else:
            # Try to use the secret - if it fails, it needs update
            try:
                user.get_current_pin()
            except Exception:
                needs_update = True
        
        if needs_update:
            # Generate new base32 secret
            random_bytes = secrets.token_bytes(20)
            user.totp_secret = base64.b32encode(random_bytes).decode('utf-8')
            user.save(update_fields=['totp_secret'])
            
            print(f"✓ Updated {user.username}: new secret generated")
            updated_count += 1
    
    print(f"\n{'='*60}")
    print(f"✅ Update complete!")
    print(f"   Total users: {users.count()}")
    print(f"   Updated: {updated_count}")
    print(f"   Already valid: {users.count() - updated_count}")
    print(f"{'='*60}")

if __name__ == '__main__':
    update_totp_secrets()
