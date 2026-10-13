"""Performance budgets for the homepage cache and staff counters."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from products.models import Product
from .views import IndexView, admin_analytics


class HomepageCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def homepage(self):
        view = IndexView()
        view.setup(RequestFactory().get('/'))
        return view.get_context_data()

    def test_warm_database_cache_needs_one_query_including_absent_president(self):
        self.assertIsNone(self.homepage()['president'])
        with self.assertNumQueries(1):
            context = self.homepage()
        self.assertIsNone(context['president'])
        self.assertEqual(context['products'], [])

    def test_product_updates_invalidate_homepage_cache(self):
        self.homepage()
        product = Product.objects.create(name='First', description='Description', price='10.00')
        self.assertEqual(self.homepage()['products'][0].name, 'First')
        product.name = 'Updated'
        product.save()
        self.assertEqual(self.homepage()['products'][0].name, 'Updated')
        product.delete()
        self.assertEqual(self.homepage()['products'], [])


class AnalyticsQueryTests(TestCase):
    def test_counters_use_seven_queries_and_keep_their_values(self):
        user = get_user_model().objects.create_user(username='perf-staff', is_staff=True)
        request = RequestFactory().get('/')
        request.user = user
        with patch('core.views.render', return_value=HttpResponse()) as render:
            with self.assertNumQueries(7):
                admin_analytics(request)
        stats = render.call_args.args[2]['stats']
        self.assertEqual(stats['user_total'], 1)
        self.assertEqual(stats['user_staff'], 1)
        self.assertEqual(stats['user_new_7d'], 1)
        self.assertEqual(stats['user_tg_linked'], 0)
        self.assertEqual(stats['post_total'], 0)
        self.assertEqual(stats['visit_total'], 0)
        self.assertEqual(stats['acr_total'], 0)
        self.assertEqual(stats['notif_total'], 0)
