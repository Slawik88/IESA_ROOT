#!/usr/bin/env python
"""
Find and optionally delete orphaned media files in DigitalOcean Spaces —
i.e. objects that are no longer referenced by any FileField / ImageField
in the Django database.

Flags:
  --dry-run        (default) List orphans without deleting.
  --delete         Actually delete orphaned objects. Use with caution!
  --prefix P       Override media prefix (default: media/).
  --min-age-days N Skip objects newer than N days (default: 3).

Usage (from IESA_ROOT/ folder):
  python scripts/cleanup_orphans.py
  python scripts/cleanup_orphans.py --delete
"""
import argparse
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')

import django
django.setup()

import boto3
from django.conf import settings
from django.db import models as dj_models

# ── Config ────────────────────────────────────────────────────────────────────
MEDIA_PREFIX = 'media/'
# ─────────────────────────────────────────────────────────────────────────────


def collect_db_keys() -> set:
    """Return all S3 keys that are referenced by any FileField/ImageField."""
    keys = set()
    for model in dj_models.get_models():
        file_fields = [
            f for f in model._meta.get_fields()
            if isinstance(f, (dj_models.FileField, dj_models.ImageField))
        ]
        if not file_fields:
            continue
        for field in file_fields:
            values = (
                model.objects
                .exclude(**{f'{field.name}__isnull': True})
                .exclude(**{f'{field.name}': ''})
                .values_list(field.name, flat=True)
            )
            for val in values:
                if val:
                    # Django storage keeps paths relative to MEDIA_ROOT;
                    # on S3 the key is MEDIA_PREFIX + val (but val may already
                    # include media/ depending on upload_to).
                    key = str(val)
                    # Normalise: some upload_to include 'media/' prefix, some don't
                    if not key.startswith('media/') and not key.startswith('/'):
                        key = 'media/' + key
                    keys.add(key.lstrip('/'))
    return keys


def make_s3():
    return boto3.client(
        's3',
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )


def iter_objects(s3, bucket, prefix):
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            yield obj


def main():
    parser = argparse.ArgumentParser(description='Clean up orphaned Spaces media.')
    parser.add_argument('--delete', action='store_true',
                        help='Delete orphans (default: dry-run / list only)')
    parser.add_argument('--prefix', default=MEDIA_PREFIX)
    parser.add_argument('--min-age-days', type=int, default=3,
                        help='Skip objects uploaded within this many days')
    args = parser.parse_args()

    s3     = make_s3()
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.min_age_days)

    print(f"Bucket    : {bucket}")
    print(f"Prefix    : {args.prefix}")
    print(f"Min age   : {args.min_age_days} days  (skip newer than {cutoff.date()})")
    print(f"Mode      : {'DELETE' if args.delete else 'DRY-RUN (list only)'}")
    print("=" * 70)

    print("Collecting DB references…")
    db_keys = collect_db_keys()
    print(f"  {len(db_keys)} referenced keys found in DB.")

    orphans = []
    total   = 0

    for obj in iter_objects(s3, bucket, args.prefix):
        key         = obj['Key']
        last_mod    = obj['LastModified']
        size_kb     = obj['Size'] // 1024
        total      += 1

        # Skip recently uploaded objects (might not be in DB yet)
        if last_mod > cutoff:
            continue

        if key not in db_keys:
            orphans.append((key, size_kb, last_mod))

    print(f"\nScanned  : {total} objects")
    print(f"Orphans  : {len(orphans)}")
    print()

    orphan_kb = 0
    for key, size_kb, last_mod in orphans:
        orphan_kb += size_kb
        print(f"  {'DELETE' if args.delete else 'ORPHAN'} {key}  ({size_kb} KB, {last_mod.date()})")
        if args.delete:
            s3.delete_object(Bucket=bucket, Key=key)

    print()
    print("=" * 70)
    print(f"Total orphan size: {orphan_kb} KB  (~{orphan_kb // 1024} MB)")
    if not args.delete and orphans:
        print("Run with --delete to remove them.")


if __name__ == '__main__':
    main()
