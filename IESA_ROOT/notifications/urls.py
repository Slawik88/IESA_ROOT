from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notification_list, name='notification_list'),
    path('panel/', views.notification_panel, name='notification_panel'),
    path('<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('<int:pk>/delete/', views.notification_delete, name='notification_delete'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
]
