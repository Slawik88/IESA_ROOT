from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User
from .validators import validate_phone_number
from django.utils import timezone
import uuid


class CustomUserCreationForm(UserCreationForm):
    """
    Форма создания нового пользователя для админки/регистрации.
    QR код и идентификатор создаются автоматически для всех пользователей.
    """
    
    class Meta(UserCreationForm.Meta):
        model = User
        # Только обязательные поля для регистрации
        fields = UserCreationForm.Meta.fields + ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # QR код и идентификатор создаются автоматически через сигналы
        # Ничего дополнительно делать не нужно
        
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
        label='Дата рождения'
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
        label='Дата рождения'
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


"""
Forms for Membership Verification System
"""
from django import forms
from .models import Visit


class MemberSearchForm(forms.Form):
    """Search form for finding members in partner dashboard"""
    query = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Search by name, pseudonym, or UUID...',
            'autocomplete': 'off',
        }),
        label=''
    )


class VisitForm(forms.ModelForm):
    """Form for logging a member visit"""
    pin = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg text-center font-monospace',
            'placeholder': '000000',
            'pattern': '[0-9]{6}',
            'inputmode': 'numeric',
            'maxlength': '6',
            'autocomplete': 'off',
        }),
        label='Member PIN (6 digits)',
        help_text='Ask member to show their current PIN from personal cabinet'
    )
    
    class Meta:
        model = Visit
        fields = ['service_type', 'service_description', 'cost', 'comments', 'pin']
        widgets = {
            'service_type': forms.Select(attrs={'class': 'form-select'}),
            'service_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional: Describe the service provided...'
            }),
            'cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Optional: Additional comments...'
            }),
        }
        labels = {
            'service_type': 'Service Type',
            'service_description': 'Service Description (Optional)',
            'cost': 'Cost (Optional)',
            'comments': 'Comments (Optional)',
        }
    
    def clean_pin(self):
        """Validate PIN format"""
        pin = self.cleaned_data.get('pin', '').strip()
        if not pin.isdigit() or len(pin) != 6:
            raise forms.ValidationError('PIN must be exactly 6 digits')
        return pin

