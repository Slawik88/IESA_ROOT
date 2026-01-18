from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Q, Max, Count, Prefetch
from django.utils import timezone
from django.contrib import messages
from django.db.models.functions import Lower

from .models import Conversation, Message, TypingIndicator
from users.models import User
from .forms import ConversationForm
from . import typing_cache


class ConversationListView(LoginRequiredMixin, ListView):
    """Display list of user's conversations with unified inbox"""
    model = Conversation
    template_name = 'messaging/inbox.html'
    context_object_name = 'conversations'
    paginate_by = 20
    
    def get_queryset(self):
        return Conversation.objects.filter(
            participants=self.request.user
        ).prefetch_related(
            'participants',
            Prefetch('messages', queryset=Message.objects.filter(is_deleted=False).order_by('-created_at'), to_attr='recent_messages')
        ).annotate(
            unread_count=Count('messages', filter=~Q(messages__sender=self.request.user) & ~Q(messages__read_by=self.request.user))
        ).order_by('-updated_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['create_group_form'] = ConversationForm()
        
        # Add last message for each conversation
        for conversation in context['conversations']:
            # Use prefetched messages (recent_messages) - avoid N+1
            conversation.last_message = conversation.recent_messages[0] if conversation.recent_messages else None
            if not conversation.is_group:
                # Use prefetched participants - avoid N+1
                conversation.other_participant = next(
                    (p for p in conversation.participants.all() if p.pk != self.request.user.pk),
                    None
                )
        
        # Get active conversation from query param
        conversation_id = self.request.GET.get('conversation')
        if conversation_id:
            try:
                active_conv = Conversation.objects.filter(
                    pk=int(conversation_id),
                    participants=self.request.user
                ).prefetch_related('participants').first()
                
                if active_conv:
                    context['active_conversation'] = active_conv
                    
                    # Get messages for active conversation with read_by count annotation
                    # Show messages that are: not deleted OR (deleted but sent by current user and not deleted for everyone)
                    messages_qs = active_conv.messages.filter(
                        Q(is_deleted=False) | (Q(sender=self.request.user) & Q(deleted_for_everyone=False))
                    ).select_related('sender').prefetch_related('read_by').annotate(
                        read_by_count=Count('read_by')
                    ).order_by('created_at')
                    
                    context['messages'] = messages_qs
                    context['participants_count'] = active_conv.participants.count()
                    
                    # Mark messages as read - bulk operation
                    unread_messages = [msg for msg in messages_qs if msg.sender != self.request.user]
                    for msg in unread_messages:
                        msg.read_by.add(self.request.user)
            except (ValueError, TypeError):
                pass
        
        # Get available users for new chat
        context['available_users'] = User.objects.filter(is_active=True).exclude(pk=self.request.user.pk).order_by('username')[:50]
        
        return context


class ConversationDetailView(LoginRequiredMixin, DetailView):
    """Display a single conversation with messages"""
    model = Conversation
    template_name = 'messaging/conversation_detail.html'
    context_object_name = 'conversation'
    
    def get_queryset(self):
        return Conversation.objects.filter(
            participants=self.request.user
        ).prefetch_related('participants')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        conversation = self.object
        
        # Get messages with read_by count annotation
        # Show messages that are: not deleted OR (deleted but sent by current user and not deleted for everyone)
        messages_qs = conversation.messages.filter(
            Q(is_deleted=False) | (Q(sender=self.request.user) & Q(deleted_for_everyone=False))
        ).select_related('sender').prefetch_related('read_by').annotate(
            read_by_count=Count('read_by')
        ).order_by('created_at')
        
        context['messages'] = messages_qs
        context['other_participant'] = conversation.get_other_participant(self.request.user)
        context['is_admin'] = conversation.is_admin(self.request.user)
        context['is_creator'] = (conversation.creator_id == self.request.user.id)
        context['participants_count'] = conversation.participants.count()
        
        # Mark all messages as read - bulk operation
        unread_messages = [msg for msg in messages_qs if msg.sender != self.request.user]
        for msg in unread_messages:
            msg.read_by.add(self.request.user)
        
        return context


@login_required
def participants_panel(request, pk):
    """Return participants panel partial for a conversation (HTMX)."""
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related('participants', 'admins'),
        pk=pk,
        participants=request.user,
        is_group=True
    )
    return render(request, 'messaging/partials/participants_panel.html', {
        'conversation': conversation,
        'user': request.user,
        'is_admin': conversation.is_admin(request.user),
        'is_creator': (conversation.creator_id == request.user.id),
    })


