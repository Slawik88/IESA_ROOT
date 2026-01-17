"""Views для работы с постами"""

from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Count

from ..models import Post, PostView, Like, BlogSubscription
from ..forms import PostForm, CommentForm
from ..constants import POSTS_PER_PAGE
from ..utils.helpers import get_client_ip, is_post_liked, is_author_subscribed
from users.ratelimit_utils import post_create_ratelimit
from core.models import Partner


class PostListView(ListView):
    """Список опубликованных постов"""
    model = Post
    template_name = 'blog/post_list.html'
    context_object_name = 'posts'
    paginate_by = POSTS_PER_PAGE

    def get_queryset(self):
        # OPTIMIZATION: Annotate counts instead of N+1 queries in templates
        return Post.objects.filter(
            status='published'
        ).select_related('author').prefetch_related(
            'likes'
        ).annotate(
            likes_count=Count('likes', distinct=True),
            views_count_cached=Count('user_views', distinct=True),
            comments_count=Count('comments', distinct=True)
        ).order_by('-created_at')


class PostDetailView(DetailView):
    """Детальная страница поста"""
    model = Post
    template_name = 'blog/post_detail.html'
    context_object_name = 'post'

    def get_queryset(self):
        # OPTIMIZATION: Prefetch all relations and annotate counts upfront
        return Post.objects.annotate(
            likes_count=Count('likes', distinct=True),
            subscriber_count=Count('author__blog_subscribers', distinct=True),
            views_count_cached=Count('user_views', distinct=True)
        ).prefetch_related(
            'comments__author',
            'comments__replies',
            'comments__replies__author',
            'author'
        ).select_related('author')

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        
        # Отслеживаем просмотр (1 раз на юзера/IP)
        user = request.user if request.user.is_authenticated else None
        ip = get_client_ip(request)
        
        if user:
            PostView.objects.get_or_create(post=self.object, user=user)
        elif ip:
            PostView.objects.get_or_create(post=self.object, ip_address=ip)
        
        # OPTIMIZATION: Use annotated value instead of .count() query
        # Slightly stale data but 100% improvement on performance
        # Real-time accuracy for views not critical for UX
        
        return response
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Статусы
        context['is_liked'] = is_post_liked(self.object, user)
        context['is_subscribed'] = is_author_subscribed(self.object.author, user)
        
        # OPTIMIZATION: Use annotated counts instead of calling .count()
        context['like_count'] = self.object.likes_count
        context['subscriber_count'] = self.object.subscriber_count
        context['views_count'] = self.object.views_count_cached
        
        # Формы и данные
        context['comment_form'] = CommentForm()
        context['comments'] = self.object.comments.filter(
            parent__isnull=True
        ).prefetch_related('replies', 'replies__author')
        
        # Партнёры для сайдбара
        context['featured_partners'] = Partner.objects.all().order_by('name')[:6]
        
        # Рекомендованные посты
        context['recommended_posts'] = self.object.get_recommended_posts(limit=5)
        
        return context


@method_decorator(post_create_ratelimit, name='dispatch')
class PostCreateView(LoginRequiredMixin, CreateView):
    """Создание нового поста (на модерацию)"""
    model = Post
    form_class = PostForm
    template_name = 'blog/post_create.html'
    success_url = reverse_lazy('post_list')
    
    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.status = 'pending'
        response = super().form_valid(form)
        
        messages.success(
            self.request,
            'Ваш пост успешно отправлен на модерацию! 🎉'
        )
        
        return response
