"""
Forms for Membership Verification System
"""
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Visit, Partner


class MemberSearchForm(forms.Form):
    """Search form for finding members in partner dashboard"""
    query = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control search-input',
            'id': 'id_query',
            'placeholder': _('🔍 Start typing name, username, or UUID...'),
            'autocomplete': 'off',
            'style': 'border-radius: 15px; border: 2px solid #e9ecef; padding: 15px 20px; font-size: 1.1rem;'
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
            'placeholder': '● ● ● ● ● ●',
            'pattern': '[0-9]{6}',
            'inputmode': 'numeric',
            'maxlength': '6',
            'autocomplete': 'off',
            'style': 'font-size: 2rem; letter-spacing: 1rem; border: 3px solid #667eea; border-radius: 15px;'
        }),
        label=_('🔑 Member PIN Code (6 digits)'),
        help_text=_('⚠️ Ask member to show their current PIN from personal cabinet')
    )
    
    class Meta:
        model = Visit
        fields = ['service_type', 'service_description', 'cost', 'comments', 'pin']
        widgets = {
            'service_type': forms.Select(attrs={
                'class': 'form-select form-select-lg',
                'style': 'border: 2px solid #667eea; border-radius: 10px;'
            }),
            'service_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Example: Massage therapy 60 minutes, Personal training session, Product purchase details...'),
                'style': 'border: 2px solid #dee2e6; border-radius: 10px;'
            }),
            'cost': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg',
                'step': '0.01',
                'min': '0',
                'placeholder': _('Enter amount (e.g., 50.00)'),
                'style': 'border: 2px solid #dee2e6; border-radius: 10px; font-size: 1.25rem;'
            }),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': _('Any additional notes about this visit...'),
                'style': 'border: 2px solid #dee2e6; border-radius: 10px;'
            }),
        }
        labels = {
            'service_type': _('📋 Service Type *'),
            'service_description': _('📝 Service Description (Optional)'),
            'cost': _('💰 Cost in CHF (Optional)'),
            'comments': _('💬 Additional Comments (Optional)'),
        }
    
    def clean_pin(self):
        """Validate PIN format"""
        pin = self.cleaned_data.get('pin', '').strip()
        if not pin.isdigit() or len(pin) != 6:
            raise forms.ValidationError(_('❌ PIN must be exactly 6 digits (numbers only)'))
        return pin
    
    def clean_cost(self):
        """Validate cost is positive"""
        cost = self.cleaned_data.get('cost')
        if cost is not None and cost < 0:
            raise forms.ValidationError(_('❌ Cost cannot be negative'))
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
            'style': 'border: 2px solid #f093fb; border-radius: 10px;'
        }),
        label=_('📝 Reason for Edit *'),
        help_text=_('Required — will be stored in the audit log and sent to member by email.')
    )

    class Meta:
        model = Visit
        fields = ['service_type', 'service_description', 'cost', 'comments']
        widgets = {
            'service_type': forms.Select(attrs={
                'class': 'form-select form-select-lg',
                'style': 'border: 2px solid #667eea; border-radius: 10px;'
            }),
            'service_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'style': 'border: 2px solid #dee2e6; border-radius: 10px;'
            }),
            'cost': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg',
                'step': '0.01',
                'min': '0',
                'style': 'border: 2px solid #dee2e6; border-radius: 10px; font-size: 1.25rem;'
            }),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'style': 'border: 2px solid #dee2e6; border-radius: 10px;'
            }),
        }
        labels = {
            'service_type': _('📋 Service Type *'),
            'service_description': _('📝 Service Description'),
            'cost': _('💰 Cost in CHF'),
            'comments': _('💬 Comments'),
        }

    def clean_cost(self):
        cost = self.cleaned_data.get('cost')
        if cost is not None and cost < 0:
            raise forms.ValidationError(_('❌ Cost cannot be negative'))
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
            'style': 'border: 2px solid #f5576c; border-radius: 10px;'
        }),
        label=_('📝 Reason for Cancellation *'),
        help_text=_('Required — will be stored in the audit log and sent to member by email.')
    )
