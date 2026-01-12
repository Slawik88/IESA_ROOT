from django.contrib.sitemaps import Sitemap
from blog.models import Post, Event
from users.models import User
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
        return ['home', 'post_list', 'event_list', 'product_list', 'gallery']
    
    def location(self, item):
        return reverse(item)


# Sitemap registry
sitemaps = {
    'posts': PostSitemap,
    'events': EventSitemap,
    'static': StaticViewSitemap,
}
