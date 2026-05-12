"""Admin utilities: impersonation, account change requests."""
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from ..forms import AccountChangeRequestForm
from ..models import AccountChangeRequest, User


@user_passes_test(lambda u: u.is_staff)
def impersonate_user(request, pk):
    """Staff-only: log in as another user. Adds session tracking (Block 8f)."""
    target = get_object_or_404(User, pk=pk)
    if not target.is_active:
        return HttpResponseForbidden('Target user is not active')
    # Block 8f: store original admin for banner display
    request.session['impersonated_by'] = request.user.pk
    request.session['impersonated_by_username'] = request.user.username
    login(request, target, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('users:profile')


@login_required
@require_POST
def account_change_request_submit(request):
    """HTMX/POST: submit account type change request."""
    user = request.user
    if AccountChangeRequest.objects.filter(user=user, status='pending').exists():
        return JsonResponse({
            'ok': False,
            'error': _('You already have a pending request. Please wait for it to be reviewed.'),
        }, status=400)

    form = AccountChangeRequestForm(request.POST)
    if form.is_valid():
        cd = form.cleaned_data
        AccountChangeRequest.objects.create(
            user=user,
            desired_type=cd['desired_type'],
            business_category=cd.get('business_category', ''),
            reason=cd['reason'],
            contact_name=cd.get('contact_name', ''),
            contact_phone=cd.get('contact_phone', ''),
            contact_telegram=cd.get('contact_telegram', ''),
            contact_email=cd.get('contact_email', ''),
            address=cd.get('address', ''),
        )
        return JsonResponse({
            'ok': True,
            'message': _('Your request has been submitted! We will contact you soon.'),
        })
    errors = {field: e.as_text() for field, e in form.errors.items()}
    return JsonResponse({'ok': False, 'errors': errors}, status=400)
