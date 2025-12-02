from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import views as auth_views, logout, login
from django.views.generic import CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.db.models import Q
from .models import User
from .forms import CustomUserCreationForm, UserProfileEditForm
from blog.models import Post
from django.http import FileResponse, Http404
import os
from django.conf import settings
from .qr_utils import generate_qr_code_for_user
from .search_utils import highlight_text, normalize_search_query


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return redirect('home')
    return redirect('home')


# View для регистрации
class RegisterView(CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        return super().form_valid(form)


# View для логина (используем стандартный Django)
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

    def get_object(self, queryset=None):
        # Показываем данные текущего авторизованного пользователя
        return self.request.user
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Добавляем посты пользователя (все статусы)
        context['user_posts'] = Post.objects.filter(author=self.request.user).order_by('-created_at')
        # Подсчитываем по статусам
        context['pending_count'] = Post.objects.filter(author=self.request.user, status='pending').count()
        context['published_count'] = Post.objects.filter(author=self.request.user, status='published').count()
        context['rejected_count'] = Post.objects.filter(author=self.request.user, status='rejected').count()
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
    """
    try:
        user_obj = User.objects.get(permanent_id=permanent_id)
    except User.DoesNotExist:
        raise Http404("User not found")

    # Expected file path
    filename = f"{permanent_id}.png"
    cards_dir = os.path.join(settings.MEDIA_ROOT, 'cards')
    filepath = os.path.join(cards_dir, filename)

    # If missing, try to generate
    if not os.path.exists(filepath):
        # generate_qr_code_for_user saves file to MEDIA_ROOT/cards/
        try:
            generate_qr_code_for_user(user_obj)
        except Exception:
            # swallow exceptions here and return 404
            raise Http404("QR generation failed")

    # If still missing -> 404
    if not os.path.exists(filepath):
        raise Http404("QR not available")

    # If download requested, ensure only owner or staff can download
    download = request.GET.get('download') in ['1', 'true', 'yes']
    if download:
        if not request.user.is_authenticated or (request.user.id != user_obj.id and not request.user.is_staff):
            return HttpResponseForbidden('Not allowed')

    # Serve file
    response = FileResponse(open(filepath, 'rb'), content_type='image/png')
    if download:
        response['Content-Disposition'] = f'attachment; filename=qr_{user_obj.username}.png'
    else:
        # Inline display
        response['Content-Disposition'] = f'inline; filename=qr_{user_obj.username}.png'
    return response


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
