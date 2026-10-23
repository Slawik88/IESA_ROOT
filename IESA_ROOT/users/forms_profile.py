"""Partial profile updates use the same validation as the full edit form."""
from .forms import UserProfileEditForm


class ProfileFieldForm(UserProfileEditForm):
    allowed_fields = frozenset({
        'first_name', 'last_name', 'phone_number', 'pseudonym',
        'github_url', 'discord_url', 'telegram_url', 'website_url',
    })

    class Meta(UserProfileEditForm.Meta):
        fields = tuple(sorted({*UserProfileEditForm.Meta.fields, 'pseudonym'}))

    def __init__(self, *args, field_name, **kwargs):
        if field_name not in self.allowed_fields:
            raise ValueError('Field not allowed')
        super().__init__(*args, **kwargs)
        self.fields = {field_name: self.fields[field_name]}
