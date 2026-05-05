from django.views.generic import TemplateView
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
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