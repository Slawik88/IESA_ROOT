from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Post, Event


User = get_user_model()


class PostCreationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='user1', password='pass12345')

    def test_anonymous_redirected_from_post_create(self):
        url = reverse('blog:post_create')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login', resp.url)

    def test_authenticated_user_can_create_post_pending_status(self):
        url = reverse('blog:post_create')
        self.client.force_login(self.user)
        payload = {
            'title': 'Test post',
            'text': 'Hello world',
        }
        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('blog:post_list'))

        post = Post.objects.get()
        self.assertEqual(post.author, self.user)
        self.assertEqual(post.status, 'pending')
        self.assertEqual(post.title, 'Test post')


class EventAccessTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(
            title='Demo event',
            description='Only admins create events',
            date=timezone.now(),
            location='Online',
            status='upcoming',
        )

    def test_event_list_accessible(self):
        resp = self.client.get(reverse('blog:event_list'))
        self.assertEqual(resp.status_code, 200)

    def test_event_detail_accessible(self):
        resp = self.client.get(reverse('blog:event_detail', args=[self.event.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_event_create_route_absent(self):
        # Обычные пользователи не должны иметь маршрут создания события
        resp_get = self.client.get('/blog/events/create/')
        resp_post = self.client.post('/blog/events/create/', {})
        self.assertEqual(resp_get.status_code, 404)
        self.assertEqual(resp_post.status_code, 404)