@login_required
def start_conversation(request, username):
    """Start or get existing conversation with a user"""
    other_user = get_object_or_404(User, username=username)
    
    if other_user == request.user:
        messages.error(request, "You cannot message yourself.")
        return redirect('users:profile')
    
    # Check if conversation already exists
    conversation = Conversation.objects.filter(
        participants=request.user,
        is_group=False
    ).filter(
        participants=other_user
    ).first()
    
    # Create new conversation if doesn't exist
    if not conversation:
        conversation = Conversation.objects.create(is_group=False)
        conversation.participants.add(request.user, other_user)
    
    return redirect('messaging:conversation_detail', pk=conversation.pk)


@login_required
def create_group_conversation(request):
    """Create a new group conversation."""
    if request.method == 'POST':
        form = ConversationForm(request.POST)
        if form.is_valid():
            conv = Conversation.objects.create(is_group=True, group_name=form.cleaned_data['group_name'], creator=request.user)
            # Add current user and selected participants
            conv.participants.add(request.user)
            conv.participants.add(*form.cleaned_data['participants'])
            # Make creator admin
            conv.admins.add(request.user)
            from django.http import HttpResponseRedirect
            from django.urls import reverse
            url = reverse('messaging:conversation_list') + f'?conversation={conv.pk}'
            return HttpResponseRedirect(url)
    return HttpResponseForbidden()


@login_required
def create_conversation(request):
    """Create or get existing 1-on-1 conversation."""
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        if user_id:
            try:
                other_user = User.objects.get(pk=int(user_id), is_active=True)
                if other_user == request.user:
                    messages.error(request, "Нельзя создать чат с самим собой.")
                    return redirect('messaging:conversation_list')
                
                # Check if conversation exists
                conversation = Conversation.objects.filter(
                    participants=request.user,
                    is_group=False
                ).filter(
                    participants=other_user
                ).first()
                
                # Create if doesn't exist
                if not conversation:
                    conversation = Conversation.objects.create(is_group=False)
                    conversation.participants.add(request.user, other_user)
                
                from django.http import HttpResponseRedirect
                from django.urls import reverse
                url = reverse('messaging:conversation_list') + f'?conversation={conversation.pk}'
                return HttpResponseRedirect(url)
            except (User.DoesNotExist, ValueError):
                messages.error(request, "Пользователь не найден.")
                return redirect('messaging:conversation_list')
    
    return HttpResponseForbidden()


@login_required
def send_message(request, pk):
    """Send a message in a conversation"""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user)
    
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        file = request.FILES.get('file')
        
        # Validate: must have either text or file
        if not text and not file:
            return HttpResponseForbidden()
        
        # Create message (text can be empty if file is provided)
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            text=text  # Can be empty string if file is attached
        )
        
        if file:
            message.file = file
            message.save()
            
            # Mark sender as having read their own message
            message.read_by.add(request.user)
            
            # No need to save conversation - updated_at has auto_now=True
            
            if request.headers.get('HX-Request'):
                # Return message bubble for inbox view
                is_own = message.sender == request.user
                return render(request, 'messaging/partials/message_bubble.html', {
                    'message': message,
                    'is_own': is_own
                })
            
            from django.http import HttpResponseRedirect
            from django.urls import reverse
            url = reverse('messaging:conversation_list') + f'?conversation={conversation.pk}'
            return HttpResponseRedirect(url)
    
    return HttpResponseForbidden()


@login_required
def new_messages(request, pk):
    """Return new messages after given message id (HTMX)."""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user)
    after_id = request.GET.get('after')
    try:
        after_id = int(after_id or 0)
    except ValueError:
        after_id = 0

    qs = conversation.messages.filter(pk__gt=after_id).select_related('sender').prefetch_related('read_by').annotate(
        read_by_count=Count('read_by')
    ).order_by('created_at')

    if not qs.exists():
        return JsonResponse({'ok': True})

    # Mark as read for current user (incoming only) - bulk operation
    unread_messages = [msg for msg in qs if msg.sender != request.user]
    for msg in unread_messages:
        msg.read_by.add(request.user)

    return render(request, 'messaging/partials/messages_chunk.html', {
        'messages': qs,
        'user': request.user,
        'conversation': conversation,
        'participants_count': conversation.participants.count(),
    })


