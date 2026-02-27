from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notification_type', 'title', 'is_read', 'created_at', 'sender')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('recipient__username', 'title', 'message', 'sender__username')
    readonly_fields = ('created_at', 'read_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    
    fieldsets = (
        (_('Notification Info'), {
            'fields': ('recipient', 'sender', 'notification_type', 'title', 'message', 'link')
        }),
        (_('Status'), {
            'fields': ('is_read', 'created_at', 'read_at')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('recipient', 'sender')
