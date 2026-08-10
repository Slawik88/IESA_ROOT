from django.views.generic import ListView
from .models import Product

class ProductListView(ListView):
    """
    Отображение списка продуктов.
    """
    model = Product
    template_name = 'products/product_list.html'
    context_object_name = 'products'
    paginate_by = 12

    def get_queryset(self):
        """Keep pagination stable as new products are added."""
        return super().get_queryset().order_by('-pk')
