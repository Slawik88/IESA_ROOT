"""
Membership Verification System Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import User, Partner, Visit
from .forms_verification import VisitForm, MemberSearchForm
import pyotp


def is_partner(user):
    """Check if user belongs to Partners group"""
    return user.groups.filter(name='Partners').exists()


def public_profile(request, uuid):
    """
    Public profile view accessible via QR code
    URL: /profile/<uuid>/public/
    """
    member = get_object_or_404(User, permanent_id=uuid)
    
    context = {
        'member': member,
        'is_public_view': True,
    }
    return render(request, 'users/public_profile.html', context)


@login_required
def member_cabinet(request):
    """
    Personal cabinet for members showing current PIN
    Login-required, members only
    """
    user = request.user
    
    # Generate current PIN
    current_pin = user.get_current_pin()
    
    # Calculate remaining time until PIN refresh (12 minutes = 720 seconds)
    import time
    current_time = int(time.time())
    interval = 720
    time_step = current_time // interval
    next_refresh = (time_step + 1) * interval
    seconds_remaining = next_refresh - current_time
    
    context = {
        'current_pin': current_pin,
        'seconds_remaining': seconds_remaining,
        'membership_status': user.membership_status,
    }
    return render(request, 'users/member_cabinet.html', context)


@login_required
@user_passes_test(is_partner, login_url='/auth/login/', redirect_field_name=None)
def partner_dashboard(request):
    """
    Partner dashboard with search and visit logging
    Restricted to users in 'Partners' group
    """
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        messages.error(request, 'Partner profile not found. Contact admin.')
        return redirect('core:home')
    
    # Handle member search
    search_results = None
    search_form = MemberSearchForm(request.GET or None)
    
    if search_form.is_valid():
        query = search_form.cleaned_data.get('query', '').strip()
        if query:
            # Search by pseudonym, first_name, last_name, or UUID
            search_results = User.objects.filter(
                Q(pseudonym__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(permanent_id__iexact=query.replace('-', '')),
                membership_status='active'
            ).distinct()[:20]  # Limit to 20 results
    
    # Get partner's recent visits (paginated)
    visits = Visit.objects.filter(partner=partner).select_related('member')
    paginator = Paginator(visits, 15)  # 15 visits per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'partner': partner,
        'search_form': search_form,
        'search_results': search_results,
        'visits': page_obj,
    }
    return render(request, 'users/partner_dashboard.html', context)


@login_required
@user_passes_test(is_partner, login_url='/auth/login/', redirect_field_name=None)
@require_http_methods(["GET", "POST"])
def log_visit(request, member_id):
    """
    Form to log a visit for a specific member
    Validates PIN and creates Visit record
    """
    try:
        partner = request.user.partner_profile
    except Partner.DoesNotExist:
        messages.error(request, 'Partner profile not found.')
        return redirect('users:partner_dashboard')
    
    member = get_object_or_404(User, id=member_id, membership_status='active')
    
    if request.method == 'POST':
        form = VisitForm(request.POST)
        if form.is_valid():
            # Verify PIN
            provided_pin = form.cleaned_data['pin']
            if member.verify_pin(provided_pin):
                # PIN is valid, create visit
                visit = form.save(commit=False)
                visit.member = member
                visit.partner = partner
                visit.pin_verified = True
                visit.save()
                
                messages.success(
                    request,
                    f'✓ Visit logged successfully for {member.get_full_name() or member.username}. PIN verified.'
                )
                return redirect('users:partner_dashboard')
            else:
                form.add_error('pin', 'Invalid PIN. Please ask member to show current PIN.')
    else:
        form = VisitForm()
    
    context = {
        'form': form,
        'member': member,
        'partner': partner,
    }
    return render(request, 'users/log_visit.html', context)
