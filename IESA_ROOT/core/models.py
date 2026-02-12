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
    CATEGORY_CHOICES = [
        ('sponsor', 'Sponsor'),
        ('media', 'Media Partner'),
        ('tech', 'Technology Partner'),
        ('venue', 'Venue Partner'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=255, verbose_name='Partner Name')
    logo = models.ImageField(upload_to='partners/', verbose_name='Logo')
    link = models.URLField(blank=True, verbose_name='Website Link')
    description = models.TextField(blank=True, verbose_name='Description', help_text='Max 300 chars for better display')
    contract = models.ImageField(upload_to='partners/contracts/', blank=True, null=True, verbose_name='Contract Document/Photo')
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
    photo = models.ImageField(upload_to='members/', verbose_name='Photo')
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


class CoreProduct(models.Model):
    """
    Core IESA products/programs that appear above events on homepage.
    Examples: Kids extreme scout camp, Weekend water sports, Yachting with diving, etc.
    """
    title = models.CharField(max_length=255, verbose_name='Название продукта')
    description = models.TextField(verbose_name='Описание продукта')
    duration = models.CharField(max_length=200, blank=True, verbose_name='Длительность', help_text='Например: 1-2 недели, с пятницы по воскресенье')
    location = models.CharField(max_length=300, blank=True, verbose_name='Место проведения', help_text='Например: тёплые страны, берег моря')
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name='Изображение продукта')
    icon = models.CharField(max_length=100, default='fas fa-star', verbose_name='Font Awesome иконка', help_text='Например: fas fa-child, fas fa-water, fas fa-ship')
    
    # Additional features/options
    features = models.TextField(blank=True, verbose_name='Дополнительные особенности', help_text='Каждая особенность с новой строки')
    price_info = models.CharField(max_length=300, blank=True, verbose_name='Информация о цене')
    
    # Display settings
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    order = models.IntegerField(default=0, verbose_name='Порядок отображения', help_text='Меньшее число = выше на странице')
    
    # Dates
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    
    class Meta:
        verbose_name = 'Основной продукт IESA'
        verbose_name_plural = 'Основные продукты IESA'
        ordering = ['order', '-created_at']
        
    def __str__(self):
        return self.title
    
    def get_features_list(self):
        """Return features as a list"""
        if self.features:
            return [f.strip() for f in self.features.split('\n') if f.strip()]
        return []


class MemberBenefit(models.Model):
    """
    Benefits/perks for association members.
    Examples: Medical insurance discount, Store discounts, Service discounts, etc.
    """
    CATEGORY_CHOICES = [
        ('medical', 'Медицинское обслуживание'),
        ('shopping', 'Покупки и магазины'),
        ('services', 'Услуги членов ассоциации'),
        ('events', 'Спортивные мероприятия'),
        ('advertising', 'Реклама и продвижение'),
        ('education', 'Обучение и курсы'),
        ('travel', 'Путешествия и туризм'),
        ('other', 'Другое'),
    ]
    
    title = models.CharField(max_length=255, verbose_name='Название преимущества')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', verbose_name='Категория')
    description = models.TextField(verbose_name='Описание преимущества')
    discount_info = models.CharField(max_length=200, blank=True, verbose_name='Информация о скидке', help_text='Например: 20%, 15% на первый уровень')
    
    # Icons and colors
    icon = models.CharField(max_length=100, default='fas fa-gift', verbose_name='Font Awesome иконка')
    color = models.CharField(max_length=50, default='primary', verbose_name='Цвет', help_text='primary, success, info, warning, danger или hex код')
    
    # Display settings
    is_active = models.BooleanField(default=True, verbose_name='Активно')
    order = models.IntegerField(default=0, verbose_name='Порядок отображения')
    
    # Additional info
    partner_info = models.CharField(max_length=300, blank=True, verbose_name='Партнёр/поставщик услуги')
    terms = models.TextField(blank=True, verbose_name='Условия получения', help_text='Как член ассоциации может получить эту скидку')
    
    # Dates
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    
    class Meta:
        verbose_name = 'Преимущество члена ассоциации'
        verbose_name_plural = 'Преимущества членов ассоциации'
        ordering = ['order', 'category', '-created_at']
        
    def __str__(self):
        return f'{self.title} ({self.get_category_display()})'
