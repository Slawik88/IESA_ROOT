"""
Messaging URL Configuration v3.0
"""

from django.urls import path
from . import views

app_name = 'messaging'

# API Endpoints
api_patterns = [
    path('api/chats/', views.api_chat_list, name='api_chat_list'),
    path('api/chats/create/', views.api_create_chat, name='api_create_chat'),
    path('api/chats/<int:chat_id>/messages/', views.api_chat_messages, name='api_chat_messages'),
    path('api/chats/<int:chat_id>/send/', views.api_send_message, name='api_send_message'),
    path('api/unread-count/', views.api_unread_count, name='api_unread_count'),
    path('api/users/search/', views.api_search_users, name='api_search_users'),
    path('api/messages/search/', views.api_search_messages, name='api_search_messages'),
]

# Page Views
page_patterns = [
    path('', views.chat_list_view, name='chat_list'),
    path('<int:chat_id>/', views.chat_detail_view, name='chat_detail'),
    path('start/<int:user_id>/', views.start_chat_view, name='start_chat'),
]

urlpatterns = api_patterns + page_patterns
