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
    email = forms.EmailField(
        required=True,
        label=_('Email address'),
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        # Только обязательные поля для регистрации
        fields = UserCreationForm.Meta.fields + ('email',)

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('An account with this e-mail address already exists.'))
        return email

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
        widget=forms.DateInput(format='%d.%m.%Y', attrs={
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

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if not email:
            raise forms.ValidationError(_('E-mail address is required.'))
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_('An account with this e-mail address already exists.'))
        self._email_changed = email.casefold() != (self.instance.email or '').strip().casefold()
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        if getattr(self, '_email_changed', False):
            user.email_verified_at = None
            user.email_verification_sent_at = None
        if commit:
            user.save()
            self.save_m2m()
        return user


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
        widget=forms.DateInput(format='%d.%m.%Y', attrs={
            'type': 'text',
            'placeholder': 'DD.MM.YYYY',
            'class': 'form-control date-mask',
            'pattern': '\\d{2}\\.\\d{2}\\.\\d{4}'
        }),
        label=_('Date of birth')
    )

    email = forms.EmailField(
        required=True,
        label=_('Email address'),
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'autocomplete': 'email',
        }),
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

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_('An account with this e-mail address already exists.'))
        self._email_changed = email.casefold() != (self.instance.email or '').strip().casefold()
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        if getattr(self, '_email_changed', False):
            user.email_verified_at = None
            user.email_verification_sent_at = None
        if commit:
            user.save()
            self.save_m2m()
        return user

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
    # BLOCK 7 (audit v4): first_name + last_name отдельно (раньше — contact_name одним полем)
    first_name = forms.CharField(
        label=_('First Name'),
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'class': 'acr-input', 'placeholder': _('e.g. John')}),
    )
    last_name = forms.CharField(
        label=_('Last Name'),
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'class': 'acr-input', 'placeholder': _('e.g. Doe')}),
    )
    # contact_name — legacy fallback (заполняется автоматически из first+last)
    contact_name = forms.CharField(required=False, widget=forms.HiddenInput())
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
        required=True,
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
        help_text=_('Describe your activity, role and goals.'),
        max_length=2000,
        widget=forms.Textarea(attrs={
            'class': 'acr-textarea',
            'rows': 5,
            'placeholder': _('E.g.: I run a sports gym in Geneva and would like to offer discounts to IESA members...'),
        }),
    )

    def clean(self):
        """BLOCK 6 (audit v4): динамическая валидация в зависимости от desired_type.

        - partner: business_category, address — required
        - association_staff / president: business_category, address, contact_telegram — НЕ обязательны
          (это частные лица без бизнеса)
        """
        cleaned = super().clean()
        desired = cleaned.get('desired_type', '')

        if desired == 'partner':
            if not cleaned.get('business_category'):
                self.add_error('business_category', _('Please choose your business category.'))
            if not (cleaned.get('address') or '').strip():
                self.add_error('address', _('Please specify your address or location.'))

        # contact_name автозаполняется из first_name + last_name (backward compat)
        fn = (cleaned.get('first_name') or '').strip()
        ln = (cleaned.get('last_name') or '').strip()
        if fn or ln:
            cleaned['contact_name'] = f'{fn} {ln}'.strip()

        return cleaned

    def clean_reason(self):
        # BLOCK 1 (audit v4): убрана min length=50 — теперь без ограничения
        return (self.cleaned_data.get('reason') or '').strip()
