from django.contrib import admin
from django.utils.html import format_html
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
	list_display = ('name', 'price', 'image_tag')
	search_fields = ('name', 'description')

	def image_tag(self, obj):
		if obj.image:
			return format_html('<img src="{}" style="width:100px;height:70px;object-fit:cover;border-radius:6px;"/>', obj.image.url)
		return '-'
	image_tag.short_description = 'Изображение'
