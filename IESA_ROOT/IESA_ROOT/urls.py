from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Core app (Главная страница)
    path('', include('core.urls')),
    
    # Users app (Авторизация, Профиль)
    path('auth/', include('users.urls')),
    
    # Blog app (Социальная сеть, События)
    path('blog/', include('blog.urls')),
    
    # Gallery app
    path('gallery/', include('gallery.urls')),
    
    # Products app
    path('products/', include('products.urls')),
    
    # Notifications app
    path('notifications/', include('notifications.urls')),
    
    # CKEditor 5 upload path
    path('ckeditor5/', include('django_ckeditor_5.urls')),
]

# Добавляем маршруты для медиа-файлов в режиме разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)