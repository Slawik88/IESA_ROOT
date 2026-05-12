"""Onboarding views: welcome modal, profile completeness, username check, inline save (Blocks 1, 3)."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from ..models import User


@login_required
@require_POST
def mark_onboarded(request):
    """Пометить пользователя как прошедшего онбординг (Block 1a).
    Вызывается HTMX POST при закрытии welcome-modal.
    """
    request.user.onboarded = True
    request.user.save(update_fields=['onboarded'])
    return HttpResponse(status=204)  # 204 No Content — HTMX проглатывает молча


@require_GET
def username_available(request):
    """Проверить доступность username в реальном времени (Block 3a).
    GET /auth/check-username/?u=johndoe → {available: bool, hint: str}
    """
    username = request.GET.get('u', '').strip()
    if len(username) < 3:
        return JsonResponse({'available': None, 'hint': 'min_length'})
    if len(username) > 150:
        return JsonResponse({'available': False, 'hint': 'too_long'})

    taken = User.objects.filter(username__iexact=username).exists()
    if taken and request.user.is_authenticated:
        if User.objects.filter(username__iexact=username, pk=request.user.pk).exists():
            taken = False

    return JsonResponse({'available': not taken})


@require_GET
def email_available(request):
    """Проверить доступность email (Block 3a).
    GET /auth/check-email/?e=user@mail.com → {available: bool}
    """
    import re
    email = request.GET.get('e', '').strip().lower()
    if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return JsonResponse({'available': None, 'hint': 'invalid_format'})

    taken = User.objects.filter(email__iexact=email).exists()
    if taken and request.user.is_authenticated:
        if User.objects.filter(email__iexact=email, pk=request.user.pk).exists():
            taken = False

    return JsonResponse({'available': not taken})


def how_it_works(request):
    """Страница «Как работает IESA Sport» (Block 1e)."""
    return render(request, 'users/how_it_works.html')


@login_required
@require_http_methods(["POST", "PATCH"])
def profile_field_save(request):
    """
    Inline autosave одного поля профиля (Block 3e).
    POST/PATCH /auth/profile/field-save/ с body: field=xxx&value=yyy
    Возвращает: JSON {ok, field, saved_value} или {ok: false, error}
    """
    ALLOWED = {
        'first_name', 'last_name', 'phone_number', 'pseudonym',
        'github_url', 'discord_url', 'telegram_url', 'website_url',
    }
    field = request.POST.get('field', '').strip()
    value = request.POST.get('value', '').strip()

    if field not in ALLOWED:
        return JsonResponse({'ok': False, 'error': 'Field not allowed'}, status=400)

    user = request.user
    # Базовая валидация длины
    max_lengths = {'first_name': 150, 'last_name': 150, 'phone_number': 20,
                   'pseudonym': 100, 'github_url': 255, 'discord_url': 255,
                   'telegram_url': 255, 'website_url': 255}
    if len(value) > max_lengths.get(field, 255):
        return JsonResponse({'ok': False, 'error': 'Value too long'}, status=400)

    setattr(user, field, value)
    user.save(update_fields=[field])

    # Пересчитываем completeness чтобы progress-bar обновился
    completeness = user.profile_completeness
    return JsonResponse({
        'ok': True,
        'field': field,
        'saved_value': value,
        'completeness_percent': completeness['percent'],
    })


@require_GET
def member_autocomplete(request):
    """HTMX autocomplete для поиска участника в дашборде партнёра (Block 3b).
    GET /auth/partner/member-autocomplete/?q=text → HTML dropdown
    """
    if not request.user.is_authenticated or not request.user.is_partner:
        return HttpResponse('', status=403)

    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return HttpResponse('')  # пустой ответ — dropdown скрыт

    from ..models import User as _User
    results = _User.objects.filter(is_active=True).search(q).order_by(
        '-is_verified', 'first_name', 'last_name', 'username'
    )[:8]

    # Возвращаем HTML-фрагмент для HTMX swap
    return render(request, 'users/partials/member_autocomplete_results.html', {
        'results': results,
    })
