from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic.base import RedirectView
from django.templatetags.static import static as static_static
from django.views.generic import TemplateView
from django.http import FileResponse
from django.views.decorators.http import condition
from pathlib import Path
from blog.sitemaps import sitemaps
from .protected_media_views import serve_protected_media

def serve_manifest(request):
    """Serve PWA manifest.json"""
    manifest_path = Path(settings.STATIC_ROOT) / 'manifest.json'
    if manifest_path.exists():
        return FileResponse(
            open(manifest_path, 'rb'),
            content_type='application/manifest+json',
            status=200
        )
    return FileResponse(open(Path(settings.BASE_DIR) / 'static' / 'manifest.json', 'rb'), 
                       content_type='application/manifest+json', 
                       status=200)

def serve_service_worker(request):
    """Serve service worker script"""
    sw_path = Path(settings.STATIC_ROOT) / 'service-worker.js'
    if sw_path.exists():
        return FileResponse(
            open(sw_path, 'rb'),
            content_type='application/javascript',
            status=200
        )
    return FileResponse(open(Path(settings.BASE_DIR) / 'static' / 'service-worker.js', 'rb'), 
                       content_type='application/javascript', 
                       status=200)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Protected media files (requires authentication)
    path('protected/<path:file_path>', serve_protected_media, name='serve_protected_media'),
    
    # PWA manifest and service worker
    path('static/manifest.json', serve_manifest, name='pwa-manifest'),
    path('static/service-worker.js', serve_service_worker, name='service-worker'),
    
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
    
    # Messaging app v3
    path('messages/', include('messaging.urls')),
    
    # Sitemap
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    
    # CKEditor 5 upload path
    path('ckeditor5/', include('django_ckeditor_5.urls')),
    # Favicon shortcut to static asset
    path('favicon.ico', RedirectView.as_view(url=static_static('img/favicon.png'), permanent=True)),
]

# Добавляем маршруты для медиа-файлов и static файлов
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    # In production, serve media files through Django
    # TODO: Move to DigitalOcean Spaces for production
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Also serve static files in production (WhiteNoise should handle this, but as fallback)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)