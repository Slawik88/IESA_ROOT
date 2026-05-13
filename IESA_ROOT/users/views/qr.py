"""QR code serving + activity levels info."""
import logging
import uuid as uuid_module
from io import BytesIO

from django.core.cache import cache
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from ..constants import ACTIVITY_LEVELS, POINTS_BREAKDOWN, QR_CACHE_TTL
from ..models import User
from ..services import QRCodeService

logger = logging.getLogger(__name__)


def qr_image(request, permanent_id):
    """Serve or generate QR code PNG.

    Hot-path (normal inline requests) は NEVER hits the DB — the QR image is
    derived entirely from the permanent_id UUID + request host.  The DB is
    only queried for ?download=1 (permission check) or on a generation error
    (to return 404 vs 500).  This eliminates the connection-exhaustion burst
    that occurred when many workers cache-missed simultaneously.
    """
    try:
        uuid_module.UUID(str(permanent_id))
    except (ValueError, AttributeError):
        raise Http404("Invalid ID format")

    download  = request.GET.get('download') in ['1', 'true', 'yes']
    cache_key = f'qr_image_{permanent_id}'
    cached_data = cache.get(cache_key)

    if not cached_data:
        try:
            qr_url = QRCodeService._build_profile_url(permanent_id, request)
            img    = QRCodeService._create_qr_image(qr_url)
            img_io = BytesIO()
            img.save(img_io, format='PNG')
            cached_data = img_io.getvalue()
            cache.set(cache_key, cached_data, QR_CACHE_TTL)
        except Exception as e:
            logger.error("QR generation failed for %s: %s", permanent_id, e, exc_info=True)
            # Only now do we need to confirm the UUID exists in DB
            get_object_or_404(User, permanent_id=permanent_id)
            raise Http404("QR generation failed")

    if download:
        # Permission check requires DB lookup — intentional, infrequent path
        user_obj = get_object_or_404(User, permanent_id=permanent_id)
        if not request.user.is_authenticated or (
            request.user.id != user_obj.id and not request.user.is_staff
        ):
            return HttpResponseForbidden('Not allowed')
        response = HttpResponse(cached_data, content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename=qr_{user_obj.username}.png'
        response['Cache-Control'] = 'public, max-age=86400'
        return response

    response = HttpResponse(cached_data, content_type='image/png')
    response['Content-Disposition'] = f'inline; filename=qr_{permanent_id}.png'
    # 24h browser cache — permanent_id never changes, so this is safe
    response['Cache-Control'] = 'public, max-age=86400'
    return response


def activity_levels_info(request):
    return render(request, 'users/activity_levels_info.html', {
        'activity_levels': ACTIVITY_LEVELS,
        'points_breakdown': POINTS_BREAKDOWN,
    })
