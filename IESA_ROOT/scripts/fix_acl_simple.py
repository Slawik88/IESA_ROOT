#!/usr/bin/env python
"""
Fix S3 ACL using direct boto3 (no Django)
"""
import boto3

# Direct credentials
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
print("FIX: Making all files PUBLIC READ")
print("=" * 80)

# Fix WRONG path files
print("\n1️⃣  Files with WRONG path (gallery/):")
response = s3.list_objects_v2(Bucket=bucket, Prefix='gallery/')
if 'Contents' in response:
    for obj in response['Contents']:
        key = obj['Key']
        print(f"\n   {key}")
        try:
            s3.put_object_acl(Bucket=bucket, Key=key, ACL='public-read')
            print(f"     ✅ Made public-read")
        except Exception as e:
            print(f"     ❌ {e}")
else:
    print("   (none)")

# Fix CORRECT path files  
print("\n\n2️⃣  Files with CORRECT path (media/gallery/):")
response = s3.list_objects_v2(Bucket=bucket, Prefix='media/gallery/')
if 'Contents' in response:
    for obj in response['Contents']:
        key = obj['Key']
        print(f"\n   {key}")
        try:
            s3.put_object_acl(Bucket=bucket, Key=key, ACL='public-read')
            print(f"     ✅ Made public-read")
        except Exception as e:
            print(f"     ❌ {e}")
else:
    print("   (none)")

print("\n" + "=" * 80)
print("✅ All files ACL fixed!")
print("=" * 80)
