from django.urls import path
from . import views

urlpatterns = [
    # Список постов
    path('', views.PostListView.as_view(), name='post_list'),
    
    # События
    path('events/', views.EventListView.as_view(), name='event_list'),
    path('events/<int:pk>/', views.EventDetailView.as_view(), name='event_detail'),
    
    # Создание поста
    path('create/', views.PostCreateView.as_view(), name='post_create'),
    
    # Детальная страница поста
    path('<int:pk>/', views.PostDetailView.as_view(), name='post_detail'),
    
    # HTMX-эндпоинты
    path('<int:pk>/like/', views.like_post, name='like_post'),
    path('<int:pk>/comment/', views.comment_create, name='comment_create'),
    path('<int:pk>/comments/', views.comment_list, name='comment_list'),
    path('<int:pk>/comment/<int:comment_pk>/delete/', views.delete_comment, name='delete_comment'),
    path('<int:pk>/comment/<int:comment_pk>/like/', views.toggle_comment_like, name='toggle_comment_like'),
    path('author/<int:author_pk>/subscribe/', views.toggle_subscription, name='toggle_subscription'),
    path('search/', views.post_search, name='post_search'),
    path('search/global/', views.global_search, name='global_search'),
    # Partners are shown on the homepage (core app); no standalone partners page here.
]