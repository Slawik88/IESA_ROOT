"""
Messaging System - Complete Rewrite (v2.0)
Architecture: Clean separation of concerns, proper error handling, no silent failures
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.db.models import Q, Prefetch, Count, Case, When, Value, CharField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.middleware.csrf import get_token
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from functools import wraps
import json
import logging

from .models import Conversation, Message, TypingIndicator
from users.models import User
from .forms import ConversationForm

logger = logging.getLogger(__name__)


# ============================================================================
# DECORATORS & UTILITIES
# ============================================================================

def api_response(success=True, message=None, data=None, status=200):
    """Standard API response format"""
    response = {
        'success': success,
        'message': message or ('OK' if success else 'Error'),
        'data': data or {}
    }
    return JsonResponse(response, status=status)


def api_error(message, status=400, data=None):
    """Standard error response"""
    return api_response(success=False, message=message, status=status, data=data)


def ensure_conversation_access(view_func):
    """Decorator to ensure user has access to conversation"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        conversation_id = kwargs.get('conversation_id') or kwargs.get('pk')
        if not conversation_id:
            return api_error('Conversation ID required', status=400)
        
        try:
            conversation = Conversation.objects.get(pk=conversation_id)
        except Conversation.DoesNotExist:
            return api_error('Conversation not found', status=404)
        
        if not conversation.participants.filter(pk=request.user.pk).exists():
            logger.warning(f"User {request.user.pk} tried to access conversation {conversation_id}")
            return api_error('Access denied', status=403)
        
        kwargs['conversation'] = conversation
        return view_func(request, *args, **kwargs)
    
    return wrapper


