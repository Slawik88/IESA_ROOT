from django import forms
from django.utils.translation import gettext_lazy as _
from .models import AdminAppeal


class AdminAppealForm(forms.Form):
    appeal_name = forms.CharField(
        max_length=150,
        error_messages={'required': _('Please enter your name.')},
    )
    appeal_email = forms.EmailField(
        error_messages={'required': _('Please enter a valid e-mail address.'),
                        'invalid': _('Please enter a valid e-mail address.')},
    )
    appeal_reason = forms.ChoiceField(
        choices=AdminAppeal.REASON_CHOICES,
        required=False,
    )
    appeal_message = forms.CharField(
        min_length=20,
        widget=forms.Textarea,
        error_messages={
            'required': _('Message must be at least 20 characters.'),
            'min_length': _('Message must be at least 20 characters.'),
        },
    )
    appeal_requested_url = forms.CharField(required=False, max_length=500)
