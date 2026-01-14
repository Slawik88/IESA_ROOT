from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User
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
        fields = ('username', 'email', 'first_name', 'last_name', 'date_of_birth', 'avatar', 'is_verified', 'is_active', 'is_staff', 'is_superuser', 'has_physical_card', 'github_url', 'discord_url', 'telegram_url', 'website_url', 'other_links')


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
        fields = ('first_name', 'last_name', 'email', 'date_of_birth', 'avatar', 'github_url', 'discord_url', 'telegram_url', 'website_url', 'other_links')
