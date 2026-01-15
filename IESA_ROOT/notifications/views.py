from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from .models import Notification

@login_required
def notification_list(request):
    """Display all notifications for the current user"""
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()
    
    # Paginate notifications
    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'notifications': page_obj,
        'unread_count': unread_count,
    }
    return render(request, 'notifications/notification_list.html', context)

@login_required
def mark_notification_read(request, pk):
    """Mark a single notification as read"""
    notification = Notification.objects.filter(pk=pk, recipient=request.user).first()
    if notification:
        notification.is_read = True
        notification.save()
    return redirect('notification_list')

@login_required
def mark_all_read(request):
    """Mark all notifications as read for the current user"""
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect('notification_list')

@login_required
def notification_delete(request, pk):
    """Delete a specific notification"""
    notification = Notification.objects.filter(pk=pk, recipient=request.user).first()
    if notification:
        notification.delete()
    
    # Return empty response for HTMX delete
    from django.http import HttpResponse
    return HttpResponse('', status=200)
