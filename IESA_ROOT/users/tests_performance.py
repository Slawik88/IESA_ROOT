"""Regression budgets for user activity and profile cards."""
from datetime import timedelta
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone
from django.urls import reverse

from blog.models import Comment, Like, Post
from .middleware import LastOnlineMiddleware
from .models import User
from .views.profile import ProfileView, _get_public_profile_context
from .search_utils import highlight_text
from .constants import PROFILE_POSTS_PER_PAGE


class ActivityQueryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='activity-budget')
        self.request = RequestFactory().get('/')
        self.request.user = self.user
        self.middleware = LastOnlineMiddleware(lambda request: HttpResponse())

    def test_fresh_activity_needs_no_database_or_cache_queries(self):
        self.user.last_online = timezone.now()
        with self.assertNumQueries(0):
            self.middleware(self.request)

    def test_stale_activity_uses_one_write_without_user_save_signals(self):
        old = timezone.now() - timedelta(minutes=6)
        User.objects.filter(pk=self.user.pk).update(last_online=old)
        self.user.last_online = old
        with patch('users.signals.generate_qr_code_for_user') as generate_qr:
            with self.assertNumQueries(1):
                self.middleware(self.request)
            generate_qr.assert_not_called()
        self.user.refresh_from_db()
        self.assertGreater(self.user.last_online, old)

    def test_concurrent_request_does_not_overwrite_recent_activity(self):
        recent = timezone.now()
        User.objects.filter(pk=self.user.pk).update(last_online=recent)
        self.user.last_online = recent - timedelta(minutes=6)
        self.middleware(self.request)
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_online, recent)


class ProfileCardQueryTests(TestCase):
    def test_public_profile_paginates_published_posts_by_username_and_card(self):
        user = User.objects.create_user(username='public-page-budget')
        for number in range(PROFILE_POSTS_PER_PAGE + 1):
            Post.objects.create(author=user, title=f'Published {number}', text='Text', status='published')
        Post.objects.create(author=user, title='Private draft', text='Secret', status='draft')
        for url in (f'/auth/user/{user.username}/', reverse('users:profile_by_card', args=[user.permanent_id])):
            with self.subTest(url=url):
                first = self.client.get(url)
                self.assertEqual(first.status_code, 200)
                self.assertEqual(len(first.context['user_posts']), PROFILE_POSTS_PER_PAGE)
                self.assertTrue(first.context['page_obj'].has_next())
                second = self.client.get(url, {'page': 2})
                self.assertEqual(len(second.context['user_posts']), 1)
                self.assertNotContains(second, 'Private draft')

    def test_profile_cards_load_counts_without_related_objects(self):
        user = User.objects.create_user(username='profile-budget', onboarded=True)
        post = Post.objects.create(author=user, title='Card', text='Text', status='published')
        Like.objects.create(post=post, user=user)
        Comment.objects.create(post=post, author=user, text='Comment')
        request = RequestFactory().get('/')
        request.user = user
        view = ProfileView()
        view.setup(request)
        view.object = user
        context = view.get_context_data()
        with self.assertNumQueries(1):
            cards = list(context['user_posts'])
            self.assertEqual((cards[0].likes_count, cards[0].comments_count), (1, 1))
            self.assertEqual(cards[0].author.username, user.username)
        public = _get_public_profile_context(user)
        with self.assertNumQueries(1):
            self.assertEqual(len(list(public['user_posts'])), 1)


class SearchHighlightTests(SimpleTestCase):
    def test_entities_and_user_markup_are_escaped_without_matching_generated_tags(self):
        self.assertEqual(highlight_text('Tom & Jerry', '& Jerry'), 'Tom <mark>&amp;</mark> <mark>Jerry</mark>')
        self.assertEqual(highlight_text('<script>mark</script>', 'script mark'),
                         '&lt;<mark>script</mark>&gt;<mark>mark</mark>&lt;/<mark>script</mark>&gt;')

    def test_overlapping_tokens_do_not_create_nested_marks(self):
        self.assertEqual(highlight_text('Mark MARK', 'Mark mar'), '<mark>Mark</mark> <mark>MARK</mark>')
        self.assertEqual(highlight_text('<b>', '  '), '&lt;b&gt;')