@login_required
def old_messages(request, pk):
    """Return older messages before given message id, prepend to list."""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user)
    before_id = request.GET.get('before')
    try:
        before_id = int(before_id or 0)
    except ValueError:
        before_id = 0

    if before_id <= 0:
        return JsonResponse({'ok': True})

    # Fetch up to 20 older messages
    qs = conversation.messages.filter(pk__lt=before_id).select_related('sender').prefetch_related('read_by').annotate(
        read_by_count=Count('read_by')
    ).order_by('-created_at')[:20]
    # Reverse to chronological order for prepend
    messages_list = list(qs)[::-1]
    if not messages_list:
        return JsonResponse({'ok': True})

    return render(request, 'messaging/partials/messages_chunk.html', {
        'messages': messages_list,
        'user': request.user,
        'conversation': conversation,
        'participants_count': conversation.participants.count(),
    })


@login_required
def old_remaining(request, pk):
    """Return count of older messages before given message id."""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user)
    before_id = request.GET.get('before')
    try:
        before_id = int(before_id or 0)
    except ValueError:
        before_id = 0

    if before_id <= 0:
        count = conversation.messages.count()
    else:
        count = conversation.messages.filter(pk__lt=before_id).count()

    return JsonResponse({'count': count})


@login_required
def delete_message(request, pk):
    """Delete a message"""
    message = get_object_or_404(Message, pk=pk)
    conversation = message.conversation
    
    # Check permission
    if message.sender != request.user and not conversation.participants.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden()
    
    if request.method == 'POST':
        delete_for_everyone = request.POST.get('delete_for_everyone') == 'true'
        
        if delete_for_everyone and message.sender == request.user:
            message.deleted_for_everyone = True
            message.text = "This message was deleted"
        
        message.is_deleted = True
        message.save()
        
        if request.headers.get('HX-Request'):
            return JsonResponse({'success': True})
        
        return redirect('messaging:conversation_detail', pk=conversation.pk)
    
    return HttpResponseForbidden()


@login_required
def pin_message(request, pk):
    """Pin/unpin a message"""
    message = get_object_or_404(Message, pk=pk)
    conversation = message.conversation
    
    # Check permission
    if not conversation.participants.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden()
    
    if request.method == 'POST':
        message.is_pinned = not message.is_pinned
        message.save()
        
        if request.headers.get('HX-Request'):
            return JsonResponse({
                'success': True,
                'is_pinned': message.is_pinned
            })
        
        return redirect('messaging:conversation_detail', pk=conversation.pk)
    
    return HttpResponseForbidden()


@login_required
def edit_message(request, pk):
    """Edit own message text via HTMX prompt."""
    message = get_object_or_404(Message, pk=pk)
    if message.sender != request.user:
        return HttpResponseForbidden()

    if request.method == 'POST':
        new_text = request.POST.get('prompt', '').strip()
        if new_text:
            message.text = new_text
            message.edited_at = timezone.now()
            message.save()
        # Reload message with annotation
        message = Message.objects.filter(pk=message.pk).select_related('sender').prefetch_related('read_by').annotate(
            read_by_count=Count('read_by')
        ).first()
        return render(request, 'messaging/partials/message_item.html', {
            'message': message,
            'user': request.user,
            'conversation': message.conversation,
            'participants_count': message.conversation.participants.count(),
        })

    return HttpResponseForbidden()


@login_required
def add_participant(request, pk):
    """Add participant to a group conversation."""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user, is_group=True)
    # Only admins/creator can add participants
    if not conversation.is_admin(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        if username:
            user = User.objects.filter(username=username, is_active=True).first()
            if user and not conversation.participants.filter(pk=user.pk).exists():
                conversation.participants.add(user)
                messages.success(request, f'Добавлен участник: {user.username}')
        if request.headers.get('HX-Request'):
            return participants_panel(request, pk)
        return redirect('messaging:conversation_detail', pk=conversation.pk)
    return HttpResponseForbidden()


@login_required
def remove_participant(request, pk, user_id):
    """Remove participant from a group conversation (cannot remove self)."""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user, is_group=True)
    # Only admins/creator can remove participants
    if not conversation.is_admin(request.user):
        return HttpResponseForbidden()
    target = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        # cannot remove creator
        if target == conversation.creator:
            messages.error(request, 'Нельзя удалить создателя группы')
        elif target != request.user and conversation.participants.filter(pk=target.pk).exists():
            conversation.participants.remove(target)
            messages.warning(request, f'Удалён участник: {target.username}')
        if request.headers.get('HX-Request'):
            return participants_panel(request, pk)
        return redirect('messaging:conversation_detail', pk=conversation.pk)
    return HttpResponseForbidden()


