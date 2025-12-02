from django.contrib import admin
from django.utils.html import format_html
from .models import Photo


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
	list_display = ('__str__', 'uploaded_at', 'image_tag')
	search_fields = ('caption',)
	ordering = ('-uploaded_at',)

	def image_tag(self, obj):
		if obj.image:
			return format_html('<img src="{}" style="width:120px;height:70px;object-fit:cover;border-radius:6px;"/>', obj.image.url)
		return '-'
	image_tag.short_description = 'Превью'
