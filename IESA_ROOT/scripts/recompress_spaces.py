#!/usr/bin/env python
"""
Re-compress existing media files in DigitalOcean Spaces to WebP at quality 65
and max 1280px on the longest side. Skips files that are already WebP or
non-image types.

Flags:
  --dry-run   List what would be changed without uploading.
  --prefix P  Only process objects under prefix P (default: all media/).
  --max N     Stop after processing N objects (default: unlimited).

Usage (from IESA_ROOT/ folder):
  python scripts/recompress_spaces.py
  python scripts/recompress_spaces.py --dry-run
  python scripts/recompress_spaces.py --prefix media/blog/ --dry-run
"""
import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')

import django
django.setup()

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from PIL import Image

# ── Config ────────────────────────────────────────────────────────────────────
WEBP_QUALITY   = 65
MAX_DIMENSION  = 1280          # longest side px
MEDIA_PREFIX   = 'media/'
CONTENT_TYPE   = 'image/webp'
CACHE_CONTROL  = 'max-age=31536000'
IMAGE_EXTS     = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
# ─────────────────────────────────────────────────────────────────────────────


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


def compress_image(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data))
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')
    # Resize if larger than MAX_DIMENSION on any side
    w, h = img.size
    if max(w, h) > MAX_DIMENSION:
        ratio = MAX_DIMENSION / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format='WEBP', quality=WEBP_QUALITY, method=6)
    return out.getvalue()


def main():
    parser = argparse.ArgumentParser(description='Re-compress Spaces media to WebP.')
    parser.add_argument('--dry-run', action='store_true',
                        help='List changes without uploading')
    parser.add_argument('--prefix', default=MEDIA_PREFIX,
                        help=f'Object key prefix (default: {MEDIA_PREFIX})')
    parser.add_argument('--max', type=int, default=0,
                        help='Max objects to process (0 = unlimited)')
    args = parser.parse_args()

    s3     = make_s3()
    bucket = settings.AWS_STORAGE_BUCKET_NAME

    print(f"Bucket : {bucket}")
    print(f"Prefix : {args.prefix}")
    print(f"Dry-run: {args.dry_run}")
    print(f"Quality: {WEBP_QUALITY}  Max-dim: {MAX_DIMENSION}px")
    print("=" * 70)

    done = skipped = errors = saved_bytes = 0

    for obj in iter_objects(s3, bucket, args.prefix):
        key = obj['Key']
        ext = os.path.splitext(key)[1].lower()

        # Skip non-images and already-WebP files
        if ext not in IMAGE_EXTS:
            continue

        # Download
        try:
            resp    = s3.get_object(Bucket=bucket, Key=key)
            data    = resp['Body'].read()
            orig_sz = len(data)
        except ClientError as e:
            print(f"  ERROR downloading {key}: {e}")
            errors += 1
            continue

        # Compress
        try:
            new_data = compress_image(data)
        except Exception as e:
            print(f"  SKIP (compress error) {key}: {e}")
            skipped += 1
            continue

        new_sz   = len(new_data)
        delta    = orig_sz - new_sz
        saved_bytes += delta
        pct      = delta / orig_sz * 100 if orig_sz else 0
        new_key  = os.path.splitext(key)[0] + '.webp'

        print(f"  {'[DRY] ' if args.dry_run else ''}{'RENAME ' if new_key != key else ''}"
              f"{key}  {orig_sz//1024}K → {new_sz//1024}K  ({pct:+.1f}%)")

        if not args.dry_run:
            # Upload re-compressed file (possibly with new .webp extension)
            s3.put_object(
                Bucket=bucket,
                Key=new_key,
                Body=new_data,
                ContentType=CONTENT_TYPE,
                CacheControl=CACHE_CONTROL,
                ACL='public-read',
            )
            # If key changed (extension added/changed) delete old object
            if new_key != key:
                s3.delete_object(Bucket=bucket, Key=key)

        done += 1
        if args.max and done >= args.max:
            print(f"\nReached --max {args.max}, stopping.")
            break

    print("=" * 70)
    print(f"Processed : {done}")
    print(f"Skipped   : {skipped}")
    print(f"Errors    : {errors}")
    print(f"Saved     : {saved_bytes // 1024} KB  (~{saved_bytes // 1024 // 1024} MB)")


if __name__ == '__main__':
    main()
