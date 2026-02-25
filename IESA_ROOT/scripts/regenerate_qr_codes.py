#!/usr/bin/env python
"""
Regenerate all QR codes for users.
This will delete old QR codes and create new ones with correct S3 storage.
Run: python manage.py shell < regenerate_qr_codes.py
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

from users.models import User
from users.qr_utils import generate_qr_code_for_user
from django.core.files.storage import default_storage
import boto3

print("=" * 80)
print("REGENERATING QR CODES")
print("=" * 80)

# Initialize S3 client
s3 = boto3.client(
    's3',
    endpoint_url='https://fra1.digitaloceanspaces.com',
    aws_access_key_id=os.getenv('SPACES_KEY'),
    aws_secret_access_key=os.getenv('SPACES_SECRET'),
    region_name='fra1'
)

bucket = os.getenv('SPACES_BUCKET', 'iesa-bucket')

# Delete old QR codes
print("\n🗑️  Deleting old QR codes from S3...")
response = s3.list_objects_v2(Bucket=bucket, Prefix='media/cards/')
if 'Contents' in response:
    count_deleted = 0
    for obj in response['Contents']:
        key = obj['Key']
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            count_deleted += 1
            print(f"   ✅ Deleted: {key}")
        except Exception as e:
            print(f"   ❌ Failed to delete {key}: {e}")
    print(f"\n   Total deleted: {count_deleted} old QR codes")
else:
    print("   (no old QR codes found)")

# Regenerate QR codes for all users
print("\n\n📱 Regenerating QR codes for all users...")
users = User.objects.filter(permanent_id__isnull=False).exclude(permanent_id='')
count_generated = 0

for user in users:
    try:
        qr_path = generate_qr_code_for_user(user)
        if qr_path:
            # Set public-read ACL
            s3.put_object_acl(
                Bucket=bucket,
                Key=f'media/cards/{user.permanent_id}.png',
                ACL='public-read'
            )
            count_generated += 1
            print(f"   ✅ Generated QR for: {user.username} (ID: {user.permanent_id})")
        else:
            print(f"   ⚠️  No permanent_id for user: {user.username}")
    except Exception as e:
        print(f"   ❌ Failed for {user.username}: {e}")

print("\n" + "=" * 80)
print(f"✅ DONE! Regenerated {count_generated} QR codes")
print("=" * 80)
print("\nAll QR codes now have:")
print("  ✓ Correct path (media/cards/)")
print("  ✓ Public-read ACL")
print("  ✓ S3 storage (not local disk)")
print("\n" + "=" * 80)
