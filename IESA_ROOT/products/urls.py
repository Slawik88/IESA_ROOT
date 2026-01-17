from django.urls import path
from . import views

app_name = 'products'  # FIX: Enable namespace for URL reversals

urlpatterns = [
    path('', views.ProductListView.as_view(), name='product_list'),
]