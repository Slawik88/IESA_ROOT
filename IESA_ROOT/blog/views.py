"""
Blog Views - Модульная архитектура

Структура:
    views/
        posts.py - работа с постами
        events.py - события
        comments.py - комментарии
        likes.py - лайки
        search.py - поиск
        subscriptions.py - подписки

Для обратной совместимости все views экспортируются отсюда
"""

# Импортируем все views из модулей
from .views.posts import PostListView, PostDetailView, PostCreateView
from .views.events import EventListView, EventDetailView
from .views.comments import comment_create, comment_list, delete_comment
from .views.likes import like_post, toggle_comment_like
from .views.search import post_search, global_search
from .views.subscriptions import toggle_subscription

# Экспортируем всё для urls.py
__all__ = [
    'PostListView',
    'PostDetailView',
    'PostCreateView',
    'EventListView',
    'EventDetailView',
    'comment_create',
    'comment_list',
    'delete_comment',
    'like_post',
    'toggle_comment_like',
    'post_search',
    'global_search',
    'toggle_subscription',
]
