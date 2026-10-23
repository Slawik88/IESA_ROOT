"""Views для комментариев"""

from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext as _

from ..models import Comment
from ..forms import CommentForm
from ..utils.helpers import get_comment_likes_map
from ..utils.querysets import comments_for_post, visible_posts
from django.views.decorators.http import require_POST
from users.ratelimit_utils import comment_ratelimit


@login_required
@comment_ratelimit
@require_POST
def comment_create(request, pk):
    """Создание комментария через HTMX"""
    post = get_object_or_404(visible_posts(request.user), pk=pk)
    
    text = request.POST.get('text', '').strip()
    parent_id = request.POST.get('parent_id')
    if parent_id:
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            return HttpResponse(status=400)
    
    if not text:
        return redirect('blog:post_detail', pk=pk)

    # Создаём комментарий
    parent = None
    if parent_id:
        parent = get_object_or_404(Comment, pk=parent_id, post=post)
        # Запрещаем ответ на ответ (максимум 1 уровень вложенности) (B2-10)
        if parent.parent_id is not None:
            return HttpResponse(status=400, content=_('Replies to replies are not supported.'))
    
    comment = Comment.objects.create(
        post=post,
        author=request.user,
        text=text,
        parent=parent
    )
    
    # Если HTMX - возвращаем обновлённый список
    if request.htmx:
        return render(request, 'blog/htmx/comments_section.html', {
            'post': post,
            'comments': comments_for_post(post),
            'comment_form': CommentForm(),
            'just_posted_id': comment.pk,
            'comment_likes_map': get_comment_likes_map(post, request.user),
        })
    
    return redirect('blog:post_detail', pk=pk)


def comment_list(request, pk):
    """Список комментариев через HTMX"""
    post = get_object_or_404(visible_posts(request.user), pk=pk)
    
    return render(request, 'blog/htmx/comments_section.html', {
        'post': post,
        'comments': comments_for_post(post),
        'comment_likes_map': get_comment_likes_map(post, request.user),
    })


@login_required
@require_POST
def delete_comment(request, pk, comment_pk):
    """Удаление комментария"""
    comment = get_object_or_404(Comment, pk=comment_pk, post_id=pk)
    
    # Только автор или модератор
    if request.user != comment.author and not request.user.is_staff:
        return HttpResponse(status=403, content=_('Forbidden'))
    
    comment.delete()
    
    # Если HTMX - обновляем список
    if request.htmx:
        post = get_object_or_404(visible_posts(request.user), pk=pk)
        return render(request, 'blog/htmx/comments_section.html', {
            'post': post,
            'comments': comments_for_post(post),
            'comment_form': CommentForm(),
            'comment_likes_map': get_comment_likes_map(post, request.user),
        })
    
    return redirect('blog:post_detail', pk=pk)
