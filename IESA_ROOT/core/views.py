from django.views.generic import TemplateView
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from products.models import Product
from core.models import Partner, AssociationMember, President, SocialNetwork, CoreProduct, MemberBenefit, AdminAppeal
from core.forms import AdminAppealForm
from blog.models import Event
from django.shortcuts import get_object_or_404, render, redirect
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.translation import gettext as _


def submit_appeal(request):
    """Handle admin appeal form submission. Works with HTMX and plain POST."""
    if request.method != 'POST':
        return redirect('core:home')

    form = AdminAppealForm(request.POST)
    is_htmx = request.headers.get('HX-Request') == 'true'

    if not form.is_valid():
        errors = [msg for field_errors in form.errors.values() for msg in field_errors]
        if is_htmx:
            return render(request, 'partials/admin_appeal_form.html', {
                'appeal_errors': errors,
                'appeal_name': form.data.get('appeal_name', ''),
                'appeal_email': form.data.get('appeal_email', ''),
                'appeal_reason': form.data.get('appeal_reason', 'other'),
                'appeal_message': form.data.get('appeal_message', ''),
                'appeal_requested_url': form.data.get('appeal_requested_url', ''),
            })
        from django.contrib import messages as dj_messages
        for e in errors:
            dj_messages.error(request, e)
        return redirect(request.META.get('HTTP_REFERER', 'core:home'))

    d = form.cleaned_data
    AdminAppeal.objects.create(
        user=request.user if request.user.is_authenticated else None,
        name=d['appeal_name'],
        email=d['appeal_email'],
        reason=d.get('appeal_reason', 'other'),
        message=d['appeal_message'],
        requested_url=d.get('appeal_requested_url', ''),
        status='new',
    )

    if is_htmx:
        return render(request, 'partials/admin_appeal_success.html')

    from django.contrib import messages as dj_messages
    dj_messages.success(request, _('✅ Your appeal was submitted. Administration will contact you by e-mail.'))
    return redirect(request.META.get('HTTP_REFERER', 'core:home'))



def partner_detail(request, pk):
    """Return partner details as an HTMX partial for modal display."""
    partner = get_object_or_404(Partner, pk=pk)
    return render(request, 'core/htmx/partner_modal.html', {'partner': partner})


def benefits_view(request):
    """Страница с преимуществами членов ассоциации."""
    # Получаем все активные преимущества, сгруппированные по категориям
    benefits = MemberBenefit.objects.filter(is_active=True).order_by('order', 'category', '-created_at')
    
    # Группируем по категориям для удобного отображения
    from itertools import groupby
    benefits_by_category = {}
    for category, items in groupby(benefits, key=lambda x: x.category):
        benefits_by_category[category] = list(items)
    
    context = {
        'benefits': benefits,
        'benefits_by_category': benefits_by_category,
    }
    return render(request, 'core/benefits.html', context)


class IndexView(TemplateView):
    """
    Главная страница, отображающая данные из разных приложений.
    """
    template_name = 'core/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Секции с редко меняющимися данными — кэш 1 час
        context['core_products'] = cache.get_or_set(
            'idx:core_products',
            lambda: list(CoreProduct.objects.filter(is_active=True).order_by('order', '-created_at')[:4]),
            3600,
        )
        context['products'] = cache.get_or_set(
            'idx:products',
            lambda: list(Product.objects.all().order_by('-id')[:3]),
            3600,
        )
        context['members'] = cache.get_or_set(
            'idx:members',
            lambda: list(AssociationMember.objects.all().order_by('id')[:50]),
            3600,
        )
        context['member_benefits'] = cache.get_or_set(
            'idx:member_benefits',
            lambda: list(MemberBenefit.objects.filter(is_active=True).order_by('order', '-created_at')[:6]),
            3600,
        )

        # Президент — отдельная обработка, т.к. может быть None
        president = cache.get('idx:president', 'MISS')
        if president == 'MISS':
            president = President.objects.first()
            cache.set('idx:president', president, 3600)
        context['president'] = president

        # Партнёры — кэшируем весь список, пагинируем в памяти
        all_partners = cache.get_or_set(
            'idx:partners',
            lambda: list(Partner.objects.all().order_by('name')),
            3600,
        )
        paginator = Paginator(all_partners, 12)
        page = self.request.GET.get('partners_page') or 1
        partners_page = paginator.get_page(page)
        context['partners'] = partners_page.object_list
        context['partners_page_obj'] = partners_page

        # События — кэш 5 минут (более динамичные данные)
        context['upcoming_events'] = cache.get_or_set(
            'idx:upcoming_events',
            lambda: list(Event.objects.filter(
                date__gte=timezone.now()
            ).select_related('created_by').order_by('date')[:6]),
            300,
        )

        return context


# ── 10d: Partner Map ─────────────────────────────────────────────
def partners_map(request):
    """Страница карты партнёров с Leaflet.js."""
    from users.models import Partner as UserPartner
    partners_with_coords = UserPartner.objects.filter(
        lat__isnull=False, lon__isnull=False
    ).exclude(partner_type='association_staff').select_related('user')
    return render(request, 'core/partners_map.html', {
        'partners_count': partners_with_coords.count(),
    })


def partners_map_data(request):
    """JSON endpoint — список партнёров с координатами для Leaflet."""
    import json
    from django.http import JsonResponse
    from users.models import Partner as UserPartner
    qs = UserPartner.objects.filter(
        lat__isnull=False, lon__isnull=False
    ).exclude(partner_type='association_staff').values(
        'id', 'company_name', 'business_type', 'address_full',
        'lat', 'lon', 'user__username',
    )
    data = [
        {
            'id': p['id'],
            'name': p['company_name'],
            'type': p['business_type'],
            'address': p['address_full'],
            'lat': float(p['lat']),
            'lon': float(p['lon']),
            'url': f"/auth/user/{p['user__username']}/",
        }
        for p in qs
    ]
    return JsonResponse({'partners': data})


