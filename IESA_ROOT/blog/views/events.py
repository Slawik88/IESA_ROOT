"""Views для работы с событиями"""

from django.views.generic import ListView, DetailView
from django.db.models import Q, Count
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.utils.translation import gettext as _
from ..models import Event, EventRegistration
from ..constants import EVENTS_PER_PAGE


class EventListView(ListView):
    """
    Список предстоящих событий с HTMX поддержкой.
    
    ВНИМАНИЕ: создание событий ТОЛЬКО через админку (is_staff=True или has_perm)
    
    Поддерживает:
    - Фильтрация по статусу (?status=upcoming/past/all)
    - Поиск по названию (?search=)
    - Сортировка (?sort=date/-date/title)
    - Бесконечный скролл через HTMX с кэшированием
    """
    model = Event
    template_name = 'blog/event_list.html'
    context_object_name = 'events'
    paginate_by = EVENTS_PER_PAGE
    
    def get_queryset(self):
        queryset = Event.objects.select_related('created_by').annotate(
            participants_confirmed=Count('registrations', filter=Q(registrations__status='confirmed'), distinct=True)
        )
        
        # Annotate with user registration status if authenticated
        if self.request.user.is_authenticated:
            queryset = queryset.annotate(
                user_registered=Count(
                    'registrations',
                    filter=Q(registrations__user=self.request.user),
                    distinct=True
                )
            )
        
        # Фильтр по статусу (upcoming/past/all)
        status = self.request.GET.get('status', 'upcoming')
        now = timezone.now()
        if status == 'upcoming':
            queryset = queryset.filter(date__gte=now)
        elif status == 'past':
            queryset = queryset.filter(date__lt=now)
        # 'all' - без фильтра
        
        # Фильтр по категории
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Поиск по названию и описанию
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        
        # Сортировка
        sort = self.request.GET.get('sort', 'date')
        if status == 'past':
            sort = '-date'  # Прошедшие - сначала новые
        allowed_sorts = ['date', '-date', 'title', '-title']
        if sort in allowed_sorts:
            queryset = queryset.order_by(sort)
        else:
            queryset = queryset.order_by('date')
        
        return queryset
    
    def get_template_names(self):
        """Возвращает partial шаблон для HTMX запросов"""
        if self.request.headers.get('HX-Request'):
            return ['blog/partials/event_list_items.html']
        return [self.template_name]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Передаём текущие фильтры в контекст
        context['category'] = self.request.GET.get('category', '')
        context['search'] = self.request.GET.get('search', '')
        context['status'] = self.request.GET.get('status', 'upcoming')
        context['sort'] = self.request.GET.get('sort', 'date')
        
        # Пагинация для infinite scroll
        page_obj = context.get('page_obj')
        if page_obj:
            context['has_next'] = page_obj.has_next()
            if page_obj.has_next():
                context['next_page'] = page_obj.next_page_number()
        
        return context
    
    def render_to_response(self, context, **response_kwargs):
        """Добавляет заголовки кэширования для HTMX запросов"""
        response = super().render_to_response(context, **response_kwargs)
        
        # Кэш на 5 минут для списка событий
        if self.request.headers.get('HX-Request'):
            response['Cache-Control'] = 'public, max-age=300'
        
        return response


class EventDetailView(DetailView):
    """Детальная страница события"""
    model = Event
    template_name = 'blog/event_detail.html'
    context_object_name = 'event'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            # Check if user is already registered
            context['is_registered'] = EventRegistration.objects.filter(
                event=self.object,
                user=self.request.user
            ).exists()
        else:
            context['is_registered'] = False
        return context


@login_required
def event_register(request, pk):
    """Register authenticated user for an event"""
    event = get_object_or_404(Event, pk=pk)
    
    # Check if already registered
    registration, created = EventRegistration.objects.get_or_create(
        event=event,
        user=request.user,
        defaults={'status': 'confirmed'}
    )
    
    if created:
        messages.success(
            request,
            _('You have successfully registered for the event! An administrator will contact you soon to confirm your participation.')
        )
    else:
        messages.info(
            request,
            _('You are already registered for this event.')
        )
    
    return redirect('blog:event_detail', pk=event.pk)
