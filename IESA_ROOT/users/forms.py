from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User
from django.utils import timezone
import uuid


class CustomUserCreationForm(UserCreationForm):
    """
    Форма создания нового пользователя для админки/регистрации.
    
    Включает чекбокс "issue_card_now" — если поставить, админ может выдать
    физическую карту прямо при создании пользователя.
    """
    issue_card_now = forms.BooleanField(
        required=False,
        label='Выдать физическую карту при создании',
        help_text='Если установлено, будет сгенерирован QR код и установлена дата выдачи карты.'
    )
    
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
    
    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('first_name', 'last_name', 'email', 'date_of_birth', 'avatar', 'github_url', 'discord_url', 'telegram_url', 'website_url', 'other_links')

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Если чекбокс установлен — генерируем карту
        if self.cleaned_data.get('issue_card_now'):
            # Убедимся что permanent_id уже установлен (default должен сработать)
            if not user.permanent_id:
                user.permanent_id = uuid.uuid4()
            user.card_active = True
            user.card_issued_at = timezone.now()
        
        if commit:
            user.save()
            # После сохранения — генерируем QR код если карта активирована
            if user.card_active:
                from .qr_utils import generate_qr_code_for_user
                generate_qr_code_for_user(user)
        
        return user


class CustomUserChangeForm(UserChangeForm):
    """
    Форма редактирования пользователя для админки.
    """
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
        fields = ('username', 'email', 'first_name', 'last_name', 'date_of_birth', 'avatar', 'is_verified', 'is_active', 'is_staff', 'is_superuser', 'github_url', 'discord_url', 'telegram_url', 'website_url', 'other_links')


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
