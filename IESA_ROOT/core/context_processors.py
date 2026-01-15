"""
Context processors для core app
"""
from django.db import connection
from core.models import SocialNetwork

def social_networks(request):
    """
    Добавляет активные соц сети в контекст всех шаблонов
    """
    # Проверяем, существует ли таблица (на случай если миграции еще не запущены)
    table_name = SocialNetwork._meta.db_table
    if table_name in connection.introspection.table_names():
        try:
            return {
                'social_networks': SocialNetwork.objects.filter(is_active=True)
            }
        except Exception:
            pass
    
    return {
        'social_networks': []
    }

