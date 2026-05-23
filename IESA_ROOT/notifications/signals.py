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


def _safe_str(value):
    """BLOCK 9 (audit v4): конвертирует lazy translatable strings в str.
       Иначе f-string могут вставить repr lazy-объекта вместо текста."""
    if value is None:
        return ''
    try:
        return str(value)
    except Exception:
        return repr(value)


def _notify_admins(event_code, *, site_title, site_message, site_link,
                   tg_text, tg_button_url=None, tg_button_label='🔧 Открыть в админке',
                   exclude_user_id=None):
    """
    HOTFIX 2026-05-23 + BLOCK 9 audit v4: универсальный sender admin-уведомлений
    с debug logging на каждом шаге.

    - site_title / site_message / site_link → in-site Notification (link → кнопка)
    - tg_text → Telegram (HTML). Если tg_button_url задан → inline-кнопка с URL.
    - exclude_user_id: если None → НЕ исключаем никого (даже автора события).
      Это нужно для тестов: админ должен видеть уведомления о СВОИХ действиях
      чтобы проверить что система работает. Раньше exclude_user_id=author исключало
      админа из его же уведомлений — это сбивало с толку при дебаге.
    """
    import threading
    from users.models import AdminNotificationProfile
    from notifications.models import Notification as _Notif

    try:
        profiles_qs = AdminNotificationProfile.objects.filter(is_active=True).select_related('admin_user')
        profiles = list(profiles_qs)
    except Exception as exc:
        logger.error("[notify_admins] AdminNotificationProfile query failed for event=%s: %s", event_code, exc, exc_info=True)
        return

    logger.info("[notify_admins] event=%s — found %d active profile(s)", event_code, len(profiles))
    if not profiles:
        logger.warning("[notify_admins] event=%s — НЕТ активных профилей (создайте AdminNotificationProfile в Django admin)", event_code)
        return

    abs_button_url = None
    if tg_button_url:
        if tg_button_url.startswith('http://') or tg_button_url.startswith('https://'):
            abs_button_url = tg_button_url
        else:
            abs_button_url = _site_origin() + '/' + tg_button_url.lstrip('/')

    # BLOCK 9: безопасная конвертация lazy strings (без неё f-string могут вставить proxy-объект)
    site_title   = _safe_str(site_title)
    site_message = _safe_str(site_message)
    tg_text      = _safe_str(tg_text)

    sent_site = 0
    sent_tg = 0
    skipped = 0

    for profile in profiles:
        admin = profile.admin_user
        if exclude_user_id is not None and admin.pk == exclude_user_id:
            logger.info("[notify_admins] event=%s — skip admin=%s (exclude_user_id matches)", event_code, admin.pk)
            skipped += 1
            continue

        # In-site
        should_site = profile.should_notify_site(event_code)
        logger.info("[notify_admins] event=%s admin=%s should_notify_site=%s telegram_events=%s site_events=%s",
                    event_code, admin.pk, should_site,
                    profile.telegram_events, profile.site_events)
        if should_site:
            try:
                _Notif.objects.create(
                    recipient=admin,
                    notification_type='system',
                    title=site_title,
                    message=site_message,
                    link=site_link,
                )
                sent_site += 1
                logger.info("[notify_admins] event=%s admin=%s — in-site notif CREATED", event_code, admin.pk)
            except Exception as exc:
                logger.error("[notify_admins] event=%s admin=%s — in-site notif FAILED: %s", event_code, admin.pk, exc, exc_info=True)

        # Telegram
        should_tg = profile.should_notify_telegram(event_code)
        chat_id = getattr(admin, 'telegram_chat_id', None)
        if should_tg and not chat_id:
            logger.warning("[notify_admins] event=%s admin=%s — TG enabled but telegram_chat_id is empty", event_code, admin.pk)
        if should_tg and chat_id:
            _cid = chat_id
            _text = tg_text
            _kb = None
            if abs_button_url:
                _kb = {"inline_keyboard": [[{"text": tg_button_label, "url": abs_button_url}]]}

            def _send_tg(cid=_cid, text=_text, kb=_kb, evt=event_code, aid=admin.pk):
                try:
                    from users.telegram.client import send_message as _sm
                    ok = _sm(text, chat_id=cid, parse_mode='HTML', reply_markup=kb)
                    if ok:
                        logger.info("[notify_admins] event=%s admin=%s — TG SENT to chat=%s", evt, aid, cid)
                    else:
                        logger.warning("[notify_admins] event=%s admin=%s — TG send_message returned False (check token/chat_id)", evt, aid)
                except Exception as exc:
                    logger.error("[notify_admins] event=%s admin=%s — TG SEND FAILED: %s", evt, aid, exc, exc_info=True)

            threading.Thread(target=_send_tg, daemon=True).start()
            sent_tg += 1

    logger.info("[notify_admins] event=%s DONE: site=%d, tg=%d (queued), skipped=%d", event_code, sent_site, sent_tg, skipped)


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
def _auto_create_admin_notification_profile(sender, instance, created, **kwargs):
    """BLOCK 9 (audit v4): при создании нового staff-юзера автоматически
    создаём AdminNotificationProfile со всеми событиями включёнными."""
    if not instance.is_staff:
        return
    try:
        from users.models import AdminNotificationProfile
        AdminNotificationProfile.objects.get_or_create(
            admin_user=instance,
            defaults={
                'telegram_events': ['new_account', 'post_moderation', 'account_upgrade', 'insurance_request', 'new_visit'],
                'site_events':     ['new_account', 'post_moderation', 'account_upgrade', 'insurance_request', 'new_visit'],
                'is_active': True,
            },
        )
    except Exception as e:
        logger.error("Auto-create AdminNotificationProfile failed for user %s: %s", instance.pk, e)


