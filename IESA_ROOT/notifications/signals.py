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


def _site_origin():
    """Возвращает абсолютный origin сайта для админ-ссылок в TG-уведомлениях."""
    import os
    return os.environ.get('SITE_URL', 'https://iesasport.ch').rstrip('/')


def _notify_admins(event_code, *, site_title, site_message, site_link,
                   tg_text, tg_button_url=None, tg_button_label='🔧 Открыть в админке',
                   exclude_user_id=None):
    """
    HOTFIX 2026-05-23: универсальный sender для admin-уведомлений.

    - site_title / site_message / site_link → in-site Notification (link рендерится как кнопка)
    - tg_text → Telegram (HTML). Если tg_button_url задан — добавляется inline-кнопка
      «Открыть в админке» (абсолютный URL для клика прямо из TG-клиента).
    """
    import threading
    from users.models import AdminNotificationProfile
    from notifications.models import Notification as _Notif

    try:
        profiles = AdminNotificationProfile.objects.filter(is_active=True).select_related('admin_user')
    except Exception as exc:
        logger.error("AdminNotificationProfile query failed: %s", exc)
        return

    abs_button_url = None
    if tg_button_url:
        if tg_button_url.startswith('http://') or tg_button_url.startswith('https://'):
            abs_button_url = tg_button_url
        else:
            abs_button_url = _site_origin() + '/' + tg_button_url.lstrip('/')

    for profile in profiles:
        admin = profile.admin_user
        if exclude_user_id is not None and admin.pk == exclude_user_id:
            continue

        # In-site
        if profile.should_notify_site(event_code):
            try:
                _Notif.objects.create(
                    recipient=admin,
                    notification_type='system',
                    title=site_title,
                    message=site_message,
                    link=site_link,
                )
            except Exception as exc:
                logger.error("%s in-site notif failed: %s", event_code, exc)

        # Telegram
        if profile.should_notify_telegram(event_code) and getattr(admin, 'telegram_chat_id', None):
            _cid = admin.telegram_chat_id
            _text = tg_text
            _kb = None
            if abs_button_url:
                _kb = {"inline_keyboard": [[{"text": tg_button_label, "url": abs_button_url}]]}

            def _send_tg(cid=_cid, text=_text, kb=_kb):
                try:
                    from users.telegram.client import send_message as _sm
                    _sm(text, chat_id=cid, parse_mode='HTML', reply_markup=kb)
                except Exception as exc:
                    logger.error("%s TG notify failed: %s", event_code, exc)

            threading.Thread(target=_send_tg, daemon=True).start()


def _notify_admins_post_moderation(post):
    """Новый пост на модерации → in-site + TG с inline-кнопкой 'Открыть в админке'."""
    from django.utils.translation import gettext as _gt
    author = post.author.username if post.author else 'Anonymous'
    title = (post.title or '')[:100]
    admin_path = f'/admin/blog/post/{post.pk}/change/'
    _notify_admins(
        'post_moderation',
        site_title=_gt('New post on moderation'),
        site_message=_gt('%(author)s submitted a post «%(title)s» for moderation.') % {
            'author': author, 'title': title,
        },
        site_link=admin_path,
        tg_text=(
            f"📝 <b>Новый пост на модерации</b>\n\n"
            f"👤 <b>{author}</b>\n"
            f"📋 «{title}»"
        ),
        tg_button_url=admin_path,
        exclude_user_id=post.author_id,
    )


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


# ──────────────────────────────────────────────────────────────────────────────
# HOTFIX 2026-05-23: Admin notifications for new_account / account_upgrade / new_visit
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _gt

_User = get_user_model()


@receiver(post_save, sender=_User)
def _notify_admins_new_account(sender, instance, created, **kwargs):
    if not created or instance.is_staff:
        return
    try:
        admin_path = f'/admin/users/user/{instance.pk}/change/'
        profile_path = f'/auth/user/{instance.username}/'
        _notify_admins(
            'new_account',
            site_title=_gt('New account registered'),
            site_message=_gt('%(name)s registered an account.') % {
                'name': instance.get_full_name() or instance.username,
            },
            site_link=admin_path,
            tg_text=(
                f"👤 <b>Новый аккаунт</b>\n\n"
                f"<b>{(instance.get_full_name() or instance.username)}</b>\n"
                f"@{instance.username}\n"
                f"✉️ {instance.email or '—'}"
            ),
            tg_button_url=admin_path,
            exclude_user_id=instance.pk,
        )
    except Exception as e:
        logger.error("new_account notification failed for user %s: %s", instance.pk, e)


try:
    from users.models import AccountChangeRequest

    @receiver(post_save, sender=AccountChangeRequest)
    def _notify_admins_account_upgrade(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            admin_path = f'/admin/users/accountchangerequest/{instance.pk}/change/'
            applicant = instance.user.username if instance.user else 'Anonymous'
            desired = instance.get_desired_type_display() if hasattr(instance, 'get_desired_type_display') else (instance.desired_type or '')
            _notify_admins(
                'account_upgrade',
                site_title=_gt('New account upgrade request'),
                site_message=_gt('%(user)s requested upgrade to %(role)s.') % {
                    'user': applicant, 'role': desired,
                },
                site_link=admin_path,
                tg_text=(
                    f"🚀 <b>Заявка на повышение статуса</b>\n\n"
                    f"👤 <b>{applicant}</b>\n"
                    f"🎯 {desired}\n"
                    + (f"📍 {instance.address}\n" if getattr(instance, 'address', '') else '')
                    + (f"💬 {(instance.reason or '')[:160]}\n" if getattr(instance, 'reason', '') else '')
                ),
                tg_button_url=admin_path,
                exclude_user_id=instance.user_id,
            )
        except Exception as e:
            logger.error("account_upgrade notification failed for %s: %s", instance.pk, e)
except ImportError:
    logger.warning("AccountChangeRequest model not importable — account_upgrade signal not registered")


try:
    from users.models import Visit

    @receiver(post_save, sender=Visit)
    def _notify_admins_new_visit(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            admin_path = f'/admin/users/visit/{instance.pk}/change/'
            partner_name = getattr(instance.partner, 'company_name', '') or '—'
            member_name = (getattr(instance.member, 'get_full_name', lambda: '')() or
                           getattr(instance.member, 'username', '') or 'Anonymous')
            service = (instance.get_service_type_display() if hasattr(instance, 'get_service_type_display') else '')
            _notify_admins(
                'new_visit',
                site_title=_gt('New partner visit logged'),
                site_message=_gt('%(member)s @ %(partner)s — %(service)s') % {
                    'member': member_name, 'partner': partner_name, 'service': service or '—',
                },
                site_link=admin_path,
                tg_text=(
                    f"🏢 <b>Новый визит партнёра</b>\n\n"
                    f"👤 {member_name}\n"
                    f"🏢 {partner_name}\n"
                    + (f"🏃 {service}\n" if service else '')
                    + (f"💰 {instance.cost} CHF\n" if getattr(instance, 'cost', None) else '')
                ),
                tg_button_url=admin_path,
                exclude_user_id=getattr(instance.member, 'pk', None),
            )
        except Exception as e:
            logger.error("new_visit notification failed for %s: %s", instance.pk, e)
except ImportError:
    logger.warning("Visit model not importable — new_visit signal not registered")
