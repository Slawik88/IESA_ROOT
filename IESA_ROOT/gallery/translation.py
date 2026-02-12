from modeltranslation.translator import register, TranslationOptions
from .models import Photo


@register(Photo)
class PhotoTranslationOptions(TranslationOptions):
    fields = ('caption',)
