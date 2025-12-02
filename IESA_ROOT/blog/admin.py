from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Post, Comment, Like, Event, PostView, CommentLike, BlogSubscription
from django.db import models as django_models
try:
    from ckeditor.widgets import CKEditorWidget
except Exception:
    CKEditorWidget = None


# Custom admin filters
class StatusFilter(admin.SimpleListFilter):
    title = 'publication status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return [
            ('published', 'Published'),
            ('pending', 'Pending Review'),
            ('rejected', 'Rejected'),
            ('draft', 'Draft'),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class AuthorFilter(admin.SimpleListFilter):
    title = 'author'
    parameter_name = 'author'

    def lookups(self, request, model_admin):
        authors = Post.objects.values_list('author__username', flat=True).distinct()
        return [(author, author) for author in authors]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(author__username=self.value())
        return queryset


# Custom admin actions
def publish_posts(modeladmin, request, queryset):
    """Publish selected posts"""
    count = queryset.update(status='published')
    modeladmin.message_user(request, f'{count} post(s) published successfully.')
publish_posts.short_description = '✅ Publish selected posts'


def reject_posts(modeladmin, request, queryset):
    """Reject selected posts"""
    count = queryset.update(status='rejected')
    modeladmin.message_user(request, f'{count} post(s) rejected.')
reject_posts.short_description = '❌ Reject selected posts'


def set_as_draft(modeladmin, request, queryset):
    """Move posts to draft"""
    count = queryset.update(status='draft')
    modeladmin.message_user(request, f'{count} post(s) moved to draft.')
set_as_draft.short_description = '📝 Move to draft'


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'status_badge', 'engagement_score', 'created_at', 'view_on_site_link', 'preview_tag')
    list_filter = (StatusFilter, AuthorFilter, 'created_at')
    search_fields = ('title', 'text', 'author__username')
    readonly_fields = ('created_at', 'views_count', 'preview_link')
    ordering = ('-created_at',)
    actions = [publish_posts, reject_posts, set_as_draft]

    # If ckeditor is available, use CKEditorWidget for the text field in admin
    if CKEditorWidget:
        formfield_overrides = {
            django_models.TextField: {'widget': CKEditorWidget},
        }

    fieldsets = (
        ('Post Information', {
            'fields': ('title', 'author', 'text', 'preview_image', 'preview_link')
        }),
        ('Publishing', {
            'fields': ('status', 'created_at')
        }),
        ('Statistics', {
            'fields': ('views_count',),
            'classes': ('collapse',),
        }),
    )

    def status_badge(self, obj):
        """Display status as a colored badge"""
        colors = {
            'published': 'green',
            'pending': 'orange',
            'rejected': 'red',
            'draft': 'gray',
        }
        color = colors.get(obj.status, 'blue')
        return format_html(
            '<span style="background-color:{};color:white;padding:3px 8px;border-radius:3px;font-weight:bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def engagement_score(self, obj):
        """Display engagement metrics"""
        likes = obj.likes.count()
        comments = obj.comments.count()
        views = obj.views_count
        score = likes * 2 + comments * 3 + views
        return format_html(
            '<span title="Likes: {}, Comments: {}, Views: {}">❤️ {} | 💬 {} | 👁️ {} | Score: <strong>{}</strong></span>',
            likes, comments, views, likes, comments, views, score
        )
    engagement_score.short_description = 'Engagement'

    def preview_tag(self, obj):
        """Display preview image thumbnail"""
        if obj.preview_image:
            return format_html('<img src="{}" style="width:80px;height:50px;object-fit:cover;border-radius:6px;"/>', obj.preview_image.url)
        return '-'
    preview_tag.short_description = 'Preview'

    def preview_link(self, obj):
        """Link to view post on site"""
        if obj.status == 'published':
            url = reverse('post_detail', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">View on site →</a>', f'/blog/{url}')
        return 'Not published'
    preview_link.short_description = 'View on Site'

    def view_on_site_link(self, obj):
        """Quick link icon to view post"""
        if obj.status == 'published':
            url = reverse('post_detail', args=[obj.pk])
            return format_html('<a href="{}" target="_blank" title="View on site">🔗</a>', f'/blog/{url}')
        return '-'
    view_on_site_link.short_description = 'Link'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('post', 'author', 'created_at', 'short_text', 'parent')
    search_fields = ('post__title', 'author__username', 'text')
    ordering = ('-created_at',)

    def short_text(self, obj):
        return (obj.text[:75] + '...') if len(obj.text) > 75 else obj.text
    short_text.short_description = 'Text'


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('post', 'user', 'created_at')
    search_fields = ('post__title', 'user__username')
    ordering = ('-created_at',)


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ('comment', 'user', 'created_at')
    search_fields = ('comment__text', 'user__username')
    ordering = ('-created_at',)


@admin.register(PostView)
class PostViewAdmin(admin.ModelAdmin):
    list_display = ('post', 'user', 'ip_address', 'created_at')
    search_fields = ('post__title', 'user__username', 'ip_address')
    ordering = ('-created_at',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'location', 'image_tag')
    list_filter = ('date',)
    search_fields = ('title', 'location', 'description')

    def image_tag(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width:100px;height:60px;object-fit:cover;border-radius:6px;"/>', obj.image.url)
        return '-'
    image_tag.short_description = 'Image'


@admin.register(BlogSubscription)
class BlogSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'author', 'subscribed_at')
    list_filter = ('subscribed_at', 'author')
    search_fields = ('user__username', 'author__username')
    readonly_fields = ('subscribed_at',)
    ordering = ('-subscribed_at',)


# Partners are handled by the `core` app; do not register a duplicate model here.