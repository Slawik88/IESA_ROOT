from django.views.generic import ListView
from .models import Photo

class GalleryView(ListView):
    """
    Отображение всех фотографий в галерее.
    """
    model = Photo
    template_name = 'gallery/gallery.html'
    context_object_name = 'photos'
    paginate_by = 20 # Пагинация для больших галерей