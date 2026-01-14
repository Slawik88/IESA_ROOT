"""Views для подписок"""

from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required

from ..models import Post, BlogSubscription


@login_required
def toggle_subscription(request, author_pk):
    """Подписка/отписка от автора через HTMX"""
    from users.models import User
    
    author = get_object_or_404(User, pk=author_pk)
    
    # Переключаем подписку
    subscription, created = BlogSubscription.objects.get_or_create(
        subscriber=request.user,
        author=author
    )
    if not created:
        subscription.delete()
        is_subscribed = False
    else:
        is_subscribed = True
    
    # Если HTMX - возвращаем фрагмент кнопки
    if request.htmx:
        return render(request, 'blog/htmx/subscribe_button.html', {
            'author': author,
            'is_subscribed': is_subscribed,
            'subscriber_count': BlogSubscription.objects.filter(author=author).count(),
        })
    
    return HttpResponse(status=204)
