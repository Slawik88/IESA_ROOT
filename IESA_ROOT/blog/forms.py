from django import forms
from .models import Post

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
