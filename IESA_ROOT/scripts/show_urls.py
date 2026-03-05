#!/usr/bin/env python
"""
Test URLs and bucket contents
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
