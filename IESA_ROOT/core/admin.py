from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django_ckeditor_5.widgets import CKEditor5Widget
from django import forms
from modeltranslation.admin import TabbedTranslationAdmin
from .models import Partner, AssociationMember, President, SocialNetwork, CoreProduct, MemberBenefit, AdminAppeal, MediaHash
from . import translation  # noqa: F401


# Формы с CKEditor для всех моделей с описаниями
class PresidentAdminForm(forms.ModelForm):
	description = forms.CharField(widget=CKEditor5Widget(), required=False, label=_('Description'))
	
	class Meta:
		model = President
		fields = '__all__'


class PartnerAdminForm(forms.ModelForm):
	description = forms.CharField(widget=CKEditor5Widget(), required=False, label=_('Description'))
	
	class Meta:
		model = Partner
		fields = '__all__'


class CoreProductAdminForm(forms.ModelForm):
	description = forms.CharField(widget=CKEditor5Widget(), required=False, label=_('Description'))
	features = forms.CharField(widget=CKEditor5Widget(), required=False, label=_('Features'))
	
	class Meta:
		model = CoreProduct
		fields = '__all__'


class MemberBenefitAdminForm(forms.ModelForm):
	description = forms.CharField(widget=CKEditor5Widget(), required=False, label=_('Description'))
	terms = forms.CharField(widget=CKEditor5Widget(), required=False, label=_('Terms'))
	
	# Добавляем детальные подсказки для иконок и цветов
	icon = forms.CharField(
		max_length=100,
		label=_('Font Awesome icon'),
		help_text=format_html('''
			<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-top: 10px; border-left: 4px solid #dc2626;">
				<h4 style="margin-top: 0; color: #dc2626;">📚 Примеры иконок Font Awesome</h4>
				<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
					<div><i class="fas fa-percent" style="color: #dc2626; font-size: 1.2rem;"></i> <code>fas fa-percent</code> - Скидки</div>
					<div><i class="fas fa-gift" style="color: #10b981; font-size: 1.2rem;"></i> <code>fas fa-gift</code> - Подарки</div>
					<div><i class="fas fa-dumbbell" style="color: #3b82f6; font-size: 1.2rem;"></i> <code>fas fa-dumbbell</code> - Спортзал</div>
					<div><i class="fas fa-utensils" style="color: #f59e0b; font-size: 1.2rem;"></i> <code>fas fa-utensils</code> - Питание</div>
					<div><i class="fas fa-heartbeat" style="color: #ef4444; font-size: 1.2rem;"></i> <code>fas fa-heartbeat</code> - Здоровье</div>
					<div><i class="fas fa-graduation-cap" style="color: #8b5cf6; font-size: 1.2rem;"></i> <code>fas fa-graduation-cap</code> - Обучение</div>
					<div><i class="fas fa-ticket-alt" style="color: #ec4899; font-size: 1.2rem;"></i> <code>fas fa-ticket-alt</code> - Билеты</div>
					<div><i class="fas fa-tshirt" style="color: #06b6d4; font-size: 1.2rem;"></i> <code>fas fa-tshirt</code> - Одежда</div>
					<div><i class="fas fa-handshake" style="color: #14b8a6; font-size: 1.2rem;"></i> <code>fas fa-handshake</code> - Партнерство</div>
					<div><i class="fas fa-trophy" style="color: #fbbf24; font-size: 1.2rem;"></i> <code>fas fa-trophy</code> - Награды</div>
					<div><i class="fas fa-calendar-check" style="color: #a855f7; font-size: 1.2rem;"></i> <code>fas fa-calendar-check</code> - События</div>
					<div><i class="fas fa-users" style="color: #84cc16; font-size: 1.2rem;"></i> <code>fas fa-users</code> - Сообщество</div>
				</div>
				<p style="margin: 10px 0 0 0; font-size: 0.9rem;">
					🔗 Больше иконок: <a href="https://fontawesome.com/icons" target="_blank" style="color: #dc2626;">fontawesome.com/icons</a>
				</p>
			</div>
		''')
	)
	
	color = forms.CharField(
		max_length=50,
		label=_('Color'),
		help_text=format_html('''
			<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-top: 10px; border-left: 4px solid #dc2626;">
				<h4 style="margin-top: 0; color: #dc2626;">🎨 Варианты цветов</h4>
				<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
					<div>
						<span style="display: inline-block; width: 20px; height: 20px; background: #dc2626; border-radius: 4px; vertical-align: middle;"></span>
						<code>primary</code> или <code>#dc2626</code> - Красный (основной)
					</div>
					<div>
						<span style="display: inline-block; width: 20px; height: 20px; background: #10b981; border-radius: 4px; vertical-align: middle;"></span>
						<code>success</code> или <code>#10b981</code> - Зелёный (успех)
					</div>
					<div>
						<span style="display: inline-block; width: 20px; height: 20px; background: #3b82f6; border-radius: 4px; vertical-align: middle;"></span>
						<code>info</code> или <code>#3b82f6</code> - Синий (информация)
					</div>
					<div>
						<span style="display: inline-block; width: 20px; height: 20px; background: #f59e0b; border-radius: 4px; vertical-align: middle;"></span>
						<code>warning</code> или <code>#f59e0b</code> - Оранжевый (внимание)
					</div>
					<div>
						<span style="display: inline-block; width: 20px; height: 20px; background: #ef4444; border-radius: 4px; vertical-align: middle;"></span>
						<code>danger</code> или <code>#ef4444</code> - Красный (опасность)
					</div>
					<div>
						<span style="display: inline-block; width: 20px; height: 20px; background: #8b5cf6; border-radius: 4px; vertical-align: middle;"></span>
						<code>#8b5cf6</code> - Фиолетовый (custom)
					</div>
				</div>
				<p style="margin: 10px 0 0 0; font-size: 0.9rem;">
					💡 Можно использовать названия (primary, success) или любой hex-код (#RRGGBB)
				</p>
			</div>
		''')
	)
	
	class Meta:
		model = MemberBenefit
		fields = '__all__'


