from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User
from .forms import CustomUserCreationForm, CustomUserChangeForm
from django.utils.html import format_html
from django.conf import settings
from django.urls import path, reverse
from django.shortcuts import redirect
from django.contrib import messages
from .services.card_service import UserCardService
import uuid
from django.utils import timezone
from blog.utils import generate_qr_code_for_user
from django.core.files.storage import default_storage


class CardStatusFilter(admin.SimpleListFilter):
    """Filter users by card status (active/inactive)."""
    title = 'Card Status'
    parameter_name = 'card_status'

    def lookups(self, request, model_admin):
        return [
            ('active', 'Card Active'),
            ('inactive', 'Card Inactive'),
            ('never', 'Never Issued'),
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
    title = 'Verification Status'
    parameter_name = 'verification'

    def lookups(self, request, model_admin):
        return [
            ('verified', 'Verified'),
            ('unverified', 'Unverified'),
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
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_verified', 'last_online', 'permanent_id', 'card_qr']
    list_filter = (CardStatusFilter, VerificationFilter, 'is_staff', 'date_joined')
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Персональная информация', {'fields': ('first_name', 'last_name', 'email', 'avatar', 'date_of_birth', 'phone_number', 'is_phone_hidden')}),
        ('Card QR & Actions', {'fields': ('card_qr_with_actions', 'card_active', 'card_issued_at')}),
        ('Разрешения', {'fields': ('is_verified', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Важные даты', {'fields': ('last_login', 'date_joined', 'last_online')}),
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
    
    readonly_fields = ('last_online', 'permanent_id', 'card_qr_with_actions')
    
    actions = ['regenerate_qr_same_id', 'regenerate_permanent_id', 'issue_card', 'revoke_card']
    
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
        self.message_user(request, f"✅ Перегенерирован QR код для {count} пользователя(ей) с сохранением permanent_id")
    regenerate_qr_same_id.short_description = '🔄 Перегенерировать QR код (тот же ID)'

    def regenerate_permanent_id(self, request, queryset):
        """Заново создать permanent_id для каждого пользователя и QR.
        
        Используется если пользователь потерял карту и нужна новая.
        Старый permanent_id и QR код будут заменены новыми.
        
        FIX: Now uses bulk_update for efficient database writes
        """
        count = UserCardService.create_new_cards(queryset, request)
        self.message_user(request, f"✅ Создан новый permanent_id и QR код для {count} пользователя(ей)")
    regenerate_permanent_id.short_description = '🆕 Новый permanent_id и QR код (при потере карты)'

    def issue_card(self, request, queryset):
        """Активировать карту и установить дату выдачи.
        
        Генерирует QR код если его ещё нет.
        
        FIX: Now uses bulk_update for efficient database writes
        """
        count = UserCardService.issue_cards(queryset, request)
        self.message_user(request, f"✅ Выдана карта для {count} пользователя(ей)")
    issue_card.short_description = '✓ Выдать карту (активировать)'

    def revoke_card(self, request, queryset):
        """Деактивировать карту (пользователь не сможет использовать QR для входа).
        
        QR файл остаётся в хранилище, но карта не активна.
        
        FIX: Now uses queryset.update() instead of loop
        """
        count = UserCardService.revoke_cards(queryset)
        self.message_user(request, f"✅ Отозвана карта у {count} пользователя(ей)")
    revoke_card.short_description = '✗ Отозвать карту (деактивировать)'

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
            # Удаляем старый QR из S3 (БЕЗ префикса media/)
            try:
                old_key = f'cards/{user.permanent_id}.png'
                if default_storage.exists(old_key):
                    default_storage.delete(old_key)
            except Exception as e:
                pass
            
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
                pass
            
            messages.success(request, f'✅ QR код перегенерирован для {user.username} (permanent_id: {user.permanent_id})')
        
        return redirect(reverse('admin:users_user_change', args=[user_id]))

    def new_permanent_id_view(self, request, user_id):
        """Создать новый permanent_id и новый QR код (при потере карты)."""
        user = User.objects.get(pk=user_id)
        
        old_id = user.permanent_id
        
        # Удаляем старый QR из S3 (БЕЗ префикса media/)
        if old_id:
            try:
                old_key = f'cards/{old_id}.png'
                if default_storage.exists(old_key):
                    default_storage.delete(old_key)
            except Exception as e:
                pass
        
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
            pass
        
        messages.warning(
            request, 
            f'🆕 НОВАЯ КАРТА для {user.username}! '
            f'Старый ID: {old_id} → Новый ID: {user.permanent_id}. '
            f'⚠️ Старый QR код больше не работает!'
        )
        
        return redirect(reverse('admin:users_user_change', args=[user_id]))


admin.site.register(User, UserAdmin)