@receiver(post_save, sender=_User)
def _notify_admins_new_account(sender, instance, created, **kwargs):
    if not created or instance.is_staff:
        return
    logger.info("[signals] new_account triggered — user_id=%s username=%s", instance.pk, instance.username)
    try:
        admin_path = f'/admin/users/user/{instance.pk}/change/'
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
            # BLOCK 9 (audit v4): новый юзер не может быть в админах сам себе (создаётся inactive)
            exclude_user_id=None,
        )
    except Exception as e:
        logger.error("new_account notification failed for user %s: %s", instance.pk, e, exc_info=True)


try:
    from users.models import AccountChangeRequest

    @receiver(post_save, sender=AccountChangeRequest)
    def _notify_admins_account_upgrade(sender, instance, created, **kwargs):
        if not created:
            return
        logger.info("[signals] account_upgrade triggered — ACR=%s user=%s desired_type=%s",
                    instance.pk, instance.user_id, instance.desired_type)
        try:
            admin_path = f'/admin/users/accountchangerequest/{instance.pk}/change/'
            applicant = instance.user.username if instance.user else 'Anonymous'
            # BLOCK 9 (audit v4): get_desired_type_display() возвращает lazy translatable —
            # str() конвертирует в реальный текст
            desired_raw = instance.get_desired_type_display() if hasattr(instance, 'get_desired_type_display') else (instance.desired_type or '')
            desired = str(desired_raw)
            # Используем first_name+last_name если есть, иначе username
            fn = (instance.first_name or '').strip()
            ln = (instance.last_name or '').strip()
            full_name = (f'{fn} {ln}'.strip()) or applicant
            _notify_admins(
                'account_upgrade',
                site_title=_gt('New account upgrade request'),
                site_message=_gt('%(user)s requested upgrade to %(role)s.') % {
                    'user': applicant, 'role': desired,
                },
                site_link=admin_path,
                tg_text=(
                    f"🚀 <b>Заявка на повышение статуса</b>\n\n"
                    f"👤 <b>{full_name}</b> (@{applicant})\n"
                    f"🎯 {desired}\n"
                    + (f"📞 {instance.contact_phone}\n" if getattr(instance, 'contact_phone', '') else '')
                    + (f"✉️ {instance.contact_email}\n" if getattr(instance, 'contact_email', '') else '')
                    + (f"📍 {instance.address}\n" if getattr(instance, 'address', '') else '')
                    + (f"\n💬 {(instance.reason or '')[:200]}\n" if getattr(instance, 'reason', '') else '')
                ),
                tg_button_url=admin_path,
                # BLOCK 9: НЕ исключаем автора — админ должен видеть уведомление о своей заявке
                # (важно для тестирования системы и для admin'ов которые подают заявку как обычные юзеры)
                exclude_user_id=None,
            )
        except Exception as e:
            logger.error("account_upgrade notification failed for %s: %s", instance.pk, e, exc_info=True)
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
