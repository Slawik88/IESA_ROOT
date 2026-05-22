import asyncio
import time
from asgiref.sync import sync_to_async
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
async def notification_stream(request):
    """
    10e: Server-Sent Events endpoint.
    Отправляет unread_count каждые 30с.

    BLOCK 10 (audit v3): async generator + asyncio.sleep + sync_to_async.
    HOTFIX 2026-05-22: request.user.pk триггерит sync ORM call внутри async-view
    (SimpleLazyObject из AuthMiddleware). Оборачиваем доступ к request.user в sync_to_async.
    """
    # HOTFIX: request.user — SimpleLazyObject; .pk триггерит синхронный ORM запрос.
    # В async-view это запрещено, поэтому оборачиваем через sync_to_async.
    @sync_to_async
    def _resolve_user_pk():
        return request.user.pk

    user_id = await _resolve_user_pk()

    @sync_to_async
    def _get_count() -> int:
        return Notification.objects.filter(recipient_id=user_id, is_read=False).count()

    async def event_generator():
        last_count = -1
        loop = asyncio.get_event_loop()
        start = loop.time()
        try:
            # Сразу отправляем текущее состояние
            count = await _get_count()
            last_count = count
            badge = str(count) if count > 0 else '0'
            yield f"event: badge\ndata: {badge}\n\n"

            while loop.time() - start < 50:  # < Heroku 55s timeout
                await asyncio.sleep(30)
                count = await _get_count()
                if count != last_count:
                    last_count = count
                    badge = str(count) if count > 0 else '0'
                    yield f"event: badge\ndata: {badge}\n\n"
                else:
                    yield ": keepalive\n\n"  # пустой comment — держит соединение
        except asyncio.CancelledError:
            # Клиент отключился / Daphne делает shutdown — выходим тихо
            return
        except GeneratorExit:
            return

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
