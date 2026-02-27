from django.db import models
from django.utils.translation import gettext_lazy as _

class Photo(models.Model):
    """
    Gallery photo model.
    """
    image = models.ImageField(upload_to='media/gallery/photos/', verbose_name=_('Photo'))
    caption = models.CharField(max_length=255, blank=True, verbose_name=_('Caption'))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Uploaded At'))
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = _('Photo')
        verbose_name_plural = _('Photos')
        
    def __str__(self):
        return self.caption or f'Photo {self.pk}'