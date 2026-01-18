import json
from django.test import TestCase
from django.urls import reverse
from users.models import User
from messaging.models import Conversation, Message


class MessagingAPIV2Tests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass1234')
        self.user2 = User.objects.create_user(username='user2', password='pass1234')

    def test_conversations_requires_auth(self):
        url = reverse('messaging:api_conversations')
        response = self.client.get(url)
        # login_required -> redirect to login (302). Some setups may return 401 if custom middleware.
        self.assertIn(response.status_code, [302, 401, 403])

    def test_search_users_returns_results(self):
        self.client.force_login(self.user1)
        url = reverse('messaging:api_search_users') + '?q=user2'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertIsInstance(data.get('data', {}).get('users'), list)
        # Should find user2 by username
        usernames = [u.get('username') for u in data['data']['users']]
        self.assertIn('user2', usernames)

    def test_create_conversation_and_send_message(self):
        self.client.force_login(self.user1)
        create_url = reverse('messaging:api_create_conversation')
        resp_create = self.client.post(
            create_url,
            data=json.dumps({'participant_id': self.user2.id}),
            content_type='application/json'
        )
        self.assertEqual(resp_create.status_code, 200)
        data_create = resp_create.json()
        self.assertTrue(data_create.get('success'))
        conv_id = data_create['data']['conversation_id']

        send_url = reverse('messaging:api_send_message', kwargs={'conversation_id': conv_id})
        resp_send = self.client.post(
            send_url,
            data=json.dumps({'text': 'hello'}),
            content_type='application/json'
        )
        self.assertEqual(resp_send.status_code, 200)
        data_send = resp_send.json()
        self.assertTrue(data_send.get('success'))

        messages_url = reverse('messaging:api_messages', kwargs={'conversation_id': conv_id})
        resp_msgs = self.client.get(messages_url)
        self.assertEqual(resp_msgs.status_code, 200)
        data_msgs = resp_msgs.json()
        self.assertTrue(data_msgs.get('success'))
        msgs = data_msgs['data'].get('messages', [])
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]['text'], 'hello')
