"""
Context processors для core app
"""
from django.db import connection
from core.models import SocialNetwork

_TABLE_EXISTS: bool | None = None


def social_networks(request):
    """
    Добавляет активные соц сети в контекст всех шаблонов
    """
    global _TABLE_EXISTS
    table_name = SocialNetwork._meta.db_table
    if _TABLE_EXISTS is None:
        try:
            _TABLE_EXISTS = table_name in connection.introspection.table_names()
        except Exception:
            _TABLE_EXISTS = False
    if _TABLE_EXISTS:
        try:
            return {
                'social_networks': SocialNetwork.objects.filter(is_active=True)
            }
        except Exception:
            pass
    return {
        'social_networks': []
    }

