from django.urls import path
from django.views.generic import TemplateView
from . import views

app_name = 'core'

urlpatterns = [
    # Главная страница
    path('', views.IndexView.as_view(), name='home'),
    # HTMX partner detail for modal
    path('partner/<int:pk>/', views.partner_detail, name='partner_detail'),
    # Преимущества членов ассоциации
    path('benefits/', views.benefits_view, name='benefits'),
    # Privacy policy — placeholder until the real text is published
    path('privacy/', TemplateView.as_view(template_name='core/privacy.html'), name='privacy'),
    # Admin appeal form submission (used from access-denied pages)
    path('appeal/', views.submit_appeal, name='submit_appeal'),
    # 10d: Partner map
    path('partners/map/', views.partners_map, name='partners_map'),
    path('partners/map/data/', views.partners_map_data, name='partners_map_data'),
    # 10b: Design system playground (staff only)
    path('dev/components/', views.component_playground, name='component_playground'),
    # audit v5: Analytics dashboard (staff only)
    path('dev/analytics/', views.admin_analytics, name='admin_analytics'),
    # BLOCK 11a (audit v3): STYLEGUIDE.md из корня репо (staff only)
    path('dev/STYLEGUIDE.md', views.styleguide_md, name='styleguide_md'),
]