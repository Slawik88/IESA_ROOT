"""
Signal handlers for automatic notification creation.
"""
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from blog.models import Post, Comment, Like
from .utils import (
    notify_post_approved, 
    notify_post_rejected,
    notify_new_comment,
    notify_comment_reply,
    notify_new_like
)

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Post)
def capture_previous_post_status(sender, instance, **kwargs):
    """Capture previous status before saving so post_save can compare."""
    if instance.pk:
        try:
            prev = sender.objects.get(pk=instance.pk)
            instance._previous_status = prev.status
        except sender.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None


def _notify_admins_post_moderation(post):
    """HOTFIX 2026-05-23: уведомить всех админов с AdminNotificationProfile.post_moderation
       о новом посте на модерации (in-site + Telegram)."""
    import threading
    from users.models import AdminNotificationProfile
    from notifications.models import Notification as _Notif
    from django.utils.translation import gettext as _gt

    try:
        profiles = AdminNotificationProfile.objects.filter(is_active=True).select_related('admin_user')
    except Exception as exc:
        logger.error("AdminNotificationProfile query failed: %s", exc)
        return

    for profile in profiles:
        admin = profile.admin_user
        if admin.pk == post.author_id:
            continue  # Не уведомляем автора (он и есть админ)

        # In-site уведомление
        if profile.should_notify_site('post_moderation'):
            try:
                _Notif.objects.create(
                    recipient=admin,
                    notification_type='system',
                    title=_gt('New post on moderation'),
                    message=_gt('%(author)s submitted a post «%(title)s» for moderation.') % {
                        'author': post.author.username if post.author else 'Anonymous',
                        'title': (post.title or '')[:80],
                    },
                    link=f'/admin/blog/post/{post.pk}/change/',
                )
            except Exception as exc:
                logger.error("post_moderation in-site notif failed: %s", exc)

        # Telegram уведомление
        if profile.should_notify_telegram('post_moderation') and getattr(admin, 'telegram_chat_id', None):
            _pid, _cid = post.pk, admin.telegram_chat_id

            def _send_tg(pid=_pid, cid=_cid):
                try:
                    from blog.models import Post as _Post
                    from users.telegram.notify import send_message as _sm
                    p = _Post.objects.select_related('author').get(pk=pid)
                    author = p.author.username if p.author else 'Anonymous'
                    msg = (
                        f"📝 <b>Новый пост на модерации</b>\n\n"
                        f"👤 <b>{author}</b>\n"
                        f"📋 «{(p.title or '')[:100]}»\n\n"
                        f"🔗 /admin/blog/post/{p.pk}/change/"
                    )
                    _sm(msg, chat_id=cid, parse_mode='HTML')
                except Exception as exc:
                    logger.error("post_moderation TG notify failed: %s", exc)

            threading.Thread(target=_send_tg, daemon=True).start()


@receiver(post_save, sender=Post)
def post_status_changed(sender, instance, created, **kwargs):
    """Send notification when post status changes.

    HOTFIX 2026-05-23: добавлено уведомление админов о новом посте на модерации
    (события из AdminNotificationProfile.post_moderation).
    """
    if created:
        # Новый пост: уведомить админов если status='pending'
        if instance.status == 'pending':
            try:
                _notify_admins_post_moderation(instance)
            except Exception as e:
                logger.error(f"Failed to notify admins about new post {instance.id}: {e}", exc_info=True)
        return

    old_status = getattr(instance, '_previous_status', None)
    new_status = instance.status

    if old_status is None or old_status == new_status:
        return

    # HOTFIX: пост перевели из draft в pending — уведомить админов
    if new_status == 'pending' and old_status != 'pending':
        try:
            _notify_admins_post_moderation(instance)
        except Exception as e:
            logger.error(f"Failed to notify admins about post pending {instance.id}: {e}", exc_info=True)

    if new_status in ['published', 'rejected']:
        try:
            if new_status == 'published':
                notify_post_approved(instance)
            elif new_status == 'rejected':
                notify_post_rejected(instance)
        except Exception as e:
            logger.error(f"Failed to create notification for post {instance.id}: {str(e)}", exc_info=True)
            # Don't raise - notification failure shouldn't break the post save


@receiver(post_save, sender=Comment)
def comment_created(sender, instance, created, **kwargs):
    """Send notification when new comment is created.
    
    FIX: Added error handling to prevent notification failures from breaking comments.
    """
    if created:
        try:
            # Notify post author
            notify_new_comment(instance)
            # Notify parent comment author if it's a reply
            if instance.parent:
                notify_comment_reply(instance)
        except Exception as e:
            logger.error(f"Failed to create notification for comment {instance.id}: {str(e)}", exc_info=True)
            # Don't raise - notification failure shouldn't break the comment creation


@receiver(post_save, sender=Like)
def like_created(sender, instance, created, **kwargs):
    """Send notification when new like is created.
    
    FIX: Added error handling.
    """
    if created:
        try:
            notify_new_like(instance)
        except Exception as e:
            logger.error(f"Failed to create notification for like {instance.id}: {str(e)}", exc_info=True)
            # Don't raise - notification failure shouldn't break the like creation


# @receiver(post_save, sender='messaging.Message')
# def message_created(sender, instance, created, **kwargs):
#     """Send notification when new message is created.
#     
#     Notifies all conversation participants except the sender.
#     DISABLED: messaging app removed from project.
#     """
#     if created:
#         try:
#             notify_new_message(instance)
#         except Exception as e:
#             logger.error(f"Failed to create notification for message {instance.id}: {str(e)}", exc_info=True)
#             # Don't raise - notification failure shouldn't break the message creation
