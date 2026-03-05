from django.views.generic import TemplateView
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from products.models import Product
from core.models import Partner, AssociationMember, President, SocialNetwork, CoreProduct, MemberBenefit, AdminAppeal
from blog.models import Event
from django.shortcuts import get_object_or_404, render, redirect
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.translation import gettext as _


def submit_appeal(request):
    """Handle admin appeal form submission. Works with HTMX and plain POST."""
    if request.method != 'POST':
        return redirect('core:home')

    name    = request.POST.get('appeal_name', '').strip()
    email   = request.POST.get('appeal_email', '').strip()
    reason  = request.POST.get('appeal_reason', 'other')
    message = request.POST.get('appeal_message', '').strip()
    req_url = request.POST.get('appeal_requested_url', '').strip()

    errors = []
    if not name:
        errors.append(_('Please enter your name.'))
    if not email or '@' not in email:
        errors.append(_('Please enter a valid e-mail address.'))
    if not message or len(message) < 20:
        errors.append(_('Message must be at least 20 characters.'))

    is_htmx = request.headers.get('HX-Request') == 'true'

    if errors:
        if is_htmx:
            return render(request, 'partials/admin_appeal_form.html', {
                'appeal_errors': errors,
                'appeal_name': name,
                'appeal_email': email,
                'appeal_reason': reason,
                'appeal_message': message,
                'appeal_requested_url': req_url,
            })
        from django.contrib import messages as dj_messages
        for e in errors:
            dj_messages.error(request, e)
        return redirect(request.META.get('HTTP_REFERER', 'core:home'))

    AppealUser = request.user if request.user.is_authenticated else None
    AdminAppeal.objects.create(
        user=AppealUser,
        name=name,
        email=email,
        reason=reason,
        message=message,
        requested_url=req_url,
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
        
        # 1. Основные продукты IESA (ВЫШЕ событий на главной)
        context['core_products'] = CoreProduct.objects.filter(is_active=True).order_by('order', '-created_at')[:4]
        
        # 2. Продукты (предположим, 3 последних)
        context['products'] = Product.objects.all().order_by('-id')[:3]
        
        # 3. Президент (отдельная модель)
        try:
            context['president'] = President.objects.first()
        except President.DoesNotExist:
            context['president'] = None
        
        # 4. Члены ассоциации (limit 50 — board/team section on homepage)
        context['members'] = AssociationMember.objects.all().order_by('id')[:50]
        
        # 5. Партнеры с пагинацией
        partners_qs = Partner.objects.all().order_by('name')
        paginator = Paginator(partners_qs, 12)
        page = self.request.GET.get('partners_page') or 1
        partners_page = paginator.get_page(page)
        context['partners'] = partners_page.object_list
        context['partners_page_obj'] = partners_page
        
        # 6. Ближайшие события (максимум 6 для главной)
        upcoming_events = Event.objects.filter(
            date__gte=timezone.now()
        ).select_related('created_by').order_by('date')[:6]
        context['upcoming_events'] = upcoming_events
        
        # 7. Преимущества членства (Top 6 для главной)
        context['member_benefits'] = MemberBenefit.objects.filter(is_active=True).order_by('order', '-created_at')[:6]
        
        return context