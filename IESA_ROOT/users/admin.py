from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import AccountChangeRequest, User, Partner, Visit, VisitAudit, InviteToken
from .forms import CustomUserCreationForm, CustomUserChangeForm
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext
from .services.card_service import UserCardService
import uuid
from django.utils import timezone
from users.qr_utils import generate_qr_code_for_user
from django.core.files.storage import default_storage
import boto3


class CardStatusFilter(admin.SimpleListFilter):
    """Filter users by card status (active/inactive)."""
    title = _('Card Status')
    parameter_name = 'card_status'

    def lookups(self, request, model_admin):
        return [
            ('active', _('Card Active')),
            ('inactive', _('Card Inactive')),
            ('never', _('Never Issued')),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(card_active=True)
        elif self.value() == 'inactive':
            return queryset.filter(card_active=False, card_issued_at__isnull=False)
        elif self.value() == 'never':
            return queryset.filter(card_issued_at__isnull=True)
        return queryset


class VerificationFilter(admin.SimpleListFilter):
    """Filter users by verification status."""
    title = _('Verification Status')
    parameter_name = 'verification'

    def lookups(self, request, model_admin):
        return [
            ('verified', _('Verified')),
            ('unverified', _('Unverified')),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'verified':
            return queryset.filter(is_verified=True)
        elif self.value() == 'unverified':
            return queryset.filter(is_verified=False)
        return queryset

class UserAdmin(BaseUserAdmin):
    """
    User admin configuration with optimized queries and bulk actions.
    
    FIX: 
    - Added CardStatusFilter and VerificationFilter for better filtering
    - Refactored admin actions to use UserCardService with bulk_update
    - Added list_select_related for query optimization
    """
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User
    list_display = ['username', 'email', 'first_name', 'last_name', 'membership_status', 'pseudonym', 'is_staff', 'is_verified', 'is_partner', 'last_online', 'permanent_id', 'card_qr']
    list_filter = (CardStatusFilter, VerificationFilter, 'membership_status', 'is_staff', 'date_joined')
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal information'), {'fields': ('first_name', 'last_name', 'email', 'avatar', 'date_of_birth', 'phone_number', 'is_phone_hidden')}),
        (_('Membership'), {'fields': ('membership_status', 'pseudonym', 'totp_secret_display')}),
        (_('Card QR & Actions'), {'fields': ('card_qr_with_actions', 'card_active', 'card_issued_at')}),
        (_('Permissions'), {'fields': ('is_verified', 'is_partner', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined', 'last_online')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'first_name', 'last_name', 'date_of_birth', 'phone_number', 'is_phone_hidden'),
        }),
        ('Card', {
            'classes': ('wide',),
            'fields': ('card_active', 'card_issued_at'),
        }),
    )
    
    readonly_fields = ('last_online', 'permanent_id', 'card_qr_with_actions', 'totp_secret_display')
    
    actions = ['regenerate_qr_same_id', 'regenerate_permanent_id', 'issue_card', 'revoke_card']
    
    def totp_secret_display(self, obj):
        """Display TOTP secret (read-only for security)."""
        if obj.totp_secret:
            return format_html(
                '<code style="background:#f0f0f0;padding:6px 10px;border-radius:4px;font-family:monospace;">{}</code>',
                obj.totp_secret
            )
        return format_html('<span style="color:#999;">Not set</span>')
    totp_secret_display.short_description = 'TOTP Secret'
    
    def card_qr_with_actions(self, obj):
        """Вывести QR код с кнопками действий."""
        if not obj.permanent_id:
            return format_html(
                '<div style="padding:10px; background:var(--body-bg); color:var(--body-fg);">'
                'Permanent ID не установлен'
                '</div>'
            )
        
        # Используем динамическую генерацию QR через view
        from django.urls import reverse
        qr_url = reverse('users:user_qr', kwargs={'permanent_id': obj.permanent_id})
        
        # URL для действий (используем правильный формат с admin namespace)
        regenerate_url = f"/admin/users/user/{obj.pk}/regenerate-qr/"
        new_id_url = f"/admin/users/user/{obj.pk}/new-permanent-id/"
        
        return format_html(
            '''
            <div style="padding:15px; border-radius:8px; background:var(--darkened-bg); border:1px solid var(--border-color);">
                <div style="text-align:center; margin-bottom:15px;">
                    <img src="{}" style="width:150px;height:150px;object-fit:contain;border:1px solid var(--border-color);border-radius:4px;background:white;padding:5px;"/>
                </div>
                <div style="margin-bottom:12px; color:var(--body-fg);">
                    <strong>Permanent ID:</strong> 
                    <code style="background:var(--darkened-bg);padding:4px 8px;border-radius:4px;border:1px solid var(--border-color);">{}</code>
                </div>
                <div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:10px;">
                    <a href="{}" 
                       class="button qr-regenerate-btn" 
                       onclick="return confirm('⚠️ Вы уверены, что хотите обновить QR-код?\\n\\nЭто создаст новый QR-код с тем же ID.\\nСтарый QR будет удалён.\\n\\nПродолжить?');"
                       style="flex:1; text-align:center; min-width:150px; padding:10px 15px; background:#417690; color:white; text-decoration:none; border-radius:4px; font-weight:500; display:inline-block; box-sizing:border-box;">
                        🔄 Обновить QR
                    </a>
                    <a href="{}" 
                       class="button qr-newid-btn" 
                       onclick="return confirm('🚨 ВНИМАНИЕ! Это создаст НОВУЮ ФИЗИЧЕСКУЮ КАРТУ!\\n\\n• Старая карта перестанет работать\\n• Создастся новый Permanent ID\\n• Потребуется напечатать новую карту\\n\\nВы УВЕРЕНЫ, что хотите продолжить?');"
                       style="flex:1; text-align:center; min-width:150px; padding:10px 15px; background:#ba2121; color:white; text-decoration:none; border-radius:4px; font-weight:500; display:inline-block; box-sizing:border-box;">
                        🆕 Новая карта
                    </a>
                </div>
                <div style="font-size:11px; color:var(--body-quiet-color); line-height:1.5;">
                    <strong>🔄 Обновить QR:</strong> Тот же ID, новый QR (повреждён)<br>
                    <strong>🆕 Новая карта:</strong> Новый ID + QR (потеря карты)
                </div>
            </div>
            ''',
            qr_url,
            obj.permanent_id,
            regenerate_url,
            new_id_url
        )
    card_qr_with_actions.short_description = 'Card QR & Actions'
    
    def card_qr(self, obj):
        """Вывести сгенерированный QR код через динамический view.
        
        QR генерируется динамически через /auth/qr/<permanent_id>/.
        """
        if not obj.permanent_id:
            return '-'
        # Используем динамическую генерацию QR
        from django.urls import reverse
        qr_url = reverse('users:user_qr', kwargs={'permanent_id': obj.permanent_id})
        return format_html('<img src="{}" style="width:80px;height:80px;object-fit:contain;border:1px solid #ddd;border-radius:4px;"/>', qr_url)
    card_qr.short_description = 'Card QR'

    def regenerate_qr_same_id(self, request, queryset):
        """Перегенерировать QR код с тем же permanent_id.
        
        Используется если QR код повреждён или неправильно отображается,
        но карта не потеряна (permanent_id остаётся тем же).
        
        FIX: Now uses UserCardService for consistency
        """
        count = UserCardService.regenerate_qr_for_users(queryset, request)
        self.message_user(request, gettext("QR code regenerated for %(count)d user(s) with same permanent_id") % {'count': count})
    regenerate_qr_same_id.short_description = _('🔄 Regenerate QR code (same ID)')

    def regenerate_permanent_id(self, request, queryset):
        """Заново создать permanent_id для каждого пользователя и QR.
        
        Используется если пользователь потерял карту и нужна новая.
        Старый permanent_id и QR код будут заменены новыми.
        
        FIX: Now uses bulk_update for efficient database writes
        """
        count = UserCardService.create_new_cards(queryset, request)
        self.message_user(request, gettext("New permanent_id and QR code created for %(count)d user(s)") % {'count': count})
    regenerate_permanent_id.short_description = _('🆕 New permanent_id and QR code (lost card)')

    def issue_card(self, request, queryset):
        """Активировать карту и установить дату выдачи.
        
        Генерирует QR код если его ещё нет.
        
        FIX: Now uses bulk_update for efficient database writes
        """
        count = UserCardService.issue_cards(queryset, request)
        self.message_user(request, gettext("Card issued for %(count)d user(s)") % {'count': count})
    issue_card.short_description = _('✓ Issue card (activate)')

    def revoke_card(self, request, queryset):
        """Деактивировать карту (пользователь не сможет использовать QR для входа).
        
        QR файл остаётся в хранилище, но карта не активна.
        
        FIX: Now uses queryset.update() instead of loop
        """
        count = UserCardService.revoke_cards(queryset)
        self.message_user(request, gettext("Card revoked for %(count)d user(s)") % {'count': count})
    revoke_card.short_description = _('✗ Revoke card (deactivate)')

    def get_urls(self):
        """Добавить кастомные URL для кнопок QR кода."""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:user_id>/regenerate-qr/',
                self.admin_site.admin_view(self.regenerate_qr_view),
                name='regenerate_qr',
            ),
            path(
                '<int:user_id>/new-permanent-id/',
                self.admin_site.admin_view(self.new_permanent_id_view),
                name='new_permanent_id',
            ),
        ]
        return custom_urls + urls

    def regenerate_qr_view(self, request, user_id):
        """Перегенерировать QR код с тем же permanent_id."""
        user = User.objects.get(pk=user_id)

        if not user.permanent_id:
            messages.error(request, f'❌ У пользователя {user.username} нет permanent_id')
        else:
            # Удаляем старый QR из S3 (B1-07: логируем ошибки вместо pass)
            try:
                old_key = f'cards/{user.permanent_id}.png'
                if default_storage.exists(old_key):
                    default_storage.delete(old_key)
            except Exception as e:
                logger.warning("regenerate_qr: failed to delete old QR for user %s: %s", user.pk, e)
                messages.warning(request, f'⚠️ Не удалось удалить старый QR из хранилища: {e}')

            # Инвалидируем Django-кэш QR-изображения
            from django.core.cache import cache as _cache
            _cache.delete(f'qr_image_{user.permanent_id}')

            # Генерируем новый QR с тем же ID
            generate_qr_code_for_user(user, request)

            # Устанавливаем ACL как public-read
            try:
                s3 = boto3.client(
                    's3',
                    endpoint_url=os.getenv('SPACES_ENDPOINT', 'https://fra1.digitaloceanspaces.com'),
                    aws_access_key_id=os.getenv('SPACES_KEY'),
                    aws_secret_access_key=os.getenv('SPACES_SECRET'),
                    region_name='fra1'
                )
                bucket = os.getenv('SPACES_BUCKET', 'iesa-bucket')
                s3.put_object_acl(
                    Bucket=bucket,
                    Key=f'media/cards/{user.permanent_id}.png',
                    ACL='public-read'
                )
            except Exception as e:
                logger.error("regenerate_qr: S3 ACL error for user %s: %s", user.pk, e)
                messages.warning(request, f'⚠️ QR сгенерирован, но не удалось установить ACL: {e}')

            messages.success(request, f'✅ QR код перегенерирован для {user.username} (permanent_id: {user.permanent_id})')
        
        return redirect(reverse('admin:users_user_change', args=[user_id]))

    def new_permanent_id_view(self, request, user_id):
        """Создать новый permanent_id и новый QR код (при потере карты)."""
        user = User.objects.get(pk=user_id)
        
        old_id = user.permanent_id
        
        # Удаляем старый QR из S3 (БЕЗ префикса media/)
        if old_id:
            # Удаляем старый файл (B1-07: логируем ошибки)
            try:
                old_key = f'cards/{old_id}.png'
                if default_storage.exists(old_key):
                    default_storage.delete(old_key)
            except Exception as e:
                logger.warning("new_permanent_id: failed to delete old QR (id=%s): %s", old_id, e)
                messages.warning(request, f'⚠️ Не удалось удалить старый QR из хранилища: {e}')

            # Инвалидируем кэш старого QR (B1-11)
            from django.core.cache import cache as _cache
            _cache.delete(f'qr_image_{old_id}')

        # Создаём новый permanent_id
        user.permanent_id = uuid.uuid4()
        user.card_active = True
        user.card_issued_at = timezone.now()
        user.save()

        # Генерируем новый QR код
        generate_qr_code_for_user(user, request)

        # Устанавливаем ACL как public-read
        try:
            s3 = boto3.client(
                's3',
                endpoint_url=os.getenv('SPACES_ENDPOINT', 'https://fra1.digitaloceanspaces.com'),
                aws_access_key_id=os.getenv('SPACES_KEY'),
                aws_secret_access_key=os.getenv('SPACES_SECRET'),
                region_name='fra1'
            )
            bucket = os.getenv('SPACES_BUCKET', 'iesa-bucket')
            s3.put_object_acl(
                Bucket=bucket,
                Key=f'media/cards/{user.permanent_id}.png',
                ACL='public-read'
            )
        except Exception as e:
            logger.error("new_permanent_id: S3 ACL error for user %s: %s", user.pk, e)
            messages.warning(request, f'⚠️ QR создан, но не удалось установить ACL: {e}')
        
        messages.warning(
            request, 
            f'🆕 НОВАЯ КАРТА для {user.username}! '
            f'Старый ID: {old_id} → Новый ID: {user.permanent_id}. '
            f'⚠️ Старый QR код больше не работает!'
        )
        
        return redirect(reverse('admin:users_user_change', args=[user_id]))


