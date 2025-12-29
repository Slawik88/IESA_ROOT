from django.views.generic import TemplateView
from products.models import Product
from core.models import Partner, AssociationMember, President
from django.shortcuts import get_object_or_404, render
from django.core.paginator import Paginator


def partner_detail(request, pk):
    """Return partner details as an HTMX partial for modal display."""
    partner = get_object_or_404(Partner, pk=pk)
    return render(request, 'core/htmx/partner_modal.html', {'partner': partner})

class IndexView(TemplateView):
    """
    Главная страница, отображающая данные из разных приложений.
    """
    template_name = 'core/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # 1. Продукты (предположим, 3 последних)
        context['products'] = Product.objects.all().order_by('-id')[:3]
        
        # 2. Президент (отдельная модель)
        try:
            context['president'] = President.objects.first()
        except President.DoesNotExist:
            context['president'] = None
        
        # 3. Члены ассоциации
        context['members'] = AssociationMember.objects.all().order_by('id')
        
        # 4. Партнеры с пагинацией
        partners_qs = Partner.objects.all().order_by('name')
        paginator = Paginator(partners_qs, 12)
        page = self.request.GET.get('partners_page') or 1
        partners_page = paginator.get_page(page)
        context['partners'] = partners_page.object_list
        context['partners_page_obj'] = partners_page
        
        return context