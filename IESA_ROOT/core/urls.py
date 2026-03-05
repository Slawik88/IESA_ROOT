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
]