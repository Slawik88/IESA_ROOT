"""Вспомогательные функции"""

from django.db.models import Q


def get_client_ip(request):
    """Получить IP клиента из запроса"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


def is_post_liked(post, user):
    """Проверить, лайкнул ли пользователь пост"""
    if not user.is_authenticated:
        return False
    from ..models import Like
    return Like.objects.filter(post=post, user=user).exists()


def is_author_subscribed(author, user):
    """Проверить, подписан ли пользователь на автора"""
    if not user.is_authenticated:
        return False
    from ..models import BlogSubscription
    return BlogSubscription.objects.filter(subscriber=user, author=author).exists()


def get_comment_likes_map(post, user):
    """Получить словарь лайкнутых комментариев"""
    if not user.is_authenticated:
        return {}
    
    from ..models import CommentLike
    liked_ids = CommentLike.objects.filter(
        comment__post=post,
        user=user
    ).values_list('comment_id', flat=True)
    
    return {cid: True for cid in liked_ids}
