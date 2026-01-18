"""
Messaging API Views v3.0
REST API для чатов с поддержкой поиска и файлов
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Max
from django.utils import timezone
from django.core.paginator import Paginator
import json
import logging

from .models import Chat, Message, TypingStatus
from users.models import User

logger = logging.getLogger(__name__)


# ============================================================================
# HELPERS
# ============================================================================

def api_response(success=True, message='OK', data=None, status=200):
    """Стандартный формат ответа API"""
    return JsonResponse({
        'success': success,
        'message': message,
        'data': data or {}
    }, status=status)


def api_error(message, status=400):
    """Ответ с ошибкой"""
    return api_response(success=False, message=message, status=status)


# ============================================================================
# CHAT LIST API
# ============================================================================

@login_required
@require_http_methods(['GET'])
def api_chat_list(request):
    """
    Получить список чатов пользователя
    GET /messages/api/chats/
    Query params:
        - search: поиск по имени собеседника
        - page: страница (default 1)
        - per_page: чатов на странице (default 20)
    """
    try:
        user = request.user
        search = request.GET.get('search', '').strip()
        page = int(request.GET.get('page', 1))
        per_page = min(int(request.GET.get('per_page', 20)), 50)
        
        # Базовый запрос
        chats = Chat.get_user_chats(user).annotate(
            unread_count=Count(
                'messages',
                filter=Q(messages__is_read=False, messages__is_deleted=False) & ~Q(messages__sender=user)
            )
        )
        
        # Поиск по имени собеседника
        if search:
            chats = chats.filter(
                Q(user1__username__icontains=search) |
                Q(user1__first_name__icontains=search) |
                Q(user1__last_name__icontains=search) |
                Q(user2__username__icontains=search) |
                Q(user2__first_name__icontains=search) |
                Q(user2__last_name__icontains=search)
            )
        
        chats = chats.order_by('-updated_at')
        
        # Пагинация
        paginator = Paginator(chats, per_page)
        page_obj = paginator.get_page(page)
        
        # Формируем ответ
        chat_list = []
        for chat in page_obj:
            other_user = chat.get_other_user(user)
            
            # Аватар
            avatar_url = None
            if hasattr(other_user, 'avatar') and other_user.avatar:
                try:
                    avatar_url = other_user.avatar.url
                except:
                    pass
            
            chat_list.append({
                'id': chat.id,
                'other_user': {
                    'id': other_user.id,
                    'username': other_user.username,
                    'name': other_user.get_full_name() or other_user.username,
                    'avatar': avatar_url,
                },
                'last_message': chat.last_message_text or None,
                'last_message_at': chat.last_message_at.isoformat() if chat.last_message_at else None,
                'unread_count': chat.unread_count,
                'updated_at': chat.updated_at.isoformat(),
            })
        
        return api_response(data={
            'chats': chat_list,
            'total': paginator.count,
            'page': page,
            'pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_prev': page_obj.has_previous(),
        })
    
    except Exception as e:
        logger.exception("Error in api_chat_list")
        return api_error(str(e), status=500)


@login_required
@require_http_methods(['GET'])
def api_unread_count(request):
    """
    Получить общее количество непрочитанных сообщений
    GET /messages/api/unread-count/
    """
    try:
        user = request.user
        
        count = Message.objects.filter(
            Q(chat__user1=user) | Q(chat__user2=user),
            is_read=False,
            is_deleted=False
        ).exclude(sender=user).count()
        
        return api_response(data={'count': count})
    
    except Exception as e:
        logger.exception("Error in api_unread_count")
        return api_error(str(e), status=500)


# ============================================================================
# CHAT DETAIL / MESSAGES API
# ============================================================================

@login_required
@require_http_methods(['GET'])
def api_chat_messages(request, chat_id):
    """
    Получить сообщения чата
    GET /messages/api/chats/<chat_id>/messages/
    Query params:
        - page: страница (default 1)
        - per_page: сообщений на странице (default 50)
        - before_id: загрузить сообщения до этого ID (для бесконечного скролла)
    """
    try:
        user = request.user
        
        # Проверка доступа
        chat = get_object_or_404(Chat, pk=chat_id)
        if chat.user1_id != user.id and chat.user2_id != user.id:
            return api_error('Access denied', status=403)
        
        page = int(request.GET.get('page', 1))
        per_page = min(int(request.GET.get('per_page', 50)), 100)
        before_id = request.GET.get('before_id')
        
        # Базовый запрос
        messages = Message.objects.filter(
            chat=chat,
            is_deleted=False
        ).select_related('sender')
        
        # Фильтр для бесконечного скролла
        if before_id:
            messages = messages.filter(id__lt=int(before_id))
        
        messages = messages.order_by('-created_at')
        
        # Пагинация
        paginator = Paginator(messages, per_page)
        page_obj = paginator.get_page(page)
        
        # Отмечаем сообщения как прочитанные
        unread_ids = [
            m.id for m in page_obj 
            if not m.is_read and m.sender_id != user.id
        ]
        if unread_ids:
            Message.objects.filter(id__in=unread_ids).update(
                is_read=True,
                read_at=timezone.now()
            )
        
        # Формируем ответ
        message_list = []
        for msg in page_obj:
            # Аватар отправителя
            avatar_url = None
            if hasattr(msg.sender, 'avatar') and msg.sender.avatar:
                try:
                    avatar_url = msg.sender.avatar.url
                except:
                    pass
            
            message_list.append({
                'id': msg.id,
                'text': msg.text,
                'sender': {
                    'id': msg.sender.id,
                    'username': msg.sender.username,
                    'name': msg.sender.get_full_name() or msg.sender.username,
                    'avatar': avatar_url,
                },
                'is_own': msg.sender_id == user.id,
                'is_read': msg.is_read,
                'created_at': msg.created_at.isoformat(),
                'edited_at': msg.edited_at.isoformat() if msg.edited_at else None,
                'file_url': msg.file.url if msg.file else None,
                'file_name': msg.file_name or None,
                'file_type': msg.file_type or None,
            })
        
        # Реверсируем для правильного порядка (старые сверху)
        message_list.reverse()
        
        # Информация о собеседнике
        other_user = chat.get_other_user(user)
        other_avatar = None
        if hasattr(other_user, 'avatar') and other_user.avatar:
            try:
                other_avatar = other_user.avatar.url
            except:
                pass
        
        return api_response(data={
            'messages': message_list,
            'chat': {
                'id': chat.id,
                'other_user': {
                    'id': other_user.id,
                    'username': other_user.username,
                    'name': other_user.get_full_name() or other_user.username,
                    'avatar': other_avatar,
                }
            },
            'total': paginator.count,
            'page': page,
            'pages': paginator.num_pages,
            'has_more': page_obj.has_next(),
        })
    
    except Exception as e:
        logger.exception("Error in api_chat_messages")
        return api_error(str(e), status=500)


# ============================================================================
# CREATE CHAT / SEND MESSAGE API
# ============================================================================

@login_required
@require_http_methods(['POST'])
def api_create_chat(request):
    """
    Создать чат с пользователем или получить существующий
    POST /messages/api/chats/create/
    Body: { "user_id": 123 }
    """
    try:
        data = json.loads(request.body)
        other_user_id = data.get('user_id')
        
        if not other_user_id:
            return api_error('user_id required')
        
        # Нельзя создать чат с самим собой
        if other_user_id == request.user.id:
            return api_error('Cannot create chat with yourself')
        
        # Получаем пользователя
        try:
            other_user = User.objects.get(pk=other_user_id, is_active=True)
        except User.DoesNotExist:
            return api_error('User not found', status=404)
        
        # Создаём или получаем чат
        chat, created = Chat.get_or_create_chat(request.user, other_user)
        
        return api_response(data={
            'chat_id': chat.id,
            'created': created,
            'other_user': {
                'id': other_user.id,
                'username': other_user.username,
                'name': other_user.get_full_name() or other_user.username,
            }
        })
    
    except json.JSONDecodeError:
        return api_error('Invalid JSON')
    except Exception as e:
        logger.exception("Error in api_create_chat")
        return api_error(str(e), status=500)


@login_required
@require_http_methods(['POST'])
def api_send_message(request, chat_id):
    """
    Отправить сообщение в чат (с поддержкой файлов)
    POST /messages/api/chats/<chat_id>/send/
    Body: FormData with text and/or file
    """
    try:
        user = request.user
        
        # Проверка доступа
        chat = get_object_or_404(Chat, pk=chat_id)
        if chat.user1_id != user.id and chat.user2_id != user.id:
            return api_error('Access denied', status=403)
        
        # Проверяем тип данных (FormData или JSON)
        content_type = request.content_type or ''
        
        if 'multipart/form-data' in content_type:
            # FormData с файлом
            text = request.POST.get('text', '').strip()
            file = request.FILES.get('file')
        else:
            # JSON
            try:
                data = json.loads(request.body)
                text = data.get('text', '').strip()
                file = None
            except json.JSONDecodeError:
                return api_error('Invalid JSON')
        
        if not text and not file:
            return api_error('Message text or file required')
        
        # Создаём сообщение
        message = Message.objects.create(
            chat=chat,
            sender=user,
            text=text,
            file=file
        )
        
        # Аватар
        avatar_url = None
        if hasattr(user, 'avatar') and user.avatar:
            try:
                avatar_url = user.avatar.url
            except:
                pass
        
        # URL файла
        file_url = None
        if message.file:
            try:
                file_url = message.file.url
            except:
                pass
        
        # Broadcast через channels (если настроен)
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'chat_{chat_id}',
                    {
                        'type': 'chat_message_event',
                        'message': {
                            'id': message.id,
                            'text': message.text,
                            'file_url': file_url,
                            'sender_id': user.id,
                            'sender_name': user.get_full_name() or user.username,
                            'sender_avatar': avatar_url,
                            'is_read': False,
                            'created_at': message.created_at.isoformat(),
                        }
                    }
                )
        except Exception as e:
            logger.warning(f"Could not broadcast message: {e}")
        
        return api_response(data={
            'message': {
                'id': message.id,
                'text': message.text,
                'file_url': file_url,
                'sender': {
                    'id': user.id,
                    'username': user.username,
                    'avatar': avatar_url,
                },
                'is_own': True,
                'created_at': message.created_at.isoformat(),
            }
        })
    
    except Exception as e:
        logger.exception("Error in api_send_message")
        return api_error(str(e), status=500)


# ============================================================================
# SEARCH API
# ============================================================================

@login_required
@require_http_methods(['GET'])
def api_search_users(request):
    """
    Поиск пользователей для создания чата
    GET /messages/api/users/search/?q=...
    """
    try:
        q = request.GET.get('q', '').strip()
        limit = min(int(request.GET.get('limit', 10)), 30)
        
        if not q or len(q) < 2:
            return api_response(data={'users': []})
        
        users = User.objects.filter(
            is_active=True
        ).exclude(pk=request.user.pk).filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q)
        )[:limit]
        
        user_list = []
        for u in users:
            avatar_url = None
            if hasattr(u, 'avatar') and u.avatar:
                try:
                    avatar_url = u.avatar.url
                except:
                    pass
            
            user_list.append({
                'id': u.id,
                'username': u.username,
                'name': u.get_full_name() or u.username,
                'avatar': avatar_url,
            })
        
        return api_response(data={'users': user_list})
    
    except Exception as e:
        logger.exception("Error in api_search_users")
        return api_error(str(e), status=500)


@login_required
@require_http_methods(['GET'])
def api_search_messages(request):
    """
    Поиск по сообщениям
    GET /messages/api/messages/search/?q=...
    """
    try:
        user = request.user
        q = request.GET.get('q', '').strip()
        chat_id = request.GET.get('chat_id')
        limit = min(int(request.GET.get('limit', 20)), 50)
        
        if not q or len(q) < 2:
            return api_response(data={'messages': []})
        
        # Базовый запрос
        messages = Message.objects.filter(
            Q(chat__user1=user) | Q(chat__user2=user),
            is_deleted=False,
            text__icontains=q
        ).select_related('sender', 'chat')
        
        # Фильтр по конкретному чату
        if chat_id:
            messages = messages.filter(chat_id=chat_id)
        
        messages = messages.order_by('-created_at')[:limit]
        
        result = []
        for msg in messages:
            other_user = msg.chat.get_other_user(user)
            
            result.append({
                'id': msg.id,
                'text': msg.text,
                'chat_id': msg.chat_id,
                'chat_name': other_user.get_full_name() or other_user.username,
                'sender': msg.sender.username,
                'created_at': msg.created_at.isoformat(),
            })
        
        return api_response(data={'messages': result})
    
    except Exception as e:
        logger.exception("Error in api_search_messages")
        return api_error(str(e), status=500)


# ============================================================================
# PAGE VIEWS
# ============================================================================

@login_required
def chat_list_view(request):
    """Страница списка чатов"""
    return render(request, 'messaging/chat_list.html')


@login_required
def chat_detail_view(request, chat_id):
    """Страница конкретного чата"""
    user = request.user
    
    chat = get_object_or_404(Chat, pk=chat_id)
    if chat.user1_id != user.id and chat.user2_id != user.id:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied')
    
    other_user = chat.get_other_user(user)
    
    context = {
        'chat': chat,
        'other_user': other_user,
    }
    return render(request, 'messaging/chat_detail.html', context)


@login_required
def start_chat_view(request, user_id):
    """Начать чат с пользователем (редирект на существующий или новый)"""
    from django.shortcuts import redirect
    
    try:
        other_user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        from django.http import Http404
        raise Http404('User not found')
    
    if other_user.id == request.user.id:
        return redirect('messaging:chat_list')
    
    chat, created = Chat.get_or_create_chat(request.user, other_user)
    return redirect('messaging:chat_detail', chat_id=chat.id)

