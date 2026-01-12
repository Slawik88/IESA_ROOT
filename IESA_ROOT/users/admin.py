from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User
from .forms import CustomUserCreationForm, CustomUserChangeForm
from django.utils.html import format_html
from django.conf import settings
import uuid
from .qr_utils import generate_qr_code_for_user
from django.utils import timezone
from django.urls import path, reverse
from django.shortcuts import redirect
from django.contrib import messages
from django.core.files.storage import default_storage
import boto3
import os

class UserAdmin(BaseUserAdmin):
    """
    Настройка админки для кастомной модели пользователя.
    """
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_verified', 'last_online', 'permanent_id', 'card_qr']
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Персональная информация', {'fields': ('first_name', 'last_name', 'email', 'avatar', 'date_of_birth')}),
        ('Card QR & Actions', {'fields': ('card_qr_with_actions', 'card_active', 'card_issued_at')}),
        ('Разрешения', {'fields': ('is_verified', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Важные даты', {'fields': ('last_login', 'date_joined', 'last_online')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'first_name', 'last_name', 'date_of_birth'),
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
            return format_html('<p>Permanent ID не установлен</p>')
        
        # Путь к сохранённому QR коду
        qr_path = f"{settings.MEDIA_URL}media/cards/{str(obj.permanent_id)}.png"
        
        # URL для действий
        regenerate_url = reverse('admin:regenerate_qr', args=[obj.pk])
        new_id_url = reverse('admin:new_permanent_id', args=[obj.pk])
        
        return format_html(
            '''
            <div style="border:1px solid #ddd; padding:15px; border-radius:8px; background:#f9f9f9;">
                <div style="text-align:center; margin-bottom:10px;">
                    <img src="{}" style="width:150px;height:150px;object-fit:contain;border:1px solid #ddd;border-radius:4px;background:white;"/>
                </div>
                <div style="margin-bottom:8px;">
                    <strong>Permanent ID:</strong> <code>{}</code>
                </div>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
                    <a href="{}" class="button" style="flex:1; text-align:center; min-width:180px;">
                        🔄 Перегенерировать QR
                    </a>
                    <a href="{}" class="button" style="flex:1; text-align:center; min-width:180px; background:#dc3545; color:white;">
                        🆕 Новый ID (потеря карты)
                    </a>
                </div>
                <div style="margin-top:8px; font-size:11px; color:#666;">
                    <strong>🔄 Перегенерировать QR:</strong> Создаёт новый QR с тем же ID (если QR повреждён)<br>
                    <strong>🆕 Новый ID:</strong> Создаёт новый permanent_id и новый QR (при потере карты)
                </div>
            </div>
            ''',
            qr_path,
            obj.permanent_id,
            regenerate_url,
            new_id_url
        )
    card_qr_with_actions.short_description = 'Card QR & Actions'
    
    def card_qr(self, obj):
        """Вывести сгенерированный QR код из media/cards/.
        
        QR ведёт на /auth/card/<permanent_id>/ и хранится локально.
        """
        if not obj.permanent_id:
            return '-'
        # Путь к сохранённому QR коду
        qr_path = f"{settings.MEDIA_URL}media/cards/{str(obj.permanent_id)}.png"
        return format_html('<img src="{}" style="width:80px;height:80px;object-fit:contain;border:1px solid #ddd;border-radius:4px;"/>', qr_path)
    card_qr.short_description = 'Card QR'

    def regenerate_qr_same_id(self, request, queryset):
        """Перегенерировать QR код с тем же permanent_id.
        
        Используется если QR код повреждён или неправильно отображается,
        но карта не потеряна (permanent_id остаётся тем же).
        """
        count = 0
        for user in queryset:
            if user.permanent_id:
                # Генерируем QR код с текущим permanent_id
                generate_qr_code_for_user(user, request)
                count += 1
        self.message_user(request, f"✅ Перегенерирован QR код для {count} пользователя(ей) с сохранением permanent_id")
    regenerate_qr_same_id.short_description = '🔄 Перегенерировать QR код (тот же ID)'

    def regenerate_permanent_id(self, request, queryset):
        """Заново создать permanent_id для каждого пользователя и QR.
        
        Используется если пользователь потерял карту и нужна новая.
        Старый permanent_id и QR код будут заменены новыми.
        """
        count = 0
        for user in queryset:
            user.permanent_id = uuid.uuid4()
            user.card_active = True
            user.card_issued_at = timezone.now()
            user.save()
            # Генерируем и сохраняем новый QR код
            generate_qr_code_for_user(user, request)
            count += 1
        self.message_user(request, f"✅ Создан новый permanent_id и QR код для {count} пользователя(ей)")
    regenerate_permanent_id.short_description = '🆕 Новый permanent_id и QR код (при потере карты)'

    def issue_card(self, request, queryset):
        """Активировать карту и установить дату выдачи.
        
        Генерирует QR код если его ещё нет.
        """
        count = 0
        for user in queryset:
            user.card_active = True
            user.card_issued_at = timezone.now()
            user.save()
            # Если QR не был сгенерирован — генерируем
            generate_qr_code_for_user(user, request)
            count += 1
        self.message_user(request, f"✅ Выдана карта для {count} пользователя(ей)")
    issue_card.short_description = '✓ Выдать карту (активировать)'

    def revoke_card(self, request, queryset):
        """Деактивировать карту (пользователь не сможет использовать QR для входа).
        
        QR файл остаётся в хранилище, но карта не активна.
        """
        count = queryset.count()
        for user in queryset:
            user.card_active = False
            user.save()
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
            # Удаляем старый QR из S3
            try:
                old_key = f'media/cards/{user.permanent_id}.png'
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
        
        # Удаляем старый QR из S3
        if old_id:
            try:
                old_key = f'media/cards/{old_id}.png'
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