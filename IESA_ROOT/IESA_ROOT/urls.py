from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic.base import RedirectView
from django.templatetags.static import static as static_static
from blog.sitemaps import sitemaps
from .protected_media_views import serve_protected_media

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Protected media files (requires authentication)
    path('protected/<path:file_path>', serve_protected_media, name='serve_protected_media'),
    
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
    
        # Messaging app
        path('messages/', include('messaging.urls')),
    
    # Sitemap
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    
    # CKEditor 5 upload path
    path('ckeditor5/', include('django_ckeditor_5.urls')),
    # Favicon shortcut to static asset
    path('favicon.ico', RedirectView.as_view(url=static_static('img/favicon.png'), permanent=True)),
]

# Добавляем маршруты для медиа-файлов в режиме разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # In production with SQLite (temporary), serve media files through Django
    # TODO: Move to DigitalOcean Spaces for production
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)