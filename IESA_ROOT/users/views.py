from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import views as auth_views, logout, login
from django.views.generic import CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.http import HttpResponseForbidden, Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q, Count
from django.utils.translation import gettext as _
from django_ratelimit.decorators import ratelimit
from django.core.cache import cache
from io import BytesIO
from .models import AccountChangeRequest, User
from .forms import AccountChangeRequestForm, CustomUserCreationForm, UserProfileEditForm
from blog.models import Post, BlogSubscription
from .search_utils import highlight_text, normalize_search_query
from .ratelimit_utils import login_ratelimit, register_ratelimit
from .constants import ACTIVITY_LEVELS, POINTS_BREAKDOWN


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return redirect('core:home')
    return redirect('core:home')


# View для регистрации
@method_decorator(register_ratelimit, name='dispatch')
class RegisterView(CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('users:login')

    def form_valid(self, form):
        return super().form_valid(form)


# View для логина (используем стандартный Django)
@method_decorator(login_ratelimit, name='dispatch')
class LoginView(auth_views.LoginView):
    template_name = 'users/login.html'


# View для личного кабинета (отображение с постами пользователя)
@method_decorator(login_required, name='dispatch')
class ProfileView(DetailView):
    model = User
    template_name = 'users/profile.html'
    context_object_name = 'profile_user'
    paginate_by = 12  # Pagination for user posts

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_object(self, queryset=None):
        # Показываем данные текущего авторизованного пользователя
        return self.request.user
    
    def get_context_data(self, **kwargs):
        from django.core.paginator import Paginator
        from django.db.models import Count, Q
        
        context = super().get_context_data(**kwargs)
        
        # Get all posts by user with prefetch for optimization
        all_posts = Post.objects.filter(
            author=self.request.user
        ).select_related('author').prefetch_related('likes', 'comments').order_by('-created_at')
        
        # Paginate posts
        paginator = Paginator(all_posts, self.paginate_by)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context['user_posts'] = page_obj
        context['page_obj'] = page_obj
        context['is_paginated'] = page_obj.has_other_pages()
        
        # Подсчитываем по статусам в одном query вместо четырех! 
        # FIX: Используем aggregate вместо четырех отдельных count() queries
        counts = Post.objects.filter(author=self.request.user).aggregate(
            pending_count=Count('id', filter=Q(status='pending')),
            published_count=Count('id', filter=Q(status='published')),
            rejected_count=Count('id', filter=Q(status='rejected')),
            draft_count=Count('id', filter=Q(status='draft')),
        )
        context.update(counts)

        # ── PIN code shown directly on profile page ──────────────────────
        import time as _time
        user = self.request.user
        if (user.is_authenticated
                and getattr(user, 'membership_status', None) == 'active'
                and user.totp_secret):
            current_pin = user.get_current_pin()
            if current_pin:
                _now = int(_time.time())
                _interval = 720
                _step = _now // _interval
                _next = (_step + 1) * _interval
                context['current_pin'] = current_pin
                context['seconds_remaining'] = _next - _now

        # ── Заявка на смену типа аккаунта ────────────────────────────────
        context['pending_upgrade_request'] = AccountChangeRequest.objects.filter(
            user=user, status='pending'
        ).order_by('-created_at').first()

        return context


# View для редактирования личного кабинета
@method_decorator(login_required, name='dispatch')
class ProfileEditView(UpdateView):
    model = User
    form_class = UserProfileEditForm
    template_name = 'users/profile_edit.html'
    
    def get_object(self, queryset=None):
        # Редактируем данные текущего авторизованного пользователя
        return self.request.user

    def get_success_url(self):
        messages.success(self.request, _('Profile updated successfully! ✨'))
        return reverse_lazy('users:profile')


def _get_public_profile_context(user_obj, request_user=None):
    """Helper function to generate context for public profile view.
    
    FIX: Extracted duplicated logic from profile_public_by_username and 
    profile_public_by_card into single reusable function.
    Added: is_subscribed for HTMX subscribe button
    """
    user_posts = Post.objects.filter(
        author=user_obj, status='published'
    ).select_related('author').prefetch_related('likes', 'comments').order_by('-created_at')
    
    other_links_list = (
        user_obj.other_links.splitlines() 
        if user_obj.other_links 
        else []
    )
    
    # Один aggregate() вместо двух отдельных exists()/count() запросов
    is_subscribed = False
    if request_user and request_user.is_authenticated and request_user != user_obj:
        agg = BlogSubscription.objects.filter(author=user_obj).aggregate(
            total=Count('id'),
            user_sub=Count('id', filter=Q(user=request_user)),
        )
        subscriber_count = agg['total']
        is_subscribed = agg['user_sub'] > 0
    else:
        subscriber_count = BlogSubscription.objects.filter(author=user_obj).count()

    return {
        'user_obj': user_obj,
        'user_posts': user_posts,
        'other_links_list': other_links_list,
        'is_subscribed': is_subscribed,
        'subscriber_count': subscriber_count,
    }


def profile_public_by_username(request, username):
    """Public profile view by username.
    
    Note: Removed cache_page to allow is_subscribed to work per-user.
    The query is still optimized via select_related/prefetch_related.
    """
    user_obj = get_object_or_404(User, username=username)
    context = _get_public_profile_context(user_obj, request.user)
    return render(request, 'users/profile_public.html', context)


def profile_public_by_card(request, permanent_id):
    """Public profile view reached via QR code (permanent_id lookup).
    
    Note: Removed cache_page to allow is_subscribed to work per-user.
    """
    user_obj = get_object_or_404(User, permanent_id=permanent_id)
    context = _get_public_profile_context(user_obj, request.user)
    return render(request, 'users/profile_public.html', context)


@ratelimit(key='ip', rate='30/m', method='GET', block=True)
def users_search(request):
    """Search users with pagination and optimized queries.
    
    FIX: 
    - Added rate limiting to prevent abuse (30 requests/minute per IP)
    - Added pagination (limit to 20 results per page instead of 80)
    - Used select_related for avatar optimization
    - Reduced memory usage for highlight processing
    """
    from django.core.paginator import Paginator
    from django.core.paginator import EmptyPage, PageNotAnInteger
    
    q = request.GET.get('q', '').strip()
    page = request.GET.get('page', 1)
    normalized_q = normalize_search_query(q)
    highlighted_results = []
    
    # Pagination setup
    paginator = Paginator([], 20)  # Default empty paginator
    page_obj = paginator.get_page(1)
    
    if normalized_q and len(normalized_q) >= 2:  # Require at least 2 chars
        # Use the custom manager for clean, deduplicated search logic
        results = User.objects.search(normalized_q).order_by(
            '-is_verified', 'username'
        ).values_list('id', 'username', 'first_name', 'last_name', 'email', 'permanent_id', flat=False)
        
        # Paginate results
        paginator = Paginator(results, 20)  # 20 results per page
        
        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        
        # Get full user objects for the current page (to avoid N+1, fetch only current page)
        user_ids = [r[0] for r in page_obj.object_list]
        page_users = User.objects.filter(id__in=user_ids).order_by('-is_verified', 'username')
        
        # Highlight matched text in results
        for user in page_users:
            highlighted_user = {
                'user': user,
                'username_html': highlight_text(user.username, normalized_q),
                'first_name_html': highlight_text(user.first_name, normalized_q),
                'last_name_html': highlight_text(user.last_name, normalized_q),
                'email_html': highlight_text(user.email, normalized_q),
                'permanent_id_html': highlight_text(str(user.permanent_id), normalized_q),
            }
            highlighted_results.append(highlighted_user)
        
        # Replace page_obj object_list with highlighted results
        page_obj.object_list = highlighted_results

    context = {
        'results': highlighted_results,
        'page_obj': page_obj,
        'query': q,
        'is_paginated': page_obj.has_other_pages() if page_obj else False,
    }
    return render(request, 'users/search_results.html', context)
import logging

logger = logging.getLogger(__name__)


def qr_image(request, permanent_id):
    """Serve QR code image for user profile.

    Hot-path optimisation: when the PNG is already in the Django cache and the
    caller is NOT requesting a file download, we skip the database entirely and
    return the cached bytes directly.  On the admin Users list page this means
    13+ simultaneous AJAX requests each hit the cache instead of racing for a
    fresh DB connection, eliminating the
    "remaining connection slots are reserved for superuser" pool-exhaustion
    error on DigitalOcean.

    URL: /auth/qr/<uuid>/
    ?download=1 – triggers file download (requires DB lookup for auth check)
    """
    from .services import QRCodeService
    import uuid as uuid_module

    # Validate permanent_id format first (no DB needed)
    try:
        uuid_module.UUID(str(permanent_id))
    except (ValueError, AttributeError):
        raise Http404("Invalid ID format")

    download = request.GET.get('download') in ['1', 'true', 'yes']

    # ── Fast path: cached image, non-download ────────────────────────────────
    # Skip DB entirely.  We deliberately use the UUID as the filename so the
    # Content-Disposition header stays meaningful without a User lookup.
    cache_key = f'qr_image_{permanent_id}'
    cached_data = cache.get(cache_key)

    if cached_data and not download:
        response = HttpResponse(cached_data, content_type='image/png')
        response['Content-Disposition'] = f'inline; filename=qr_{permanent_id}.png'
        response['Cache-Control'] = 'public, max-age=3600'
        return response

    # ── Slow path: cache miss or download request (needs DB) ─────────────────
    user_obj = get_object_or_404(User, permanent_id=permanent_id)

    if not cached_data:
        try:
            qr_url = QRCodeService._build_profile_url(permanent_id, request)
            img = QRCodeService._create_qr_image(qr_url)
            img_io = BytesIO()
            img.save(img_io, format='PNG')
            cached_data = img_io.getvalue()
            cache.set(cache_key, cached_data, 3600)
        except Exception as e:
            logger.error(f"QR generation failed for user {user_obj.id}: {str(e)}", exc_info=True)
            raise Http404("QR generation failed")

    if download:
        if not request.user.is_authenticated or (
            request.user.id != user_obj.id and not request.user.is_staff
        ):
            return HttpResponseForbidden('Not allowed')

    response = HttpResponse(cached_data, content_type='image/png')
    if download:
        response['Content-Disposition'] = f'attachment; filename=qr_{user_obj.username}.png'
    else:
        response['Content-Disposition'] = f'inline; filename=qr_{user_obj.username}.png'
    response['Cache-Control'] = 'public, max-age=3600'
    return response


def activity_levels_info(request):
    """Display information about activity levels and how to earn them.
    
    FIX: Moved hardcoded activity level data to constants.py
    This makes the data reusable and testable.
    """
    context = {
        'activity_levels': ACTIVITY_LEVELS,
        'points_breakdown': POINTS_BREAKDOWN,
    }
    return render(request, 'users/activity_levels_info.html', context)


@login_required
def profile_deactivate(request):
    """
    Деактивировать аккаунт пользователя.
    После деактивации пользователь не может входить, но его данные остаются в БД.
    """
    if request.method == 'POST':
        # Дополнительная проверка - требуем пароль для подтверждения
        password = request.POST.get('password', '')
        
        if not password:
            messages.error(request, _('❌ Please enter your password to confirm account deactivation.'))
            return redirect('users:profile')
        
        if not request.user.check_password(password):
            messages.error(request, _('❌ Incorrect password. Account deactivation cancelled.'))
            return redirect('users:profile')
        
        # Деактивируем аккаунт
        request.user.is_active = False
        request.user.save()
        
        # Логируем пользователя
        logout(request)
        
        messages.success(request, _('✅ Your account has been deactivated. You can reactivate it by contacting support.'))
        return redirect('core:home')
    
    # GET запрос - показываем страницу подтверждения
    return render(request, 'users/profile_deactivate_confirm.html')


@user_passes_test(lambda u: u.is_staff)
def impersonate_user(request, pk):
    """Allow staff to impersonate another user by logging in as them. Use cautiously."""
    target = get_object_or_404(User, pk=pk)
    if not target.is_active:
        return HttpResponseForbidden('Target user is not active')
    # Log the admin in as the target user
    # Note: this will replace the current session; consider storing original user id if you need to return
    login(request, target)
    return redirect('users:profile_public_username', username=target.username)


# ---------------------------------------------------------------------------
# Заявка на смену типа аккаунта (Часть 1, Задача 3)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def account_change_request_submit(request):
    """
    HTMX/POST: принимает заявку на смену типа аккаунта.
    Правило: если у пользователя уже есть pending-заявка — возвращаем ошибку.
    Смена типа аккаунта НЕ происходит автоматически.
    """
    from django.utils.translation import gettext as _

    user = request.user

    # Проверяем: нет ли уже активной заявки
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
    else:
        errors = {field: e.as_text() for field, e in form.errors.items()}
        return JsonResponse({'ok': False, 'errors': errors}, status=400)


# ---------------------------------------------------------------------------
# Умный редирект в личный кабинет (Задача 3)
# ---------------------------------------------------------------------------

@login_required
def dashboard_redirect(request):
    """
    Направляет пользователя в нужный кабинет в зависимости от его роли.
      - Технический администратор (is_staff) → Django Admin
      - Партнёр или сотрудник ассоциации → Partner Portal
      - Активный участник (membership_status='active') → Member Cabinet (PIN)
      - Обычный пользователь → My Cabinet (profile)
    """
    user = request.user
    # is_staff НЕ редиректит в /admin/ — личный кабинет важнее
    try:
        is_p = user.is_partner or user.partner_profile is not None
    except Exception:
        is_p = user.is_partner
    if is_p:
        return redirect('users:partner_dashboard')
    if user.membership_status == 'active':
        return redirect('users:member_cabinet')
    return redirect('users:profile')
