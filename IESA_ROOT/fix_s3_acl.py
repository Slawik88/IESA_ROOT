#!/usr/bin/env python
"""
Fix S3 ACL for gallery photos to make them public readable.
This script should be run after fixing the upload_to paths.
"""
import os
import sys

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')

import django
django.setup()

import boto3
from django.conf import settings

# Create S3 client using Django settings
s3 = boto3.client(
    's3',
    endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_S3_REGION_NAME
)

bucket = settings.AWS_STORAGE_BUCKET_NAME

print("=" * 80)
print("Fixing S3 ACL for gallery photos...")
print("=" * 80)

# List all files with gallery prefix (wrong path - should be media/gallery/)
print("\n1. Files with WRONG path (gallery/...):")
response = s3.list_objects_v2(Bucket=bucket, Prefix='gallery/')
wrong_files = []
if 'Contents' in response:
    for obj in response['Contents']:
        wrong_files.append(obj['Key'])
        print(f"   - {obj['Key']}")
        
        # Make it public
        try:
            s3.put_object_acl(
                Bucket=bucket,
                Key=obj['Key'],
                ACL='public-read'
            )
            print(f"     ✅ Made public")
        except Exception as e:
            print(f"     ❌ Error: {e}")
else:
    print("   (no files found)")

# List correct path files
print("\n2. Files with CORRECT path (media/gallery/...):")
response = s3.list_objects_v2(Bucket=bucket, Prefix='media/gallery/')
correct_files = []
if 'Contents' in response:
    for obj in response['Contents']:
        correct_files.append(obj['Key'])
        print(f"   - {obj['Key']}")
        
        # Make it public
        try:
            s3.put_object_acl(
                Bucket=bucket,
                Key=obj['Key'],
                ACL='public-read'
            )
            print(f"     ✅ Made public")
        except Exception as e:
            print(f"     ❌ Error: {e}")
else:
    print("   (no files found)")

print("\n" + "=" * 80)
print(f"Summary:")
print(f"  - Wrong path files: {len(wrong_files)}")
print(f"  - Correct path files: {len(correct_files)}")
print("=" * 80)

if wrong_files:
    print("\n⚠️  ACTION REQUIRED:")
    print("  Files with wrong path exist in bucket. You need to:")
    print("  1. Delete wrong files (gallery/...)")
    print("  2. Re-upload through Django admin with fixed upload_to paths")
    print("\nTo delete, run:")
    print("  python fix_s3_acl.py --delete-wrong")
