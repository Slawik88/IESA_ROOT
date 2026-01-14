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
    
    # DEBUG
    logger.info(f"[SEARCH DEBUG] Received query: '{query}' (length: {len(query)})")
    
    # Пустой запрос
    if not query:
        logger.info("[SEARCH DEBUG] Empty query - returning empty results")
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
        logger.info(f"[SEARCH DEBUG] Query too short ({len(normalized)} < {MIN_SEARCH_LENGTH})")
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
        
        # DEBUG: Выводим конкретные найденные объекты
        if results['users']:
            logger.info(f"[SEARCH DEBUG] Users: {[u.username for u in results['users']]}")
        if results['posts']:
            logger.info(f"[SEARCH DEBUG] Posts: {[p.title for p in results['posts']]}")
        if results['events']:
            logger.info(f"[SEARCH DEBUG] Events: {[e.title for e in results['events']]}")
        if results['partners']:
            logger.info(f"[SEARCH DEBUG] Partners: {[p.name for p in results['partners']]}")
        
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
    
    logger.info(f"[SEARCH DEBUG] Rendering template with query='{query}', results keys: {results.keys()}")
    return render(request, 'blog/htmx/post_search_results.html', {
        'query': query,
        'results': results
    })
