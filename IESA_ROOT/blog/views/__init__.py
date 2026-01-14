"""Views для blog - модульная структура"""

from .posts import PostListView, PostDetailView, PostCreateView
from .events import EventListView, EventDetailView
from .comments import comment_create, comment_list, delete_comment
from .likes import like_post, toggle_comment_like
from .search import post_search, global_search
from .subscriptions import toggle_subscription

__all__ = [
    # Posts
    'PostListView',
    'PostDetailView',
    'PostCreateView',
    
    # Events
    'EventListView',
    'EventDetailView',
    
    # Comments
    'comment_create',
    'comment_list',
    'delete_comment',
    
    # Likes
    'like_post',
    'toggle_comment_like',
    
    # Search
    'post_search',
    'global_search',
    
    # Subscriptions
    'toggle_subscription',
]
