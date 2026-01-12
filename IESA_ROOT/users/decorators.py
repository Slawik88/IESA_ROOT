"""
Security decorators для защиты endpoints от abuse
"""
from django.utils.decorators import decorator_from_middleware
from django_ratelimit.decorators import ratelimit
from django.http import HttpResponse


def ratelimit_view(rate='5/m', key='ip'):
    """
    Decorator для rate limiting на views
    
    Args:
        rate: строка вида '5/m' (5 запросов в минуту)
        key: 'ip' или 'user'
    """
    def decorator(view_func):
        return ratelimit(key=key, rate=rate, method='GET')(view_func)
    return decorator


# Готовые rate limits для разных типов действий
SEARCH_RATE = '20/m'  # 20 поисков в минуту
QR_RATE = '10/m'  # 10 QR requests в минуту  
AUTH_RATE = '5/m'  # 5 попыток логина в минуту
API_RATE = '100/h'  # 100 API запросов в час
