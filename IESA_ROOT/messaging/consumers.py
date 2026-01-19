"""
Messaging WebSocket Consumer v3.0
Real-time чат с поддержкой:
- Отправка/получение сообщений
- Индикатор печати
- Статус прочтения
- Отправка файлов
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from asgiref.sync import sync_to_async


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer для чата.
    Обрабатывает real-time сообщения, typing indicators, и статус прочтения.
    """
    
    async def connect(self):
        """Подключение к чату"""
        self.chat_id = self.scope['url_route']['kwargs']['chat_id']
        self.room_group_name = f'chat_{self.chat_id}'
        self.user = self.scope['user']
        
        # Проверка авторизации
        if not self.user.is_authenticated:
            await self.close(code=4001)
            return
        
        # Проверка доступа к чату
        has_access = await self.check_chat_access()
        if not has_access:
            await self.close(code=4003)
            return
        
        # Присоединяемся к группе чата
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Отправляем информацию о подключении
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'chat_id': int(self.chat_id),
            'user_id': self.user.id,
            'username': self.user.username
        }))
    
    async def disconnect(self, close_code):
        """Отключение от чата"""
        # Очищаем статус печати
        await self.clear_typing_status()
        
        # Покидаем группу
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Получение сообщения от клиента"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'typing_start':
                await self.handle_typing_start()
            elif message_type == 'typing_stop':
                await self.handle_typing_stop()
            elif message_type == 'mark_read':
                await self.handle_mark_read(data)
            elif message_type == 'edit_message':
                await self.handle_edit_message(data)
            elif message_type == 'delete_message':
                await self.handle_delete_message(data)
            else:
                await self.send_error(f'Unknown message type: {message_type}')
        
        except json.JSONDecodeError:
            await self.send_error('Invalid JSON')
        except Exception as e:
            await self.send_error(str(e))
    
    # =========================================================================
    # MESSAGE HANDLERS
    # =========================================================================
    
    async def handle_chat_message(self, data):
        """Обработка нового сообщения"""
        text = data.get('text', '').strip()
        file_data = data.get('file')  # Base64 encoded file
        
        if not text and not file_data:
            await self.send_error('Message text or file required')
            return
        
        # Сохраняем сообщение в БД
        message = await self.save_message(text, file_data)
        
        if not message:
            await self.send_error('Failed to save message')
            return
        
        # Отправляем сообщение всем в группе
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message_broadcast',
                'message': {
                    'id': message['id'],
                    'text': message['text'],
                    'sender_id': message['sender_id'],
                    'sender_username': message['sender_username'],
                    'sender_avatar': message['sender_avatar'],
                    'created_at': message['created_at'],
                    'file_url': message.get('file_url'),
                    'file_name': message.get('file_name'),
                    'file_type': message.get('file_type'),
                }
            }
        )

        # Уведомляем собеседника о новом непрочитанном сообщении
        try:
            other_user_id = await self.get_other_user_id()
            # Если сообщение не от собеседника (то есть от текущего пользователя), увеличиваем счётчик у другого
            if other_user_id and other_user_id != self.user.id:
                await self.channel_layer.group_send(
                    f'user_{other_user_id}',
                    {
                        'type': 'unread_delta',
                        'delta': 1
                    }
                )
        except Exception:
            pass
        
        # Очищаем статус печати
        await self.clear_typing_status()
    
    async def handle_typing_start(self):
        """Начало печати"""
        await self.set_typing_status()
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_indicator',
                'user_id': self.user.id,
                'username': self.user.username,
                'is_typing': True
            }
        )
    
    async def handle_typing_stop(self):
        """Конец печати"""
        await self.clear_typing_status()
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_indicator',
                'user_id': self.user.id,
                'username': self.user.username,
                'is_typing': False
            }
        )
    
    async def handle_mark_read(self, data):
        """Отметить сообщения как прочитанные"""
        message_ids = data.get('message_ids', [])
        
        if message_ids:
            await self.mark_messages_read(message_ids)
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'messages_read',
                    'user_id': self.user.id,
                    'message_ids': message_ids
                }
            )

            # Уменьшаем счётчик непрочитанных у текущего пользователя
            try:
                await self.channel_layer.group_send(
                    f'user_{self.user.id}',
                    {
                        'type': 'unread_delta',
                        'delta': -len(message_ids)
                    }
                )
            except Exception:
                pass
    
    async def handle_edit_message(self, data):
        """Редактирование сообщения"""
        message_id = data.get('message_id')
        new_text = data.get('text', '').strip()
        
        if not message_id or not new_text:
            await self.send_error('Message ID and text required')
            return
        
        success = await self.edit_message(message_id, new_text)
        
        if success:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'message_edited',
                    'message_id': message_id,
                    'text': new_text,
                    'edited_at': timezone.now().isoformat()
                }
            )
        else:
            await self.send_error('Cannot edit message')
    
    async def handle_delete_message(self, data):
        """Удаление сообщения"""
        message_id = data.get('message_id')
        
        if not message_id:
            await self.send_error('Message ID required')
            return
        
        success = await self.delete_message(message_id)
        
        if success:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'message_deleted',
                    'message_id': message_id
                }
            )
        else:
            await self.send_error('Cannot delete message')
    
    # =========================================================================
    # BROADCAST HANDLERS (receive from group)
    # =========================================================================
    
    async def chat_message_broadcast(self, event):
        """Отправка сообщения клиенту"""
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'message': event['message']
        }))
    
    async def typing_indicator(self, event):
        """Отправка индикатора печати"""
        # Не отправляем себе
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user_id': event['user_id'],
                'username': event['username'],
                'is_typing': event['is_typing']
            }))
    
    async def messages_read(self, event):
        """Отправка статуса прочтения"""
        await self.send(text_data=json.dumps({
            'type': 'messages_read',
            'user_id': event['user_id'],
            'message_ids': event['message_ids']
        }))
    
    async def message_edited(self, event):
        """Отправка уведомления о редактировании"""
        await self.send(text_data=json.dumps({
            'type': 'message_edited',
            'message_id': event['message_id'],
            'text': event['text'],
            'edited_at': event['edited_at']
        }))
    
    async def message_deleted(self, event):
        """Отправка уведомления об удалении"""
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id']
        }))
    
    async def chat_message_event(self, event):
        """Обработка события от REST API (загрузка файла)"""
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))
    
    # =========================================================================
    # DATABASE OPERATIONS
    # =========================================================================
    
    @database_sync_to_async
    def check_chat_access(self):
        """Проверка доступа к чату"""
        from .models import Chat
        try:
            chat = Chat.objects.get(pk=self.chat_id)
            return chat.user1_id == self.user.id or chat.user2_id == self.user.id
        except Chat.DoesNotExist:
            return False
    
    @database_sync_to_async
    def save_message(self, text, file_data=None):
        """Сохранение сообщения в БД"""
        from .models import Chat, Message
        import base64
        from django.core.files.base import ContentFile
        
        try:
            chat = Chat.objects.get(pk=self.chat_id)
            
            message = Message(
                chat=chat,
                sender=self.user,
                text=text
            )
            
            # Обработка файла (base64)
            if file_data:
                file_content = file_data.get('content')
                file_name = file_data.get('name', 'file')
                if file_content:
                    # Декодируем base64
                    format_str, imgstr = file_content.split(';base64,')
                    decoded = base64.b64decode(imgstr)
                    message.file.save(file_name, ContentFile(decoded), save=False)
                    message.file_name = file_name
            
            message.save()
            
            # Получаем URL аватара
            avatar_url = None
            if hasattr(self.user, 'avatar') and self.user.avatar:
                try:
                    avatar_url = self.user.avatar.url
                except:
                    pass
            
            return {
                'id': message.id,
                'text': message.text,
                'sender_id': self.user.id,
                'sender_username': self.user.username,
                'sender_avatar': avatar_url,
                'created_at': message.created_at.isoformat(),
                'file_url': message.file.url if message.file else None,
                'file_name': message.file_name,
                'file_type': message.file_type,
            }
        except Exception as e:
            print(f"Error saving message: {e}")
            return None
    
    @database_sync_to_async
    def set_typing_status(self):
        """Установить статус печати"""
        from .models import Chat, TypingStatus
        try:
            chat = Chat.objects.get(pk=self.chat_id)
            TypingStatus.set_typing(chat, self.user)
        except:
            pass
    
    @database_sync_to_async
    def clear_typing_status(self):
        """Очистить статус печати"""
        from .models import Chat, TypingStatus
        try:
            chat = Chat.objects.get(pk=self.chat_id)
            TypingStatus.clear_typing(chat, self.user)
        except:
            pass
    
    @database_sync_to_async
    def mark_messages_read(self, message_ids):
        """Отметить сообщения как прочитанные"""
        from .models import Message
        Message.objects.filter(
            id__in=message_ids,
            chat_id=self.chat_id,
            is_read=False
        ).exclude(sender=self.user).update(
            is_read=True,
            read_at=timezone.now()
        )

    @database_sync_to_async
    def get_other_user_id(self):
        """Возвращает ID собеседника по чату"""
        from .models import Chat
        try:
            chat = Chat.objects.get(pk=self.chat_id)
            return chat.user2_id if chat.user1_id == self.user.id else chat.user1_id
        except Chat.DoesNotExist:
            return None
    
    @database_sync_to_async
    def edit_message(self, message_id, new_text):
        """Редактирование сообщения"""
        from .models import Message
        try:
            message = Message.objects.get(
                pk=message_id,
                chat_id=self.chat_id,
                sender=self.user,
                is_deleted=False
            )
            message.edit(new_text)
            return True
        except Message.DoesNotExist:
            return False
    
    @database_sync_to_async
    def delete_message(self, message_id):
        """Удаление сообщения"""
        from .models import Message
        try:
            message = Message.objects.get(
                pk=message_id,
                chat_id=self.chat_id,
                sender=self.user,
                is_deleted=False
            )
            message.soft_delete()
            return True
        except Message.DoesNotExist:
            return False
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    async def send_error(self, message):
        """Отправка ошибки клиенту"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))


class NotificationsConsumer(AsyncWebsocketConsumer):
    """Уведомления пользователя: непрочитанные сообщения (значок в navbar)."""

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close(code=4001)
            return

        self.user_group = f'user_{self.user.id}'
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

        # Отправляем начальный счётчик (защита от расхождений)
        try:
            count = await self.get_unread_count()
            await self.send(text_data=json.dumps({'type': 'unread_set', 'count': count}))
        except Exception:
            await self.send(text_data=json.dumps({'type': 'unread_set', 'count': 0}))

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def unread_delta(self, event):
        # Пробрасываем изменение счётчика на клиента
        await self.send(text_data=json.dumps({'type': 'unread_delta', 'delta': event.get('delta', 0)}))

    @database_sync_to_async
    def get_unread_count(self):
        from .models import Message
        from django.db.models import Q
        return Message.objects.filter(
            Q(chat__user1=self.user) | Q(chat__user2=self.user),
            is_read=False,
            is_deleted=False
        ).exclude(sender=self.user).count()
