"""
Формы для blog

Вынесены в отдельный модуль для лучшей организации
"""

from django import forms
from .models import Comment, Post


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


class PostForm(forms.ModelForm):
    """Форма создания поста (уже существует)"""
    class Meta:
        model = Post
        fields = ['title', 'text', 'preview_image', 'category']
