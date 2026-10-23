"""Shared navigation must expose the same actions across breakpoints."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from blog.models import Event, Post
from notifications.models import Notification
from users.models import Partner


class MobileNavigationTests(TestCase):
    def test_guest_uses_one_search_dialog_and_identical_language_options(self):
        response = self.client.get(reverse('core:home'))
        self.assertContains(response, 'id="siteSearchModal"', count=1)
        self.assertContains(response, 'id="global-community-search"', count=1)
        self.assertContains(response, 'data-bs-target="#siteSearchModal"', count=2)
        self.assertContains(response, 'id="mobile-language-select"', count=1)
        self.assertContains(response, 'hx-sync="this:replace"')
        self.assertContains(response, 'js/site-search.js')
        self.assertNotContains(response, 'data-notification-badge')

    def test_member_has_mobile_cabinet_notifications_and_account_actions(self):
        user = get_user_model().objects.create_user(username='mobile-member')
        self.client.force_login(user)
        response = self.client.get(reverse('core:home'))
        mobile = response.content.decode().split('class="iesa-nav-actions')[0]
        for name in ('dashboard', 'profile_edit'):
            self.assertIn(f'href="{reverse("users:" + name)}"', mobile)
        self.assertIn(f'href="{reverse("notifications:notification_list")}"', mobile)
        self.assertContains(response, 'data-notification-badge', count=4)  # Three badges plus the JS selector.
        for badge in ('navbar-notif-badge', 'navbar-notif-badge-mob', 'bottom-nav-notif-badge'):
            self.assertContains(response, f'id="{badge}"', count=1)
        self.assertNotIn('data-theme-toggle', mobile)

    def test_partner_and_superuser_actions_are_available_in_mobile_menu(self):
        user = get_user_model().objects.create_user(username='mobile-partner', is_partner=True, is_superuser=True, is_staff=True)
        Partner.objects.create(user=user, company_name='Parity Partner', business_type='other')
        Notification.objects.create(recipient=user, notification_type='system', title='Unread')
        self.client.force_login(user)
        response = self.client.get(reverse('core:home'))
        mobile = response.content.decode().split('class="iesa-nav-actions')[0]
        for name in ('partner_dashboard', 'partner_profile_edit'):
            self.assertIn(f'href="{reverse("users:" + name)}"', mobile)
        self.assertIn('data-theme-toggle', mobile)
        self.assertContains(response, 'id="navbar-notif-badge-mob" class="notif-dot" data-notification-badge >1</span>')

    def test_mobile_language_form_preserves_current_page(self):
        response = self.client.post(reverse('set_language'), {'language': 'fr', 'next': '/blog/events/?status=all'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/blog/events/?status=all')
        self.assertEqual(response.cookies['django_language'].value, 'fr')

    def test_blog_mobile_filters_serialize_status_and_sort_and_filter_own_posts(self):
        user = get_user_model().objects.create_user(username='mobile-filter-author')
        Post.objects.create(author=user, title='Parity pending', text='Text', status='pending')
        Post.objects.create(author=user, title='Parity published', text='Text', status='published')
        self.client.force_login(user)
        page = self.client.get(reverse('blog:post_list'))
        self.assertContains(page, 'id="mob-status" name="status"')
        self.assertContains(page, 'id="mob-sort" name="sort"')
        self.assertContains(page, 'hx-include="#mob-status, #post-search-input"')
        filtered = self.client.get(reverse('blog:post_search'), {'q': 'Parity', 'status': 'pending', 'sort': 'popular'}, HTTP_HX_REQUEST='true')
        self.assertContains(filtered, 'Parity pending')
        self.assertNotContains(filtered, 'Parity published')

    def test_event_filters_keep_status_and_order_for_htmx_results(self):
        now = timezone.now()
        Event.objects.create(title='Parity event Z future', description='Text', date=now + timedelta(days=1), location='Online')
        Event.objects.create(title='Parity event A past', description='Text', date=now - timedelta(days=1), location='Online', status='completed')
        page = self.client.get(reverse('blog:event_list'))
        self.assertContains(page, 'cmd-bar--events')
        all_events = self.client.get(reverse('blog:event_list'), {'search': 'Parity event', 'status': 'all', 'sort': 'title'}, HTTP_HX_REQUEST='true')
        self.assertEqual([event.title for event in all_events.context['events']], ['Parity event A past', 'Parity event Z future'])
        past = self.client.get(reverse('blog:event_list'), {'search': 'Parity event', 'status': 'past'}, HTTP_HX_REQUEST='true')
        self.assertEqual([event.title for event in past.context['events']], ['Parity event A past'])
