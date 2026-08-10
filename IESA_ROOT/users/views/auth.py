"""Auth views: register, login, logout, and e-mail ownership verification."""
from django.contrib import messages
from django.contrib.auth import views as auth_views, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import caches
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from ..forms import CustomUserCreationForm
from ..models import User
from ..ratelimit_utils import login_ratelimit, register_ratelimit
from ..services.email_verification import (
    EmailVerificationConflict,
    EmailVerificationExpired,
    EmailVerificationInvalid,
    send_email_verification,
    verify_email_token,
)


def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('core:home')


@method_decorator(register_ratelimit, name='dispatch')
class RegisterView(CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('users:login')

    def form_valid(self, form):
        response = super().form_valid(form)
        delivered = send_email_verification(self.object, self.request)
        if delivered:
            messages.success(
                self.request,
                _('Account created. We sent a confirmation link to your e-mail address.'),
            )
        else:
            messages.warning(
                self.request,
                _('Account created, but the confirmation e-mail could not be sent. Sign in and try again from your cabinet.'),
            )
        return response


@method_decorator(login_ratelimit, name='dispatch')
class LoginView(auth_views.LoginView):
    template_name = 'users/login.html'


@require_GET
def verify_email(request, token):
    """Consume an expiring link without requiring the user to be signed in."""
    try:
        result = verify_email_token(token)
    except EmailVerificationExpired:
        messages.error(request, _('This confirmation link has expired. Sign in to request a new one.'))
        return redirect('users:login')
    except EmailVerificationInvalid:
        messages.error(request, _('This confirmation link is invalid or belongs to an old e-mail address.'))
        return redirect('users:login')
    except EmailVerificationConflict:
        messages.error(
            request,
            _('This e-mail address has already been confirmed by another account. Contact iesa@iesasport.ch if you believe this is a mistake.'),
        )
        return redirect('users:login')

    if result.already_verified:
        messages.info(request, _('This e-mail address is already confirmed.'))
    else:
        messages.success(request, _('Your e-mail address has been confirmed. Thank you!'))

    if request.user.is_authenticated and request.user.pk == result.user.pk:
        return redirect('users:profile')
    return redirect('users:login')


@login_required
@require_POST
def resend_email_verification(request):
    """Resend with a per-account cooldown; never changes account permissions."""
    user = request.user
    if user.is_email_verified:
        messages.info(request, _('Your e-mail address is already confirmed.'))
        return _verification_return(request)
    if not user.email:
        messages.error(request, _('Add an e-mail address to your profile first.'))
        return _verification_return(request)

    cooldown = caches['ratelimit']
    key = f'email-verification-resend:{user.pk}'
    if not cooldown.add(key, '1', timeout=60):
        messages.warning(request, _('Please wait one minute before requesting another confirmation e-mail.'))
        return _verification_return(request)

    if send_email_verification(user, request):
        messages.success(request, _('A new confirmation link has been sent to your e-mail address.'))
    else:
        cooldown.delete(key)
        messages.error(request, _('We could not send the confirmation e-mail. Please try again later or contact iesa@iesasport.ch.'))
    return _verification_return(request)


def _verification_return(request):
    target = request.POST.get('next', '')
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target)
    return redirect('users:profile')
