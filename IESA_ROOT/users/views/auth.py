"""Auth views: register, login, logout, password reset, and e-mail ownership verification."""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm
from django.core.cache import caches
from django.views.generic import CreateView
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from .. import account_switch, antispam
from ..forms import CustomUserCreationForm
from ..models import User
from ..ratelimit_utils import login_ratelimit, password_reset_ratelimit, register_ratelimit
from ..services.email_verification import (
    EmailVerificationConflict,
    EmailVerificationExpired,
    EmailVerificationInvalid,
    send_email_verification,
    verify_email_token,
)

logger = logging.getLogger(__name__)


def _antibot_context():
    """Hidden-field values every public form must render (see users/antispam.py)."""
    return {
        'antibot_token': antispam.issue_form_token(),
        'antibot_timer_field': antispam.TIMER_FIELD,
        'antibot_honeypot_field': antispam.HONEYPOT_FIELD,
        'turnstile_site_key': settings.TURNSTILE_SITE_KEY if antispam.turnstile_enabled() else '',
    }


def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('core:home')


@method_decorator(register_ratelimit, name='dispatch')
class RegisterView(CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('users:profile')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('users:profile')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_antibot_context())
        return context

    def post(self, request, *args, **kwargs):
        refusal = None
        if getattr(request, 'limited', False) or not antispam.throttle(
            'register-ip', antispam.client_ip(request), 60, 3600,
        ):
            refusal = _(
                'Too many sign-up attempts from your network. '
                'Please wait a little and try again, or write to iesa@iesasport.ch.'
            )
        else:
            reason = antispam.bot_problem(request)
            if reason:
                logger.info('Registration refused (%s) from %s', reason, antispam.client_ip(request))
                refusal = antispam.bot_message()
        if refusal:
            self.object = None  # CreateView.post() normally sets this before get_form()
            form = self.get_form()
            form.add_error(None, refusal)
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        # Sign the new member in right away: sending a freshly registered person
        # back to a login form is where most people on phones give up.
        login(self.request, self.object, backend='django.contrib.auth.backends.ModelBackend')
        delivered = send_email_verification(self.object, self.request)
        if delivered:
            messages.success(
                self.request,
                _('Account created. We sent a confirmation link to your e-mail address.'),
            )
        else:
            messages.warning(
                self.request,
                _('Account created, but the confirmation e-mail could not be sent. You can request it again from your profile.'),
            )
        return response


@method_decorator(login_ratelimit, name='dispatch')
class LoginView(auth_views.LoginView):
    template_name = 'users/login.html'
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        # "Add another account": a signed-in person may open the login form on purpose.
        self.adding_account = (
            request.user.is_authenticated
            and (request.GET.get('add_account') == '1' or request.POST.get('add_account') == '1')
        )
        if self.adding_account:
            self.redirect_authenticated_user = False
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['adding_account'] = self.adding_account
        return context

    def form_valid(self, form):
        previous_pk = self.request.user.pk if self.adding_account else None
        if previous_pk:
            self.request._keep_linked_accounts = True   # see users/account_switch.py
        response = super().form_valid(form)
        if previous_pk and previous_pk != self.request.user.pk:
            previous = User.objects.get(pk=previous_pk)
            account_switch.remember(response, self.request, previous, self.request.user)
        return response


@login_required
@require_POST
def switch_account(request, pk):
    """Switch to another account previously added with "Add another account"."""
    target = next((u for u in account_switch.linked_accounts(request, exclude=request.user) if u.pk == pk), None)
    if target is None:
        messages.error(request, _('That account is no longer linked. Please sign in to it again.'))
        return redirect('users:profile')
    current = request.user
    request._keep_linked_accounts = True
    login(request, target, backend='django.contrib.auth.backends.ModelBackend')
    destination = request.POST.get('next', '')
    if not (destination and url_has_allowed_host_and_scheme(
        destination, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    )):
        destination = reverse('users:profile')
    response = redirect(destination)
    account_switch.remember(response, request, current, target)
    messages.success(request, _('Switched to %(username)s.') % {'username': target.username})
    return response


# -- Password reset (self-service, no admin involved) ------------------------
# Django's PasswordResetForm already logs and swallows mail-delivery errors, so an
# SMTP outage never turns into a 500 that reveals which e-mails exist.

class ThrottledPasswordResetForm(PasswordResetForm):
    """At most 3 reset e-mails per address per hour, so a bot cannot mail-bomb a member.

    A throttled address silently gets nothing; the visitor still sees the same
    "check your e-mail" page, so this reveals nothing either.
    """

    def get_users(self, email):
        if not antispam.throttle('reset-email', email, 3, 3600):
            return iter(())
        return super().get_users(email)


@method_decorator(password_reset_ratelimit, name='dispatch')
class PasswordResetView(auth_views.PasswordResetView):
    form_class = ThrottledPasswordResetForm
    template_name = 'users/password_reset_form.html'
    email_template_name = 'users/email/password_reset.txt'
    html_email_template_name = 'users/email/password_reset.html'
    subject_template_name = 'users/email/password_reset_subject.txt'
    success_url = reverse_lazy('users:password_reset_done')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_antibot_context())
        return context

    def post(self, request, *args, **kwargs):
        refusal = None
        if getattr(request, 'limited', False) or not antispam.throttle(
            'reset-ip', antispam.client_ip(request), 20, 3600,
        ):
            refusal = _('Too many requests. Please wait a little and try again.')
        elif antispam.bot_problem(request):
            refusal = antispam.bot_message()
        if refusal:
            form = self.get_form()
            form.add_error(None, refusal)
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = 'users/password_reset_done.html'


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = 'users/password_reset_confirm.html'
    success_url = reverse_lazy('users:password_reset_complete')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # `user` in the template context is the (anonymous) visitor, not the account being reset.
        context['reset_user'] = getattr(self, 'user', None)
        return context


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = 'users/password_reset_complete.html'


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
