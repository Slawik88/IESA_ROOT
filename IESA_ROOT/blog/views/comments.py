"""Views для комментариев"""

from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required

from ..models import Post, Comment
from ..forms import CommentForm
from ..utils.helpers import get_comment_likes_map
from users.ratelimit_utils import comment_ratelimit


@login_required
@comment_ratelimit
def comment_create(request, pk):
    """Создание комментария через HTMX"""
    post = get_object_or_404(Post, pk=pk)
    
    # Только POST
    if request.method != 'POST':
        return HttpResponse(status=405, content='Method Not Allowed. Use POST.')
    
    text = request.POST.get('text', '').strip()
    parent_id = request.POST.get('parent_id')
    
    if not text:
        return redirect('post_detail', pk=pk)
    
    # Создаём комментарий
    parent = None
    if parent_id:
        parent = get_object_or_404(Comment, pk=parent_id, post=post)
    
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
            'comments': post.comments.filter(parent__isnull=True),
            'comment_form': CommentForm(),
            'just_posted_id': comment.pk,
            'comment_likes_map': get_comment_likes_map(post, request.user),
        })
    
    return redirect('post_detail', pk=pk)


def comment_list(request, pk):
    """Список комментариев через HTMX"""
    post = get_object_or_404(Post, pk=pk)
    
    return render(request, 'blog/htmx/comments_section.html', {
        'post': post,
        'comments': post.comments.filter(parent__isnull=True),
        'comment_likes_map': get_comment_likes_map(post, request.user),
    })


@login_required
def delete_comment(request, pk, comment_pk):
    """Удаление комментария"""
    comment = get_object_or_404(Comment, pk=comment_pk, post_id=pk)
    
    # Только автор или модератор
    if request.user != comment.author and not request.user.is_staff:
        return HttpResponse(status=403, content='Forbidden')
    
    comment.delete()
    
    # Если HTMX - обновляем список
    if request.htmx:
        post = get_object_or_404(Post, pk=pk)
        return render(request, 'blog/htmx/comments_section.html', {
            'post': post,
            'comments': post.comments.filter(parent__isnull=True),
            'comment_form': CommentForm(),
            'comment_likes_map': get_comment_likes_map(post, request.user),
        })
    
    return redirect('post_detail', pk=pk)
