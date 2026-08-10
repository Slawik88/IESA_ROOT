import os
import django
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import translation

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

User = get_user_model()


class ProfileQRAndSearchTests(TestCase):
    def setUp(self):
        # create a test user
        self.user = User.objects.create_user(username='testuser1', email='testuser1@example.com', password='testpass')
        self.user.card_active = True
        self.user.save()
        self.client = Client()

    def test_profile_contains_qr(self):
        # QR is intentionally visible only to the profile owner and is served
        # by the protected dynamic endpoint, not a legacy media/cards path.
        self.client.force_login(self.user)
        resp = self.client.get(f'/auth/user/{self.user.username}/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        self.assertIn(reverse('users:user_qr', kwargs={'permanent_id': self.user.permanent_id}), content)

    def test_user_search_returns_user(self):
        resp = self.client.get('/auth/search/', {'q': 'testuser1'})
        # search endpoint supports GET; ensure response OK (200) and contains username or email
        self.assertEqual(resp.status_code, 200)
        self.assertTrue('testuser1' in resp.content.decode('utf-8') or 'testuser1@example.com' in resp.content.decode('utf-8'))

    def test_empty_member_search_shows_prompt_instead_of_empty_query_error(self):
        with translation.override('en'):
            resp = self.client.get(reverse('users:users_search'))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Find a member')
        self.assertNotContains(resp, 'No results for ""')

    def test_member_search_controls_stack_cleanly_on_mobile(self):
        resp = self.client.get(reverse('users:users_search'))

        self.assertContains(resp, 'member-search-group')
        self.assertContains(resp, 'member-search-sort')
