#!/usr/bin/env python3
"""
Set DigitalOcean Spaces lifecycle rules for automatic cost reduction.

Run once after bucket creation (or whenever you change the rules):
  cd IESA_ROOT
  python scripts/spaces_lifecycle.py

Required env vars:
  SPACES_KEY, SPACES_SECRET, SPACES_BUCKET
Optional:
  SPACES_ENDPOINT  (default: https://fra1.digitaloceanspaces.com)
  BACKUP_EXPIRY_DAYS   (default: 30)
"""

import os
import sys

import boto3
from botocore.exceptions import ClientError

SPACES_KEY      = os.environ.get("SPACES_KEY")
SPACES_SECRET   = os.environ.get("SPACES_SECRET")
SPACES_BUCKET   = os.environ.get("SPACES_BUCKET")
SPACES_ENDPOINT = os.getenv("SPACES_ENDPOINT", "https://fra1.digitaloceanspaces.com")
BACKUP_EXPIRY   = int(os.getenv("BACKUP_EXPIRY_DAYS", "30"))

if not all([SPACES_KEY, SPACES_SECRET, SPACES_BUCKET]):
    print("❌  SPACES_KEY, SPACES_SECRET, SPACES_BUCKET must all be set.")
    sys.exit(1)

s3 = boto3.client(
    "s3",
    endpoint_url=SPACES_ENDPOINT,
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET,
    region_name="fra1",
)

lifecycle = {
    "Rules": [
        {
            # Automatically expire DB backup objects after N days.
            # Adjust BACKUP_EXPIRY_DAYS env var to change the window.
            "ID": f"expire-backups-{BACKUP_EXPIRY}d",
            "Filter": {"Prefix": "backups/"},
            "Status": "Enabled",
            "Expiration": {"Days": BACKUP_EXPIRY},
        },
        {
            # CKEditor uploads: keep for 90 days; editors rarely re-use old drafts.
            # Increase if you keep long-lived draft articles.
            "ID": "expire-ckeditor-uploads-90d",
            "Filter": {"Prefix": "ckeditor5/uploads/"},
            "Status": "Enabled",
            "Expiration": {"Days": 90},
        },
    ]
}

try:
    s3.put_bucket_lifecycle_configuration(
        Bucket=SPACES_BUCKET,
        LifecycleConfiguration=lifecycle,
    )
except ClientError as exc:
    print(f"❌  Failed to apply lifecycle rules: {exc}")
    sys.exit(1)

print(f"✅  Lifecycle rules applied to '{SPACES_BUCKET}':")
for rule in lifecycle["Rules"]:
    days   = rule["Expiration"]["Days"]
    prefix = rule["Filter"]["Prefix"]
    print(f"   • {prefix!r:40s} → delete after {days} days")
