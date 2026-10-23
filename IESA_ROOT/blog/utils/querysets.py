"""Bounded queries shared by full pages and HTMX fragments."""
from django.db.models import Count, OuterRef, Subquery, IntegerField, Prefetch
from django.db.models.functions import Coalesce


def related_count(model, field, outer_field='pk'):
    """Count an indexed relation without multiplying unrelated JOIN rows."""
    counts = (model.objects.filter(**{field: OuterRef(outer_field)})
              .order_by().values(field).annotate(total=Count('pk')).values('total'))
    return Coalesce(Subquery(counts, output_field=IntegerField()), 0)


def comments_for_post(post):
    from ..models import Comment
    return post.comments.filter(parent__isnull=True).select_related('author').annotate(
        likes_count=Count('likes')
    ).prefetch_related(Prefetch('replies', queryset=Comment.objects.select_related('author')))


def visible_posts(user=None):
    from django.db.models import Q
    from ..models import Post

    posts = Post.objects.all()
    if user is not None and user.is_authenticated:
        if user.is_staff:
            return posts
        return posts.filter(Q(status='published') | Q(author=user))
    return posts.filter(status='published')
