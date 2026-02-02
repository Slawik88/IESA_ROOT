from django.views.generic import TemplateView
from products.models import Product
from core.models import Partner, AssociationMember, President, SocialNetwork, CoreProduct, MemberBenefit
from blog.models import Event
from django.shortcuts import get_object_or_404, render
from django.core.paginator import Paginator
from django.utils import timezone


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
        
        # 4. Члены ассоциации
        context['members'] = AssociationMember.objects.all().order_by('id')
        
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
        ).order_by('date')[:6]
        context['upcoming_events'] = upcoming_events
        
        return context