admin.site.register(User, UserAdmin)


# PARTNER AND VISIT ADMIN

@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    """Admin interface for Partner model"""
    list_display = ['company_name', 'user', 'business_type', 'created_at', 'total_visits']
    list_filter = ['business_type', 'created_at']
    search_fields = ['company_name', 'user__username', 'user__email']
    raw_id_fields = ['user']
    readonly_fields = ['created_at', 'total_visits']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('user', 'company_name', 'business_type')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'total_visits')
        }),
    )
    
    def total_visits(self, obj):
        """Display total visits count"""
        count = obj.logged_visits.count()
        return format_html(
            '<span style="font-weight: bold; color: #28a745;">{}</span>',
            count
        )
    total_visits.short_description = 'Total Visits'


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    """Admin interface for Visit model"""
    list_display = [
        'timestamp', 'member_info', 'partner', 'service_type', 
        'cost', 'verified_badge', 'member_status'
    ]
    list_filter = [
        'service_type', 'pin_verified', 'timestamp', 
        'partner__business_type', 'member__membership_status'
    ]
    search_fields = [
        'member__username', 'member__first_name', 'member__last_name',
        'member__pseudonym', 'partner__company_name', 'service_description'
    ]
    raw_id_fields = ['member', 'partner']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        (_('Visit Information'), {
            'fields': ('member', 'partner', 'timestamp')
        }),
        (_('Service Details'), {
            'fields': ('service_type', 'service_description', 'cost', 'comments')
        }),
        (_('Verification'), {
            'fields': ('pin_verified',)
        }),
    )
    
    def member_info(self, obj):
        """Display member username with link"""
        url = reverse('admin:users_user_change', args=[obj.member.id])
        return format_html(
            '<a href="{}">{}</a>',
            url, obj.member.username
        )
    member_info.short_description = 'Member'
    
    def verified_badge(self, obj):
        """Display verification status badge"""
        if obj.pin_verified:
            return format_html(
                '<span style="color: white; background-color: #28a745; '
                'padding: 3px 8px; border-radius: 3px; font-weight: bold;">✓ Verified</span>'
            )
        return format_html(
            '<span style="color: white; background-color: #dc3545; '
            'padding: 3px 8px; border-radius: 3px;">✗ Not Verified</span>'
        )
    verified_badge.short_description = 'PIN Verified'
    
    def member_status(self, obj):
        """Display member's current status"""
        if obj.member.membership_status == 'active':
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">●</span> Active'
            )
        return format_html(
            '<span style="color: #6c757d;">●</span> Inactive'
        )
    member_status.short_description = 'Member Status'


