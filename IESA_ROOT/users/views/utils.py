"""Shared utilities: partner_required decorator, UUID parsing, public_profile, server_time."""
import uuid as _uuid_mod
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..models import User


def _try_parse_uuid(s: str):
    s = s.strip()
    try:
        return _uuid_mod.UUID(s)
    except ValueError:
        pass
    clean = s.replace('-', '')
    if len(clean) == 32:
        try:
            return _uuid_mod.UUID(f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:]}")
        except ValueError:
            pass
    return None


def is_partner(user) -> bool:
    """True если у пользователя есть партнёрский доступ. Кэшируется на request."""
    if hasattr(user, '_is_partner_cached'):
        return user._is_partner_cached
    try:
        has_profile = user.partner_profile is not None
        if has_profile and not user.is_partner:
            User.objects.filter(pk=user.pk).update(is_partner=True)
            user.is_partner = True
        result = user.is_partner or has_profile
    except Exception:
        result = bool(user.is_partner)
    user._is_partner_cached = result
    return result


def partner_required(view_func):
    """Декоратор: требует авторизации и партнёрского доступа."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.conf import settings
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        if not is_partner(request.user):
            return render(request, 'users/partner_access_denied.html', status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped


def public_profile(request, uuid):
    member = get_object_or_404(User, permanent_id=uuid)
    return render(request, 'users/member_scan_card.html', {'member': member, 'is_public_view': True})


def server_time(request):
    return JsonResponse({'timestamp': timezone.now().isoformat()})
