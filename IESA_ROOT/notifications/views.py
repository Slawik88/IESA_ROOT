import time
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseNotAllowed, StreamingHttpResponse
from django.utils.translation import gettext as _
from .models import Notification

@login_required
def unread_count(request):
    """Return just the unread notification count for HTMX badge polling"""
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    if count > 0:
        display = '99+' if count > 99 else str(count)
        return HttpResponse(f'<span class="badge bg-danger rounded-pill">{display}</span>')
    return HttpResponse('')  # No badge if 0 unread

@login_required
def notification_list(request):
    """Display all notifications - full page or dropdown partial via HTMX"""
    notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')
    
    # For HTMX dropdown requests, show only 10 latest notifications
    if request.headers.get('HX-Request'):
        notifications = notifications[:10]
        return render(request, 'notifications/dropdown_list.html', {'notifications': notifications})
    
    # For full page view, paginate
    total_count = notifications.count()
    unread_count = notifications.filter(is_read=False).count()
    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'notifications': page_obj,
        'unread_count': unread_count,
        'total_count': total_count,
    }
    return render(request, 'notifications/notification_list.html', context)

@login_required
def mark_notification_read(request, pk):
    """Mark a single notification as read"""
    notification = Notification.objects.filter(pk=pk, recipient=request.user).first()
    if notification:
        notification.mark_as_read()
    return redirect('notifications:notification_list')

@login_required
def notification_panel(request):
    """Return notifications partial for the slide-out panel"""
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:20]
    context = {
        'notifications': notifications,
    }
    return render(request, 'notifications/notification_list_partial.html', context)

@login_required
def mark_all_read(request):
    """Mark all notifications as read for the current user"""
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    
    # Check if it's an HTMX request
    if request.headers.get('HX-Request'):
        from django.http import HttpResponse
        return HttpResponse(f'<span class="text-muted small">{_("All notifications marked as read")}</span>')
    
    return redirect('notifications:notification_list')

@login_required
def notification_stream(request):
    """
    10e: Server-Sent Events endpoint.
    Отправляет unread_count каждые 30с.
    Клиент получает событие 'badge' и обновляет badge без polling.
    Fallback: если SSE недоступен, клиент использует hx-trigger="every 5m".
    Heroku: timeouts после 55с — клиент reconnect автоматически.
    """
    def event_generator():
        user_id = request.user.pk
        last_count = -1
        start = time.time()
        try:
            # Сразу отправляем текущее состояние
            count = Notification.objects.filter(recipient_id=user_id, is_read=False).count()
            last_count = count
            badge = str(count) if count > 0 else '0'
            yield f"event: badge\ndata: {badge}\n\n"

            while time.time() - start < 50:  # < Heroku 55s timeout
                time.sleep(30)
                count = Notification.objects.filter(recipient_id=user_id, is_read=False).count()
                if count != last_count:
                    last_count = count
                    badge = str(count) if count > 0 else '0'
                    yield f"event: badge\ndata: {badge}\n\n"
                else:
                    yield ": keepalive\n\n"  # пустой comment — держит соединение
        except GeneratorExit:
            pass

    response = StreamingHttpResponse(event_generator(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # отключаем nginx буферизацию
    return response


@login_required
def notification_delete(request, pk):
    """Delete a specific notification"""
    if request.method not in ("POST", "DELETE"):
        return HttpResponseNotAllowed(["POST", "DELETE"])

    notification = Notification.objects.filter(pk=pk, recipient=request.user).first()
    if notification:
        notification.delete()

    # HTMX: return HX-Trigger to refresh unread badge + empty body
    # Set status 200 to confirm successful deletion
    response = HttpResponse('', status=200)
    response['HX-Trigger'] = 'notificationDeleted'  # Trigger JS event
    return response
