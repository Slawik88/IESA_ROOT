import boto3
import os

key = os.getenv('SPACES_KEY')
secret = os.getenv('SPACES_SECRET')
bucket = os.getenv('SPACES_BUCKET')
endpoint = os.getenv('SPACES_ENDPOINT')

if not all([key, secret, bucket, endpoint]):
    print('Missing env vars')
    exit(1)

s3 = boto3.client(
    's3',
    endpoint_url=endpoint,
    aws_access_key_id=key,
    aws_secret_access_key=secret,
    region_name='fra1'
)

print('=' * 60)
print('Files with gallery/ prefix (WRONG PATH):')
print('=' * 60)
response = s3.list_objects_v2(Bucket=bucket, Prefix='gallery/')
if 'Contents' in response:
    for obj in response['Contents']:
        print(f"  {obj['Key']}")
else:
    print('  (none)')

print('\n' + '=' * 60)
print('Files with media/gallery/ prefix (CORRECT PATH):')
print('=' * 60)
response = s3.list_objects_v2(Bucket=bucket, Prefix='media/gallery/')
if 'Contents' in response:
    for obj in response['Contents']:
        print(f"  {obj['Key']}")
else:
    print('  (none)')

print('\n' + '=' * 60)
print('All prefixes in bucket:')
print('=' * 60)
response = s3.list_objects_v2(Bucket=bucket)
prefixes = set()
if 'Contents' in response:
    for obj in response['Contents']:
        key_parts = obj['Key'].split('/')
        if len(key_parts) > 1:
            prefixes.add(key_parts[0])
    for p in sorted(prefixes):
        print(f"  - {p}/")
