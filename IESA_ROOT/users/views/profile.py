"""Profile views: personal cabinet, public profiles, deactivation."""
import time as _time

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.generic import DetailView, UpdateView

from ..constants import (
    CABINET_VISITS_LIMIT, PIN_INTERVAL, PROFILE_POSTS_PER_PAGE,
)
from ..forms import UserProfileEditForm
from ..models import AccountChangeRequest, User, Visit
from ..services.email_verification import send_email_verification
from blog.models import BlogSubscription, Post


@method_decorator(login_required, name='dispatch')
class ProfileView(DetailView):
    model = User
    template_name = 'users/profile.html'
    context_object_name = 'profile_user'
    paginate_by = PROFILE_POSTS_PER_PAGE

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        all_posts = Post.objects.filter(
            author=user
        ).select_related('author').prefetch_related('likes', 'comments').order_by('-created_at')
        page_obj = Paginator(all_posts, self.paginate_by).get_page(self.request.GET.get('page'))
        context.update({'user_posts': page_obj, 'page_obj': page_obj,
                        'is_paginated': page_obj.has_other_pages()})

        context.update(Post.objects.filter(author=user).aggregate(
            pending_count=Count('id', filter=Q(status='pending')),
            published_count=Count('id', filter=Q(status='published')),
            rejected_count=Count('id', filter=Q(status='rejected')),
            draft_count=Count('id', filter=Q(status='draft')),
        ))

        # BLOCK 8 (audit v4): PIN доступен ВСЕМ юзерам сразу после регистрации.
        # Убран гейт membership_status == 'active' — теперь PIN работает с момента
        # создания totp_secret (генерируется автоматически в User.save()).
        # Физическая карта всё ещё выдаётся вручную (контекст card_active).
        if user.is_authenticated and user.totp_secret:
            _now  = int(_time.time())
            _step = _now // PIN_INTERVAL
            _secs = (_step + 1) * PIN_INTERVAL - _now
            current_pin = cache.get_or_set(
                f'pin_code_{user.pk}_{_step}',
                user.get_current_pin,
                timeout=_secs + 5,
            )
            if current_pin:
                context['current_pin']       = current_pin
                context['seconds_remaining'] = _secs

        context['card_active']    = user.card_active
        context['card_issued_at'] = user.card_issued_at
        _vq = Visit.objects.filter(member=user).select_related('partner').order_by('-timestamp')
        context['total_visits']  = _vq.count()
        context['recent_visits'] = _vq[:CABINET_VISITS_LIMIT]

        context['pending_upgrade_request'] = AccountChangeRequest.objects.filter(
            user=user, status='pending'
        ).order_by('-created_at').first()

        # ── Онбординг (Block 1) ───────────────────────────────────────
        # FIX 2026-05-28: welcome-модалка заменена на interactive tour ниже.
        # show_welcome всегда False — модалка не показывается.
        context['show_welcome']         = False
        context['profile_completeness'] = user.profile_completeness
        context['show_quick_actions']   = context['total_visits'] < 3

        # ── Interactive tour (2026-05-27) ─────────────────────────────
        # Показываем "user" тур если он ещё не пройден.
        # Партнёры/президенты увидят свои туры на соответствующих страницах.
        tours = user.tours_completed or {}
        context['show_tour'] = not tours.get('user', False)
        context['tour_name'] = 'user'

        # Если показываем тур — заодно помечаем onboarded=True, чтобы
        # старая welcome-модалка точно никогда не всплыла.
        if context['show_tour'] and not user.onboarded:
            user.onboarded = True
            user.save(update_fields=['onboarded'])

        return context


@method_decorator(login_required, name='dispatch')
class ProfileEditView(UpdateView):
    model = User
    form_class = UserProfileEditForm
    template_name = 'users/profile_edit.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        messages.success(self.request, _('Profile updated successfully! ✨'))
        return reverse_lazy('users:profile')

    def form_valid(self, form):
        email_changed = 'email' in form.changed_data
        response = super().form_valid(form)
        if email_changed:
            if send_email_verification(self.object, self.request):
                messages.info(self.request, _('We sent a confirmation link to your new e-mail address.'))
            else:
                messages.warning(
                    self.request,
                    _('Your new e-mail was saved, but the confirmation message could not be sent. Try again from your cabinet.'),
                )
        return response


def _get_public_profile_context(user_obj, request_user=None):
    user_posts = Post.objects.filter(
        author=user_obj, status='published'
    ).select_related('author').prefetch_related('likes', 'comments').order_by('-created_at')
    other_links_list = user_obj.other_links.splitlines() if user_obj.other_links else []
    is_subscribed = False
    if request_user and request_user.is_authenticated and request_user != user_obj:
        agg = BlogSubscription.objects.filter(author=user_obj).aggregate(
            total=Count('id'),
            user_sub=Count('id', filter=Q(user=request_user)),
        )
        subscriber_count = agg['total']
        is_subscribed = agg['user_sub'] > 0
    else:
        subscriber_count = BlogSubscription.objects.filter(author=user_obj).count()
    return {
        'user_obj': user_obj, 'user_posts': user_posts,
        'other_links_list': other_links_list,
        'is_subscribed': is_subscribed, 'subscriber_count': subscriber_count,
    }


def profile_public_by_username(request, username):
    user_obj = get_object_or_404(User, username=username)
    return render(request, 'users/profile_public.html', _get_public_profile_context(user_obj, request.user))


def profile_public_by_card(request, permanent_id):
    user_obj = get_object_or_404(User, permanent_id=permanent_id)
    return render(request, 'users/profile_public.html', _get_public_profile_context(user_obj, request.user))


@login_required
def profile_deactivate(request):
    if request.method == 'POST':
        password = request.POST.get('password', '')
        if not password:
            messages.error(request, _('❌ Please enter your password to confirm account deactivation.'))
            return redirect('users:profile')
        if not request.user.check_password(password):
            messages.error(request, _('❌ Incorrect password. Account deactivation cancelled.'))
            return redirect('users:profile')
        request.user.is_active = False
        request.user.save()
        logout(request)
        messages.success(request, _('✅ Your account has been deactivated. You can reactivate it by contacting support.'))
        return redirect('core:home')
    return render(request, 'users/profile_deactivate_confirm.html')


@login_required
def dashboard_redirect(request):
    """«Мой кабинет» — ВСЕГДА личный профиль.

    BLOCK fix 2026-05-23: раньше партнёры авто-редиректились в partner_dashboard,
    но в navbar dropdown есть отдельная кнопка «Partner Portal». Теперь оба пути
    разделены: «My Cabinet» → личный профиль, «Partner Portal» → партнёрский кабинет.
    """
    return redirect('users:profile')
