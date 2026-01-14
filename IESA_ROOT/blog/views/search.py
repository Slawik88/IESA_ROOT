"""Views для поиска"""

import logging
from django.shortcuts import render
from django.db.models import Q

from ..models import Post, Event
from ..constants import (
    MIN_SEARCH_LENGTH,
    SEARCH_USERS_LIMIT,
    SEARCH_POSTS_LIMIT,
    SEARCH_EVENTS_LIMIT,
    SEARCH_PARTNERS_LIMIT,
)
from ..utils.search import search_posts as util_search_posts
from core.models import Partner
from users.models import User
from users.search_utils import normalize_search_query

logger = logging.getLogger('blog')


def post_search(request):
    """Поиск постов через HTMX"""
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    sort = request.GET.get('sort', 'latest').strip()
    
    # Используем утилиту поиска
    posts = util_search_posts(
        normalize_search_query(query) if query else '',
        status=status,
        sort=sort
    )
    
    return render(request, 'blog/htmx/posts_list_fragment.html', {
        'posts': posts
    })


def global_search(request):
    """Глобальный поиск по всему сайту через HTMX"""
    query = request.GET.get('q', '').strip()
    
    # Пустой запрос
    if not query:
        return render(request, 'blog/htmx/post_search_results.html', {
            'query': '',
            'results': {'users': [], 'posts': [], 'events': [], 'partners': []}
        })
    
    # Нормализуем
    normalized = normalize_search_query(query)
    
    logger.info(f"Search: '{query}' → '{normalized}' by {request.user.username if request.user.is_authenticated else 'anon'}")
    
    results = {'users': [], 'posts': [], 'events': [], 'partners': []}
    
    # Минимум 2 символа
    if len(normalized) < MIN_SEARCH_LENGTH:
        return render(request, 'blog/htmx/post_search_results.html', {
            'query': query,
            'results': results
        })
    
    try:
        # Поиск пользователей
        results['users'] = User.objects.filter(
            Q(username__icontains=normalized) |
            Q(first_name__icontains=normalized) |
            Q(last_name__icontains=normalized) |
            Q(email__icontains=normalized)
        ).exclude(username='').order_by('-is_verified', 'username')[:SEARCH_USERS_LIMIT]
        
        # Поиск постов
        results['posts'] = Post.objects.filter(
            Q(title__icontains=normalized) | Q(text__icontains=normalized),
            status='published'
        ).select_related('author').order_by('-created_at')[:SEARCH_POSTS_LIMIT]
        
        # Поиск событий
        results['events'] = Event.objects.filter(
            Q(title__icontains=normalized) | Q(description__icontains=normalized)
        ).select_related('created_by').order_by('-date')[:SEARCH_EVENTS_LIMIT]
        
        # Поиск партнёров
        results['partners'] = Partner.objects.filter(
            Q(name__icontains=normalized) | Q(description__icontains=normalized)
        ).order_by('name')[:SEARCH_PARTNERS_LIMIT]
        
        logger.info(
            f"Found: {len(results['users'])} users, {len(results['posts'])} posts, "
            f"{len(results['events'])} events, {len(results['partners'])} partners"
        )
        
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
    
    return render(request, 'blog/htmx/post_search_results.html', {
        'query': query,
        'results': results
    })
