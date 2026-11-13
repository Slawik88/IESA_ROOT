"""Copy Spaces objects to R2 without deleting or overwriting existing data.

Default: inventory only. --apply copies and verifies SHA-256; --verify-only
checks an existing copy. Source: SPACES_*; target: R2_ENDPOINT, R2_KEY,
R2_SECRET, R2_BUCKET (public media), R2_PRIVATE_BUCKET (private objects).
The private target must never have public access enabled.
"""

import argparse
import hashlib
import os
from tempfile import SpooledTemporaryFile
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import ClientError


PUBLIC_GRANTEE = 'http://acs.amazonaws.com/groups/global/AllUsers'
COPY_HEADERS = (
    'ContentType', 'ContentEncoding', 'ContentDisposition',
    'ContentLanguage', 'CacheControl', 'Expires', 'Metadata',
)
CHUNK_BYTES = 1024 * 1024
PRIVATE_PREFIXES = ('backups/', 'predvestnik-bot/', 'protected/')
PRIVATE_SUFFIXES = ('.sqlite3', '.db', '.sql', '.sql.gz', '.env')


def inventory(client, bucket):
    return {
        obj['Key']: (obj['ETag'], obj['Size'])
        for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket)
        for obj in page.get('Contents', [])
    }


def is_public_media(client, bucket, key):
    # A legacy public ACL must never publish database copies in the new bucket.
    if key.startswith(PRIVATE_PREFIXES) or key.lower().endswith(PRIVATE_SUFFIXES):
        return False
    acl = client.get_object_acl(Bucket=bucket, Key=key)
    return any(
        grant.get('Grantee', {}).get('URI') == PUBLIC_GRANTEE
        and grant.get('Permission') in ('READ', 'FULL_CONTROL')
        for grant in acl.get('Grants', [])
    )


def read_object(client, bucket, key, etag=None):
    response = client.get_object(
        Bucket=bucket, Key=key, **({'IfMatch': etag} if etag else {}),
    )
    spool = SpooledTemporaryFile(max_size=8 * CHUNK_BYTES)
    digest = hashlib.sha256()
    body = response['Body']
    try:
        while chunk := body.read(CHUNK_BYTES):
            digest.update(chunk)
            spool.write(chunk)
        spool.seek(0)
        return spool, digest.digest(), response
    except BaseException:
        spool.close()
        raise
    finally:
        body.close()


def copy_object(source, target, source_bucket, target_bucket, key, etag, verify_only):
    contents, expected_hash, metadata = read_object(source, source_bucket, key, etag)
    with contents:
        try:
            existing, actual_hash, actual_metadata = read_object(target, target_bucket, key)
        except ClientError as error:
            if error.response['Error']['Code'] not in ('NoSuchKey', '404'):
                raise
            if verify_only:
                raise RuntimeError(f'Target object missing: {key}') from error
            target.put_object(
                Bucket=target_bucket, Key=key, Body=contents, IfNoneMatch='*',
                **{name: metadata[name] for name in COPY_HEADERS if name in metadata},
            )
            existing, actual_hash, actual_metadata = read_object(target, target_bucket, key)
        with existing:
            if actual_hash != expected_hash:
                raise RuntimeError(f'Content mismatch; target was not overwritten: {key}')
            for name in COPY_HEADERS:
                if metadata.get(name) != actual_metadata.get(name):
                    raise RuntimeError(f'Metadata mismatch ({name}): {key}')


def migrate(source, target, source_bucket, public_bucket, private_bucket, mode='plan'):
    if not public_bucket or not private_bucket or public_bucket == private_bucket:
        raise ValueError('Public and private R2 buckets must be different.')
    initial = inventory(source, source_bucket)
    routes = {
        key: public_bucket if is_public_media(source, source_bucket, key) else private_bucket
        for key in initial
    }
    if mode != 'plan':
        for key, (etag, _) in initial.items():
            copy_object(source, target, source_bucket, routes[key], key, etag, mode == 'verify')
        if inventory(source, source_bucket) != initial:
            raise RuntimeError('Source changed during migration; do not switch or delete Spaces.')
        if any(is_public_media(source, source_bucket, key) != (bucket == public_bucket)
               for key, bucket in routes.items()):
            raise RuntimeError('Source permissions changed; keep both R2 buckets private.')
    return {
        'public_objects': sum(bucket == public_bucket for bucket in routes.values()),
        'private_objects': sum(bucket == private_bucket for bucket in routes.values()),
        'bytes': sum(size for _, size in initial.values()),
    }


def client_from_env(prefix, default_region):
    endpoint = os.environ[f'{prefix}_ENDPOINT']
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f'{prefix}_ENDPOINT must be an HTTPS endpoint without credentials.')
    if prefix == 'R2' and not parsed.hostname.endswith('.r2.cloudflarestorage.com'):
        raise ValueError('R2_ENDPOINT must point to Cloudflare R2.')
    return boto3.client(
        's3', endpoint_url=endpoint,
        aws_access_key_id=os.environ[f'{prefix}_KEY'],
        aws_secret_access_key=os.environ[f'{prefix}_SECRET'],
        region_name=os.getenv(f'{prefix}_REGION', default_region),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    source = client_from_env('SPACES', 'fra1')
    target = client_from_env('R2', 'auto')
    result = migrate(
        source, target, os.environ['SPACES_BUCKET'],
        os.environ['R2_BUCKET'], os.environ['R2_PRIVATE_BUCKET'],
        'apply' if args.apply else 'verify' if args.verify_only else 'plan',
    )
    print(('Verified copy' if args.apply or args.verify_only else 'Inventory only'), result)


if __name__ == '__main__':
    main()
