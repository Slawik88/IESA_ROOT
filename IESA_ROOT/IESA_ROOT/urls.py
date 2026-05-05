from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic.base import RedirectView, TemplateView
from django.templatetags.static import static as static_static
from django.http import FileResponse, JsonResponse
from pathlib import Path
from blog.sitemaps import sitemaps
from .protected_media_views import serve_protected_media
from core.admin_site import CustomAdminSite

# Переопределить стандартный админ на кастомный
admin.site.__class__ = CustomAdminSite


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
    path('i18n/', include('django.conf.urls.i18n')),

    # Защищённые медиа-файлы (контракты партнёров и т.п.)
    path('protected/<path:file_path>', serve_protected_media, name='serve_protected_media'),

    # Core app (Главная страница)
    path('', include('core.urls')),

    # Users app (Авторизация, Профиль, Телеграм-бот)
    path('auth/', include('users.urls')),

    # Blog app (Социальная сеть, События)
    path('blog/', include('blog.urls')),

    # Gallery app
    path('gallery/', include('gallery.urls')),

    # Products app
    path('products/', include('products.urls')),

    # Notifications app
    path('notifications/', include('notifications.urls')),

    # Sitemap
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),

    # robots.txt
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name='robots_txt'),

    # /.well-known/traffic-advice
    path('.well-known/traffic-advice', lambda r: JsonResponse(
        [{"user_agent": "prefetch-proxy", "google-extended": "disallow"}],
        safe=False, content_type='application/trafficadvice+json'
    )),

    # /shop → /products/
    path('shop', RedirectView.as_view(url='/products/', permanent=True)),
    path('shop/', RedirectView.as_view(url='/products/', permanent=True)),

    # CKEditor 5
    path('ckeditor5/', include('django_ckeditor_5.urls')),

    # Favicon
    path('favicon.ico', RedirectView.as_view(url=static_static('img/favicon.png'), permanent=True)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
