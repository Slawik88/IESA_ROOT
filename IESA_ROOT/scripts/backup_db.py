#!/usr/bin/env python3
"""
Compressed PostgreSQL → DigitalOcean Spaces backup.

Pipe: pg_dump | gzip -9 (in-process) | boto3.put_object  (no temp file on disk)

Usage:
  python scripts/backup_db.py

Required env vars:
  DATABASE_URL, SPACES_KEY, SPACES_SECRET, SPACES_BUCKET
Optional:
  SPACES_ENDPOINT  (default: https://fra1.digitaloceanspaces.com)
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

import boto3
from botocore.exceptions import ClientError

DATABASE_URL    = os.environ.get("DATABASE_URL")
SPACES_KEY      = os.environ.get("SPACES_KEY")
SPACES_SECRET   = os.environ.get("SPACES_SECRET")
SPACES_BUCKET   = os.environ.get("SPACES_BUCKET")
SPACES_ENDPOINT = os.getenv("SPACES_ENDPOINT", "https://fra1.digitaloceanspaces.com")
BACKUP_PREFIX   = os.getenv("BACKUP_PREFIX", "backups/")

if not all([DATABASE_URL, SPACES_KEY, SPACES_SECRET, SPACES_BUCKET]):
    print("❌  DATABASE_URL, SPACES_KEY, SPACES_SECRET, SPACES_BUCKET must all be set.")
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
print(f"☁️   Uploading → s3://{SPACES_BUCKET}/{object_key} …")
s3 = boto3.client(
    "s3",
    endpoint_url=SPACES_ENDPOINT,
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET,
    region_name="fra1",
)
try:
    s3.put_object(
        Bucket=SPACES_BUCKET,
        Key=object_key,
        Body=compressed,
        ContentType="application/gzip",
        ACL="private",
    )
except ClientError as exc:
    print(f"❌  Upload failed: {exc}")
    sys.exit(1)

print(f"✅  Done: {object_key}  ({comp_kb:.1f} KB, private)")
