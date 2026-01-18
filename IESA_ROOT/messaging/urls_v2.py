"""
Messaging URL Configuration - v2.0
Clean API endpoints with proper authentication and error handling
"""

from django.urls import path
from . import views_v2 as views

app_name = 'messaging'

# ============================================================================
# API ENDPOINTS - CONVERSATIONS
# ============================================================================
api_patterns = [
    path('api/conversations/', views.api_get_conversations, name='api_conversations'),
    path('api/conversations/<int:conversation_id>/messages/', views.api_get_messages, name='api_messages'),
    path('api/users/search/', views.api_search_users, name='api_search_users'),
]

# ============================================================================
# API ENDPOINTS - MESSAGE OPERATIONS
# ============================================================================
message_patterns = [
    path('api/conversations/<int:conversation_id>/send/', views.api_send_message, name='api_send_message'),
    path('api/messages/<int:message_id>/edit/', views.api_edit_message, name='api_edit_message'),
    path('api/messages/<int:message_id>/delete/', views.api_delete_message, name='api_delete_message'),
    path('api/messages/<int:message_id>/read/', views.api_mark_read, name='api_mark_read'),
]

# ============================================================================
# API ENDPOINTS - CREATE CONVERSATIONS
# ============================================================================
create_patterns = [
    path('api/conversations/create/one-to-one/', views.api_create_conversation, name='api_create_conversation'),
    path('api/conversations/create/group/', views.api_create_group, name='api_create_group'),
]

# ============================================================================
# UI VIEWS
# ============================================================================
ui_patterns = [
    path('', views.inbox_view, name='inbox'),
    path('<int:pk>/', views.conversation_detail_view, name='conversation_detail'),
]

urlpatterns = api_patterns + message_patterns + create_patterns + ui_patterns
