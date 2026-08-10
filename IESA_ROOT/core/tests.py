from django.test import TestCase
from django.urls import reverse


class PublicShellRegressionTests(TestCase):
    def test_homepage_critical_counters_are_visible_without_javascript_delay(self):
        response = self.client.get(reverse('core:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span class="cnt" data-count="6">6</span>', html=False)
        self.assertNotContains(response, 'Hero counters')

    def test_homepage_contains_only_one_partner_modal_target(self):
        response = self.client.get(reverse('core:home'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.count(b'id="partnerModal"'), 1)
        self.assertEqual(response.content.count(b'id="partner-modal-body"'), 1)

    def test_partner_map_has_page_heading(self):
        response = self.client.get(reverse('core:partners_map'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1 class="map-hero-title">', html=False)
