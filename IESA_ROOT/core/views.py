from django.views.generic import TemplateView
from django.http import HttpResponse
from django.contrib.auth.decorators import user_passes_test
from django.core.cache import cache
from products.models import Product
from core.models import Partner, AssociationMember, President, CoreProduct, MemberBenefit, AdminAppeal
from core.forms import AdminAppealForm
from users.ratelimit_utils import safe_ratelimit
from blog.models import Event
from django.shortcuts import get_object_or_404, render, redirect
from django.core.paginator import Paginator
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.translation import gettext as _


@safe_ratelimit(group='appeal', rate='10/h')
def submit_appeal(request):
    """Handle admin appeal form submission. Works with HTMX and plain POST."""
    if request.method != 'POST':
        return redirect('core:home')

    return_url = request.META.get('HTTP_REFERER', '')
    if not url_has_allowed_host_and_scheme(return_url, {request.get_host()}, require_https=request.is_secure()):
        return_url = 'core:home'
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
        return redirect(return_url)

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
    return redirect(return_url)



def partner_detail(request, pk):
    """Return partner details as an HTMX partial for modal display."""
    partner = get_object_or_404(Partner, pk=pk)
    return render(request, 'core/htmx/partner_modal.html', {'partner': partner})


def benefits_view(request):
    """Страница с преимуществами членов ассоциации."""
    # Получаем все активные преимущества, сгруппированные по категориям
    benefits = MemberBenefit.objects.filter(is_active=True).order_by('order', 'category', '-created_at')
    
    # Группируем по категориям для удобного отображения
    benefits_by_category = {}
    for benefit in benefits:
        benefits_by_category.setdefault(benefit.category, []).append(benefit)
    
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

        # DatabaseCache is shared across workers: fetch all section keys in one query.
        loaders = {
            'idx:core_products': lambda: list(CoreProduct.objects.filter(is_active=True).order_by('order', '-created_at')[:4]),
            'idx:products': lambda: list(Product.objects.all().order_by('-id')[:3]),
            'idx:members': lambda: list(AssociationMember.objects.all().order_by('id')[:50]),
            'idx:member_benefits': lambda: list(MemberBenefit.objects.filter(is_active=True).order_by('order', '-created_at')[:6]),
            'idx:president': President.objects.first,
            'idx:partners': lambda: list(Partner.objects.all().order_by('name')),
            'idx:upcoming_events': lambda: list(Event.objects.filter(
                date__gte=timezone.now()
            ).select_related('created_by').order_by('date')[:6]),
        }
        sections = cache.get_many(loaders)
        for key, loader in loaders.items():
            if key not in sections:  # A cached None (no president) is still a hit.
                sections[key] = loader()
                cache.set(key, sections[key], 300 if key == 'idx:upcoming_events' else 3600)
        for name in ('core_products', 'products', 'members', 'member_benefits', 'president', 'upcoming_events'):
            context[name] = sections['idx:' + name]

        # Партнёры — кэшируем весь список, пагинируем в памяти
        all_partners = sections['idx:partners']
        paginator = Paginator(all_partners, 12)
        page = self.request.GET.get('partners_page') or 1
        partners_page = paginator.get_page(page)
        context['partners'] = partners_page.object_list
        context['partners_page_obj'] = partners_page

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

    # One aggregate per table instead of one round trip per counter.
    stats = {}
    stats.update(User.objects.aggregate(
        user_total=Count('pk'),
        user_active=Count('pk', filter=Q(membership_status='active')),
        user_partners=Count('pk', filter=Q(is_partner=True)),
        user_staff=Count('pk', filter=Q(is_staff=True)),
        user_president=Count('pk', filter=Q(is_president=True)),
        user_verified=Count('pk', filter=Q(is_verified=True)),
        user_new_7d=Count('pk', filter=Q(date_joined__gte=d7)),
        user_new_30d=Count('pk', filter=Q(date_joined__gte=d30)),
        user_tg_linked=Count('pk', filter=Q(telegram_chat_id__isnull=False) & ~Q(telegram_chat_id=0)),
    ))
    stats.update(Post.objects.aggregate(
        post_total=Count('pk'),
        post_published=Count('pk', filter=Q(status='published')),
        post_pending=Count('pk', filter=Q(status='pending')),
        post_new_7d=Count('pk', filter=Q(created_at__gte=d7)),
    ))
    stats.update(Comment.objects.aggregate(
        comment_total=Count('pk'),
    ))
    stats.update(Like.objects.aggregate(
        like_total=Count('pk'),
    ))
    stats.update(Visit.objects.aggregate(
        visit_total=Count('pk'),
        visit_7d=Count('pk', filter=Q(timestamp__gte=d7)),
        visit_30d=Count('pk', filter=Q(timestamp__gte=d30)),
        visit_verified=Count('pk', filter=Q(pin_verified=True)),
    ))
    stats.update(AccountChangeRequest.objects.aggregate(
        acr_pending=Count('pk', filter=Q(status='pending')),
        acr_approved=Count('pk', filter=Q(status='approved')),
        acr_rejected=Count('pk', filter=Q(status='rejected')),
        acr_total=Count('pk'),
    ))
    stats.update(Notification.objects.aggregate(
        notif_total=Count('pk'),
        notif_unread=Count('pk', filter=Q(is_read=False)),
    ))

    # Recent activity (last 5 of each)
    recent_acr    = AccountChangeRequest.objects.select_related('user').order_by('-created_at')[:5]
    recent_users  = User.objects.order_by('-date_joined')[:5]
    recent_posts  = Post.objects.select_related('author').order_by('-created_at')[:5]
    recent_visits = Visit.objects.select_related('member', 'partner').order_by('-timestamp')[:5]

    return render(request, 'core/admin_analytics.html', {
        'stats': stats,
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