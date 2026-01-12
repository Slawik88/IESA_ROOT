#!/usr/bin/env python
"""
Delete old files with wrong path from bucket.
Run ONLY after verifying you don't need gallery/photos/ files.
"""
import boto3

key = 'DO00KZ7JADFLXJ2MNGJF'
secret = 'eh42Jkc7x6hmCiWHn861t4258Lp7oYrXChKQhgQDQf4'
bucket = 'iesa-bucket'
endpoint = 'https://fra1.digitaloceanspaces.com'

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
        key = obj['Key']
        print(f"\nDeleting: {key}")
        try:
            s3.delete_object(Bucket=bucket, Key=key)
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
