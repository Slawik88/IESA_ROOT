"""
Custom storage backends.

MediaOptimizationStorage  — production S3/Spaces backend that:
  1. Strips EXIF metadata (applies orientation first via ImageOps.exif_transpose)
  2. Resizes: max 1024×1024 for content, 512×512 for avatars/icons
  3. Converts to WebP @ quality 80 (≈ 60–70 % smaller than JPEG/PNG)
  4. Deduplicates via SHA-256: if the processed bytes already exist in
     Spaces, the existing S3 key is reused and no second upload happens.

ProtectedMediaStorage     — local filesystem storage for sensitive files
                            that require authentication before serving.
"""

import hashlib
import io
import logging
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from whitenoise.storage import CompressedManifestStaticFilesStorage

logger = logging.getLogger(__name__)

# ─── Tunables ─────────────────────────────────────────────────────────────────

WEBP_QUALITY = 80            # WebP encode quality (0–100)
ART_MAX_SIZE  = (1024, 1024) # blog posts, events, gallery, products
ICON_MAX_SIZE = (512, 512)   # avatars, member photos, partner logos

# upload_to prefixes that get the smaller ICON_MAX_SIZE budget
_ICON_PREFIXES = ("avatars/", "members/", "partners/", "cards/")

# PIL format strings we will optimise; anything else passes through untouched
_OPTIMISABLE = frozenset({"JPEG", "PNG", "BMP", "TIFF", "WEBP", "GIF"})

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    _OPTIMISABLE = _OPTIMISABLE | {"HEIF"}
except ImportError:
    pass


# ─── Static files storage ─────────────────────────────────────────────────────

class WhitenoiseManifestStorage(CompressedManifestStaticFilesStorage):
    """WhiteNoise storage with manifest_strict=False.

    Django 5.x passes STORAGES['OPTIONS'] as **kwargs to __init__(), but
    manifest_strict is a class attribute on ManifestFilesMixin, not an
    __init__ parameter. Subclassing is the correct way to override it.
    """
    manifest_strict = False


# ─── Image helpers ────────────────────────────────────────────────────────────

def _is_optimisable(file) -> bool:
    """Return True when Pillow can open *file* and its format is on our list."""
    from PIL import Image
    try:
        file.seek(0)
        img = Image.open(file)
        img.verify()          # verify() closes the image
        file.seek(0)
        img = Image.open(file)
        return img.format in _OPTIMISABLE
    except Exception:
        try:
            file.seek(0)
        except Exception:
            pass
        return False


def _to_webp(file, upload_path: str) -> bytes:
    """
    Open *file*, apply EXIF orientation, resize, convert to WebP.
    EXIF is stripped implicitly because Pillow only copies it when you
    pass ``exif=img.info["exif"]`` explicitly to ``save()``.
    Returns raw WebP bytes.
    """
    from PIL import Image, ImageOps

    file.seek(0)
    img = Image.open(file)
    img.load()  # force full decode before we close/seek the source

    # Apply EXIF rotation so orientation is baked into pixels
    img = ImageOps.exif_transpose(img)

    # Normalise colour mode for WebP
    if img.mode == "P":
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    # Choose resize budget based on upload path
    prefix = upload_path.lstrip("/")
    max_size = (
        ICON_MAX_SIZE if any(prefix.startswith(p) for p in _ICON_PREFIXES)
        else ART_MAX_SIZE
    )
    img.thumbnail(max_size, Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WebP", quality=WEBP_QUALITY, method=4)
    return buf.getvalue()


# ─── MediaOptimizationStorage ─────────────────────────────────────────────────

try:
    from storages.backends.s3boto3 import S3Boto3Storage as _S3Base
except ImportError:  # django-storages not installed (local dev without full deps)
    from django.core.files.storage import FileSystemStorage as _S3Base  # type: ignore[assignment]


class MediaOptimizationStorage(_S3Base):
    """
    Drop-in replacement for S3Boto3Storage with WebP optimisation +
    SHA-256 deduplication.

    Non-image files (PDF, SVG, …) are passed through unchanged.

    Deduplication safety with django-cleanup
    ─────────────────────────────────────────
    When two model instances share the same S3 key (dedup hit), the
    ``delete()`` override below prevents that file from being removed
    when *one* of the records is deleted, protecting the remaining reference.
    """

    def _save(self, name: str, content) -> str:
        # ── 0. Skip non-images ─────────────────────────────────────────────
        if not _is_optimisable(content):
            return super()._save(name, content)

        # ── 1. Optimise → WebP ────────────────────────────────────────────
        try:
            webp_bytes = _to_webp(content, upload_path=name)
        except Exception as exc:
            logger.warning(
                "MediaOptimizationStorage: optimisation skipped for %s: %s",
                name, exc,
            )
            content.seek(0)
            return super()._save(name, content)

        # ── 2. Deduplicate ────────────────────────────────────────────────
        sha256 = hashlib.sha256(webp_bytes).hexdigest()
        MediaHash = None
        try:
            from django.apps import apps
            MediaHash = apps.get_model("core", "MediaHash")
            existing = MediaHash.objects.filter(sha256=sha256).first()
            if existing:
                logger.debug(
                    "MediaOptimizationStorage: dedup hit %s → %s",
                    name, existing.s3_key,
                )
                return existing.s3_key
        except Exception:
            MediaHash = None  # ORM not ready yet — skip dedup silently

        # ── 3. Upload ─────────────────────────────────────────────────────
        stem = os.path.splitext(name)[0]
        new_name = stem + ".webp"
        saved_key = super()._save(new_name, ContentFile(webp_bytes, name=new_name))

        # ── 4. Register hash ──────────────────────────────────────────────
        if MediaHash is not None:
            try:
                MediaHash.objects.get_or_create(
                    sha256=sha256,
                    defaults={"s3_key": saved_key},
                )
            except Exception as exc:
                logger.warning(
                    "MediaOptimizationStorage: hash register failed: %s", exc
                )

        return saved_key

    def delete(self, name: str) -> None:
        """
        Skip deletion for any file that is registered as a canonical
        dedup target in MediaHash — another DB record still references it.
        """
        try:
            from django.apps import apps
            MediaHash = apps.get_model("core", "MediaHash")
            if MediaHash.objects.filter(s3_key=name).exists():
                logger.debug(
                    "MediaOptimizationStorage: skipping deletion of"
                    " dedup-referenced file %s",
                    name,
                )
                return
        except Exception:
            pass
        super().delete(name)


# ─── ProtectedMediaStorage ────────────────────────────────────────────────────

class ProtectedMediaStorage(FileSystemStorage):
    """
    Local filesystem storage for files that require permission checks
    before serving (user avatars in dev, private documents, etc.).
    """

    def __init__(self, *args, **kwargs):
        kwargs['location'] = os.path.join(settings.MEDIA_ROOT, 'protected')
        kwargs['base_url'] = '/protected/'
        super().__init__(*args, **kwargs)

    def get_available_name(self, name, max_length=None):
        """Prevent filename collisions by appending a counter suffix."""
        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        count = 1
        while self.exists(name):
            name = os.path.join(dir_name, f"{file_root}_{count}{file_ext}")
            count += 1
        return name
