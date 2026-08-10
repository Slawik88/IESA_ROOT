from django.test import TestCase
from django.urls import reverse

from .models import Photo


class GalleryResilienceTests(TestCase):
    def test_gallery_renders_immediate_count_and_missing_image_fallback(self):
        Photo.objects.create(image='gallery/missing-preview.jpg', caption='Preview')

        response = self.client.get(reverse('gallery:gallery'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span>1</span>', html=False)
        self.assertContains(response, 'row-cols-1 row-cols-sm-2')
        self.assertContains(response, 'gallery-card__fallback')
        self.assertContains(response, 'markMissing')
