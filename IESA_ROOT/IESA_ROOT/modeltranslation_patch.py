"""
Patch modeltranslation to support CKEditor5Field
"""
from modeltranslation.fields import TranslationField

try:
    from django_ckeditor_5.fields import CKEditor5Field
    
    # Register CKEditor5Field as a translatable field type
    # It will be treated like TextField
    TranslationField.SUPPORTED_FIELDS.add(CKEditor5Field)
except ImportError:
    # CKEditor5 not installed, skip
    pass
