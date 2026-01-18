"""
Typing indicator utilities using Django cache instead of database.
This is much faster and more suitable for real-time features.
"""
from django.core.cache import cache
from django.utils import timezone
import json


TYPING_TIMEOUT = 5  # seconds - how long typing indicator stays active


def set_typing(conversation_id, user_id, username):
    """
    Mark a user as typing in a conversation.
    
    Args:
        conversation_id: ID of the conversation
        user_id: ID of the user who is typing
        username: Username for display
    """
    cache_key = f'typing:conv:{conversation_id}:user:{user_id}'
    cache.set(cache_key, {
        'user_id': user_id,
        'username': username,
        'timestamp': timezone.now().isoformat()
    }, timeout=TYPING_TIMEOUT)


def get_typing_users(conversation_id, exclude_user_id=None):
    """
    Get list of users currently typing in a conversation.
    
    Args:
        conversation_id: ID of the conversation
        exclude_user_id: Optional user ID to exclude (typically current user)
        
    Returns:
        List of dicts with 'user_id' and 'username'
    """
    # Get all typing indicators for this conversation
    # Note: This requires scanning cache keys, which is not ideal
    # Better approach: use a single key with JSON list
    return get_typing_users_v2(conversation_id, exclude_user_id)


def get_typing_users_v2(conversation_id, exclude_user_id=None):
    """
    Improved version: Store all typing users in a single cache key as JSON.
    
    Args:
        conversation_id: ID of the conversation
        exclude_user_id: Optional user ID to exclude
        
    Returns:
        List of usernames currently typing
    """
    cache_key = f'typing:conv:{conversation_id}'
    typing_data = cache.get(cache_key, {})
    
    # Remove expired entries (older than TYPING_TIMEOUT seconds)
    current_time = timezone.now()
    typing_data = {
        user_id: data 
        for user_id, data in typing_data.items()
        if (current_time - timezone.datetime.fromisoformat(data['timestamp'])).total_seconds() < TYPING_TIMEOUT
    }
    
    # Filter out excluded user
    if exclude_user_id is not None:
        typing_data = {
            uid: data 
            for uid, data in typing_data.items() 
            if int(uid) != int(exclude_user_id)
        }
    
    return [data['username'] for data in typing_data.values()]


def set_typing_v2(conversation_id, user_id, username):
    """
    Improved version: Add user to the typing users list for this conversation.
    
    Args:
        conversation_id: ID of the conversation
        user_id: ID of the user who is typing
        username: Username for display
    """
    cache_key = f'typing:conv:{conversation_id}'
    
    # Get current typing data
    typing_data = cache.get(cache_key, {})
    
    # Add/update this user
    typing_data[str(user_id)] = {
        'username': username,
        'timestamp': timezone.now().isoformat()
    }
    
    # Store with timeout
    cache.set(cache_key, typing_data, timeout=TYPING_TIMEOUT * 2)


def clear_typing(conversation_id, user_id):
    """
    Clear typing indicator for a user in a conversation.
    
    Args:
        conversation_id: ID of the conversation
        user_id: ID of the user to clear
    """
    cache_key = f'typing:conv:{conversation_id}'
    typing_data = cache.get(cache_key, {})
    
    if str(user_id) in typing_data:
        del typing_data[str(user_id)]
        cache.set(cache_key, typing_data, timeout=TYPING_TIMEOUT * 2)
