from django import forms
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
        # Remove 'required' from text field to prevent validation errors on hidden textarea
        # Validation will be done on frontend via JavaScript in Quill editor
        self.fields['text'].required = False


class CommentForm(forms.ModelForm):
    """Форма создания комментария"""
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Напишите комментарий...'
            })
        }