@login_required
def leave_group(request, pk):
    """Leave a group conversation."""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user, is_group=True)
    if request.method == 'POST':
        conversation.participants.remove(request.user)
        messages.info(request, 'Вы покинули группу')
        return redirect('messaging:conversation_list')
    return HttpResponseForbidden()


@login_required
def search_users(request):
    """Search active users by username, names, or permanent_id excluding current user. Returns HTML list (HTMX)."""
    q = (request.GET.get('q') or '').strip()
    users = User.objects.none()
    if q:
        users = User.objects.filter(is_active=True).exclude(pk=request.user.pk).filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(permanent_id__icontains=q)
        ).order_by(Lower('username'))[:20]
    return render(request, 'messaging/partials/search_results.html', {
        'users': users,
    })


@login_required
def toggle_admin(request, pk, user_id):
    """Creator toggles admin rights for a participant."""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user, is_group=True)
    if conversation.creator_id != request.user.id:
        return HttpResponseForbidden()
    target = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        if target == conversation.creator:
            messages.error(request, 'Создатель и так главный админ')
        elif conversation.participants.filter(pk=target.pk).exists():
            if conversation.admins.filter(pk=target.pk).exists():
                conversation.admins.remove(target)
                messages.info(request, f'Снят админ: {target.username}')
            else:
                conversation.admins.add(target)
                messages.success(request, f'Назначен админ: {target.username}')
        if request.headers.get('HX-Request'):
            return participants_panel(request, pk)
        return redirect('messaging:conversation_detail', pk=conversation.pk)
    return HttpResponseForbidden()


@login_required
def mark_message_read(request, pk):
    """Mark a message as read"""
    message = get_object_or_404(Message, pk=pk)
    
    if message.conversation.participants.filter(pk=request.user.pk).exists():
        message.mark_as_read(request.user)
        
        if request.headers.get('HX-Request'):
            return JsonResponse({'success': True})
    
    return JsonResponse({'success': False})


@login_required
def typing_indicator(request, pk):
    """Update typing indicator for a conversation using cache"""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user)
    
    if request.method == 'POST':
        typing_cache.set_typing_v2(
            conversation_id=conversation.pk,
            user_id=request.user.pk,
            username=request.user.username
        )
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False})


@login_required
def typing_status(request, pk):
    """Get typing status for a conversation from cache"""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user)
    
    typing_usernames = typing_cache.get_typing_users_v2(
        conversation_id=conversation.pk,
        exclude_user_id=request.user.pk
    )
    
    return JsonResponse({
        'typing': len(typing_usernames) > 0,
        'users': typing_usernames
    })


@login_required
def api_conversations(request):
    """API endpoint: Get user's conversations for messaging panel"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    conversations = Conversation.objects.filter(
        participants=request.user
    ).prefetch_related(
        'participants',
        Prefetch('messages', queryset=Message.objects.filter(is_deleted=False).order_by('-created_at')[:1], to_attr='recent_messages')
    ).annotate(
        unread_count=Count('messages', filter=~Q(messages__sender=request.user) & ~Q(messages__read_by=request.user))
    ).order_by('-updated_at')[:20]  # Limit to 20 conversations
    
    data = []
    for conv in conversations:
        last_message = conv.recent_messages[0] if conv.recent_messages else None
        
        # Get other participant for 1-on-1 chats
        other_participant = None
        if not conv.is_group:
            other_participant = next(
                (p for p in conv.participants.all() if p.pk != request.user.pk),
                None
            )
        
        conv_data = {
            'id': conv.id,
            'is_group': conv.is_group,
            'group_name': conv.group_name,
            'unread_count': conv.unread_count,
            'last_message': {
                'text': last_message.text or '[File]' if last_message else '',
                'created_at': last_message.created_at.isoformat() if last_message else None,
                'sender': last_message.sender.username if last_message else None,
            } if last_message else None,
            'other_participant': {
                'id': other_participant.id,
                'username': other_participant.username,
                'avatar': {
                    'url': other_participant.avatar.url if other_participant.avatar and other_participant.avatar.name != 'avatars/default.png' else None
                }
            } if other_participant else None,
            'participants_count': conv.participants.count(),
        }
        
        data.append(conv_data)
    
    return JsonResponse(data, safe=False)

