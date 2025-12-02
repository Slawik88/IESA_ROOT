from django.db import models

class Photo(models.Model):
    """
    Модель для фотографий в галерее.
    """
    image = models.ImageField(upload_to='gallery/photos/', verbose_name='Фотография')
    caption = models.CharField(max_length=255, blank=True, verbose_name='Описание')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата загрузки')
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Фотография'
        verbose_name_plural = 'Фотографии'
        
    def __str__(self):
        return self.caption or f'Photo {self.pk}'