"""Views для лайков"""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from ..models import Post, Comment, Like, CommentLike


def like_post(request, pk):
    """Кнопка лайка поста.

    GET — текущее состояние кнопки (доступно и анониму: hx-trigger="load"
    в post_detail не должен ни переключать лайк, ни свапать страницу логина).
    POST — переключение лайка (только для залогиненных).
    """
    post = get_object_or_404(Post, pk=pk)

    if request.method == 'POST':
        if not request.user.is_authenticated:
            if request.htmx:
                response = HttpResponse(status=204)
                response['HX-Redirect'] = f"{reverse('users:login')}?next={post.get_absolute_url()}"
                return response
            return redirect_to_login(post.get_absolute_url())
        like, created = Like.objects.get_or_create(post=post, user=request.user)
        if not created:
            like.delete()
        is_liked = created
    else:
        is_liked = request.user.is_authenticated and Like.objects.filter(
            post=post, user=request.user,
        ).exists()

    if request.htmx:
        # OPTIMIZATION: Use aggregate instead of .count() query
        like_count = Like.objects.filter(post=post).aggregate(count=Count('id'))['count']

        return render(request, 'blog/htmx/like_button.html', {
            'post': post,
            'is_liked': is_liked,
            'like_count': like_count,
        })

    return HttpResponse(status=204)


@login_required
def toggle_comment_like(request, pk, comment_pk):
    """Лайк/дизлайк комментария через HTMX"""
    comment = get_object_or_404(Comment, pk=comment_pk, post_id=pk)
    
    # Переключаем лайк
    like, created = CommentLike.objects.get_or_create(
        comment=comment,
        user=request.user
    )
    if not created:
        like.delete()
        is_liked = False
    else:
        is_liked = True
    
    # Если HTMX - возвращаем фрагмент кнопки
    if request.htmx:
        return render(request, 'blog/htmx/comment_like_button.html', {
            'comment': comment,
            'is_liked': is_liked,
        })
    
    return HttpResponse(status=204)
