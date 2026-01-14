"""Views для работы с событиями"""

from django.views.generic import ListView, DetailView
from ..models import Event
from ..constants import EVENTS_PER_PAGE


class EventListView(ListView):
    """Список предстоящих событий"""
    model = Event
    template_name = 'blog/event_list.html'
    context_object_name = 'events'
    paginate_by = EVENTS_PER_PAGE
    
    def get_queryset(self):
        return Event.objects.select_related('created_by').order_by('-date')


class EventDetailView(DetailView):
    """Детальная страница события"""
    model = Event
    template_name = 'blog/event_detail.html'
    context_object_name = 'event'
