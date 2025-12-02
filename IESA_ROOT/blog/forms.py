from django import forms
from .models import Post

try:
    # CKEditor widget (works for django-ckeditor)
    from ckeditor.widgets import CKEditorWidget
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
