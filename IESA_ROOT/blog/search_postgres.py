"""
PostgreSQL Full-Text Search implementation for IESA.
Provides advanced search capabilities using SearchVector and SearchQuery.

Requirements:
- PostgreSQL database
- Install psycopg2: pip install psycopg2-binary
- Run migrations after implementing

Usage in views:
    from .search import advanced_search
    results = advanced_search(query, user=request.user)
"""

from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, F
from users.models import User
from blog.models import Post, Event


def advanced_search(query_text, user=None, search_type='all'):
    """
    Advanced full-text search across Users, Posts, and Events.
    
    Args:
        query_text (str): Search query
        user (User): Current user for permission filtering
        search_type (str): 'all', 'users', 'posts', or 'events'
    
    Returns:
        dict: {
            'users': QuerySet,
            'posts': QuerySet,
            'events': QuerySet,
            'total_count': int
        }
    """
    results = {
        'users': User.objects.none(),
        'posts': Post.objects.none(),
        'events': Event.objects.none(),
        'total_count': 0
    }
    
    if not query_text or len(query_text) < 3:
        return results
    
    # Create search query
    search_query = SearchQuery(query_text, search_type='websearch')
    
    # Search Users
    if search_type in ['all', 'users']:
        user_vector = SearchVector('username', weight='A') + \
                      SearchVector('first_name', weight='B') + \
                      SearchVector('last_name', weight='B') + \
                      SearchVector('bio', weight='C')
        
        users = (User.objects.annotate(
            search=user_vector,
            rank=SearchRank(user_vector, search_query)
        )
        .filter(search=search_query)
        .filter(username__isnull=False)
        .exclude(username='')
        .select_related('profile')
        .order_by('-rank', '-date_joined')[:20])
        
        results['users'] = users
        results['total_count'] += users.count()
    
    # Search Posts
    if search_type in ['all', 'posts']:
        post_vector = SearchVector('title', weight='A') + \
                      SearchVector('text', weight='B')
        
        posts = (Post.objects.annotate(
            search=post_vector,
            rank=SearchRank(post_vector, search_query)
        )
        .filter(search=search_query)
        .filter(status='published')
        .select_related('author', 'author__profile')
        .prefetch_related('likes', 'comments')
        .order_by('-rank', '-created_at')[:20])
        
        results['posts'] = posts
        results['total_count'] += posts.count()
    
    # Search Events
    if search_type in ['all', 'events']:
        event_vector = SearchVector('title', weight='A') + \
                       SearchVector('description', weight='B') + \
                       SearchVector('location', weight='C')
        
        events = (Event.objects.annotate(
            search=event_vector,
            rank=SearchRank(event_vector, search_query)
        )
        .filter(search=search_query)
        .select_related('organizer')
        .prefetch_related('participants')
        .order_by('-rank', '-date')[:20])
        
        results['events'] = events
        results['total_count'] += events.count()
    
    return results


def create_search_indexes():
    """
    Create GIN indexes for full-text search.
    
    Run this in a migration or management command:
    
    from django.contrib.postgres.search import SearchVector
    from django.db import migrations
    
    def create_indexes(apps, schema_editor):
        schema_editor.execute(
            "CREATE INDEX IF NOT EXISTS user_search_idx ON users_user USING GIN ((to_tsvector('russian', coalesce(username, '') || ' ' || coalesce(first_name, '') || ' ' || coalesce(last_name, '') || ' ' || coalesce(bio, ''))))"
        )
        schema_editor.execute(
            "CREATE INDEX IF NOT EXISTS post_search_idx ON blog_post USING GIN ((to_tsvector('russian', coalesce(title, '') || ' ' || coalesce(text, ''))))"
        )
        schema_editor.execute(
            "CREATE INDEX IF NOT EXISTS event_search_idx ON blog_event USING GIN ((to_tsvector('russian', coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(location, ''))))"
        )
    
    class Migration(migrations.Migration):
        dependencies = [
            ('blog', '0002_initial'),
        ]
        operations = [
            migrations.RunPython(create_indexes, reverse_code=migrations.RunPython.noop),
        ]
    """
    pass


def autocomplete_search(query_text, limit=10):
    """
    Fast autocomplete suggestions.
    
    Args:
        query_text (str): Partial query
        limit (int): Maximum results
    
    Returns:
        list: Suggested search terms
    """
    if len(query_text) < 2:
        return []
    
    suggestions = []
    
    # Username suggestions
    users = User.objects.filter(
        Q(username__istartswith=query_text) |
        Q(first_name__istartswith=query_text) |
        Q(last_name__istartswith=query_text)
    ).values_list('username', flat=True)[:limit]
    
    suggestions.extend(users)
    
    # Post title suggestions
    posts = Post.objects.filter(
        title__icontains=query_text,
        status='published'
    ).values_list('title', flat=True)[:limit]
    
    suggestions.extend(posts)
    
    return list(set(suggestions))[:limit]
