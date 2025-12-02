from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User
from .forms import CustomUserCreationForm, CustomUserChangeForm
from django.utils.html import format_html
from django.conf import settings
import uuid
from .qr_utils import generate_qr_code_for_user
from django.utils import timezone

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
        ('Card QR', {'fields': ('permanent_id', 'card_qr', 'card_active', 'card_issued_at')}),
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
    
    readonly_fields = ('last_online', 'permanent_id', 'card_qr')

    actions = ['regenerate_permanent_id', 'issue_card', 'revoke_card']
    
    def card_qr(self, obj):
        """Вывести сгенерированный QR код из media/cards/.
        
        QR ведёт на /auth/card/<permanent_id>/ и хранится локально.
        """
        if not obj.permanent_id:
            return '-'
        # Путь к сохранённому QR коду
        qr_path = f"{settings.MEDIA_URL}cards/{str(obj.permanent_id)}.png"
        return format_html('<img src="{}" style="width:80px;height:80px;object-fit:contain;border:1px solid #ddd;border-radius:4px;"/>', qr_path)
    card_qr.short_description = 'Card QR'

    def regenerate_permanent_id(self, request, queryset):
        """Заново создать permanent_id для каждого пользователя и QR.
        
        Используется если пользователь потерял карту и нужна новая.
        """
        for user in queryset:
            user.permanent_id = uuid.uuid4()
            user.card_active = True
            user.card_issued_at = timezone.now()
            user.save()
            # Генерируем и сохраняем новый QR код
            generate_qr_code_for_user(user)
        self.message_user(request, f"Regenerated permanent_id for {queryset.count()} user(s)")
    regenerate_permanent_id.short_description = 'Regenerate permanent ID and issue new card'

    def issue_card(self, request, queryset):
        """Активировать карту и установить дату выдачи.
        
        Генерирует QR код если его ещё нет.
        """
        for user in queryset:
            user.card_active = True
            user.card_issued_at = timezone.now()
            user.save()
            # Если QR не был сгенерирован — генерируем
            generate_qr_code_for_user(user)
        self.message_user(request, f"Issued card for {queryset.count()} user(s)")
    issue_card.short_description = 'Mark card as issued (activate)'

    def revoke_card(self, request, queryset):
        """Деактивировать карту (пользователь не сможет использовать QR для входа).
        
        QR файл остаётся на диске, но карта не активна.
        """
        for user in queryset:
            user.card_active = False
            user.save()
        self.message_user(request, f"Revoked card for {queryset.count()} user(s)")
    revoke_card.short_description = 'Revoke physical card (deactivate)'


admin.site.register(User, UserAdmin)