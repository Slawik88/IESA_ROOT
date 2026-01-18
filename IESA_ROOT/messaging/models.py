"""
Messaging System v3.0 - Models
Чистая архитектура для личных чатов 1-на-1 с real-time через WebSocket
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid
import os


def message_file_path(instance, filename):
    """Генерация пути для файлов сообщений"""
    ext = filename.split('.')[-1]
    new_filename = f"{uuid.uuid4().hex}.{ext}"
    return os.path.join('chat_files', str(instance.chat.id), new_filename)


class Chat(models.Model):
    """
    Личный чат между двумя пользователями.
    Один чат = один уникальный разговор между user1 и user2.
    """
    # Участники чата (всегда 2 пользователя)
    user1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chats_as_user1'
    )
    user2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chats_as_user2'
    )
    
    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Кеш последнего сообщения для быстрой загрузки списка чатов
    last_message_text = models.CharField(max_length=255, blank=True, default='')
    last_message_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-updated_at']
        # Уникальная пара пользователей (независимо от порядка)
        constraints = [
            models.UniqueConstraint(
                fields=['user1', 'user2'],
                name='unique_chat_pair'
            )
        ]
        indexes = [
            models.Index(fields=['user1', 'updated_at']),
            models.Index(fields=['user2', 'updated_at']),
        ]
    
    def __str__(self):
        return f"Chat {self.id}: {self.user1.username} <-> {self.user2.username}"
    
    def get_other_user(self, user):
        """Получить собеседника"""
        return self.user2 if self.user1_id == user.id else self.user1
    
    def update_last_message(self, message):
        """Обновить кеш последнего сообщения"""
        self.last_message_text = message.text[:255] if message.text else '[File]'
        self.last_message_at = message.created_at
        self.save(update_fields=['last_message_text', 'last_message_at', 'updated_at'])
    
    @classmethod
    def get_or_create_chat(cls, user1, user2):
        """
        Получить или создать чат между двумя пользователями.
        Нормализует порядок пользователей для уникальности.
        """
        # Нормализуем порядок по ID
        if user1.id > user2.id:
            user1, user2 = user2, user1
        
        chat, created = cls.objects.get_or_create(
            user1=user1,
            user2=user2
        )
        return chat, created
    
    @classmethod
    def get_user_chats(cls, user):
        """Получить все чаты пользователя"""
        return cls.objects.filter(
            models.Q(user1=user) | models.Q(user2=user)
        ).select_related('user1', 'user2')


class Message(models.Model):
    """
    Сообщение в чате.
    Поддерживает текст, файлы, статус прочтения и редактирование.
    """
    chat = models.ForeignKey(
        Chat,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    
    # Контент
    text = models.TextField(blank=True, default='')
    file = models.FileField(upload_to=message_file_path, blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True, default='')
    file_type = models.CharField(max_length=50, blank=True, default='')  # image, document, etc.
    
    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    
    # Статус
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['chat', 'created_at']),
            models.Index(fields=['sender', 'created_at']),
            models.Index(fields=['chat', 'is_read']),
        ]
    
    def __str__(self):
        return f"Message {self.id} from {self.sender.username}"
    
    def mark_as_read(self):
        """Отметить как прочитанное"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
    
    def edit(self, new_text):
        """Редактировать сообщение"""
        self.text = new_text
        self.edited_at = timezone.now()
        self.save(update_fields=['text', 'edited_at'])
    
    def soft_delete(self):
        """Мягкое удаление"""
        self.is_deleted = True
        self.save(update_fields=['is_deleted'])
    
    def save(self, *args, **kwargs):
        # Определяем тип файла
        if self.file and not self.file_type:
            name = self.file.name.lower()
            if any(ext in name for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                self.file_type = 'image'
            elif any(ext in name for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']):
                self.file_type = 'document'
            else:
                self.file_type = 'file'
            
            if not self.file_name:
                self.file_name = os.path.basename(self.file.name)
        
        super().save(*args, **kwargs)
        
        # Обновляем кеш последнего сообщения в чате
        if not self.is_deleted:
            self.chat.update_last_message(self)


class TypingStatus(models.Model):
    """
    Индикатор печати пользователя в чате.
    Хранится временно, очищается через 5 секунд.
    """
    chat = models.ForeignKey(
        Chat,
        on_delete=models.CASCADE,
        related_name='typing_statuses'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    started_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['chat', 'user']
    
    def __str__(self):
        return f"{self.user.username} typing in chat {self.chat_id}"
    
    @classmethod
    def set_typing(cls, chat, user):
        """Установить статус печати"""
        obj, _ = cls.objects.update_or_create(
            chat=chat,
            user=user,
            defaults={'started_at': timezone.now()}
        )
        return obj
    
    @classmethod
    def clear_typing(cls, chat, user):
        """Очистить статус печати"""
        cls.objects.filter(chat=chat, user=user).delete()
    
    @classmethod
    def get_typing_users(cls, chat, exclude_user=None):
        """Получить пользователей, которые печатают (за последние 5 секунд)"""
        threshold = timezone.now() - timezone.timedelta(seconds=5)
        qs = cls.objects.filter(chat=chat, started_at__gte=threshold)
        if exclude_user:
            qs = qs.exclude(user=exclude_user)
        return qs.select_related('user')
