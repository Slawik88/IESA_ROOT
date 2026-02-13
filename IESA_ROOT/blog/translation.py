from modeltranslation.translator import register, TranslationOptions
from .models import Post, Event


@register(Post)
class PostTranslationOptions(TranslationOptions):
    # Only translate title, not text field (CKEditor5Field not fully supported)
    # Users can manually create separate posts in different languages if needed
    fields = ('title',)


@register(Event)
class EventTranslationOptions(TranslationOptions):
    fields = ('title', 'description', 'location')
