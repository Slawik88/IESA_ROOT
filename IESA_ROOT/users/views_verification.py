"""
Membership Verification System Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from .models import User, Partner, Visit
from .forms_verification import VisitForm, MemberSearchForm


def is_partner(user):
    """Check if user has Partner profile (more reliable than group membership)"""
    # Check if user has Partner profile
    # This is better than checking groups because:
    # 1. Partner profile is the actual business entity
    # 2. Groups can be cached in session
    # 3. If user has profile, they ARE a partner
    try:
        has_profile = hasattr(user, 'partner_profile')
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"is_partner check - user: {user.username}, has_profile: {has_profile}")
        return has_profile
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"is_partner check error: {e}")
        return False


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
    return render(request, 'users/member_scan_card.html', context)


@login_required
def member_cabinet(request):
    """
    Personal cabinet for members showing current PIN
    Login-required, members only
    """
    user = request.user
    
    # Check if user has required fields (migration applied)
    if not hasattr(user, 'membership_status'):
        messages.error(request, '⚠️ System error: Database migration required. Contact administrator.')
        return redirect('core:home')
    
    # Check if membership is active
    if user.membership_status != 'active':
        context = {
            'membership_status': user.membership_status,
            'current_pin': None,
            'seconds_remaining': 0,
            'error_message': 'Your membership is inactive. Contact administrator to activate your account.'
        }
        return render(request, 'users/member_cabinet.html', context)
    
    # Check TOTP secret exists before generating PIN
    if not user.totp_secret:
        messages.error(request, '⚠️ TOTP secret not configured. Contact administrator.')
        context = {
            'membership_status': user.membership_status,
            'current_pin': None,
            'seconds_remaining': 0,
            'error_message': 'PIN system not initialized. Contact administrator.'
        }
        return render(request, 'users/member_cabinet.html', context)
    
    # Generate current PIN
    current_pin = user.get_current_pin()
    
    if not current_pin:
        messages.error(request, '⚠️ Unable to generate PIN. Contact administrator.')
        context = {
            'membership_status': user.membership_status,
            'current_pin': None,
            'seconds_remaining': 0,
            'error_message': 'PIN generation failed. Contact administrator.'
        }
        return render(request, 'users/member_cabinet.html', context)
    
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
        'user_name': user.get_full_name() or user.username,
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
        messages.error(request, '⚠️ Partner profile not configured. Contact administrator to create your partner account.')
        return redirect('core:home')
    except AttributeError:
        messages.error(request, '⚠️ System error: Database migration required. Contact administrator.')
        return redirect('core:home')
    
    # Calculate partner statistics
    from django.db.models import Sum, Count
    
    visits = Visit.objects.filter(partner=partner).select_related('member').order_by('-timestamp')
    total_visits = visits.count()
    verified_visits = visits.filter(pin_verified=True).count()
    total_cost = visits.aggregate(Sum('cost'))['cost__sum'] or 0
    unique_members = visits.values('member').distinct().count()
    
    # Handle member search
    search_results = None
    search_form = MemberSearchForm(request.GET or None)
    
    if search_form.is_valid():
        query = search_form.cleaned_data.get('query', '').strip()
        if query:
            # Search by pseudonym, first_name, last_name, username, or UUID
            search_filter = (
                Q(pseudonym__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(username__icontains=query)
            )
            
            # Try to parse as UUID (only if query looks like UUID)
            # UUID can be with or without dashes
            if len(query.replace('-', '')) >= 32:
                try:
                    import uuid
                    # Try to parse with dashes
                    uuid_obj = uuid.UUID(query)
                    search_filter |= Q(permanent_id=uuid_obj)
                except ValueError:
                    try:
                        # Try to parse without dashes (insert dashes)
                        clean_uuid = query.replace('-', '')
                        if len(clean_uuid) == 32:
                            formatted_uuid = f"{clean_uuid[0:8]}-{clean_uuid[8:12]}-{clean_uuid[12:16]}-{clean_uuid[16:20]}-{clean_uuid[20:32]}"
                            uuid_obj = uuid.UUID(formatted_uuid)
                            search_filter |= Q(permanent_id=uuid_obj)
                    except (ValueError, IndexError):
                        pass  # Not a valid UUID, skip UUID search
            
            # FIX: Don't filter by membership_status - show ALL users!
            # Partners should see ALL members, not just active ones
            search_results = User.objects.filter(
                search_filter
            ).distinct()[:20]  # Limit to 20 results
    
    # Get partner's recent visits (paginated)
    paginator = Paginator(visits, 15)  # 15 visits per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'partner': partner,
        'search_form': search_form,
        'search_results': search_results,
        'visits': page_obj,
        'total_visits': total_visits,
        'verified_visits': verified_visits,
        'total_cost': total_cost,
        'unique_members': unique_members,
    }
    
    # If it's an HTMX request, return only search results partial
    if request.headers.get('HX-Request'):
        return render(request, 'users/partials/partner_search_results.html', context)
    
    return render(request, 'users/partner_dashboard.html', context)


@login_required
@user_passes_test(is_partner, login_url='/auth/login/', redirect_field_name=None)
@require_http_methods(["GET", "POST"])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
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
    
    # FIX: Remove membership_status filter - partners should see ALL members
    member = get_object_or_404(User, id=member_id)
    
    # Check if member is active (warning, but allow)
    if member.membership_status != 'active':
        messages.warning(request, f'⚠️ Warning: {member.get_full_name()} membership is currently inactive.')
    
    if request.method == 'POST':
        form = VisitForm(request.POST)
        if form.is_valid():
            # Verify PIN
            provided_pin = form.cleaned_data['pin']
            
            if not member.totp_secret:
                messages.error(request, '⚠️ Member PIN system not configured. Contact administrator.')
                return redirect('users:partner_dashboard')
            
            if member.verify_pin(provided_pin):
                # PIN is valid, create visit
                visit = form.save(commit=False)
                visit.member = member
                visit.partner = partner
                visit.pin_verified = True
                visit.save()
                
                member_name = member.get_full_name() or member.username
                service_name = visit.get_service_type_display()
                cost_display = f"{visit.cost} CHF" if visit.cost else "N/A"
                
                messages.success(
                    request,
                    f'✅ Visit successfully logged! Member: {member_name} | Service: {service_name} | Cost: {cost_display}'
                )
                return redirect('users:partner_dashboard')
            else:
                form.add_error('pin', '❌ Invalid PIN. Please ask member to show their current 6-digit PIN from personal cabinet.')
    else:
        form = VisitForm()
    
    context = {
        'form': form,
        'member': member,
        'partner': partner,
    }
    return render(request, 'users/log_visit.html', context)
