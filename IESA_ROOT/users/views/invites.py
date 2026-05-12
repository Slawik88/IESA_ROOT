"""Invite system views."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from ..models import InviteToken, Partner, User


@user_passes_test(lambda u: u.is_staff)
def invite_list(request):
    invites = InviteToken.objects.select_related('created_by', 'used_by').order_by('-created_at')
    return render(request, 'users/invite_list.html', {'invites': invites})


@user_passes_test(lambda u: u.is_staff)
@require_http_methods(["GET", "POST"])
def invite_generate(request):
    from ..forms_verification import InviteGenerateForm
    if request.method == 'POST':
        form = InviteGenerateForm(request.POST)
        if form.is_valid():
            days = form.cleaned_data.get('expires_days', 7)
            invite = InviteToken.objects.create(
                partner_type=form.cleaned_data['partner_type'],
                company_name=form.cleaned_data.get('company_name', ''),
                note=form.cleaned_data.get('note', ''),
                max_uses=form.cleaned_data.get('max_uses', 1),
                expires_at=timezone.now() + timedelta(days=days),
                created_by=request.user,
            )
            messages.success(request, f"Инвайт создан! Ссылка: {request.build_absolute_uri(f'/users/invite/{invite.token}/')}")
            return redirect('users:invite_list')
    else:
        form = InviteGenerateForm()
    return render(request, 'users/invite_generate.html', {'form': form})


@require_http_methods(["GET", "POST"])
def invite_register(request, token):
    invite = get_object_or_404(InviteToken, token=token)
    if not invite.is_valid():
        return render(request, 'users/invite_invalid.html', {
            'reason': 'expired' if timezone.now() >= invite.expires_at else 'used',
        }, status=410)
    if request.user.is_authenticated:
        return render(request, 'users/invite_invalid.html', {'reason': 'already_logged_in'})

    from ..forms_verification import InviteRegisterForm
    if request.method == 'POST':
        form = InviteRegisterForm(request.POST, invite=invite)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password1'],
                first_name=form.cleaned_data.get('first_name', ''),
                last_name=form.cleaned_data.get('last_name', ''),
                is_partner=True,
            )
            Partner.objects.create(
                user=user,
                company_name=form.cleaned_data.get('company_name', ''),
                business_type=form.cleaned_data.get('business_type', 'other'),
                partner_type=invite.partner_type,
            )
            invite.mark_used(user)
            auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, _("Добро пожаловать! Ваш аккаунт партнёра создан."))
            return redirect('users:partner_dashboard')
    else:
        form = InviteRegisterForm(invite=invite)
    return render(request, 'users/invite_register.html', {'form': form, 'invite': invite})
