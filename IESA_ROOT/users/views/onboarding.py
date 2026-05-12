"""Onboarding views: welcome modal, profile completeness, username check (Block 1)."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

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
    """Проверить доступность username в реальном времени (Block 3a, live validation).
    GET /auth/check-username/?u=johndoe → {available: true/false}
    """
    username = request.GET.get('u', '').strip()
    if len(username) < 3:
        return JsonResponse({'available': None, 'hint': 'min_length'})

    taken = User.objects.filter(username__iexact=username).exists()
    # Если это текущий юзер (редактирование профиля) — не считать занятым
    if not taken and request.user.is_authenticated:
        pass  # свободен
    elif taken and request.user.is_authenticated:
        if User.objects.filter(username__iexact=username, pk=request.user.pk).exists():
            taken = False  # это сам пользователь

    return JsonResponse({'available': not taken})


def how_it_works(request):
    """Страница «Как работает IESA Sport» (Block 1e)."""
    return render(request, 'users/how_it_works.html')
