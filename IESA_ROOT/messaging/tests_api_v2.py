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

    def test_group_creation_and_message_lifecycle(self):
        """Full group flow: create group, send, edit, delete, mark read."""
        self.client.force_login(self.user1)

        # Create group
        create_group_url = reverse('messaging:api_create_group')
        resp_group = self.client.post(
            create_group_url,
            data=json.dumps({'name': 'My Group', 'participant_ids': [self.user2.id]}),
            content_type='application/json'
        )
        self.assertEqual(resp_group.status_code, 200)
        data_group = resp_group.json()
        self.assertTrue(data_group.get('success'))
        conv_id = data_group['data']['conversation_id']

        # Send message
        send_url = reverse('messaging:api_send_message', kwargs={'conversation_id': conv_id})
        resp_send = self.client.post(
            send_url,
            data=json.dumps({'text': 'group hi'}),
            content_type='application/json'
        )
        self.assertEqual(resp_send.status_code, 200)
        msg_id = resp_send.json()['data']['message']['id']

        # Edit message
        edit_url = reverse('messaging:api_edit_message', kwargs={'message_id': msg_id})
        resp_edit = self.client.post(
            edit_url,
            data=json.dumps({'text': 'group hi edited'}),
            content_type='application/json'
        )
        self.assertEqual(resp_edit.status_code, 200)

        # Mark read (by self no-op, but should succeed)
        mark_url = reverse('messaging:api_mark_read', kwargs={'message_id': msg_id})
        resp_mark = self.client.post(mark_url)
        self.assertEqual(resp_mark.status_code, 200)

        # Delete message (soft delete)
        delete_url = reverse('messaging:api_delete_message', kwargs={'message_id': msg_id})
        resp_del = self.client.post(
            delete_url,
            data=json.dumps({'for_everyone': True}),
            content_type='application/json'
        )
        self.assertEqual(resp_del.status_code, 200)

    def test_search_requires_auth(self):
        url = reverse('messaging:api_search_users') + '?q=x'
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [302, 401, 403])

    def test_get_messages_denies_non_participant(self):
        self.client.force_login(self.user1)
        # create conversation with user2
        conv = Conversation.objects.create(creator=self.user1, is_group=False)
        conv.participants.add(self.user1, self.user2)
        # try as another user
        intruder = User.objects.create_user(username='hacker', password='pass1234')
        self.client.force_login(intruder)
        url = reverse('messaging:api_messages', kwargs={'conversation_id': conv.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)
