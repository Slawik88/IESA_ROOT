from django.contrib import admin
from django.utils.html import format_html
from .models import Partner, AssociationMember


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
	list_display = ('name', 'link', 'logo_tag')
	search_fields = ('name',)

	def logo_tag(self, obj):
		if obj.logo:
			return format_html('<img src="{}" style="width:90px;height:40px;object-fit:contain;border-radius:6px;background:#fff;"/>', obj.logo.url)
		return '-'
	logo_tag.short_description = 'Логотип'


@admin.register(AssociationMember)
class AssociationMemberAdmin(admin.ModelAdmin):
	list_display = ('name', 'position', 'photo_tag')
	search_fields = ('name', 'position')

	def photo_tag(self, obj):
		if obj.photo:
			return format_html('<img src="{}" style="width:60px;height:60px;object-fit:cover;border-radius:50%;"/>', obj.photo.url)
		return '-'
	photo_tag.short_description = 'Фото'
