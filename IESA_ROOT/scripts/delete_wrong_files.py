#!/usr/bin/env python
"""
Delete old files with wrong path from bucket.
Run ONLY after verifying you don't need gallery/photos/ files.
"""
import os
import sys
import boto3

key = os.getenv('SPACES_KEY')
secret = os.getenv('SPACES_SECRET')
bucket = os.getenv('SPACES_BUCKET', 'iesa-bucket')
endpoint = os.getenv('SPACES_ENDPOINT', 'https://fra1.digitaloceanspaces.com')

if not key or not secret:
    sys.exit('❌ Set SPACES_KEY and SPACES_SECRET environment variables before running.')

s3 = boto3.client(
    's3',
    endpoint_url=endpoint,
    aws_access_key_id=key,
    aws_secret_access_key=secret,
    region_name='fra1'
)

print("=" * 80)
print("⚠️  DELETING OLD FILES WITH WRONG PATH")
print("=" * 80)

response = s3.list_objects_v2(Bucket=bucket, Prefix='gallery/')
deleted_count = 0

if 'Contents' in response:
    for obj in response['Contents']:
        obj_key = obj['Key']
        print(f"\nDeleting: {obj_key}")
        try:
            s3.delete_object(Bucket=bucket, Key=obj_key)
            print(f"  ✅ Deleted")
            deleted_count += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
else:
    print("No files to delete")

print("\n" + "=" * 80)
print(f"✅ Deleted {deleted_count} files")
print("=" * 80)
print("\n💡 Next steps:")
print("  1. Upload new files through Django admin")
print("  2. Files will be saved to: media/gallery/photos/")
print("  3. URLs will be: https://iesa-bucket.../media/gallery/photos/[name]")
