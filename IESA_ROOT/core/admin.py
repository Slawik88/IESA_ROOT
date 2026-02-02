from django.contrib import admin
from django.utils.html import format_html
from .models import Partner, AssociationMember, President, SocialNetwork, CoreProduct, MemberBenefit


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


@admin.register(CoreProduct)
class CoreProductAdmin(admin.ModelAdmin):
	list_display = ('title', 'duration', 'location', 'is_active', 'order', 'icon_preview', 'created_at')
	list_filter = ('is_active', 'created_at')
	list_editable = ('is_active', 'order')
	search_fields = ('title', 'description', 'location')
	readonly_fields = ('created_at', 'updated_at')
	
	fieldsets = (
		('Основная информация', {
			'fields': ('title', 'description', 'icon', 'image')
		}),
		('Детали программы', {
			'fields': ('duration', 'location', 'features', 'price_info')
		}),
		('Настройки отображения', {
			'fields': ('is_active', 'order')
		}),
		('Служебная информация', {
			'fields': ('created_at', 'updated_at'),
			'classes': ('collapse',)
		}),
	)
	
	def icon_preview(self, obj):
		return format_html('<i class="{}" style="font-size: 1.5rem; color: #667eea;"></i>', obj.icon)
	icon_preview.short_description = 'Иконка'


@admin.register(MemberBenefit)
class MemberBenefitAdmin(admin.ModelAdmin):
	list_display = ('title', 'category', 'discount_info', 'is_active', 'order', 'icon_preview', 'created_at')
	list_filter = ('is_active', 'category', 'created_at')
	list_editable = ('is_active', 'order')
	search_fields = ('title', 'description', 'partner_info')
	readonly_fields = ('created_at', 'updated_at')
	
	fieldsets = (
		('Основная информация', {
			'fields': ('title', 'category', 'description', 'discount_info')
		}),
		('Дизайн', {
			'fields': ('icon', 'color')
		}),
		('Дополнительно', {
			'fields': ('partner_info', 'terms')
		}),
		('Настройки отображения', {
			'fields': ('is_active', 'order')
		}),
		('Служебная информация', {
			'fields': ('created_at', 'updated_at'),
			'classes': ('collapse',)
		}),
	)
	
	def icon_preview(self, obj):
		return format_html('<i class="{}" style="font-size: 1.5rem; color: {};"></i>', obj.icon, obj.color if obj.color.startswith('#') else '#28a745')
	icon_preview.short_description = 'Иконка'
