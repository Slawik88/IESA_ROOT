#!/usr/bin/env python
"""
Test URLs and bucket contents
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

cdn_domain = f'{bucket}.fra1.digitaloceanspaces.com'

print("=" * 80)
print("📋 Bucket Contents & URLs")
print("=" * 80)

print("\n❌ WRONG PATHS (should be deleted):")
response = s3.list_objects_v2(Bucket=bucket, Prefix='gallery/')
if 'Contents' in response:
    for obj in response['Contents']:
        url = f'https://{cdn_domain}/{obj["Key"]}'
        print(f'\n   File: {obj["Key"]}')
        print(f'   URL:  {url}')
        print(f'   ACL:  (should be public-read now)')
else:
    print("   (none)")

print("\n\n✅ CORRECT PATHS:")
response = s3.list_objects_v2(Bucket=bucket, Prefix='media/gallery/')
if 'Contents' in response:
    for obj in response['Contents']:
        url = f'https://{cdn_domain}/{obj["Key"]}'
        print(f'\n   File: {obj["Key"]}')
        print(f'   URL:  {url}')
else:
    print("   (none)")

print("\n" + "=" * 80)
print("Test the URLs in browser to verify they work now!")
print("=" * 80)
