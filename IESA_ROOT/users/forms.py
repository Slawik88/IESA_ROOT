from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.utils.translation import gettext_lazy as _
from .models import User
from .validators import (
    validate_phone_number, 
    validate_github_url, 
    validate_discord_url, 
    validate_telegram_url, 
    validate_website_url, 
    validate_other_links
)


class CustomUserCreationForm(UserCreationForm):
    """
    Форма создания нового пользователя для админки/регистрации.
    QR код и идентификатор создаются автоматически для всех пользователей.

    HOTFIX 2026-05-23: добавлено обязательное согласие — пользователь должен подтвердить,
    что соглашается стать членом ассоциации и принимает политику конфиденциальности.
    После согласия membership_status='active' и PIN-код доступен сразу.
    """
    membership_consent = forms.BooleanField(
        required=True,
        label=_("I agree to become a member of IESA Sport and accept the privacy policy"),
        error_messages={
            'required': _("You must agree to become a member to register."),
        },
    )

    class Meta(UserCreationForm.Meta):
        model = User
        # Только обязательные поля для регистрации
        fields = UserCreationForm.Meta.fields + ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)

        # HOTFIX 2026-05-23: активируем membership сразу — юзер дал согласие.
        # PIN-код (TOTP, ротация каждые 12 мин) доступен сразу.
        # Физическая карта выдаётся позже по запросу на iesa@iesasport.ch.
        user.membership_status = 'active'

        # QR-UUID и totp_secret создаются автоматически в User.save()

        if commit:
            user.save()

        return user


class CustomUserChangeForm(UserChangeForm):
    """
    Форма редактирования пользователя для админки.
    """
    date_of_birth = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y'],
        widget=forms.TextInput(attrs={
            'type': 'text',
            'placeholder': 'DD.MM.YYYY',
            'class': 'form-control date-mask',
            'pattern': '\\d{2}\\.\\d{2}\\.\\d{4}'
        }),
        label=_('Date of birth')
    )
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'date_of_birth', 'phone_number', 'is_phone_hidden', 'avatar', 'is_verified', 'is_active', 'is_staff', 'is_superuser', 'github_url', 'discord_url', 'telegram_url', 'website_url', 'other_links')

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            validate_phone_number(phone)
            # Normalize multiple spaces
            phone = ' '.join(phone.split())
        return phone


class UserProfileEditForm(forms.ModelForm):
    """
    Форма для личного кабинета (юзер может менять не все поля).
    
    Включает маску для date_of_birth для удобства ввода (DD.MM.YYYY).
    Валидация социальных ссылок с понятными сообщениями об ошибках.
    """
    # Используем DateField с custom widget для маски ввода
    date_of_birth = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y'],  # Принимаем разные форматы ввода
        widget=forms.TextInput(attrs={
            'type': 'text',
            'placeholder': 'DD.MM.YYYY',
            'class': 'form-control date-mask',
            'pattern': '\\d{2}\\.\\d{2}\\.\\d{4}'
        }),
        label=_('Date of birth')
    )
    
    github_url = forms.CharField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://github.com/username'
        }),
        label=_('GitHub profile'),
        help_text=_('Enter the full link to your GitHub profile')
    )
    
    discord_url = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'username or username#1234'
        }),
        label=_('Discord'),
        help_text=_('Enter your Discord username')
    )
    
    telegram_url = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '@username or t.me/username'
        }),
        label=_('Telegram'),
        help_text=_('Enter your Telegram username or link')
    )
    
    website_url = forms.CharField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://example.com'
        }),
        label=_('Website'),
        help_text=_('Enter the full link to your website')
    )
    
    other_links = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'https://example.com\nhttps://another-site.com'
        }),
        label=_('Other links'),
        help_text=_('Enter additional links, one per line')
    )
    
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'date_of_birth', 'phone_number', 'is_phone_hidden', 'avatar', 'github_url', 'discord_url', 'telegram_url', 'website_url', 'other_links')

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            validate_phone_number(phone)
            phone = ' '.join(phone.split())
        return phone

    def clean_github_url(self):
        url = self.cleaned_data.get('github_url')
        if url:
            validate_github_url(url)
        return url

    def clean_discord_url(self):
        url = self.cleaned_data.get('discord_url')
        if url:
            validate_discord_url(url)
        return url

    def clean_telegram_url(self):
        url = self.cleaned_data.get('telegram_url')
        if url:
            validate_telegram_url(url)
        return url

    def clean_website_url(self):
        url = self.cleaned_data.get('website_url')
        if url:
            validate_website_url(url)
        return url

    def clean_other_links(self):
        links = self.cleaned_data.get('other_links')
        if links:
            validate_other_links(links)
        return links



# MemberSearchForm и VisitForm удалены — Block 2 (DRY).
# Канонические определения в users/forms_verification.py.

# ---------------------------------------------------------------------------
# Форма заявки на смену типа аккаунта
# ---------------------------------------------------------------------------

class AccountChangeRequestForm(forms.Form):
    """Форма подачи заявки на повышение/смену типа аккаунта — расширенная версия."""

    from .models import AccountChangeRequest as _ACR

    desired_type = forms.ChoiceField(
        choices=_ACR.DESIRED_TYPE_CHOICES,
        label=_('Desired Role'),
        widget=forms.Select(attrs={'class': 'acr-select'}),
    )
    business_category = forms.ChoiceField(
        choices=[('', '— ' + str(_('choose your category')) + ' —')] + list(_ACR.BUSINESS_CATEGORY_CHOICES),
        label=_('Business Category'),
        required=False,
        widget=forms.Select(attrs={'class': 'acr-select'}),
    )
    contact_name = forms.CharField(
        label=_('Full Name'),
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'acr-input', 'placeholder': _('Your full name')}),
    )
    contact_phone = forms.CharField(
        label=_('Phone / WhatsApp'),
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'acr-input', 'placeholder': '+41 79 000 00 00'}),
    )
    contact_telegram = forms.CharField(
        label=_('Telegram'),
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'acr-input', 'placeholder': '@username'}),
    )
    contact_email = forms.EmailField(
        label=_('Contact Email'),
        required=False,
        widget=forms.EmailInput(attrs={'class': 'acr-input', 'placeholder': 'email@example.com'}),
    )
    address = forms.CharField(
        label=_('Address / Location'),
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={'class': 'acr-input', 'placeholder': _('City, street, or region')}),
    )
    reason = forms.CharField(
        label=_('Description of Activity'),
        help_text=_('Describe your activity, role and goals. Minimum 50 characters.'),
        min_length=50,
        max_length=2000,
        widget=forms.Textarea(attrs={
            'class': 'acr-textarea',
            'rows': 5,
            'placeholder': _('E.g.: I run a sports gym in Geneva and would like to offer discounts to IESA members...'),
        }),
    )

    def clean_reason(self):
        reason = self.cleaned_data.get('reason', '').strip()
        if len(reason) < 50:
            raise forms.ValidationError(
                _('Please describe your activity in at least 50 characters.')
            )
        return reason

