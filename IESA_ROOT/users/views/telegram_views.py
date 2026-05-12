"""Telegram bot views: webhook, linking, test page."""
import asyncio
import html as _html
import logging
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..constants import WEBHOOK_RATE_LIMIT
from ..models import User
from users.telegram import (
    consume_link_code, get_webhook_info, init_bot_commands,
    is_configured as _token_configured, process_incoming_update,
    send_message, set_webhook, token as _token, verify_telegram_auth,
    webhook_secret as _webhook_secret,
)
from users.telegram.config import bot_name as _bot_name_fn

logger = logging.getLogger(__name__)


def _tg_bot_name() -> str:
    """Canonical bot-name lookup: TELEGRAM_BOT_USERNAME → TELEGRAM_BOT_NAME → fallback."""
    return (
        os.environ.get('TELEGRAM_BOT_USERNAME')
        or os.environ.get('TELEGRAM_BOT_NAME')
        or _bot_name_fn()
        or 'IESA_Administrator_bot'
    )


@login_required
def test_telegram_view(request):
    """Staff-only Telegram setup page (Block 8e: uses template instead of inline HTML)."""
    if not request.user.is_staff:
        return HttpResponseForbidden(_("Access restricted to administrators only."))

    result_html = ""
    webhook_secret = _webhook_secret()
    webhook_url = request.build_absolute_uri(f"/auth/telegram/webhook/{webhook_secret}/") if webhook_secret else ""

    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "set_webhook":
                if not webhook_secret:
                    result_html = '<div class="alert err">❌ TELEGRAM_WEBHOOK_SECRET не задан в DigitalOcean.</div>'
                else:
                    ok, msg = set_webhook(webhook_url)
                    result_html = f'<div class="alert {"ok" if ok else "err"}>{"✅" if ok else "❌"} {_html.escape(msg)}</div>'
                    if ok:
                        import threading as _thr
                        _cmd_result = {}
                        def _run_init():
                            loop = asyncio.new_event_loop()
                            try:
                                loop.run_until_complete(init_bot_commands())
                                _cmd_result['ok'] = True
                            except Exception as _e:
                                _cmd_result['err'] = str(_e)
                            finally:
                                loop.close()
                        t = _thr.Thread(target=_run_init, daemon=True); t.start(); t.join(timeout=10)
                        if _cmd_result.get('ok'):
                            result_html += '<div class="alert ok">✅ Команды бота зарегистрированы в Telegram</div>'
                        elif 'err' in _cmd_result:
                            result_html += f'<div class="alert err">⚠️ Команды не установлены: {_html.escape(_cmd_result["err"])}</div>'
                        else:
                            result_html += '<div class="alert err">⚠️ Timeout регистрации команд (>10s)</div>'
            else:
                result_html = '<div class="alert err">❌ Неизвестное действие.</div>'
        except Exception as exc:
            logger.error("test_telegram_view failed: %s", exc)
            result_html = f'<div class="alert err">❌ Ошибка: {_html.escape(str(exc))}</div>'

    token_set  = bool(_token())
    secret_set = bool(webhook_secret)
    webhook_info = get_webhook_info() if token_set else {}
    current_url  = (webhook_info.get("result") or {}).get("url", "") if isinstance(webhook_info, dict) else ""

    return render(request, 'users/test_telegram.html', {
        'token_set': token_set, 'secret_set': secret_set,
        'current_url': current_url, 'webhook_url': webhook_url,
        'result_html': result_html,
    })