def ensure_message_access(view_func):
    """Decorator to ensure user has access to message"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        message_id = kwargs.get('message_id') or kwargs.get('pk')
        if not message_id:
            return api_error('Message ID required', status=400)
        
        try:
            message = Message.objects.get(pk=message_id)
        except Message.DoesNotExist:
            return api_error('Message not found', status=404)
        
        # Check if user is participant in the conversation
        if not message.conversation.participants.filter(pk=request.user.pk).exists():
            logger.warning(f"User {request.user.pk} tried to access message {message_id}")
            return api_error('Access denied', status=403)
        
        kwargs['message'] = message
        return view_func(request, *args, **kwargs)
    
    return wrapper


# ============================================================================
# API ENDPOINTS - CONVERSATIONS
# ============================================================================

@login_required
@require_http_methods(["GET"])
def api_get_conversations(request):
    """
    Get list of conversations for current user
    Query params:
        - limit: max results (default 20)
        - offset: pagination offset (default 0)
    """
    try:
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))
        
        # Limit bounds
        limit = min(max(limit, 1), 100)
        
        # Get conversations with optimized queries
        conversations = Conversation.objects.filter(
            participants=request.user
        ).prefetch_related(
            Prefetch(
                'messages',
                queryset=Message.objects.filter(
                    is_deleted=False
                ).select_related('sender').order_by('-created_at')[:1],
                to_attr='last_message_list'
            ),
            'participants'
        ).annotate(
            unread_count=Count(
                'messages',
                filter=Q(
                    messages__is_deleted=False,
                    messages__sender__ne=request.user
                ) & ~Q(messages__read_by=request.user)
            )
        ).order_by('-updated_at')[offset:offset + limit]
        
        # Build response
        data = {
            'conversations': [],
            'total': Conversation.objects.filter(participants=request.user).count(),
            'offset': offset,
            'limit': limit
        }
        
        for conv in conversations:
            # Get last message
            last_msg = conv.last_message_list[0] if conv.last_message_list else None
            
            # Get other participant for 1-to-1 chats
            other_participant = None
            if not conv.is_group:
                other_participant = conv.participants.exclude(pk=request.user.pk).first()
            
            conv_data = {
                'id': conv.pk,
                'is_group': conv.is_group,
                'group_name': conv.group_name,
                'created_at': conv.created_at.isoformat(),
                'updated_at': conv.updated_at.isoformat(),
                'unread_count': conv.unread_count,
                'last_message': {
                    'text': last_msg.text[:100] if last_msg else '',
                    'sender': last_msg.sender.username if last_msg else '',
                    'sent_at': last_msg.created_at.isoformat() if last_msg else '',
                } if last_msg else None,
                'participants': [
                    {'id': p.pk, 'username': p.username, 'name': p.get_full_name()}
                    for p in conv.participants.all()
                ],
                'other_participant': {
                    'id': other_participant.pk,
                    'username': other_participant.username,
                    'name': other_participant.get_full_name()
                } if other_participant else None
            }
            data['conversations'].append(conv_data)
        
        return api_response(data=data)
    
    except ValueError as e:
        return api_error(f'Invalid parameter: {str(e)}', status=400)
    except Exception as e:
        logger.exception(f"Error fetching conversations for user {request.user.pk}")
        return api_error('Server error', status=500)


@login_required
@require_http_methods(["GET"])
@ensure_conversation_access
def api_get_messages(request, conversation_id=None, conversation=None):
    """
    Get messages for a conversation
    Query params:
        - limit: max results (default 20)
        - offset: pagination offset (default 0)
        - before_id: get messages before this ID (for infinite scroll)
    """
    try:
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))
        before_id = request.GET.get('before_id')
        
        limit = min(max(limit, 1), 100)
        
        # Base query
        query = Message.objects.filter(
            conversation=conversation,
            is_deleted=False
        ).select_related('sender').prefetch_related('read_by')
        
        # If before_id provided, get older messages
        if before_id:
            try:
                before_msg = Message.objects.get(pk=before_id)
                query = query.filter(created_at__lt=before_msg.created_at)
            except Message.DoesNotExist:
                pass
        
        total = query.count()
        # Evaluate slice to list so we can safely iterate and mark read
        messages = list(query.order_by('-created_at')[offset:offset + limit])
        
        # Mark as read (only non-sender messages, avoid re-filtering sliced QS)
        for msg in messages:
            if msg.sender_id != request.user.id and not msg.read_by.filter(pk=request.user.pk).exists():
                msg.read_by.add(request.user)
        
        data = {
            'messages': [],
            'total': total,
            'offset': offset,
            'limit': limit,
            'conversation_id': conversation.pk
        }
        
        for msg in messages:
            msg_data = {
                'id': msg.pk,
                'text': msg.text,
                'sender': {
                    'id': msg.sender.pk,
                    'username': msg.sender.username
                },
                'created_at': msg.created_at.isoformat(),
                'edited_at': msg.edited_at.isoformat() if msg.edited_at else None,
                'is_pinned': msg.is_pinned,
                'is_own_message': msg.sender.pk == request.user.pk,
                'read_by_count': msg.read_by.count() - (1 if msg.sender in msg.read_by.all() else 0),
            }
            data['messages'].append(msg_data)
        
        return api_response(data=data)
    
    except ValueError as e:
        return api_error(f'Invalid parameter: {str(e)}', status=400)
    except Exception as e:
        logger.exception(f"Error fetching messages for conversation {conversation_id}")
        return api_error('Server error', status=500)


# ============================================================================
# API ENDPOINTS - SEARCH
# ============================================================================

@login_required
@require_http_methods(["GET"])
def api_search_users(request):
    """
    Search for users to start a conversation
    Query params:
        - q: search query (username, first_name, last_name)
        - limit: max results (default 10)
    """
    try:
        q = request.GET.get('q', '').strip()
        limit = int(request.GET.get('limit', 10))
        
        if not q:
            return api_response(data={'users': []})
        
        limit = min(max(limit, 1), 50)
        
        # Search in username, first_name, last_name
        users = User.objects.filter(
            is_active=True
        ).exclude(pk=request.user.pk).filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q)
        )[:limit]
        
        data = {
            'users': [
                {
                    'id': u.pk,
                    'username': u.username,
                    'name': u.get_full_name() or u.username,
                    'avatar': str(u.avatar.url) if u.avatar else None
                }
                for u in users
            ]
        }
        
        return api_response(data=data)
    
    except ValueError as e:
        return api_error(f'Invalid parameter: {str(e)}', status=400)
    except Exception as e:
        logger.exception(f"Error searching users")
        return api_error('Server error', status=500)


# ============================================================================
# API ENDPOINTS - MESSAGE OPERATIONS
# ============================================================================

@login_required
@require_http_methods(["POST"])
@ensure_conversation_access
def api_send_message(request, conversation_id=None, conversation=None):
    """
    Send a message to a conversation
    POST data:
        - text: message text (required)
        - file: attached file (optional)
    """
    try:
        data = json.loads(request.body)
        text = data.get('text', '').strip()
        
        if not text and not request.FILES.get('file'):
            return api_error('Message text or file required', status=400)
        
        # Create message
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            text=text
        )
        
        # Handle file if provided
        if request.FILES.get('file'):
            message.file = request.FILES['file']
            message.save()
        
        # Update conversation timestamp
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])
        
        msg_data = {
            'id': message.pk,
            'text': message.text,
            'sender': {
                'id': message.sender.pk,
                'username': message.sender.username
            },
            'created_at': message.created_at.isoformat(),
            'is_own_message': True
        }
        
        return api_response(data={'message': msg_data})
    
    except json.JSONDecodeError:
        return api_error('Invalid JSON', status=400)
    except Exception as e:
        logger.exception(f"Error sending message")
        return api_error('Server error', status=500)


@login_required
@require_http_methods(["POST"])
@ensure_message_access
def api_edit_message(request, message_id=None, message=None):
    """
    Edit a message (only sender can edit)
    POST data:
        - text: new message text (required)
    """
    try:
        # Only sender can edit
        if message.sender.pk != request.user.pk:
            return api_error('Only sender can edit', status=403)
        
        data = json.loads(request.body)
        text = data.get('text', '').strip()
        
        if not text:
            return api_error('Message text required', status=400)
        
        message.text = text
        message.edited_at = timezone.now()
        message.save()
        
        return api_response(message='Message edited')
    
    except json.JSONDecodeError:
        return api_error('Invalid JSON', status=400)
    except Exception as e:
        logger.exception(f"Error editing message")
        return api_error('Server error', status=500)


@login_required
@require_http_methods(["POST"])
@ensure_message_access
def api_delete_message(request, message_id=None, message=None):
    """
    Delete a message (only sender can delete)
    POST data:
        - for_everyone: delete for all participants (default False, only for sender)
    """
    try:
        # Only sender can delete
        if message.sender.pk != request.user.pk:
            return api_error('Only sender can delete', status=403)
        
        data = json.loads(request.body) if request.body else {}
        for_everyone = data.get('for_everyone', False)
        
        if for_everyone:
            message.deleted_for_everyone = True
            message.is_deleted = True
        else:
            message.is_deleted = True
        
        message.save()
        return api_response(message='Message deleted')
    
    except json.JSONDecodeError:
        return api_error('Invalid JSON', status=400)
    except Exception as e:
        logger.exception(f"Error deleting message")
        return api_error('Server error', status=500)


@login_required
@require_http_methods(["POST"])
@ensure_message_access
def api_mark_read(request, message_id=None, message=None):
    """
    Mark message as read
    """
    try:
        if message.sender.pk != request.user.pk:
            message.read_by.add(request.user)
        
        return api_response(message='Message marked as read')
    
    except Exception as e:
        logger.exception(f"Error marking message read")
        return api_error('Server error', status=500)


# ============================================================================
# API ENDPOINTS - CREATE CONVERSATIONS
# ============================================================================

@login_required
@require_http_methods(["POST"])
def api_create_conversation(request):
    """
    Create a new 1-to-1 conversation
    POST data:
        - participant_id: ID of the other participant (required)
    """
    try:
        data = json.loads(request.body)
        participant_id = data.get('participant_id')
        
        if not participant_id:
            return api_error('participant_id required', status=400)
        
        try:
            participant = User.objects.get(pk=participant_id)
        except User.DoesNotExist:
            return api_error('User not found', status=404)
        
        # Check if conversation already exists
        conv = Conversation.objects.filter(
            is_group=False,
            participants=request.user
        ).filter(participants=participant).first()
        
        if conv:
            # Already exists, return it
            return api_response(data={
                'conversation_id': conv.pk,
                'created': False
            })
        
        # Create new conversation
        conv = Conversation.objects.create(
            creator=request.user,
            is_group=False
        )
        conv.participants.add(request.user, participant)
        
        return api_response(data={
            'conversation_id': conv.pk,
            'created': True
        })
    
    except json.JSONDecodeError:
        return api_error('Invalid JSON', status=400)
    except Exception as e:
        logger.exception(f"Error creating conversation")
        return api_error('Server error', status=500)


@login_required
@require_http_methods(["POST"])
def api_create_group(request):
    """
    Create a new group conversation
    POST data:
        - name: group name (required)
        - participant_ids: list of participant IDs (optional, creator always added)
    """
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        participant_ids = data.get('participant_ids', [])
        
        if not name:
            return api_error('Group name required', status=400)
        
        # Create group
        conv = Conversation.objects.create(
            creator=request.user,
            is_group=True,
            group_name=name
        )
        conv.participants.add(request.user)
        conv.admins.add(request.user)
        
        # Add participants
        for pid in participant_ids:
            try:
                participant = User.objects.get(pk=pid)
                conv.participants.add(participant)
            except (User.DoesNotExist, ValueError):
                pass
        
        return api_response(data={
            'conversation_id': conv.pk,
            'created': True
        })
    
    except json.JSONDecodeError:
        return api_error('Invalid JSON', status=400)
    except Exception as e:
        logger.exception(f"Error creating group")
        return api_error('Server error', status=500)


# ============================================================================
# UI VIEWS
# ============================================================================

@login_required
def inbox_view(request):
    """
    Main inbox view - shows conversation list and detail
    """
    context = {
        'csrf_token': get_token(request)
    }
    return render(request, 'messaging/inbox_v2.html', context)


@login_required
def conversation_detail_view(request, pk):
    """
    Conversation detail view
    """
    try:
        conversation = Conversation.objects.get(pk=pk)
        
        if not conversation.participants.filter(pk=request.user.pk).exists():
            return HttpResponseForbidden('Access denied')
        
        context = {
            'conversation': conversation,
            'csrf_token': get_token(request)
        }
        return render(request, 'messaging/conversation_v2.html', context)
    
    except Conversation.DoesNotExist:
        return HttpResponseForbidden('Conversation not found')
