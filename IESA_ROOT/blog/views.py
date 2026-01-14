import logging
import re
from django.views.generic import ListView, DetailView, CreateView
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.urls import reverse_lazy
from django.utils import timezone
from django.contrib import messages
from django import forms
from django.utils.decorators import method_decorator
from .models import Post, Comment, Like, Event, PostView, BlogSubscription
from core.models import Partner
from .forms import PostForm
from users.search_utils import highlight_text, normalize_search_query
from users.ratelimit_utils import post_create_ratelimit, comment_ratelimit, search_ratelimit

logger = logging.getLogger('blog')


class CommentForm(forms.ModelForm):
    """
    Форма для создания комментария.
    """
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Напишите комментарий...'
            })
        }

# ====================================================================
# Основные Views
# ====================================================================

class PostListView(ListView):
    """
    Отображение списка опубликованных постов.
    """
    model = Post
    template_name = 'blog/post_list.html'
    context_object_name = 'posts'
    paginate_by = 10

    def get_queryset(self):
        # Показываем только опубликованные посты
        # select_related author to reduce queries, prefetch likes for counts
        return (Post.objects.filter(status='published')
                .select_related('author')
                .prefetch_related('likes')
                .order_by('-created_at'))

class PostDetailView(DetailView):
    """
    Детальная страница поста.
    """
    model = Post
    template_name = 'blog/post_detail.html'
    context_object_name = 'post'

    def get(self, request, *args, **kwargs):
        # Track view - only count once per user/IP
        response = super().get(request, *args, **kwargs)
        
        # Get user or IP
        user = request.user if request.user.is_authenticated else None
        ip_address = self.get_client_ip(request)
        
        # Try to record view (unique_together constraint prevents duplicates)
        if user:
            PostView.objects.get_or_create(post=self.object, user=user)
        elif ip_address:
            PostView.objects.get_or_create(post=self.object, ip_address=ip_address)
        
        # Update view count
        self.object.views_count = self.object.user_views.count()
        self.object.save(update_fields=['views_count'])
        return response
    
    def get_client_ip(self, request):
        """Get client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Проверяем, лайкал ли пользователь этот пост
        context['is_liked'] = False  # Дефолтное значение
        context['is_subscribed'] = False  # Дефолтное значение для подписки
        if self.request.user.is_authenticated:
            context['is_liked'] = Like.objects.filter(post=self.object, user=self.request.user).exists()
            context['is_subscribed'] = BlogSubscription.objects.filter(user=self.request.user, author=self.object.author).exists()
        # Use annotations or cached prefetch where possible
        context['like_count'] = self.object.likes.count()
        context['subscriber_count'] = BlogSubscription.objects.filter(author=self.object.author).count()
        context['comment_form'] = CommentForm()
        # Prefetch top-level comments and their replies to avoid N+1
        context['comments'] = self.object.comments.filter(parent__isnull=True).prefetch_related('replies', 'replies__author')
        # Expose partners for sidebar/modal — Partner model doesn't have is_featured field
        # Используем просто последние партнеры, отсортированные по name (или по id при отсутствии даты)
        try:
            context['featured_partners'] = Partner.objects.all().order_by('name')[:6]
        except Exception:
            context['featured_partners'] = Partner.objects.all()[:6]
        # Recommended posts (same author or popular)
        context['recommended_posts'] = self.object.get_recommended_posts(limit=5)
        return context

def partner_list(request):
    """Render partners listing (cards) — can be used standalone or via HTMX/modal."""
    # Not used anymore: partners are shown on the homepage (core app)
    return redirect('home')

@method_decorator(post_create_ratelimit, name='dispatch')
class PostCreateView(LoginRequiredMixin, CreateView):
    """
    Форма для создания нового поста (уходит на модерацию).
    """
    model = Post
    form_class = PostForm
    template_name = 'blog/post_create.html'
    success_url = reverse_lazy('post_list') 
    
    def form_valid(self, form):
        # Автоматически устанавливаем автора и статус "pending"
        form.instance.author = self.request.user
        form.instance.status = 'pending'
        response = super().form_valid(form)
        # Отправляем сообщение об успешной отправке поста
        messages.success(self.request, 'Ваш пост успешно отправлен на модерацию! 🎉 Статус можно отследить в личном кабинете.')
        return response

class EventListView(ListView):
    """
    Список предстоящих событий.
    Optimized with select_related and prefetch_related
    """
    model = Event
    template_name = 'blog/event_list.html'
    context_object_name = 'events'
    
    def get_queryset(self):
        # Сортировка по дате (предстоящие - первыми)
        # OPTIMIZED: select_related для created_by
        return Event.objects.filter(
            date__gte=timezone.now()
        ).select_related(
            'created_by'
        ).order_by('date')


class EventDetailView(DetailView):
    """
    Детальная страница события.
    """
    model = Event
    template_name = 'blog/event_detail.html'
    context_object_name = 'event'

# ====================================================================
# HTMX и Комментарии Views
# ====================================================================

def like_post(request, pk):
    """
    HTMX endpoint:
    - GET: возвращает шаблон кнопки (не меняя состояние) — доступно всем
    - POST: переключает лайк для аутентифицированного пользователя
    """
    post = get_object_or_404(Post, pk=pk)
    is_liked = False

    # Если POST — пытаемся переключить лайк (требуется авторизация)
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return HttpResponse(status=401)  # unauthorized for AJAX
        user = request.user
        try:
            like = Like.objects.get(post=post, user=user)
            like.delete()
            is_liked = False
        except Like.DoesNotExist:
            Like.objects.create(post=post, user=user)
            is_liked = True
    else:
        # GET — только показываем состояние для текущего пользователя (если он есть)
        if request.user.is_authenticated:
            is_liked = Like.objects.filter(post=post, user=request.user).exists()

    context = {
        'post': post,
        'is_liked': is_liked,
        'like_count': post.likes.count(),
    }
    return render(request, 'blog/htmx/like_button.html', context)

@login_required
@comment_ratelimit
def comment_create(request, pk):
    """Создание комментария через HTMX"""
    post = get_object_or_404(Post, pk=pk)
    
    # Только POST
    if request.method != 'POST':
        return HttpResponse(status=405, content='Method Not Allowed. Use POST.')
    
    text = request.POST.get('text', '').strip()
    parent_id = request.POST.get('parent_id')
    
    if not text:
        return redirect('post_detail', pk=pk)
    
    # Создаём комментарий
    parent = None
    if parent_id:
        parent = get_object_or_404(Comment, pk=parent_id, post=post)
    
    comment = Comment.objects.create(
        post=post,
        author=request.user,
        text=text,
        parent=parent
    )
    
    # Если HTMX - возвращаем обновлённый список комментариев
    if request.htmx:
        from .models import CommentLike
        
        # Какие комментарии лайкнул текущий юзер
        liked_ids = CommentLike.objects.filter(
            comment__post=post,
            user=request.user
        ).values_list('comment_id', flat=True)
        
        return render(request, 'blog/htmx/comments_section.html', {
            'post': post,
            'comments': post.comments.filter(parent__isnull=True),
            'comment_form': CommentForm(),
            'just_posted_id': comment.pk,
            'comment_likes_map': {cid: True for cid in liked_ids},
        })
    
    return redirect('post_detail', pk=pk)



def comment_list(request, pk):
    """
    Load comments section for HTMX (root comments only).
    """
    post = get_object_or_404(Post, pk=pk)
    comments = post.comments.filter(parent__isnull=True)
    
    # Подготавливаем мап лайков текущего пользователя для каждого комментария
    comment_likes_map = {}
    if request.user.is_authenticated:
        from .models import CommentLike
        # Получаем все лайки текущего пользователя для комментариев этого поста
        liked_comment_ids = CommentLike.objects.filter(
            comment__post=post,
            user=request.user
        ).values_list('comment_id', flat=True)
        comment_likes_map = {cid: True for cid in liked_comment_ids}
    
    context = {
        'post': post,
        'comments': comments,
        'comment_likes_map': comment_likes_map,
    }
    return render(request, 'blog/htmx/comments_section.html', context)


from django.db import models as django_models


def post_search(request):
    """Поиск постов с фильтрами через HTMX"""
    from django.db.models import Q, Count
    
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    sort = request.GET.get('sort', 'latest').strip()
    
    # Базовый queryset
    posts = Post.objects.all()
    
    # Фильтр по статусу
    if status:
        posts = posts.filter(status=status)
    
    # Поиск по тексту
    if query:
        normalized = normalize_search_query(query)
        posts = posts.filter(Q(title__icontains=normalized) | Q(text__icontains=normalized))
    
    # Сортировка
    if sort == 'popular':
        posts = posts.annotate(
            engagement=Count('likes') * 2 + Count('comments') * 3
        ).order_by('-engagement', '-created_at')
    elif sort == 'trending':
        posts = posts.annotate(
            engagement=Count('likes') + Count('comments')
        ).filter(engagement__gt=0).order_by('-engagement', '-created_at')
    else:  # latest
        posts = posts.order_by('-created_at')
    
    return render(request, 'blog/htmx/posts_list_fragment.html', {
        'posts': posts[:12]
    })



@login_required
def delete_comment(request, pk, comment_pk):
    """
    HTMX endpoint to delete a comment. Only author or staff can delete.
    """
    post = get_object_or_404(Post, pk=pk)
    comment = get_object_or_404(Comment, pk=comment_pk, post=post)

    # Права: только автор или стафф
    if request.user == comment.author or request.user.is_staff:
        comment.delete()

    # Return refreshed comments section for HTMX
    if request.htmx:
        context = {
            'post': post,
            'comments': post.comments.filter(parent__isnull=True),
            'comment_form': CommentForm(),
        }
        return render(request, 'blog/htmx/comments_section.html', context)

    return redirect('post_detail', pk=pk)


@login_required
def toggle_comment_like(request, pk, comment_pk):
    """
    Toggle like on a comment via HTMX.
    """
    post = get_object_or_404(Post, pk=pk)
    comment = get_object_or_404(Comment, pk=comment_pk, post=post)
    user = request.user

    # Try to remove like
    from .models import CommentLike
    try:
        cl = CommentLike.objects.get(comment=comment, user=user)
        cl.delete()
        is_liked = False
    except CommentLike.DoesNotExist:
        CommentLike.objects.create(comment=comment, user=user)
        is_liked = True

    context = {'comment': comment, 'is_liked': is_liked, 'like_count': comment.likes.count()}
    return render(request, 'blog/htmx/comment_like_button.html', context)


@login_required
def toggle_subscription(request, author_pk):
    """
    HTMX endpoint to toggle blog subscription to an author.
    - GET: Return the current subscription button state
    - POST: Toggle subscription status
    """
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    author = get_object_or_404(User, pk=author_pk)
    user = request.user
    
    # Prevent user from subscribing to themselves
    if user == author:
        return HttpResponse(status=400)
    
    is_subscribed = False
    
    # If POST, toggle subscription
    if request.method == 'POST':
        # Toggle subscription
        subscription, created = BlogSubscription.objects.get_or_create(user=user, author=author)
        if not created:
            subscription.delete()
            is_subscribed = False
        else:
            is_subscribed = True
    else:
        # GET - just check if subscribed
        is_subscribed = BlogSubscription.objects.filter(user=user, author=author).exists()
    
    # Get subscription count for the author
    subscriber_count = BlogSubscription.objects.filter(author=author).count()
    
    context = {
        'author': author,
        'is_subscribed': is_subscribed,
        'subscriber_count': subscriber_count,
    }
    return render(request, 'blog/htmx/subscribe_button.html', context)


def validate_search_query(query):
    """
    Validate and sanitize search query for security
    """
    if not query:
        return ''
    
    # Limit length to prevent abuse
    if len(query) > 100:
        logger.warning(f"Search query too long ({len(query)} chars), truncating")
        query = query[:100]
    
    # Allow only safe characters: alphanumeric, spaces, and basic punctuation
    # Supports Cyrillic, Latin, numbers, spaces, hyphens, underscores
    safe_pattern = re.compile(r'[^a-zA-Zа-яА-ЯёЁ0-9\s\-_.,!?]')
    if safe_pattern.search(query):
        logger.info(f"Removing unsafe characters from search query")
        query = safe_pattern.sub('', query)
    
    return query.strip()


def global_search(request):
    """Глобальный поиск по всему сайту через HTMX"""
    from django.db.models import Q
    from core.models import Partner
    from users.models import User
    
    query = request.GET.get('q', '').strip()
    
    # Пустой запрос - возвращаем пустые результаты
    if not query:
        return render(request, 'blog/htmx/post_search_results.html', {
            'query': '',
            'results': {'users': [], 'posts': [], 'events': [], 'partners': []}
        })
    
    # Нормализуем запрос (удаляем @ в начале и т.д.)
    normalized = normalize_search_query(query)
    
    # Логируем поиск
    logger.info(f"Search: '{query}' (normalized: '{normalized}') by {request.user.username if request.user.is_authenticated else 'anon'}")
    
    results = {'users': [], 'posts': [], 'events': [], 'partners': []}
    
    # Минимум 2 символа для поиска
    if len(normalized) < 2:
        return render(request, 'blog/htmx/post_search_results.html', {
            'query': query,
            'results': results
        })
    
    try:
        # Поиск пользователей (только с валидным username)
        results['users'] = User.objects.filter(
            Q(username__icontains=normalized) |
            Q(first_name__icontains=normalized) |
            Q(last_name__icontains=normalized) |
            Q(email__icontains=normalized)
        ).exclude(username='').order_by('-is_verified', 'username')[:8]
        
        # Поиск постов (только опубликованные)
        results['posts'] = Post.objects.filter(
            Q(title__icontains=normalized) | Q(text__icontains=normalized),
            status='published'
        ).select_related('author').order_by('-created_at')[:6]
        
        # Поиск событий
        results['events'] = Event.objects.filter(
            Q(title__icontains=normalized) | Q(description__icontains=normalized)
        ).select_related('created_by').order_by('-date')[:6]
        
        # Поиск партнёров
        results['partners'] = Partner.objects.filter(
            Q(name__icontains=normalized) | Q(description__icontains=normalized)
        ).order_by('name')[:6]
        
        logger.info(f"Found: {len(results['users'])} users, {len(results['posts'])} posts, {len(results['events'])} events, {len(results['partners'])} partners")
        
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
    
    return render(request, 'blog/htmx/post_search_results.html', {
        'query': query,
        'results': results
    })