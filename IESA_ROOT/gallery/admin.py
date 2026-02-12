from django.contrib import admin
from django.utils.html import format_html
from django_ckeditor_5.widgets import CKEditor5Widget
from django.db import models
from modeltranslation.admin import TranslationAdmin
from .models import Photo
from . import translation  # noqa: F401


@admin.register(Photo)
class PhotoAdmin(TranslationAdmin):
	list_display = ('__str__', 'uploaded_at', 'image_tag')
	search_fields = ('caption',)
	ordering = ('-uploaded_at',)
	
	# CKEditor для caption
	formfield_overrides = {
		models.TextField: {'widget': CKEditor5Widget},
	}

	def image_tag(self, obj):
		if obj.image:
			return format_html('<img src="{}" style="width:120px;height:70px;object-fit:cover;border-radius:6px;"/>', obj.image.url)
		return '-'
	image_tag.short_description = 'Превью'