@admin.register(VisitAudit)
class VisitAuditAdmin(admin.ModelAdmin):
    """Read-only audit trail for visit edits/cancellations."""
    list_display = ['visit', 'action', 'changed_by', 'changed_at', 'reason_short']
    list_filter = ['action', 'changed_at']
    search_fields = ['visit__member__username', 'visit__partner__company_name', 'reason']
    readonly_fields = [
        'visit', 'action', 'previous_service_type', 'previous_service_description',
        'previous_cost', 'previous_comments', 'reason', 'changed_at', 'changed_by',
    ]
    ordering = ['-changed_at']

    def reason_short(self, obj):
        return obj.reason[:60] + '…' if len(obj.reason) > 60 else obj.reason
    reason_short.short_description = 'Reason'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# InviteToken admin
# ---------------------------------------------------------------------------

@admin.register(InviteToken)
class InviteTokenAdmin(admin.ModelAdmin):
    """Администрирование инвайт-ссылок."""
    list_display = [
        'short_token', 'partner_type', 'company_name', 'note',
        'created_by', 'used_by', 'use_count', 'max_uses',
        'is_active', 'expires_at', 'created_at', 'invite_link',
    ]
    list_filter = ['partner_type', 'is_active']
    search_fields = ['company_name', 'note', 'created_by__username', 'used_by__username']
    readonly_fields = ['token', 'used_by', 'used_at', 'use_count', 'created_at', 'invite_link']

    def short_token(self, obj):
        return str(obj.token)[:8] + '…'
    short_token.short_description = 'Token'

    def invite_link(self, obj):
        url = f'/users/invite/{obj.token}/'
        return format_html('<a href="{}" target="_blank">{}</a>', url, url)
    invite_link.short_description = 'Invite URL'

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# AccountChangeRequest admin — Задача 2
# ---------------------------------------------------------------------------

