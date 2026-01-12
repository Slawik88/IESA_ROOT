from django.db import models

class Photo(models.Model):
    """
    Gallery photo model.
    """
    image = models.ImageField(upload_to='media/gallery/photos/', verbose_name='Photo')
    caption = models.CharField(max_length=255, blank=True, verbose_name='Caption')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Uploaded At')
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Photo'
        verbose_name_plural = 'Photos'
        
    def __str__(self):
        return self.caption or f'Photo {self.pk}'