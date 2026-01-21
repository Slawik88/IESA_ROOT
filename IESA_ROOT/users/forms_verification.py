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
