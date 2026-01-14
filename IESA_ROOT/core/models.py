from django.db import models

class President(models.Model):
    """
    Association president model (only one should exist).
    """
    name = models.CharField(max_length=255, verbose_name='Full Name')
    photo = models.ImageField(upload_to='media/members/', verbose_name='Photo')
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
    CATEGORY_CHOICES = [
        ('sponsor', 'Sponsor'),
        ('media', 'Media Partner'),
        ('tech', 'Technology Partner'),
        ('venue', 'Venue Partner'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=255, verbose_name='Partner Name')
    logo = models.ImageField(upload_to='media/partners/', verbose_name='Logo')
    link = models.URLField(blank=True, verbose_name='Website Link')
    description = models.TextField(blank=True, verbose_name='Description', help_text='Max 300 chars for better display')
    contract = models.ImageField(upload_to='media/partners/contracts/', blank=True, null=True, verbose_name='Contract Document/Photo')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', verbose_name='Partner Category')
    
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
    photo = models.ImageField(upload_to='media/members/', verbose_name='Photo')
    position = models.CharField(max_length=255, verbose_name='Position')
    description = models.TextField(verbose_name='Short Bio/Description')
    
    class Meta:
        verbose_name = 'Association Member'
        verbose_name_plural = 'Association Members'
        
    def __str__(self):
        return self.name

class SocialNetwork(models.Model):
    """
    Social network links for the footer and other places.
    """
    SOCIAL_CHOICES = [
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('linkedin', 'LinkedIn'),
        ('twitter', 'Twitter/X'),
        ('youtube', 'YouTube'),
        ('telegram', 'Telegram'),
        ('discord', 'Discord'),
        ('tiktok', 'TikTok'),
        ('whatsapp', 'WhatsApp'),
        ('github', 'GitHub'),
        ('reddit', 'Reddit'),
        ('snapchat', 'Snapchat'),
        ('pinterest', 'Pinterest'),
        ('twitch', 'Twitch'),
        ('vk', 'VK (VKontakte)'),
        ('wechat', 'WeChat'),
        ('line', 'Line'),
        ('viber', 'Viber'),
        ('other', 'Other'),
    ]
    
    # Иконки Font Awesome для каждой соц сети
    ICON_MAP = {
        'facebook': 'fab fa-facebook-f',
        'instagram': 'fab fa-instagram',
        'linkedin': 'fab fa-linkedin-in',
        'twitter': 'fab fa-x-twitter',
        'youtube': 'fab fa-youtube',
        'telegram': 'fab fa-telegram',
        'discord': 'fab fa-discord',
        'tiktok': 'fab fa-tiktok',
        'whatsapp': 'fab fa-whatsapp',
        'github': 'fab fa-github',
        'reddit': 'fab fa-reddit-alien',
        'snapchat': 'fab fa-snapchat',
        'pinterest': 'fab fa-pinterest-p',
        'twitch': 'fab fa-twitch',
        'vk': 'fab fa-vk',
        'wechat': 'fab fa-weixin',
        'line': 'fab fa-line',
        'viber': 'fab fa-viber',
        'other': 'fas fa-link',
    }
    
    name = models.CharField(max_length=50, choices=SOCIAL_CHOICES, unique=True, verbose_name='Social Network')
    url = models.URLField(verbose_name='Profile URL')
    is_active = models.BooleanField(default=True, verbose_name='Active')
    order = models.IntegerField(default=0, verbose_name='Display Order', help_text='Lower numbers appear first')
    
    class Meta:
        verbose_name = 'Social Network'
        verbose_name_plural = 'Social Networks'
        ordering = ['order', 'name']
    
    def __str__(self):
        return self.get_name_display()
    
    def get_icon(self):
        """Get Font Awesome icon class for this social network"""
        return self.ICON_MAP.get(self.name, 'fas fa-link')