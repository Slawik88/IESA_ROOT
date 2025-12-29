from django.db import models

class President(models.Model):
    """
    Association president model (only one should exist).
    """
    name = models.CharField(max_length=255, verbose_name='Full Name')
    photo = models.ImageField(upload_to='members/', verbose_name='Photo')
    position = models.CharField(max_length=255, default='President', verbose_name='Position')
    description = models.TextField(verbose_name='Bio/Message')
    
    class Meta:
        verbose_name = 'President'
        verbose_name_plural = 'Presidents'
        
    def __str__(self):
        return f'{self.name} ({self.position})'
    
    def save(self, *args, **kwargs):
        # Ensure only one president exists
        if self.pk is None and President.objects.exists():
            raise ValueError('Only one President can exist. Delete the existing one first.')
        super().save(*args, **kwargs)

class Partner(models.Model):
    """
    Association partner model.
    """
    name = models.CharField(max_length=255, verbose_name='Partner Name')
    logo = models.ImageField(upload_to='partners/', verbose_name='Logo')
    link = models.URLField(blank=True, verbose_name='Website Link')
    description = models.TextField(blank=True, verbose_name='Description', help_text='Max 300 chars for better display')
    contract = models.ImageField(upload_to='partners/contracts/', blank=True, null=True, verbose_name='Contract Document/Photo')
    
    class Meta:
        verbose_name = 'Partner'
        verbose_name_plural = 'Partners'
        
    def __str__(self):
        return self.name

class AssociationMember(models.Model):
    """
    Association member model (excluding president).
    """
    name = models.CharField(max_length=255, verbose_name='Full Name')
    photo = models.ImageField(upload_to='members/', verbose_name='Photo')
    position = models.CharField(max_length=255, verbose_name='Position')
    description = models.TextField(verbose_name='Short Bio/Description')
    
    class Meta:
        verbose_name = 'Association Member'
        verbose_name_plural = 'Association Members'
        
    def __str__(self):
        return self.name