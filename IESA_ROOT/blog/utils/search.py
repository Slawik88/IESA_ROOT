"""Утилиты поиска"""

from django.db.models import Q, F
from .querysets import related_count, visible_posts
from ..models import Event, Like, Comment
from ..constants import SEARCH_POSTS_LIMIT, SEARCH_EVENTS_LIMIT


def search_posts(query, status=None, sort='latest', limit=SEARCH_POSTS_LIMIT, user=None):
    """
    Поиск постов
    
    Args:
        query: поисковый запрос
        status: фильтр по статусу (published, pending и т.д.)
        sort: сортировка (latest, popular, trending)
        limit: максимум результатов
    """
    posts = visible_posts(user).select_related('author').annotate(
        likes_count=related_count(Like, 'post_id'),
        comments_count=related_count(Comment, 'post_id'),
    )
    
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
            engagement=F('likes_count') * LIKE_WEIGHT + F('comments_count') * COMMENT_WEIGHT
        ).order_by('-engagement', '-created_at')
    elif sort == 'trending':
        posts = posts.annotate(
            engagement=F('likes_count') + F('comments_count')
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
