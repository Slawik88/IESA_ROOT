from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Post, Comment

try:
    # CKEditor 5 widget (безопасная версия)
    from django_ckeditor_5.widgets import CKEditor5Widget
    CKEditorWidget = CKEditor5Widget
except Exception:
    CKEditorWidget = None


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['title', 'text', 'preview_image']
        widgets = {}
        if CKEditorWidget:
            widgets['text'] = CKEditorWidget()
        else:
            widgets['text'] = forms.Textarea(attrs={'class': 'form-control', 'rows': 10})    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The editor hides this textarea; clean_text validates the submitted HTML.
        self.fields['text'].required = False

    def clean_text(self):
        from django.utils.html import strip_tags
        from .utils.html import sanitize_post_html
        text = sanitize_post_html(self.cleaned_data.get('text'))
        if not strip_tags(text).replace('&nbsp;', ' ').strip() and '<img ' not in text:
            raise forms.ValidationError(_('Post text is required.'))
        return text


class CommentForm(forms.ModelForm):
    """Форма создания комментария"""
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Write a comment...')
            })
        }