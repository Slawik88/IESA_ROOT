"""Утилиты поиска"""

from django.db.models import Q, Count
from ..models import Post, Event
from ..constants import SEARCH_POSTS_LIMIT, SEARCH_EVENTS_LIMIT


def search_posts(query, status=None, sort='latest', limit=SEARCH_POSTS_LIMIT):
    """
    Поиск постов
    
    Args:
        query: поисковый запрос
        status: фильтр по статусу (published, pending и т.д.)
        sort: сортировка (latest, popular, trending)
        limit: максимум результатов
    """
    posts = Post.objects.all()
    
    # Фильтр по статусу
    if status:
        posts = posts.filter(status=status)
    
    # Поиск по тексту
    if query:
        posts = posts.filter(Q(title__icontains=query) | Q(text__icontains=query))
    
    # Сортировка
    if sort == 'popular':
        from ..constants import LIKE_WEIGHT, COMMENT_WEIGHT
        posts = posts.annotate(
            engagement=Count('likes') * LIKE_WEIGHT + Count('comments') * COMMENT_WEIGHT
        ).order_by('-engagement', '-created_at')
    elif sort == 'trending':
        posts = posts.annotate(
            engagement=Count('likes') + Count('comments')
        ).filter(engagement__gt=0).order_by('-engagement', '-created_at')
    else:  # latest
        posts = posts.order_by('-created_at')
    
    return posts[:limit]


def search_events(query, limit=SEARCH_EVENTS_LIMIT):
    """Поиск событий"""
    if not query:
        return Event.objects.none()
    
    return Event.objects.filter(
        Q(title__icontains=query) | Q(description__icontains=query)
    ).select_related('created_by').order_by('-date')[:limit]
