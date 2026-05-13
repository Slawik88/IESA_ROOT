from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notification_list, name='notification_list'),
    path('panel/', views.notification_panel, name='notification_panel'),
    path('unread-count/', views.unread_count, name='unread_count'),
    path('<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('<int:pk>/delete/', views.notification_delete, name='notification_delete'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    # 10e: Server-Sent Events endpoint
    path('stream/', views.notification_stream, name='notification_stream'),
]
