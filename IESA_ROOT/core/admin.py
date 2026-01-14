from django.contrib import admin
from django.utils.html import format_html
from .models import Partner, AssociationMember, President, SocialNetwork


@admin.register(President)
class PresidentAdmin(admin.ModelAdmin):
	list_display = ('name', 'position')
	fieldsets = (
		('Info', {'fields': ('name', 'position', 'photo')}),
		('Message', {'fields': ('description',)}),
	)

@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
	list_display = ('name', 'category', 'link', 'contract', 'logo_tag')
	list_filter = ('category', 'contract')
	search_fields = ('name',)
	fieldsets = (
		('Info', {'fields': ('name', 'category', 'link', 'contract')}),
		('Media', {'fields': ('logo', 'description')}),
	)

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


@admin.register(SocialNetwork)
class SocialNetworkAdmin(admin.ModelAdmin):
	list_display = ('name', 'url', 'is_active', 'order', 'icon_preview')
	list_filter = ('is_active', 'name')
	list_editable = ('is_active', 'order')
	search_fields = ('name', 'url')
	
	def icon_preview(self, obj):
		return format_html('<i class="{}" style="font-size: 1.5rem; color: #7aa5ff;"></i>', obj.get_icon())
	icon_preview.short_description = 'Icon'
