from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Q, Max, Count, Prefetch
from django.utils import timezone
from django.contrib import messages

from .models import Conversation, Message, TypingIndicator
from users.models import User
from .forms import ConversationForm


class ConversationListView(LoginRequiredMixin, ListView):
    """Display list of user's conversations"""
    model = Conversation
    template_name = 'messaging/conversation_list.html'
    context_object_name = 'conversations'
    paginate_by = 20
    
    def get_queryset(self):
        return Conversation.objects.filter(
            participants=self.request.user
        ).prefetch_related(
            'participants',
            Prefetch('messages', queryset=Message.objects.filter(is_deleted=False)[:1])
        ).annotate(
            unread_count=Count('messages', filter=~Q(messages__sender=self.request.user) & ~Q(messages__read_by=self.request.user))
        ).order_by('-updated_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['create_group_form'] = ConversationForm()
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
        
        # Get messages
        messages_qs = conversation.messages.filter(
            Q(is_deleted=False) | Q(sender=self.request.user)
        ).select_related('sender').prefetch_related('read_by').order_by('created_at')
        
        context['messages'] = messages_qs
        context['other_participant'] = conversation.get_other_participant(self.request.user)
        
        # Mark all messages as read
        for msg in messages_qs:
            if msg.sender != self.request.user:
                msg.mark_as_read(self.request.user)
        
        return context


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
            return redirect('messaging:conversation_detail', pk=conv.pk)
    return HttpResponseForbidden()


@login_required
def send_message(request, pk):
    """Send a message in a conversation"""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user)
    
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        file = request.FILES.get('file')
        
        if text or file:
            message = Message.objects.create(
                conversation=conversation,
                sender=request.user,
                text=text
            )
            
            if file:
                message.file = file
                message.save()
            
            # Mark sender as having read their own message
            message.read_by.add(request.user)
            
            # Update conversation timestamp
            conversation.save()
            
            if request.headers.get('HX-Request'):
                # Return HTMX response
                return render(request, 'messaging/partials/message_item.html', {
                    'message': message,
                    'user': request.user
                })
            
            return redirect('messaging:conversation_detail', pk=conversation.pk)
    
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

    qs = conversation.messages.filter(pk__gt=after_id).select_related('sender').prefetch_related('read_by').order_by('created_at')

    if not qs.exists():
        return JsonResponse({'ok': True})

    # Mark as read for current user (incoming only)
    for msg in qs:
        if msg.sender != request.user:
            msg.mark_as_read(request.user)

    return render(request, 'messaging/partials/messages_chunk.html', {
        'messages': qs,
        'user': request.user,
        'conversation': conversation,
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
    qs = conversation.messages.filter(pk__lt=before_id).select_related('sender').prefetch_related('read_by').order_by('-created_at')[:20]
    # Reverse to chronological order for prepend
    messages_list = list(qs)[::-1]
    if not messages_list:
        return JsonResponse({'ok': True})

    return render(request, 'messaging/partials/messages_chunk.html', {
        'messages': messages_list,
        'user': request.user,
        'conversation': conversation,
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
    if message.sender != request.user and request.user not in conversation.participants.all():
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
    if request.user not in conversation.participants.all():
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
        return render(request, 'messaging/partials/message_item.html', {
            'message': message,
            'user': request.user,
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
            if user and user not in conversation.participants.all():
                conversation.participants.add(user)
                messages.success(request, f'Добавлен участник: {user.username}')
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
        if target != request.user and target in conversation.participants.all():
            conversation.participants.remove(target)
            messages.warning(request, f'Удалён участник: {target.username}')
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
def mark_message_read(request, pk):
    """Mark a message as read"""
    message = get_object_or_404(Message, pk=pk)
    
    if request.user in message.conversation.participants.all():
        message.mark_as_read(request.user)
        
        if request.headers.get('HX-Request'):
            return JsonResponse({'success': True})
    
    return JsonResponse({'success': False})


@login_required
def typing_indicator(request, pk):
    """Update typing indicator for a conversation"""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user)
    
    if request.method == 'POST':
        TypingIndicator.set_typing(conversation, request.user)
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False})


@login_required
def typing_status(request, pk):
    """Get typing status for a conversation"""
    conversation = get_object_or_404(Conversation, pk=pk, participants=request.user)
    
    typing_users = TypingIndicator.get_typing_users(conversation, exclude_user=request.user)
    typing_usernames = [indicator.user.username for indicator in typing_users]
    
    return JsonResponse({
        'typing': len(typing_usernames) > 0,
        'users': typing_usernames
    })
