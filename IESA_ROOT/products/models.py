from django.db import models
from django.utils.translation import gettext_lazy as _

class Product(models.Model):
    """
    Product model for catalog.
    """
    name = models.CharField(max_length=255, verbose_name=_('Product Name'))
    description = models.TextField(verbose_name=_('Description'))
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Price'))
    image = models.ImageField(upload_to='media/products/', verbose_name=_('Product Image'))
    
    class Meta:
        verbose_name = _('Product')
        verbose_name_plural = _('Products')
        
    def __str__(self):
        return self.name