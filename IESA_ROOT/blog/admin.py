from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext
from django.urls import reverse
from .models import Post, Comment, Like, Event, PostView, CommentLike, BlogSubscription, EventRegistration
from django.db import models as django_models
from modeltranslation.admin import TabbedTranslationAdmin
from . import translation  # noqa: F401
try:
    from django_ckeditor_5.widgets import CKEditor5Widget
    CKEditorWidget = CKEditor5Widget
except Exception:
    CKEditorWidget = None


# Custom admin filters
class StatusFilter(admin.SimpleListFilter):
    title = _('publication status')
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return [
            ('published', _('Published')),
            ('pending', _('Pending Review')),
            ('rejected', _('Rejected')),
            ('draft', _('Draft')),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class AuthorFilter(admin.SimpleListFilter):
    title = _('author')
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
    modeladmin.message_user(request, gettext('%(count)d post(s) published successfully.') % {'count': count})
publish_posts.short_description = _('✅ Publish selected posts')


def reject_posts(modeladmin, request, queryset):
    """Reject selected posts"""
    count = queryset.update(status='rejected')
    modeladmin.message_user(request, gettext('%(count)d post(s) rejected.') % {'count': count})
reject_posts.short_description = _('❌ Reject selected posts')


def set_as_draft(modeladmin, request, queryset):
    """Move posts to draft"""
    count = queryset.update(status='draft')
    modeladmin.message_user(request, gettext('%(count)d post(s) moved to draft.') % {'count': count})
set_as_draft.short_description = _('📝 Move to draft')


@admin.register(Post)
class PostAdmin(TabbedTranslationAdmin):
    list_display = ('id', 'title', 'author_with_link', 'status_badge', 'created_at', 'engagement_score', 'preview_tag', 'view_on_site_link')
    list_filter = (StatusFilter, AuthorFilter, 'created_at')
    search_fields = ('id', 'title', 'text', 'author__username', 'author__email', 'author__first_name', 'author__last_name')
    readonly_fields = ('created_at', 'views_count', 'preview_link', 'engagement_details')
    ordering = ('-created_at',)
    actions = [publish_posts, reject_posts, set_as_draft]
    list_per_page = 25
    date_hierarchy = 'created_at'

    # If ckeditor is available, use CKEditorWidget for the text field in admin
    if CKEditorWidget:
        formfield_overrides = {
            django_models.TextField: {'widget': CKEditorWidget},
        }

    fieldsets = (
        (_('Post Information'), {
            'fields': ('title', 'author', 'text', 'preview_image', 'preview_link')
        }),
        (_('Publishing'), {
            'fields': ('status', 'created_at')
        }),
        (_('Statistics'), {
            'fields': ('views_count', 'engagement_details'),
            'classes': ('collapse',),
        }),
    )

    def author_with_link(self, obj):
        """Display author name with link to user profile"""
        url = reverse('admin:users_user_change', args=[obj.author.id])
        return format_html(
            '<a href="{}" title="{}">👤 {}</a>',
            url,
            obj.author.email,
            obj.author.username
        )
    author_with_link.short_description = 'Author'
    author_with_link.admin_order_field = 'author__username'

    def engagement_details(self, obj):
        """Detailed engagement statistics"""
        likes = obj.likes.count()
        comments = obj.comments.count()
        views = obj.views_count
        score = likes * 2 + comments * 3 + views
        return format_html(
            '<div style="padding:10px;background:#f8f9fa;border-radius:8px;">'
            '<p><strong>Engagement Score:</strong> {}</p>'
            '<p>❤️ Likes: {} (2 points each)</p>'
            '<p>💬 Comments: {} (3 points each)</p>'
            '<p>👁️ Views: {} (1 point each)</p>'
            '</div>',
            score, likes, comments, views
        )
    engagement_details.short_description = 'Engagement Details'

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
            url = reverse('blog:post_detail', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">View on site →</a>', f'/blog/{url}')
        return _('Not published')
    preview_link.short_description = _('View on Site')

    def view_on_site_link(self, obj):
        """Quick link icon to view post"""
        if obj.status == 'published':
            url = reverse('blog:post_detail', args=[obj.pk])
            return format_html('<a href="{}" target="_blank" title="View on site">🔗</a>', f'/blog/{url}')
        return '-'
    view_on_site_link.short_description = 'Link'

    class Media:
        css = {
            'all': ('css/admin-ckeditor-theme.css',)
        }


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
class EventAdmin(TabbedTranslationAdmin):
    list_display = ('title', 'date', 'location', 'status', 'participants_count', 'image_tag')
    list_filter = ('status', 'date', 'created_at')
    search_fields = ('title', 'location', 'description')
    readonly_fields = ('created_at', 'updated_at', 'participants_count')
    
    # CKEditor для description
    if CKEditorWidget:
        formfield_overrides = {
            django_models.TextField: {'widget': CKEditorWidget},
        }
    
    fieldsets = (
        (_('Event Information'), {
            'fields': ('title', 'description', 'image')
        }),
        (_('Date & Time'), {
            'fields': ('date', 'end_date', 'registration_deadline')
        }),
        (_('Location & Capacity'), {
            'fields': ('location', 'min_age', 'max_age', 'max_participants', 'status')
        }),
        (_('System'), {
            'fields': ('created_by', 'created_at', 'updated_at', 'participants_count'),
            'classes': ('collapse',)
        }),
    )

    def image_tag(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width:100px;height:60px;object-fit:cover;border-radius:6px;"/>', obj.image.url)
        return '-'
    image_tag.short_description = 'Image'
    
    def participants_count(self, obj):
        confirmed = obj.registrations.filter(status='confirmed').count()
        if obj.max_participants:
            return format_html(
                '<span style="font-weight:bold;">{}/{}</span>',
                confirmed, obj.max_participants
            )
        return confirmed
    participants_count.short_description = 'Participants'


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'status', 'registered_at')
    list_filter = ('status', 'registered_at', 'event')
    search_fields = ('user__username', 'event__title')
    readonly_fields = ('registered_at',)
    ordering = ('-registered_at',)

    class Media:
        css = {
            'all': ('css/admin-ckeditor-theme.css',)
        }


@admin.register(BlogSubscription)
class BlogSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'author', 'subscribed_at')
    list_filter = ('subscribed_at', 'author')
    search_fields = ('user__username', 'author__username')
    readonly_fields = ('subscribed_at',)
    ordering = ('-subscribed_at',)


# Partners are handled by the `core` app; do not register a duplicate model here.