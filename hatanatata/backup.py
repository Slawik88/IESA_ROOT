"""Root-only encrypted SQLite snapshots; uses only the personal backup bucket."""

import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
from botocore.config import Config
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path("/var/backups/hatanatata")
PREFIX = "hatanatata/"
BUCKET = "makss-projects-backups"


def snapshot(now):
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    files = {
        "etc/iesa/hatanatata.env": Path("/etc/iesa/hatanatata.env").read_bytes(),
        "etc/iesa/OPERATIONS.md": Path("/etc/iesa/OPERATIONS.md").read_bytes(),
    }
    for name in (
        "hatanatata.service",
        "hatanatata-backup.service",
        "hatanatata-backup.timer",
    ):
        files["etc/systemd/system/" + name] = Path(
            "/etc/systemd/system", name
        ).read_bytes()
    workdir = subprocess.check_output(
        ["systemctl", "show", "hatanatata", "-p", "WorkingDirectory", "--value"],
        text=True,
    ).strip()
    revision = Path(workdir).name
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("Invalid release revision")
    # SQLite online backup provides a transactionally consistent WAL snapshot.
    temporary = ROOT / ".snapshot.db"
    try:
        with (
            sqlite3.connect(
                "file:/var/lib/hatanatata/state.db?mode=ro", uri=True
            ) as source,
            sqlite3.connect(temporary) as target,
        ):
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite snapshot integrity check failed")
        files["var/lib/hatanatata/state.db"] = temporary.read_bytes()
    finally:
        temporary.unlink(missing_ok=True)
    metadata = {
        "created_utc": now.isoformat(),
        "revision": revision,
        "workdir": workdir,
        "repository": "https://github.com/Slawik88/IESA_ROOT",
        "sha256": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()},
    }
    files["snapshot.json"] = json.dumps(metadata, sort_keys=True).encode()
    plain = io.BytesIO()
    with tarfile.open(fileobj=plain, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o600, int(now.timestamp())
            archive.addfile(info, io.BytesIO(data))
    key = Path("/etc/iesa/recovery.key").read_bytes()
    if len(key) != 32:
        raise RuntimeError("Invalid existing recovery key")
    header = b"IESACFG1" + hashlib.sha256(key).hexdigest()[:16].encode()
    nonce = os.urandom(12)
    encoded = header + nonce + AESGCM(key).encrypt(nonce, plain.getvalue(), header)
    # Verify recovery, file hashes and metadata before upload.
    decoded = AESGCM(key).decrypt(encoded[24:36], encoded[36:], encoded[:24])
    with tarfile.open(fileobj=io.BytesIO(decoded), mode="r:gz") as archive:
        for name, digest in metadata["sha256"].items():
            if hashlib.sha256(archive.extractfile(name).read()).hexdigest() != digest:
                raise RuntimeError("Encrypted recovery verification failed")
    return encoded


def main():
    os.umask(0o077)
    now = datetime.now(UTC)
    blob = snapshot(now)
    filename = now.strftime("%Y%m%dT%H%M%SZ") + ".enc"
    (ROOT / filename).write_bytes(blob)
    cfg = json.loads(Path("/etc/iesa/r2-backup.json").read_text())
    if cfg["bucket"] != BUCKET:
        raise RuntimeError("Expected private personal backup bucket")
    client = boto3.client(
        "s3",
        endpoint_url=cfg["endpoint"],
        region_name="auto",
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        config=Config(
            signature_version="s3v4",
            connect_timeout=10,
            read_timeout=40,
            retries={"max_attempts": 2},
        ),
    )
    objects = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=BUCKET):
        objects.extend(page.get("Contents", []))
    if sum(o["Size"] for o in objects) + len(blob) > 8_000_000_000:
        raise RuntimeError("Personal backup 8GB cap reached")
    key = PREFIX + filename
    digest = hashlib.sha256(blob).hexdigest()
    client.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=blob,
        ContentType="application/octet-stream",
        Metadata={"sha256": digest},
    )
    downloaded = client.get_object(Bucket=BUCKET, Key=key)["Body"]
    try:
        verified = hashlib.sha256(downloaded.read()).hexdigest()
    finally:
        downloaded.close()
    if verified != digest:
        raise RuntimeError("R2 download checksum mismatch")
    cutoff = now - timedelta(days=14)
    expired = []
    for obj in objects:
        match = re.fullmatch(r"hatanatata/(\d{8}T\d{6}Z)\.enc", obj["Key"])
        if (
            match
            and datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            < cutoff
        ):
            expired.append({"Key": obj["Key"]})
    for offset in range(0, len(expired), 1000):
        result = client.delete_objects(
            Bucket=BUCKET,
            Delete={"Objects": expired[offset : offset + 1000], "Quiet": True},
        )
        if result.get("Errors"):
            raise RuntimeError("Partial retention deletion")
    for candidate in ROOT.glob("*.enc"):
        if (
            not re.fullmatch(r"\d{8}T\d{6}Z\.enc", candidate.name)
            or candidate.resolve().parent != ROOT.resolve()
        ):
            continue
        if (
            datetime.strptime(candidate.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            < cutoff
        ):
            candidate.unlink()
    print("HATANATATA_BACKUP_R2_SHA256_VERIFIED", filename, flush=True)


if __name__ == "__main__":
    main()
