from django.contrib import admin
from django.utils.html import format_html
from django_ckeditor_5.widgets import CKEditor5Widget
from django import forms
from django.db import models
from modeltranslation.admin import TranslationAdmin
from .models import Product
from . import translation  # noqa: F401


@admin.register(Product)
class ProductAdmin(TranslationAdmin):
	list_display = ('name', 'price', 'image_tag')
	search_fields = ('name', 'description')
	
	# CKEditor для description
	formfield_overrides = {
		models.TextField: {'widget': CKEditor5Widget},
	}

	def image_tag(self, obj):
		if obj.image:
			return format_html('<img src="{}" style="width:100px;height:70px;object-fit:cover;border-radius:6px;"/>', obj.image.url)
		return '-'
	image_tag.short_description = 'Изображение'
