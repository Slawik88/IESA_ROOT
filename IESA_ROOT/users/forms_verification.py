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
            'placeholder': 'Enter name, username, pseudonym, or member ID...',
            'autocomplete': 'off',
            'style': 'border: 2px solid #667eea; border-radius: 10px;'
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
        label='🔑 Member PIN Code (6 digits)',
        help_text='⚠️ Ask member to show their current PIN from personal cabinet'
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
                'placeholder': 'Example: Massage therapy 60 minutes, Personal training session, Product purchase details...',
                'style': 'border: 2px solid #dee2e6; border-radius: 10px;'
            }),
            'cost': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Enter amount (e.g., 50.00)',
                'style': 'border: 2px solid #dee2e6; border-radius: 10px; font-size: 1.25rem;'
            }),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Any additional notes about this visit...',
                'style': 'border: 2px solid #dee2e6; border-radius: 10px;'
            }),
        }
        labels = {
            'service_type': '📋 Service Type *',
            'service_description': '📝 Service Description (Optional)',
            'cost': '💰 Cost in CHF (Optional)',
            'comments': '💬 Additional Comments (Optional)',
        }
    
    def clean_pin(self):
        """Validate PIN format"""
        pin = self.cleaned_data.get('pin', '').strip()
        if not pin.isdigit() or len(pin) != 6:
            raise forms.ValidationError('❌ PIN must be exactly 6 digits (numbers only)')
        return pin
    
    def clean_cost(self):
        """Validate cost is positive"""
        cost = self.cleaned_data.get('cost')
        if cost is not None and cost < 0:
            raise forms.ValidationError('❌ Cost cannot be negative')
        return cost
