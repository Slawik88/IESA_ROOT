"""
Custom Django Admin Site with Enhanced Styling
"""
from django.contrib.admin import AdminSite
from django.templatetags.static import static


class CustomAdminSite(AdminSite):
    """Custom admin site with enhanced styling"""
    site_header = "IESA Administration"
    site_title = "IESA Admin"
    index_title = "Welcome to IESA Admin Panel"
    
    def get_urls(self):
        """Add custom CSS to admin"""
        return super().get_urls()
    
    class Media:
        css = {
            'all': (
                static('css/admin-enhanced.css'),
            )
        }
