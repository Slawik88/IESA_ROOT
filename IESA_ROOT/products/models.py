from django.db import models

class Product(models.Model):
    """
    Product model for catalog.
    """
    name = models.CharField(max_length=255, verbose_name='Product Name')
    description = models.TextField(verbose_name='Description')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Price')
    image = models.ImageField(upload_to='products/', verbose_name='Product Image')
    
    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        
    def __str__(self):
        return self.name