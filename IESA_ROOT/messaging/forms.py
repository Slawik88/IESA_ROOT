from django import forms
from users.models import User
from .models import Conversation


class ConversationForm(forms.ModelForm):
    group_name = forms.CharField(
        label='Название группы',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например: Команда A'})
    )
    participants = forms.ModelMultipleChoiceField(
        label='Участники',
        queryset=User.objects.filter(is_active=True),
        widget=forms.SelectMultiple(attrs={'class': 'form-select'}),
        required=True,
        help_text='Выберите участников (минимум 2). Вас добавим автоматически.'
    )

    class Meta:
        model = Conversation
        fields = ['group_name', 'participants']

    def clean_participants(self):
        qs = self.cleaned_data['participants']
        if qs.count() < 2:
            raise forms.ValidationError('Минимум 2 участника для группы')
        return qs
