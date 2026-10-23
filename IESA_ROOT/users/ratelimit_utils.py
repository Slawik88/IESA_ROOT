"""
Rate limiting utilities for IESA platform.
Protects against spam and abuse with sensible limits that won't affect normal users.
"""
from django_ratelimit.decorators import ratelimit
from functools import wraps


def safe_ratelimit(group=None, key='ip', rate='60/h', method='POST', block=True):
    """
    Wrapper for django-ratelimit with safe defaults.
    These limits are high enough that normal users won't notice them.

    Default limits:
    - 60 requests per hour per IP (1 per minute average)

    Common usage:
    - Login: 40/h (prevents brute force)
    - Register: 30/h (prevents spam accounts)
    - Post creation: 30/h (prevents spam)
    - Comments: 60/h (normal conversation rate)

    With block=False the view still runs and ``request.limited`` is set, so it
    can answer with a human message instead of the generic 403 page.

    Mobile carriers and event Wi-Fi put many people behind one public IP, so
    auth limits must leave room for a crowd, not just one person.
    """
    def decorator(view_func):
        @wraps(view_func)
        @ratelimit(group=group, key=key, rate=rate, method=method, block=block)
        def wrapped_view(request, *args, **kwargs):
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


# Predefined decorators for common scenarios
login_ratelimit = safe_ratelimit(group='login', rate='40/h')
register_ratelimit = safe_ratelimit(group='register', rate='30/h', block=False)
password_reset_ratelimit = safe_ratelimit(group='password_reset', rate='10/h', block=False)
post_create_ratelimit = safe_ratelimit(group='post_create', rate='30/h')
comment_ratelimit = safe_ratelimit(group='comment', rate='60/h')
search_ratelimit = safe_ratelimit(group='search', rate='100/h', method='GET')
