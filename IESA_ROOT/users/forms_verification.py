"""
Forms for Membership Verification System
"""
from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import Visit, Partner
from .constants import PIN_LENGTH


class MemberSearchForm(forms.Form):
    """Search form for finding members in partner dashboard"""
    query = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control search-input',
            'id': 'id_query',
            'placeholder': _('Start typing name, username, or UUID...'),
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
            'class': 'form-control partner-pin-input',
            'placeholder': '● ● ● ● ● ●',
            'pattern': '[0-9]{6}',
            'inputmode': 'numeric',
            'maxlength': '6',
            'autocomplete': 'off',
        }),
        label=_('Member PIN Code (6 digits)'),
        help_text=_('Ask the member to show the current PIN from their personal cabinet.')
    )
    
    class Meta:
        model = Visit
        fields = ['service_type', 'service_description', 'cost', 'comments', 'pin']
        widgets = {
            'service_type': forms.Select(attrs={
                'class': 'form-select form-select-lg',
            }),
            'service_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Example: Massage therapy 60 minutes, Personal training session, Product purchase details...'),
            }),
            'cost': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg',
                'step': '0.01',
                'min': '0',
                'placeholder': _('Enter amount (e.g., 50.00)'),
            }),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': _('Any additional notes about this visit...'),
            }),
        }
        labels = {
            'service_type': _('Service Type'),
            'service_description': _('Service Description (Optional)'),
            'cost': _('Cost in CHF (Optional)'),
            'comments': _('Additional Comments (Optional)'),
        }
    
    def clean_pin(self):
        """Validate PIN format"""
        pin = self.cleaned_data.get('pin', '').strip()
        if not pin.isdigit() or len(pin) != PIN_LENGTH:
            raise forms.ValidationError(_('PIN must be exactly 6 digits (numbers only).'))
        return pin
    
    def clean_cost(self):
        """Validate cost is positive"""
        cost = self.cleaned_data.get('cost')
        if cost is not None and cost < 0:
            raise forms.ValidationError(_('Cost cannot be negative.'))
        return cost


class EditVisitForm(forms.ModelForm):
    """Form for editing an existing visit within the 20-minute window."""
    reason = forms.CharField(
        max_length=500,
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Explain why this visit record needs to be corrected...'),
        }),
        label=_('Reason for Edit'),
        help_text=_('Required — will be stored in the audit log and sent to member by email.')
    )

    class Meta:
        model = Visit
        fields = ['service_type', 'service_description', 'cost', 'comments']
        widgets = {
            'service_type': forms.Select(attrs={
                'class': 'form-select form-select-lg',
            }),
            'service_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
            }),
            'cost': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg',
                'step': '0.01',
                'min': '0',
            }),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
            }),
        }
        labels = {
            'service_type': _('Service Type'),
            'service_description': _('Service Description'),
            'cost': _('Cost in CHF'),
            'comments': _('Comments'),
        }

    def clean_cost(self):
        cost = self.cleaned_data.get('cost')
        if cost is not None and cost < 0:
            raise forms.ValidationError(_('Cost cannot be negative.'))
        return cost


class PartnerProfileForm(forms.ModelForm):
    """Form for editing partner company profile."""
    class Meta:
        model = Partner
        fields = ['company_name', 'business_type']
        widgets = {
            'company_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Your company or business name'),
                'autocomplete': 'organization',
            }),
            'business_type': forms.Select(attrs={
                'class': 'form-select',
            }),
        }
        labels = {
            'company_name': _('Company / Business Name'),
            'business_type': _('Business Type'),
        }


class CancelVisitForm(forms.Form):
    """Form for cancelling a visit within the 20-minute window."""
    reason = forms.CharField(
        max_length=500,
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Explain why this visit is being cancelled...'),
        }),
        label=_('Reason for Cancellation'),
        help_text=_('Required — will be stored in the audit log and sent to member by email.')
    )


# ---------------------------------------------------------------------------
# Формы инвайт-системы (Задача 2)
# ---------------------------------------------------------------------------

class InviteGenerateForm(forms.Form):
    """Форма создания инвайт-ссылки администратором (только is_staff)."""

    partner_type = forms.ChoiceField(
        choices=Partner.PARTNER_TYPE_CHOICES,
        label=_('Partner Type'),
        help_text=_('Какую роль получит зарегистрировавшийся?'),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    company_name = forms.CharField(
        max_length=255, required=False,
        label=_('Company Name (optional)'),
        help_text=_('Предзаполнит поле в форме регистрации.'),
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. FitnessPro Geneva')}),
    )
    note = forms.CharField(
        max_length=255, required=False,
        label=_('Internal Note'),
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. Invite for lawyer M. Schmid')}),
    )
    expires_days = forms.IntegerField(
        min_value=1, max_value=90, initial=7,
        label=_('Expires in (days)'),
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    max_uses = forms.IntegerField(
        min_value=1, max_value=10, initial=1,
        label=_('Max Uses'),
        help_text=_('Сколько раз можно воспользоваться ссылкой.'),
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )


class InviteRegisterForm(forms.Form):
    """
    Форма регистрации по инвайт-ссылке.
    Получает invite для предзаполнения company_name и определения business_type.
    """

    username = forms.CharField(
        max_length=150,
        label=_('Username'),
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'username'}),
    )
    email = forms.EmailField(
        label=_('Email'),
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
    )
    first_name = forms.CharField(
        max_length=150, required=False,
        label=_('First Name'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        max_length=150, required=False,
        label=_('Last Name'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    company_name = forms.CharField(
        max_length=255,
        label=_('Company / Organisation Name'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    business_type = forms.ChoiceField(
        choices=[
            ('shop', _('Shop/Retail')),
            ('service', _('Service Provider')),
            ('gym', _('Gym/Fitness')),
            ('restaurant', _('Restaurant/Cafe')),
            ('other', _('Other')),
        ],
        label=_('Business Type'),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    password1 = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        label=_('Confirm Password'),
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, invite=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.invite = invite
        if invite and invite.company_name:
            self.fields['company_name'].initial = invite.company_name
        # Для сотрудников ассоциации скрываем business_type (всегда 'other')
        if invite and invite.partner_type == 'association_staff':
            self.fields['business_type'].required = False
            self.fields['business_type'].widget = forms.HiddenInput()

    def clean_username(self):
        from .models import User
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise ValidationError(_('This username is already taken.'))
        return username

    def clean_email(self):
        from .models import User
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_('This email is already registered.'))
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError({'password2': _('Passwords do not match.')})
        if p1:
            try:
                validate_password(p1)
            except ValidationError as e:
                raise ValidationError({'password1': e})
        return cleaned
