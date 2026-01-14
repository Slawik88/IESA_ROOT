from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import views as auth_views, logout, login
from django.views.generic import CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.http import HttpResponseForbidden, FileResponse, Http404
from django.db.models import Q
from django_ratelimit.decorators import ratelimit
from django.core.cache import cache
from io import BytesIO
from .models import User
from .forms import CustomUserCreationForm, UserProfileEditForm
from blog.models import Post
import os
from django.conf import settings
from .qr_utils import generate_qr_code_for_user
from .search_utils import highlight_text, normalize_search_query
from .ratelimit_utils import login_ratelimit, register_ratelimit, search_ratelimit


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
        context = super().get_context_data(**kwargs)
        
        # Get all posts by user
        all_posts = Post.objects.filter(author=self.request.user).order_by('-created_at')
        
        # Paginate posts
        paginator = Paginator(all_posts, self.paginate_by)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context['user_posts'] = page_obj
        context['page_obj'] = page_obj
        context['is_paginated'] = page_obj.has_other_pages()
        
        # Подсчитываем по статусам
        context['pending_count'] = Post.objects.filter(author=self.request.user, status='pending').count()
        context['published_count'] = Post.objects.filter(author=self.request.user, status='published').count()
        context['rejected_count'] = Post.objects.filter(author=self.request.user, status='rejected').count()
        context['draft_count'] = Post.objects.filter(author=self.request.user, status='draft').count()
        
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


def profile_public_by_username(request, username):
    """Public profile view by username."""
    user_obj = get_object_or_404(User, username=username)
    user_posts = Post.objects.filter(author=user_obj, status='published').order_by('-created_at')
    other_links_list = user_obj.other_links.splitlines() if (hasattr(user_obj, 'other_links') and user_obj.other_links) else []
    return render(request, 'users/profile_public.html', {'user_obj': user_obj, 'user_posts': user_posts, 'other_links_list': other_links_list})


def profile_public_by_card(request, permanent_id):
    """Public profile view reached via static QR code identifying a user by permanent_id."""
    user_obj = get_object_or_404(User, permanent_id=permanent_id)
    user_posts = Post.objects.filter(author=user_obj, status='published').order_by('-created_at')
    other_links_list = user_obj.other_links.splitlines() if (hasattr(user_obj, 'other_links') and user_obj.other_links) else []
    return render(request, 'users/profile_public.html', {'user_obj': user_obj, 'user_posts': user_posts, 'other_links_list': other_links_list})


def users_search(request):
    q = request.GET.get('q', '').strip()
    normalized_q = normalize_search_query(q)
    results = []
    highlighted_results = []
    
    if normalized_q:
        # Basic multi-field search: username, names, email, permanent_id
        base_q = Q(username__icontains=normalized_q) | Q(first_name__icontains=normalized_q) | Q(last_name__icontains=normalized_q) | Q(email__icontains=normalized_q) | Q(permanent_id__icontains=normalized_q)

        # If user typed two words, try to match as first+last name
        tokens = [t for t in normalized_q.split() if t]
        if len(tokens) >= 2:
            t1, t2 = tokens[0], tokens[1]
            base_q |= (Q(first_name__icontains=t1) & Q(last_name__icontains=t2))
            base_q |= (Q(first_name__icontains=t2) & Q(last_name__icontains=t1))

        results = User.objects.filter(base_q).order_by('-is_verified', 'username')[:80]
        
        # Highlight matched text in results
        for user in results:
            highlighted_user = {
                'user': user,
                'username_html': highlight_text(user.username, normalized_q),
                'first_name_html': highlight_text(user.first_name, normalized_q),
                'last_name_html': highlight_text(user.last_name, normalized_q),
                'email_html': highlight_text(user.email, normalized_q),
                'permanent_id_html': highlight_text(str(user.permanent_id), normalized_q),
            }
            highlighted_results.append(highlighted_user)

    return render(request, 'users/search_results.html', {'results': highlighted_results, 'query': q})