@user_passes_test(lambda u: u.is_staff)
def component_playground(request):
    """10b: Design system component playground — только для staff."""
    return render(request, 'core/components.html')


@user_passes_test(lambda u: u.is_staff)
def admin_analytics(request):
    """audit v5: простой аналитический дашборд для staff.

    Показывает ключевые метрики экосистемы IESA:
      - Users: всего / active / partners / staff / new last 7d / 30d
      - Posts: total / published / pending / created last 7d
      - Visits (Partner visits) last 7d/30d
      - ACR requests pending / approved / rejected
      - Notifications: total / unread
    Без графиков (чистый Django + CSS). Графики — отдельный блок если нужны.
    """
    from datetime import timedelta
    from django.db.models import Count, Q
    from django.utils import timezone
    from users.models import User, AccountChangeRequest, Visit
    from blog.models import Post, Comment, Like
    from notifications.models import Notification

    now = timezone.now()
    d7  = now - timedelta(days=7)
    d30 = now - timedelta(days=30)

    # User stats
    user_total      = User.objects.count()
    user_active     = User.objects.filter(membership_status='active').count()
    user_partners   = User.objects.filter(is_partner=True).count()
    user_staff      = User.objects.filter(is_staff=True).count()
    user_president  = User.objects.filter(is_president=True).count()
    user_verified   = User.objects.filter(is_verified=True).count()
    user_new_7d     = User.objects.filter(date_joined__gte=d7).count()
    user_new_30d    = User.objects.filter(date_joined__gte=d30).count()
    user_tg_linked  = User.objects.filter(telegram_chat_id__isnull=False).exclude(telegram_chat_id=0).count()

    # Posts
    post_total      = Post.objects.count()
    post_published  = Post.objects.filter(status='published').count()
    post_pending    = Post.objects.filter(status='pending').count()
    post_new_7d     = Post.objects.filter(created_at__gte=d7).count()
    comment_total   = Comment.objects.count()
    like_total      = Like.objects.count()

    # Visits
    visit_total    = Visit.objects.count()
    visit_7d       = Visit.objects.filter(timestamp__gte=d7).count()
    visit_30d      = Visit.objects.filter(timestamp__gte=d30).count()
    visit_verified = Visit.objects.filter(pin_verified=True).count()

    # ACR
    acr_pending  = AccountChangeRequest.objects.filter(status='pending').count()
    acr_approved = AccountChangeRequest.objects.filter(status='approved').count()
    acr_rejected = AccountChangeRequest.objects.filter(status='rejected').count()
    acr_total    = AccountChangeRequest.objects.count()

    # Notifications
    notif_total  = Notification.objects.count()
    notif_unread = Notification.objects.filter(is_read=False).count()

    # Recent activity (last 5 of each)
    recent_acr    = AccountChangeRequest.objects.select_related('user').order_by('-created_at')[:5]
    recent_users  = User.objects.order_by('-date_joined')[:5]
    recent_posts  = Post.objects.select_related('author').order_by('-created_at')[:5]
    recent_visits = Visit.objects.select_related('member', 'partner').order_by('-timestamp')[:5]

    return render(request, 'core/admin_analytics.html', {
        'stats': {
            'user_total': user_total,
            'user_active': user_active,
            'user_partners': user_partners,
            'user_staff': user_staff,
            'user_president': user_president,
            'user_verified': user_verified,
            'user_new_7d': user_new_7d,
            'user_new_30d': user_new_30d,
            'user_tg_linked': user_tg_linked,
            'post_total': post_total,
            'post_published': post_published,
            'post_pending': post_pending,
            'post_new_7d': post_new_7d,
            'comment_total': comment_total,
            'like_total': like_total,
            'visit_total': visit_total,
            'visit_7d': visit_7d,
            'visit_30d': visit_30d,
            'visit_verified': visit_verified,
            'acr_pending': acr_pending,
            'acr_approved': acr_approved,
            'acr_rejected': acr_rejected,
            'acr_total': acr_total,
            'notif_total': notif_total,
            'notif_unread': notif_unread,
        },
        'recent_acr': recent_acr,
        'recent_users': recent_users,
        'recent_posts': recent_posts,
        'recent_visits': recent_visits,
        # Interactive tour (2026-05-27) — для президента
        'show_tour': request.user.is_authenticated and not (request.user.tours_completed or {}).get('president', False),
        'tour_name': 'president',
    })


@user_passes_test(lambda u: u.is_staff)
def styleguide_md(request):
    """BLOCK 11a (audit v3): отдаём STYLEGUIDE.md из корня репо как text/markdown.
    Файл живёт вне статики (он dev-док), поэтому Django не обслуживает его автоматически.
    Доступ только для staff."""
    import os
    from django.conf import settings
    # BASE_DIR = .../IESA_ROOT/IESA_ROOT; STYLEGUIDE.md в g:/IESA_ROOT/STYLEGUIDE.md
    candidates = [
        os.path.join(os.path.dirname(settings.BASE_DIR), 'STYLEGUIDE.md'),
        os.path.join(settings.BASE_DIR, 'STYLEGUIDE.md'),
        os.path.join(os.path.dirname(os.path.dirname(settings.BASE_DIR)), 'STYLEGUIDE.md'),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return HttpResponse(content, content_type='text/markdown; charset=utf-8')
            except OSError:
                continue
    return HttpResponse('STYLEGUIDE.md not found on server.', status=404, content_type='text/plain')