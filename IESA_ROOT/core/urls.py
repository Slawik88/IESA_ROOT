from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Главная страница
    path('', views.IndexView.as_view(), name='home'),
    # HTMX partner detail for modal
    path('partner/<int:pk>/', views.partner_detail, name='partner_detail'),
    # Преимущества членов ассоциации
    path('benefits/', views.benefits_view, name='benefits'),
    # Admin appeal form submission (used from access-denied pages)
    path('appeal/', views.submit_appeal, name='submit_appeal'),
    # 10d: Partner map
    path('partners/map/', views.partners_map, name='partners_map'),
    path('partners/map/data/', views.partners_map_data, name='partners_map_data'),
    # 10b: Design system playground (staff only)
    path('dev/components/', views.component_playground, name='component_playground'),
]