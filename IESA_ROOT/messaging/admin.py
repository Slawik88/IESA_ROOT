from django.contrib import admin
from .models import Conversation, Message, TypingIndicator


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'is_group', 'group_name', 'created_at', 'updated_at', 'participant_count']
    list_filter = ['is_group', 'created_at']
    search_fields = ['group_name', 'participants__username']
    filter_horizontal = ['participants']
    readonly_fields = ['created_at', 'updated_at']
    
    def participant_count(self, obj):
        return obj.participants.count()
    participant_count.short_description = 'Participants'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'sender', 'conversation', 'text_preview', 'created_at', 'is_pinned', 'is_deleted']
    list_filter = ['is_pinned', 'is_deleted', 'deleted_for_everyone', 'created_at']
    search_fields = ['text', 'sender__username']
    readonly_fields = ['created_at', 'edited_at']
    raw_id_fields = ['conversation', 'sender', 'reply_to']
    filter_horizontal = ['read_by']
    
    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Message'


@admin.register(TypingIndicator)
class TypingIndicatorAdmin(admin.ModelAdmin):
    list_display = ['user', 'conversation', 'timestamp']
    list_filter = ['timestamp']
    readonly_fields = ['timestamp']
