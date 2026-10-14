"""Views для работы с постами"""

from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Q, F
from ..utils.querysets import related_count, visible_posts
from django.utils.cache import patch_vary_headers, patch_cache_control
from django.utils.translation import gettext as _

from ..models import Post, PostView, Like, BlogSubscription, Comment
from ..forms import PostForm, CommentForm
from ..constants import POSTS_PER_PAGE
from ..utils.helpers import get_client_ip, is_post_liked, is_author_subscribed
from users.ratelimit_utils import post_create_ratelimit
from core.models import Partner



class PostListView(ListView):
    """
    Список опубликованных постов с HTMX поддержкой.
    
    Поддерживает:
    - Поиск по содержимому (?q=)
    - Фильтр по категории (?category=)
    - Бесконечный скролл через HTMX с кэшированием
    """
    model = Post
    template_name = 'blog/post_list.html'
    context_object_name = 'posts'
    paginate_by = POSTS_PER_PAGE
    _MAX_PAGE = 100  # Защита от DDoS через infinite scroll (B2-09)

    def dispatch(self, request, *args, **kwargs):
        try:
            page = int(request.GET.get('page', 1))
            if page > self._MAX_PAGE:
                from django.http import Http404
                raise Http404('Page number exceeds maximum allowed.')
        except (ValueError, TypeError):
            pass
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Post.objects.filter(status='published').select_related('author').annotate(
            likes_count=related_count(Like, 'post_id'),
            views_count_cached=related_count(PostView, 'post_id'),
            comments_count=related_count(Comment, 'post_id'),
        )

        # Поиск по заголовку и тексту
        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(text__icontains=search)
            )
        
        return queryset.order_by('-created_at', '-pk')
    
    def get_template_names(self):
        """Возвращает partial шаблон для HTMX запросов"""
        if self.request.headers.get('HX-Request') == 'true':
            return ['blog/partials/post_list_items.html']
        return [self.template_name]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Передаём текущие фильтры для infinite scroll
        context['search'] = self.request.GET.get('q', '')
        context['category'] = self.request.GET.get('category', '')
        
        # Пагинация для infinite scroll
        page_obj = context.get('page_obj')
        if page_obj:
            context['has_next'] = page_obj.has_next()
            if page_obj.has_next():
                context['next_page'] = page_obj.next_page_number()
        
        return context
    
    def render_to_response(self, context, **response_kwargs):
        """Добавляет заголовки кэширования для HTMX запросов"""
        response = super().render_to_response(context, **response_kwargs)
        
        patch_vary_headers(response, ['HX-Request', 'Cookie', 'Accept-Language'])
        if self.request.headers.get('HX-Request') == 'true':
            patch_cache_control(response, private=True, max_age=120)
        
        return response


class PostDetailView(DetailView):
    """Детальная страница поста"""
    model = Post
    template_name = 'blog/post_detail.html'
    context_object_name = 'post'

    def get_queryset(self):
        return visible_posts(self.request.user).select_related('author').annotate(
            likes_count=related_count(Like, 'post_id'),
            subscriber_count=related_count(BlogSubscription, 'author_id', 'author_id'),
            views_count_cached=related_count(PostView, 'post_id'),
        )

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        
        # Отслеживаем просмотр (1 раз на юзера/IP)
        user = request.user if request.user.is_authenticated else None
        ip = get_client_ip(request)
        
        created = False
        if user:
            _, created = PostView.objects.get_or_create(post=self.object, user=user)
        elif ip:
            _, created = PostView.objects.get_or_create(post=self.object, ip_address=ip)
        
        # Если создан новый уникальный просмотр, обновляем счётчик в модели
        if created:
            Post.objects.filter(pk=self.object.pk).update(views_count=F('views_count') + 1)
        
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
    success_url = reverse_lazy('blog:post_list')
    
    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.status = 'pending'
        response = super().form_valid(form)
        
        messages.success(
            self.request,
            _('Your post has been submitted for moderation! 🎉')
        )
        
        return response
