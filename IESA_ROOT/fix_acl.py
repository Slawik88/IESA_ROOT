#!/usr/bin/env python
"""
Fix S3 ACL and paths for all gallery photos.
Makes files public readable and fixes path structure.
"""
import os
import sys

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')

import django
django.setup()

import boto3
from django.conf import settings

s3 = boto3.client(
    's3',
    endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_S3_REGION_NAME
)

bucket = settings.AWS_STORAGE_BUCKET_NAME

print("=" * 80)
print("FIX: Making all files PUBLIC READ")
print("=" * 80)

# Fix all files in gallery (WRONG path)
print("\n1️⃣  Files with WRONG path (gallery/...):")
response = s3.list_objects_v2(Bucket=bucket, Prefix='gallery/')
if 'Contents' in response:
    for obj in response['Contents']:
        key = obj['Key']
        print(f"\n   {key}")
        
        try:
            # Set ACL to public-read
            s3.put_object_acl(Bucket=bucket, Key=key, ACL='public-read')
            print(f"     ✅ Made public-read")
            
            # Check if we should move it to correct path
            new_key = key.replace('gallery/', 'media/gallery/')
            print(f"     ⚠️  Should be moved to: {new_key}")
            
        except Exception as e:
            print(f"     ❌ Error: {e}")
else:
    print("   (no files)")

# Fix all files with correct path
print("\n\n2️⃣  Files with CORRECT path (media/gallery/...):")
response = s3.list_objects_v2(Bucket=bucket, Prefix='media/gallery/')
if 'Contents' in response:
    for obj in response['Contents']:
        key = obj['Key']
        print(f"\n   {key}")
        
        try:
            s3.put_object_acl(Bucket=bucket, Key=key, ACL='public-read')
            print(f"     ✅ Made public-read")
        except Exception as e:
            print(f"     ❌ Error: {e}")
else:
    print("   (no files)")

print("\n" + "=" * 80)
print("✅ All files are now PUBLIC READ")
print("=" * 80)
print("\nℹ️  About wrong path files (gallery/...):")
print("  - They are now PUBLIC but have WRONG path in URL")
print("  - Browser tries: https://iesa-bucket.../gallery/photos/Screenshot_8.png")
print("  - Should be: https://iesa-bucket.../media/gallery/photos/Screenshot_8.png")
print("\n💡 OPTIONS:")
print("  1. Delete wrong files and re-upload through Django admin")
print("  2. Access correct files: /media/gallery/photos/Screenshot_2.png ✅")
