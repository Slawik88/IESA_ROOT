from django.test import TestCase
from django.urls import reverse

from .models import Product


class ProductListTests(TestCase):
    def test_empty_catalog_does_not_claim_fake_preparation_progress(self):
        response = self.client.get(reverse('products:product_list'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-progress="65"')
        self.assertContains(response, reverse('core:benefits'))

    def test_catalog_pagination_uses_stable_newest_first_order(self):
        older = Product.objects.create(
            name='Older product', description='First', price='10.00', image='products/older.png'
        )
        newer = Product.objects.create(
            name='Newer product', description='Second', price='20.00', image='products/newer.png'
        )

        response = self.client.get(reverse('products:product_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['products']), [newer, older])