@admin.register(AccountChangeRequest)
class AccountChangeRequestAdmin(admin.ModelAdmin):
    """
    Админка заявок на смену типа аккаунта.
    Показывает контакты пользователя прямо в списке для быстрой связи.
    """
    list_display = [
        'user_link', 'desired_type', 'status',
        'user_email', 'user_phone', 'user_telegram',
        'reason_short', 'created_at',
    ]
    list_filter  = ['status', 'desired_type', 'created_at']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name', 'reason']
    readonly_fields = ['user', 'desired_type', 'reason', 'created_at', 'user_contact_card']
    ordering = ['-created_at']

    fieldsets = [
        ('Заявка', {'fields': ['user', 'desired_type', 'reason', 'created_at']}),
        ('Контакт пользователя', {'fields': ['user_contact_card']}),
        ('Решение администратора', {'fields': ['status', 'admin_note']}),
    ]

    # ── Вычисляемые колонки ──────────────────────────────────────

    def user_link(self, obj):
        url = f'/admin/users/user/{obj.user.pk}/change/'
        name = obj.user.get_full_name() or obj.user.username
        return format_html('<a href="{}">{}</a>', url, name)
    user_link.short_description = 'Пользователь'
    user_link.admin_order_field = 'user__username'

    def user_email(self, obj):
        return format_html('<a href="mailto:{}">{}</a>', obj.user.email, obj.user.email)
    user_email.short_description = 'Email'

    def user_phone(self, obj):
        p = obj.user.phone_number or '—'
        return p
    user_phone.short_description = 'Телефон'

    def user_telegram(self, obj):
        if obj.user.telegram_linked_at:
            return format_html(
                '<span style="color:#29a8eb;font-weight:700;">✓ привязан</span>'
            )
        tg = getattr(obj.user, 'telegram_url', '') or ''
        if tg:
            return format_html('<a href="{}" target="_blank">открыть</a>', tg)
        return '—'
    user_telegram.short_description = 'Telegram'

    def reason_short(self, obj):
        return obj.reason[:80] + '…' if len(obj.reason) > 80 else obj.reason
    reason_short.short_description = 'Причина'

    def user_contact_card(self, obj):
        u = obj.user
        lines = [
            f'<strong>Username:</strong> {u.username}',
            f'<strong>Email:</strong> <a href="mailto:{u.email}">{u.email}</a>',
            f'<strong>Телефон:</strong> {u.phone_number or "не указан"}',
            f'<strong>Telegram chat_id:</strong> {u.telegram_chat_id or "нет"}',
            f'<strong>Telegram linked:</strong> {u.telegram_linked_at or "нет"}',
            f'<strong>Членство:</strong> {u.membership_status}',
            f'<strong>Партнёр:</strong> {"да" if u.is_partner else "нет"}',
        ]
        return format_html('<br>'.join(lines))
    user_contact_card.short_description = 'Контактная карточка'

    def has_add_permission(self, request):
        return False  # заявки создаются только пользователями, не из Admin