@login_required
@require_http_methods(["GET", "POST"])
def connect_telegram_code_view(request):
    """Link Telegram via 6-digit code from bot /link command."""
    error = ""
    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        if not code.isdigit() or len(code) != 6:
            error = _("Code must be exactly 6 digits.")
        else:
            chat_id = consume_link_code(code)
            if not chat_id:
                error = _("Code is invalid or expired. Get a new one with /link in the bot.")
            elif User.objects.filter(telegram_chat_id=int(chat_id)).exclude(pk=request.user.pk).exists():
                error = _("This Telegram account is already linked to another user.")
            else:
                request.user.telegram_chat_id = int(chat_id)
                request.user.telegram_linked_at = timezone.now()
                request.user.save(update_fields=["telegram_chat_id", "telegram_linked_at"])
                send_message(
                    f"✅ Telegram привязан к аккаунту <b>{_html.escape(request.user.username)}</b> на IESA Sport!",
                    chat_id=chat_id,
                )
                messages.success(request, _("✅ Telegram linked successfully!"))
                return redirect("users:profile")
    return render(request, "users/connect_telegram_code.html", {
        "error": error, "telegram_bot_name": _tg_bot_name(),
    })


@login_required
@require_http_methods(["POST"])
def disconnect_telegram_view(request):
    request.user.telegram_chat_id = None
    request.user.telegram_linked_at = None
    request.user.save(update_fields=["telegram_chat_id", "telegram_linked_at"])
    messages.success(request, _("Telegram disconnected from your account."))
    return redirect("users:profile")


@login_required
def telegram_login_callback_view(request):
    """Telegram Login Widget callback — verifies HMAC and links account."""
    import time
    flat = {k: (v[0] if isinstance(v, list) else v) for k, v in dict(request.GET).items()}
    if not flat.get("hash") or not verify_telegram_auth(flat):
        messages.error(request, _("Telegram signature verification failed."))
        return redirect("users:profile")
    if time.time() - int(flat.get("auth_date", 0)) > 300:
        messages.error(request, _("Telegram request expired. Please try again."))
        return redirect("users:profile")
    tg_id = int(flat.get("id", 0))
    if not tg_id:
        messages.error(request, _("Unable to retrieve Telegram ID."))
        return redirect("users:profile")
    if User.objects.filter(telegram_chat_id=tg_id).exclude(pk=request.user.pk).exists():
        messages.error(request, _("This Telegram account is already linked to another user."))
        return redirect("users:profile")
    request.user.telegram_chat_id = tg_id
    request.user.telegram_linked_at = timezone.now()
    request.user.save(update_fields=["telegram_chat_id", "telegram_linked_at"])
    messages.success(request, _("✅ Telegram (%(name)s) linked successfully!") % {
        'name': flat.get("username") or flat.get("first_name", "")
    })
    return redirect("users:profile")


@csrf_exempt
@require_http_methods(["POST"])
async def telegram_webhook_view(request, secret):
    """Async Telegram webhook handler with rate limiting and signature verification."""
    import json as _json
    from django.core.cache import cache

    _ip     = request.META.get('REMOTE_ADDR', 'unknown')
    _rl_key = f'webhook_rl_{_ip}'
    _count  = cache.get(_rl_key, 0)
    if _count >= WEBHOOK_RATE_LIMIT:
        return JsonResponse({"ok": False}, status=429)
    cache.set(_rl_key, _count + 1, timeout=60)

    from users.telegram.config import webhook_secret as _get_expected_secret, is_active
    expected = _get_expected_secret()
    if not expected or secret != expected:
        logger.warning("Webhook rejected: invalid secret (ip=%s)", _ip)
        return JsonResponse({"ok": False}, status=403)

    try:
        body    = request.body.decode("utf-8")
        payload = _json.loads(body) if body else {}
    except Exception as exc:
        logger.error("Webhook JSON parse error: %s", exc)
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    if not isinstance(payload, dict) or "update_id" not in payload:
        return JsonResponse({"ok": False, "error": "invalid update"}, status=400)

    update_type = next((k for k in ("callback_query", "message", "chat_member", "edited_message") if k in payload), list(payload.keys())[:2])
    logger.info("Webhook received: type=%s update_id=%s", update_type, payload.get("update_id"))

    if is_active():
        try:
            await process_incoming_update(payload)
        except asyncio.CancelledError:
            logger.warning("Webhook processing cancelled (update_id=%s)", payload.get("update_id"))
            raise
        except Exception as exc:
            logger.exception("process_incoming_update raised: %s", exc)
            return JsonResponse({"ok": False, "error": "processing failed"}, status=500)
    return JsonResponse({"ok": True})
