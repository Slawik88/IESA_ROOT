from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class President(models.Model):
    """
    Association president model (only one should exist).
    """
    name = models.CharField(max_length=255, verbose_name=_('Full Name'))
    photo = models.ImageField(upload_to='members/', verbose_name=_('Photo'))
    position = models.CharField(max_length=255, default='President', verbose_name=_('Position'))
    description = models.TextField(verbose_name=_('Bio/Message'))
    
    class Meta:
        verbose_name = _('President')
        verbose_name_plural = _('Presidents')
        
    def __str__(self):
        return f'{self.name} ({self.position})'
    
    def save(self, *args, **kwargs):
        # Ensure only one president exists
        if self.pk is None and President.objects.exists():
            raise ValueError(_('Only one President can exist. Delete the existing one first.'))
        super().save(*args, **kwargs)

class Partner(models.Model):
    """
    Association partner model.
    """
    CATEGORY_CHOICES = [
        ('sponsor', _('Sponsor')),
        ('media', _('Media Partner')),
        ('tech', _('Technology Partner')),
        ('venue', _('Venue Partner')),
        ('other', _('Other')),
    ]
    
    name = models.CharField(max_length=255, verbose_name=_('Partner Name'))
    logo = models.ImageField(upload_to='partners/', verbose_name=_('Logo'))
    link = models.URLField(blank=True, verbose_name=_('Website Link'))
    description = models.TextField(blank=True, verbose_name=_('Description'), help_text=_('Max 300 chars for better display'))
    contract = models.ImageField(upload_to='partners/contracts/', blank=True, null=True, verbose_name=_('Contract Document/Photo'))
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', verbose_name=_('Partner Category'))
    
    class Meta:
        verbose_name = _('Partner')
        verbose_name_plural = _('Partners')
        
    def __str__(self):
        return self.name

class AssociationMember(models.Model):
    """
    Association member model (excluding president).
    """
    name = models.CharField(max_length=255, verbose_name=_('Full Name'))
    photo = models.ImageField(upload_to='members/', verbose_name=_('Photo'))
    position = models.CharField(max_length=255, verbose_name=_('Position'))
    description = models.TextField(verbose_name=_('Short Bio/Description'))
    
    class Meta:
        verbose_name = _('Association Member')
        verbose_name_plural = _('Association Members')
        
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
    
    name = models.CharField(max_length=50, choices=SOCIAL_CHOICES, unique=True, verbose_name=_('Social Network'))
    url = models.URLField(verbose_name=_('Profile URL'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    order = models.IntegerField(default=0, verbose_name=_('Display Order'), help_text=_('Lower numbers appear first'))
    
    class Meta:
        verbose_name = _('Social Network')
        verbose_name_plural = _('Social Networks')
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
    title = models.CharField(max_length=255, verbose_name=_('Product name'))
    description = models.TextField(verbose_name=_('Product description'))
    duration = models.CharField(max_length=200, blank=True, verbose_name=_('Duration'), help_text=_('E.g.: 1-2 weeks, Friday to Sunday'))
    location = models.CharField(max_length=300, blank=True, verbose_name=_('Location'), help_text=_('E.g.: warm countries, seaside'))
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name=_('Product image'))
    icon = models.CharField(max_length=100, default='fas fa-star', verbose_name=_('Font Awesome icon'), help_text=_('E.g.: fas fa-child, fas fa-water, fas fa-ship'))
    
    # Additional features/options
    features = models.TextField(blank=True, verbose_name=_('Additional features'), help_text=_('One feature per line'))
    price_info = models.CharField(max_length=300, blank=True, verbose_name=_('Price info'))
    
    # Display settings
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    order = models.IntegerField(default=0, verbose_name=_('Display order'), help_text=_('Lower number = higher on page'))
    
    # Dates
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created at'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated at'))
    
    class Meta:
        verbose_name = _('Core IESA product')
        verbose_name_plural = _('Core IESA products')
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
        ('medical', _('Medical services')),
        ('shopping', _('Shopping & retail')),
        ('services', _('Member services')),
        ('events', _('Sports events')),
        ('advertising', _('Advertising & promotion')),
        ('education', _('Education & courses')),
        ('travel', _('Travel & tourism')),
        ('other', _('Other')),
    ]
    
    title = models.CharField(max_length=255, verbose_name=_('Benefit name'))
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', verbose_name=_('Category'))
    description = models.TextField(verbose_name=_('Benefit description'))
    discount_info = models.CharField(max_length=200, blank=True, verbose_name=_('Discount info'), help_text=_('E.g.: 20%, 15% on first level'))
    
    # Icons and colors
    icon = models.CharField(max_length=100, default='fas fa-gift', verbose_name=_('Font Awesome icon'))
    color = models.CharField(max_length=50, default='primary', verbose_name=_('Color'), help_text=_('primary, success, info, warning, danger or hex code'))
    
    # Display settings
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    order = models.IntegerField(default=0, verbose_name=_('Display order'))
    
    # Additional info
    partner_info = models.CharField(max_length=300, blank=True, verbose_name=_('Partner/service provider'))
    terms = models.TextField(blank=True, verbose_name=_('Terms'), help_text=_('How a member can receive this discount'))
    
    # Dates
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created at'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated at'))
    
    class Meta:
        verbose_name = _('Member benefit')
        verbose_name_plural = _('Member benefits')
        ordering = ['order', 'category', '-created_at']
        
    def __str__(self):
        return f'{self.title} ({self.get_category_display()})'


class AdminAppeal(models.Model):
    """
    User appeals to administration — submitted from access-denied pages
    and other places where users need admin assistance.
    """
    REASON_CHOICES = [
        ('partner_access',  _('Partner portal access request')),
        ('account_issue',   _('Account / membership issue')),
        ('verification',    _('Verification request')),
        ('other',           _('Other')),
    ]
    STATUS_CHOICES = [
        ('new',       _('New')),
        ('in_review', _('In review')),
        ('resolved',  _('Resolved')),
        ('declined',  _('Declined')),
    ]

    user            = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='admin_appeals',
        verbose_name=_('User'),
    )
    name            = models.CharField(max_length=150, verbose_name=_('Name'))
    email           = models.EmailField(verbose_name=_('E-mail'))
    reason          = models.CharField(max_length=30, choices=REASON_CHOICES, default='other', verbose_name=_('Reason'))
    message         = models.TextField(verbose_name=_('Message'))
    requested_url   = models.CharField(max_length=500, blank=True, verbose_name=_('Requested URL'))
    status          = models.CharField(max_length=12, choices=STATUS_CHOICES, default='new', verbose_name=_('Status'))
    admin_notes     = models.TextField(blank=True, verbose_name=_('Admin notes'))
    created_at      = models.DateTimeField(auto_now_add=True, verbose_name=_('Submitted at'))
    updated_at      = models.DateTimeField(auto_now=True, verbose_name=_('Updated at'))

    class Meta:
        verbose_name        = _('Admin appeal')
        verbose_name_plural = _('Admin appeals')
        ordering            = ['-created_at']

    def __str__(self):
        return f'[{self.get_status_display()}] {self.get_reason_display()} — {self.name} ({self.email})'
