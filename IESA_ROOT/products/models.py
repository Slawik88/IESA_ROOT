from django.db import models

class Product(models.Model):
    """
    Модель продукта для каталога.
    """
    name = models.CharField(max_length=255, verbose_name='Название продукта')
    description = models.TextField(verbose_name='Описание')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена')
    image = models.ImageField(upload_to='products/', verbose_name='Изображение продукта')
    
    class Meta:
        verbose_name = 'Продукт'
        verbose_name_plural = 'Продукты'
        
    def __str__(self):
        return self.name