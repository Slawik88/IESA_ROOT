#!/usr/bin/env python3
"""
Compressed PostgreSQL backup to a private S3-compatible bucket.

Pipe: pg_dump | gzip -9 (in-process) | boto3.put_object  (no temp file on disk)

Usage:
  python scripts/backup_db.py

Required env vars:
  DATABASE_URL, SPACES_KEY, SPACES_SECRET, SPACES_BUCKET
Optional:
  SPACES_ENDPOINT  (default: https://fra1.digitaloceanspaces.com)
  SPACES_REGION    (default: fra1; use auto for R2)
  BACKUP_BUCKET    (required for R2, otherwise defaults to SPACES_BUCKET)
  BACKUP_PREFIX    (default: backups/)

The /backups/ prefix is covered by the 30-day lifecycle rule set up via
scripts/spaces_lifecycle.py — objects are automatically deleted by Spaces
after BACKUP_EXPIRY_DAYS (default 30).
"""

import gzip
import io
import os
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import ClientError

DATABASE_URL    = os.environ.get("DATABASE_URL")
SPACES_KEY      = os.environ.get("SPACES_KEY")
SPACES_SECRET   = os.environ.get("SPACES_SECRET")
SPACES_BUCKET   = os.environ.get("SPACES_BUCKET")
SPACES_ENDPOINT = os.getenv("SPACES_ENDPOINT", "https://fra1.digitaloceanspaces.com")
IS_R2 = (urlsplit(SPACES_ENDPOINT).hostname or '').endswith('.r2.cloudflarestorage.com')
SPACES_REGION = os.getenv("SPACES_REGION", "auto" if IS_R2 else "fra1")
BACKUP_BUCKET = os.getenv("BACKUP_BUCKET") or (None if IS_R2 else SPACES_BUCKET)
BACKUP_PREFIX   = os.getenv("BACKUP_PREFIX", "backups/")

if not all([DATABASE_URL, SPACES_KEY, SPACES_SECRET, SPACES_BUCKET]):
    print("❌  DATABASE_URL, SPACES_KEY, SPACES_SECRET, SPACES_BUCKET must all be set.")
    sys.exit(1)

if not BACKUP_BUCKET or (IS_R2 and BACKUP_BUCKET == SPACES_BUCKET):
    print("BACKUP_BUCKET must name a separate private bucket when using R2.")
    sys.exit(1)

timestamp  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
object_key = f"{BACKUP_PREFIX}backup_{timestamp}.sql.gz"

# ── 1. Dump ──────────────────────────────────────────────────────────────────
print("🗄️   Dumping database …")
try:
    result = subprocess.run(
        ["pg_dump", DATABASE_URL, "--no-password"],
        capture_output=True,
        check=True,
    )
except subprocess.CalledProcessError as exc:
    print(f"❌  pg_dump failed:\n{exc.stderr.decode()}")
    sys.exit(1)

sql_bytes = result.stdout

# ── 2. Compress (gzip level 9, in memory) ───────────────────────────────────
print("🗜️   Compressing (gzip -9) …")
buf = io.BytesIO()
with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9) as gz:
    gz.write(sql_bytes)
compressed = buf.getvalue()

raw_kb  = len(sql_bytes)  / 1024
comp_kb = len(compressed) / 1024
ratio   = (1 - len(compressed) / max(len(sql_bytes), 1)) * 100
print(f"   {raw_kb:.1f} KB → {comp_kb:.1f} KB  ({ratio:.0f}% reduction)")

# ── 3. Upload → Spaces ───────────────────────────────────────────────────────
print(f"☁️   Uploading → s3://{BACKUP_BUCKET}/{object_key} …")
s3 = boto3.client(
    "s3",
    endpoint_url=SPACES_ENDPOINT,
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET,
    region_name=SPACES_REGION,
)
try:
    s3.put_object(
        Bucket=BACKUP_BUCKET,
        Key=object_key,
        Body=compressed,
        ContentType="application/gzip",
        **({} if IS_R2 else {"ACL": "private"}),
    )
except ClientError as exc:
    print(f"❌  Upload failed: {exc}")
    sys.exit(1)

print(f"✅  Done: {object_key}  ({comp_kb:.1f} KB, private)")