@admin.register(President)
class PresidentAdmin(TabbedTranslationAdmin):
	form = PresidentAdminForm
	list_display = ('name', 'position')
	fieldsets = (
		('Info', {'fields': ('name', 'position', 'photo')}),
		('Message', {'fields': ('description',)}),
	)

@admin.register(Partner)
class PartnerAdmin(TabbedTranslationAdmin):
	form = PartnerAdminForm
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
	logo_tag.short_description = _('Logo')


@admin.register(AssociationMember)
class AssociationMemberAdmin(TabbedTranslationAdmin):
	list_display = ('name', 'position', 'photo_tag')
	search_fields = ('name', 'position')

	def photo_tag(self, obj):
		if obj.photo:
			return format_html('<img src="{}" style="width:60px;height:60px;object-fit:cover;border-radius:50%;"/>', obj.photo.url)
		return '-'
	photo_tag.short_description = _('Photo')


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
class CoreProductAdmin(TabbedTranslationAdmin):
	form = CoreProductAdminForm
	list_display = ('title', 'duration', 'location', 'is_active', 'order', 'icon_preview', 'created_at')
	list_filter = ('is_active', 'created_at')
	list_editable = ('is_active', 'order')
	search_fields = ('title', 'description', 'location')
	readonly_fields = ('created_at', 'updated_at')
	
	fieldsets = (
		(_('Basic information'), {
			'fields': ('title', 'description', 'icon', 'image')
		}),
		(_('Program details'), {
			'fields': ('duration', 'location', 'features', 'price_info')
		}),
		(_('Display settings'), {
			'fields': ('is_active', 'order')
		}),
		(_('Service information'), {
			'fields': ('created_at', 'updated_at'),
			'classes': ('collapse',)
		}),
	)
	
	def icon_preview(self, obj):
		return format_html('<i class="{}" style="font-size: 1.5rem; color: #667eea;"></i>', obj.icon)
	icon_preview.short_description = _('Icon')


@admin.register(MemberBenefit)
class MemberBenefitAdmin(TabbedTranslationAdmin):
	form = MemberBenefitAdminForm
	list_display = ('title', 'category', 'discount_info', 'is_active', 'order', 'icon_preview', 'created_at')
	list_filter = ('is_active', 'category', 'created_at')
	list_editable = ('is_active', 'order')
	search_fields = ('title', 'description', 'partner_info')
	readonly_fields = ('created_at', 'updated_at')
	
	fieldsets = (
		(_('Basic information'), {
			'fields': ('title', 'category', 'description', 'discount_info')
		}),
		(_('Design'), {
			'fields': ('icon', 'color')
		}),
		(_('Additional'), {
			'fields': ('partner_info', 'terms')
		}),
		(_('Display settings'), {
			'fields': ('is_active', 'order')
		}),
		(_('Service information'), {
			'fields': ('created_at', 'updated_at'),
			'classes': ('collapse',)
		}),
	)
	
	def icon_preview(self, obj):
		return format_html('<i class="{}" style="font-size: 1.5rem; color: {};"></i>', obj.icon, obj.color if obj.color.startswith('#') else '#28a745')
	icon_preview.short_description = _('Icon')


@admin.register(AdminAppeal)
class AdminAppealAdmin(admin.ModelAdmin):
	list_display = ('__str__', 'reason', 'status', 'created_at')
	list_filter = ('status', 'reason', 'created_at')
	list_editable = ('status',)
	search_fields = ('name', 'email', 'message', 'admin_notes')
	readonly_fields = ('user', 'name', 'email', 'reason', 'message', 'requested_url', 'created_at', 'updated_at')
	date_hierarchy = 'created_at'

	fieldsets = (
		(_('Request'), {
			'fields': ('user', 'name', 'email', 'reason', 'message', 'requested_url')
		}),
		(_('Processing'), {
			'fields': ('status', 'admin_notes')
		}),
		(_('Timestamps'), {
			'fields': ('created_at', 'updated_at'),
			'classes': ('collapse',)
		}),
	)


@admin.register(MediaHash)
class MediaHashAdmin(admin.ModelAdmin):
	list_display  = ('sha256_short', 's3_key', 'created')
	search_fields = ('sha256', 's3_key')
	readonly_fields = ('sha256', 's3_key', 'created')

	def sha256_short(self, obj):
		return obj.sha256[:16] + '…'
	sha256_short.short_description = 'SHA-256'
