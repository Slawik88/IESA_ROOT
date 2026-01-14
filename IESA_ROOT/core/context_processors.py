"""
Context processors для core app
"""
from core.models import SocialNetwork

def social_networks(request):
    """
    Добавляет активные соц сети в контекст всех шаблонов
    """
    return {
        'social_networks': SocialNetwork.objects.filter(is_active=True)
    }
