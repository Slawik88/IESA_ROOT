from django.contrib.sitemaps import Sitemap
from blog.models import Post, Event
from django.urls import reverse


class PostSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.9
    
    def items(self):
        return Post.objects.filter(status='published').order_by('-created_at')
    
    def lastmod(self, obj):
        return obj.updated_at if hasattr(obj, 'updated_at') and obj.updated_at else obj.created_at


class EventSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8
    
    def items(self):
        from django.utils import timezone
        return Event.objects.filter(date__gte=timezone.now()).order_by('date')
    
    def lastmod(self, obj):
        return obj.created_at if hasattr(obj, 'created_at') else None


class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = "monthly"
    
    def items(self):
        # FIX 2026-05-28: 'home' → 'core:home' (правильное URL name из core/urls.py).
        # Раньше при каждом hit sitemap.xml логировался warning.
        return ['core:home', 'blog:post_list', 'blog:event_list', 'products:product_list', 'gallery:gallery']
    
    def location(self, item):
        try:
            return reverse(item)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Sitemap: could not reverse URL name %r — skipping", item)
            return '/'


# Sitemap registry
sitemaps = {
    'posts': PostSitemap,
    'events': EventSitemap,
    'static': StaticViewSitemap,
}
