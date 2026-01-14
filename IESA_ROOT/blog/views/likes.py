"""Views для лайков"""

from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required

from ..models import Post, Comment, Like, CommentLike


@login_required
def like_post(request, pk):
    """Лайк/дизлайк поста через HTMX"""
    post = get_object_or_404(Post, pk=pk)
    
    # Переключаем лайк
    like, created = Like.objects.get_or_create(post=post, user=request.user)
    if not created:
        like.delete()
        is_liked = False
    else:
        is_liked = True
    
    # Если HTMX - возвращаем фрагмент кнопки
    if request.htmx:
        return render(request, 'blog/htmx/like_button.html', {
            'post': post,
            'is_liked': is_liked,
            'like_count': post.likes.count(),
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
