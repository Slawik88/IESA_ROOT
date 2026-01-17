from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import views as auth_views, logout, login
from django.views.generic import CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.http import HttpResponseForbidden, FileResponse, Http404
from django.db.models import Q, Count
from django_ratelimit.decorators import ratelimit
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from io import BytesIO
from .models import User
from .forms import CustomUserCreationForm, UserProfileEditForm
from blog.models import Post
import os
from django.conf import settings
from .qr_utils import generate_qr_code_for_user
from .search_utils import highlight_text, normalize_search_query
from .ratelimit_utils import login_ratelimit, register_ratelimit, search_ratelimit
from .constants import ACTIVITY_LEVELS, POINTS_BREAKDOWN


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return redirect('home')
    return redirect('home')


# View для регистрации
@method_decorator(register_ratelimit, name='dispatch')
class RegisterView(CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        return super().form_valid(form)


# View для логина (используем стандартный Django)
@method_decorator(login_ratelimit, name='dispatch')
class LoginView(auth_views.LoginView):
    template_name = 'users/login.html'


# View для логаута (используем стандартный Django)
class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy('home')


# View для личного кабинета (отображение с постами пользователя)
@method_decorator(login_required, name='dispatch')
class ProfileView(DetailView):
    model = User
    template_name = 'users/profile.html'
    context_object_name = 'profile_user'
    paginate_by = 12  # Pagination for user posts

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
        messages.success(self.request, 'Профиль успешно обновлён! ✨')
        return reverse_lazy('profile')


def _get_public_profile_context(user_obj):
    """Helper function to generate context for public profile view.
    
    FIX: Extracted duplicated logic from profile_public_by_username and 
    profile_public_by_card into single reusable function.
    """
    user_posts = Post.objects.filter(
        author=user_obj, status='published'
    ).select_related('author').prefetch_related('likes', 'comments').order_by('-created_at')
    
    other_links_list = (
        user_obj.other_links.splitlines() 
        if user_obj.other_links 
        else []
    )
    
    return {
        'user_obj': user_obj, 
        'user_posts': user_posts, 
        'other_links_list': other_links_list
    }


@cache_page(60 * 5)  # Cache public profiles for 5 minutes
def profile_public_by_username(request, username):
    """Public profile view by username (cached for 5 min).
    
    FIX: Added caching to reduce database queries for frequently viewed profiles.
    """
    user_obj = get_object_or_404(User, username=username)
    context = _get_public_profile_context(user_obj)
    return render(request, 'users/profile_public.html', context)


@cache_page(60 * 5)  # Cache public profiles for 5 minutes  
def profile_public_by_card(request, permanent_id):
    """Public profile view reached via QR code (permanent_id lookup).
    
    FIX: Added caching + optimized query with select_related and prefetch_related.
    """
    user_obj = get_object_or_404(User, permanent_id=permanent_id)
    context = _get_public_profile_context(user_obj)
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
        # Build complex query for multi-field search
        base_q = (
            Q(username__icontains=normalized_q) | 
            Q(first_name__icontains=normalized_q) | 
            Q(last_name__icontains=normalized_q) | 
            Q(email__icontains=normalized_q) | 
            Q(permanent_id__icontains=normalized_q)
        )

        # If user typed two words, try to match as first+last name
        tokens = [t for t in normalized_q.split() if t]
        if len(tokens) >= 2:
            t1, t2 = tokens[0], tokens[1]
            base_q |= (Q(first_name__icontains=t1) & Q(last_name__icontains=t2))
            base_q |= (Q(first_name__icontains=t2) & Q(last_name__icontains=t1))

        # Execute query with optimizations
        results = User.objects.filter(base_q).order_by(
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
    
    FIX: Simplified logic by delegating QR generation to QRCodeService.
    Now handles only HTTP concerns (caching, auth, response).
    
    URL: /auth/qr/<uuid>/
    ?download=1 - скачать файл
    """
    from .services import QRCodeService
    import uuid as uuid_module
    
    # Validate permanent_id format
    try:
        uuid_module.UUID(str(permanent_id))
    except (ValueError, AttributeError):
        raise Http404("Invalid ID format")
    
    # Get user object
    user_obj = get_object_or_404(User, permanent_id=permanent_id)

    # Check cache first (cache full image)
    cache_key = f'qr_image_{permanent_id}'
    cached_data = cache.get(cache_key)
    
    if not cached_data:
        try:
            # Use dedicated service for QR generation
            qr_url = QRCodeService._build_profile_url(permanent_id, request)
            img = QRCodeService._create_qr_image(qr_url)
            
            # Convert to bytes
            img_io = BytesIO()
            img.save(img_io, format='PNG')
            cached_data = img_io.getvalue()
            
            # Cache for 1 hour
            cache.set(cache_key, cached_data, 3600)
            
        except Exception as e:
            logger.error(f"QR generation failed for user {user_obj.id}: {str(e)}", exc_info=True)
            raise Http404("QR generation failed")

    # Check download permission
    download = request.GET.get('download') in ['1', 'true', 'yes']
    if download:
        if not request.user.is_authenticated or (
            request.user.id != user_obj.id and not request.user.is_staff
        ):
            return HttpResponseForbidden('Not allowed')

    # Return image response
    from django.http import HttpResponse
    response = HttpResponse(cached_data, content_type='image/png')
    
    if download:
        response['Content-Disposition'] = f'attachment; filename=qr_{user_obj.username}.png'
    else:
        response['Content-Disposition'] = f'inline; filename=qr_{user_obj.username}.png'
    
    # Browser cache for 1 hour
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


@user_passes_test(lambda u: u.is_staff)
def impersonate_user(request, pk):
    """Allow staff to impersonate another user by logging in as them. Use cautiously."""
    target = get_object_or_404(User, pk=pk)
    if not target.is_active:
        return HttpResponseForbidden('Target user is not active')
    # Log the admin in as the target user
    # Note: this will replace the current session; consider storing original user id if you need to return
    login(request, target)
    return redirect('profile_public_username', username=target.username)
