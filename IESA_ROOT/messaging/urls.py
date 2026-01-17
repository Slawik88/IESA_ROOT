from django.urls import path
from . import views

app_name = 'messaging'

urlpatterns = [
    # Conversation list
    path('', views.ConversationListView.as_view(), name='conversation_list'),
    # Search users to start chat
    path('search-users/', views.search_users, name='search_users'),
    
    # Start new conversation
    path('new/<str:username>/', views.start_conversation, name='start_conversation'),
    
    # View conversation
    path('<int:pk>/', views.ConversationDetailView.as_view(), name='conversation_detail'),
    # Create group conversation
    path('groups/new/', views.create_group_conversation, name='create_group'),
    
    # Send message
    path('<int:pk>/send/', views.send_message, name='send_message'),
    # Get new messages (HTMX polling)
    path('<int:pk>/new/', views.new_messages, name='new_messages'),
    
    # Message actions
    path('message/<int:pk>/delete/', views.delete_message, name='delete_message'),
    path('message/<int:pk>/pin/', views.pin_message, name='pin_message'),
    path('message/<int:pk>/edit/', views.edit_message, name='edit_message'),
    path('message/<int:pk>/read/', views.mark_message_read, name='mark_message_read'),
    
    # Typing indicator
    path('<int:pk>/typing/', views.typing_indicator, name='typing_indicator'),
    path('<int:pk>/typing/status/', views.typing_status, name='typing_status'),
    # Get older messages (scroll up)
    path('<int:pk>/old/', views.old_messages, name='old_messages'),
    # Count of older messages
    path('<int:pk>/old/count/', views.old_remaining, name='old_remaining'),
    # Group participants management
    path('groups/<int:pk>/participants/add/', views.add_participant, name='add_participant'),
    path('groups/<int:pk>/participants/remove/<int:user_id>/', views.remove_participant, name='remove_participant'),
    path('groups/<int:pk>/leave/', views.leave_group, name='leave_group'),
    path('groups/<int:pk>/participants/panel/', views.participants_panel, name='participants_panel'),
    path('groups/<int:pk>/admins/toggle/<int:user_id>/', views.toggle_admin, name='toggle_admin'),
]