def qr_image(request, permanent_id):
    """Serve user QR image; generate if missing.

    URL: /auth/qr/<uuid>/
    If ?download=1 is present, respond with Content-Disposition attachment.
    
    SECURITY: Validates permanent_id is valid UUID to prevent path traversal.
    Uses Redis cache with 1-hour timeout to reduce disk I/O.
    """
    # Validate permanent_id format - must be valid UUID
    try:
        import uuid
        uuid.UUID(str(permanent_id))
    except (ValueError, AttributeError):
        raise Http404("Invalid ID format")
    
    try:
        user_obj = User.objects.get(permanent_id=permanent_id)
    except User.DoesNotExist:
        raise Http404("User not found")

    # Use Django storage (works with S3 and local)
    from django.core.files.storage import default_storage
    # НЕ добавляем media/ - это добавится автоматически
    filename = f"cards/{permanent_id}.png"
    
    # Check cache first
    cache_key = f'qr_image_{permanent_id}'
    cached_data = cache.get(cache_key)
    if cached_data:
        # Return from cache if available
        return FileResponse(BytesIO(cached_data), content_type='image/png')
    
    # If file doesn't exist, try to generate
    if not default_storage.exists(filename):
        try:
            generate_qr_code_for_user(user_obj, request)
        except Exception as e:
            import logging
            logging.error(f"QR generation failed for user {user_obj.id}: {str(e)}")
            raise Http404("QR generation failed")

    # If still missing -> 404
    if not default_storage.exists(filename):
        raise Http404("QR not available")

    # If download requested, ensure only owner or staff can download
    download = request.GET.get('download') in ['1', 'true', 'yes']
    if download:
        if not request.user.is_authenticated or (request.user.id != user_obj.id and not request.user.is_staff):
            return HttpResponseForbidden('Not allowed')

    # Read file from storage (works with S3 and local)
    try:
        from io import BytesIO
        file_content = default_storage.open(filename, 'rb').read()
        
        # Cache file content for 1 hour (3600 seconds)
        cache.set(cache_key, file_content, 3600)
        
        # Return cached or fresh content
        from django.http import HttpResponse
        response = HttpResponse(file_content, content_type='image/png')
        if download:
            response['Content-Disposition'] = f'attachment; filename=qr_{user_obj.username}.png'
        else:
            response['Content-Disposition'] = f'inline; filename=qr_{user_obj.username}.png'
        return response
    except IOError:
        raise Http404("Cannot read file")


def activity_levels_info(request):
    """Display information about activity levels and how to earn them"""
    activity_levels = [
        {
            'name': 'Beginner',
            'icon': 'leaf',
            'color': 'secondary',
            'min_points': 0,
            'max_points': 50,
            'description': 'Just starting your journey in the IESA community',
            'tips': [
                'Create your first blog post (10 points)',
                'Leave comments on other posts (1 point each)',
                'Engage with the community',
            ]
        },
        {
            'name': 'Intermediate',
            'icon': 'fire',
            'color': 'success',
            'min_points': 50,
            'max_points': 200,
            'description': 'You\'re becoming an active member',
            'tips': [
                'Publish 5-10 quality posts (10 points each)',
                'Receive 50+ likes on your posts (2 points each)',
                'Participate in discussions',
            ]
        },
        {
            'name': 'Advanced',
            'icon': 'rocket',
            'color': 'info',
            'min_points': 200,
            'max_points': 500,
            'description': 'You\'re a valuable contributor',
            'tips': [
                'Publish 15-25 popular posts',
                'Accumulate 100+ total likes',
                'Build a strong reputation',
            ]
        },
        {
            'name': 'Expert',
            'icon': 'star',
            'color': 'warning',
            'min_points': 500,
            'max_points': 1000,
            'description': 'You\'re a recognized authority',
            'tips': [
                'Publish 50+ high-quality posts',
                'Achieve 300+ total likes',
                'Mentor other members',
            ]
        },
        {
            'name': 'Legend',
            'icon': 'crown',
            'color': 'danger',
            'min_points': 1000,
            'max_points': 'Unlimited',
            'description': 'You\'re a pillar of the IESA community',
            'tips': [
                'Maintain extraordinary engagement',
                'Lead by example',
                'Shape the future of IESA',
            ]
        },
    ]
    
    context = {
        'activity_levels': activity_levels,
        'points_breakdown': {
            'post': 10,
            'like': 2,
            'comment': 1,
        }
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
