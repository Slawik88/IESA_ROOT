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
from .miniapp_views import (
    miniapp_index, miniapp_user_data,
    miniapp_leaderboard, miniapp_checkin, miniapp_boss_damage,
    miniapp_marriage, miniapp_marriage_propose, miniapp_bonds, miniapp_equip,
    miniapp_dev_stats, miniapp_dev_setbalance,
)

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

    # ─── Telegram Mini App ─────────────────────────────────────────────────────
    path('app', miniapp_index, name='miniapp'),
    path('app/', miniapp_index, name='miniapp_slash'),
    path('api/user_data', miniapp_user_data, name='miniapp_api'),
    path('api/user_data/', miniapp_user_data, name='miniapp_api_slash'),
    path('api/leaderboard', miniapp_leaderboard, name='miniapp_leaderboard'),
    path('api/checkin', miniapp_checkin, name='miniapp_checkin'),
    path('api/boss/submit_damage', miniapp_boss_damage, name='miniapp_boss_damage'),
    path('api/marriage', miniapp_marriage, name='miniapp_marriage'),
    path('api/marriage/propose', miniapp_marriage_propose, name='miniapp_marriage_propose'),
    path('api/bonds', miniapp_bonds, name='miniapp_bonds'),
    path('api/equip', miniapp_equip, name='miniapp_equip'),
    path('api/dev/stats', miniapp_dev_stats, name='miniapp_dev_stats'),
    path('api/dev/setbalance', miniapp_dev_setbalance, name='miniapp_dev_setbalance'),
    # ───────────────────────────────────────────────────────────────────────────
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
    
    
    # Sitemap
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),

    # robots.txt — served as plain text from template
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name='robots_txt'),

    # /.well-known/traffic-advice — Chrome prerender hint (prevents 404 noise in logs)
    path('.well-known/traffic-advice', lambda r: JsonResponse([{"user_agent": "prefetch-proxy", "google-extended": "disallow"}], safe=False, content_type='application/trafficadvice+json')),

    # /shop → redirect to /products/
    path('shop', RedirectView.as_view(url='/products/', permanent=True)),
    path('shop/', RedirectView.as_view(url='/products/', permanent=True)),

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