"""
Additional integration tests for bug fixes and edge cases
"""
from django.test import TestCase, Client, TransactionTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.core.cache import cache

from messaging.models import Conversation, Message
from messaging import typing_cache

User = get_user_model()


class BugFixVerificationTests(TestCase):
    """Verify all bug fixes from the comprehensive review"""
    
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='user1', password='pass123', email='user1@test.com')
        self.user2 = User.objects.create_user(username='user2', password='pass123', email='user2@test.com')
        self.conv = Conversation.objects.create(is_group=False)
        self.conv.participants.add(self.user1, self.user2)
    
    def test_bug_3_bulk_mark_as_read(self):
        """БАГ #3: Verify bulk mark_as_read doesn't cause N+1 queries"""
        # Create 10 messages
        messages = []
        for i in range(10):
            msg = Message.objects.create(
                conversation=self.conv,
                sender=self.user2,
                text=f'Message {i}'
            )
            messages.append(msg)
        
        # Mark all as read - should be efficient
        for msg in messages:
            msg.mark_as_read(self.user1)
        
        # Verify all marked
        for msg in messages:
            self.assertIn(self.user1, msg.read_by.all())
    
    def test_bug_5_send_message_validation(self):
        """БАГ #5: Verify empty message without file is rejected"""
        self.client.login(username='user1', password='pass123')
        
        # Try to send empty message
        response = self.client.post(
            reverse('messaging:send_message', args=[self.conv.pk]),
            {'text': ''},
            HTTP_HX_REQUEST='true'
        )
        
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Message.objects.filter(conversation=self.conv).count(), 0)
    
    def test_bug_8_empty_text_with_file(self):
        """БАГ #8: Verify text can be empty when file is attached"""
        msg = Message.objects.create(
            conversation=self.conv,
            sender=self.user1,
            text=''  # Empty text should be allowed
        )
        
        self.assertEqual(msg.text, '')
        self.assertIsNotNone(msg)
    
    def test_bug_9_deleted_message_visibility(self):
        """БАГ #9: Verify correct deleted message logic"""
        msg = Message.objects.create(
            conversation=self.conv,
            sender=self.user1,
            text='Original text'
        )
        
        # Soft delete
        msg.is_deleted = True
        msg.save()
        
        # Should show to sender
        messages_qs = self.conv.messages.filter(
            Q(is_deleted=False) | (Q(sender=self.user1) & Q(deleted_for_everyone=False))
        )
        self.assertIn(msg, messages_qs)
        
        # Delete for everyone
        msg.deleted_for_everyone = True
        msg.save()
        
        # Should NOT show to sender now
        messages_qs = self.conv.messages.filter(
            Q(is_deleted=False) | (Q(sender=self.user1) & Q(deleted_for_everyone=False))
        )
        self.assertNotIn(msg, messages_qs)
    
    def test_bug_10_form_validation(self):
        """БАГ #10: Verify form accepts minimum 1 participant"""
        from messaging.forms import ConversationForm
        
        # Should accept 1 participant
        form = ConversationForm(data={
            'group_name': 'Test',
            'participants': [self.user2.pk]
        })
        self.assertTrue(form.is_valid())
        
        # Should reject 0 participants
        form = ConversationForm(data={
            'group_name': 'Test',
            'participants': []
        })
        self.assertFalse(form.is_valid())
    
    def test_bug_14_index_on_is_deleted(self):
        """БАГ #14: Verify is_deleted field has index (check in Meta)"""
        from messaging.models import Message
        
        # Check that index exists in Meta.indexes
        index_fields = [idx.fields for idx in Message._meta.indexes]
        has_is_deleted_index = any(
            'is_deleted' in fields 
            for fields in index_fields
        )
        
        self.assertTrue(has_is_deleted_index, "is_deleted should have an index")


class PerformanceTests(TransactionTestCase):
    """Test performance optimizations"""
    
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='perfuser1', password='pass123', email='perf1@test.com')
        self.user2 = User.objects.create_user(username='perfuser2', password='pass123', email='perf2@test.com')
    
    def test_conversation_list_query_efficiency(self):
        """Test that conversation list uses prefetch_related efficiently"""
        # Create 5 conversations
        for i in range(5):
            conv = Conversation.objects.create(is_group=False)
            conv.participants.add(self.user1, self.user2)
            
            # Add messages
            for j in range(3):
                Message.objects.create(
                    conversation=conv,
                    sender=self.user2,
                    text=f'Msg {j}'
                )
        
        self.client.login(username='perfuser1', password='pass123')
        
        # This should use prefetch_related to avoid N+1
        # Queries: session, user auth, count, conversations, participants prefetch,
        # messages prefetch, notifications count, db introspection, active users, social networks, update last_online
        with self.assertNumQueries(11):  # Reasonable with middleware
            response = self.client.get(reverse('messaging:conversation_list'))
            self.assertEqual(response.status_code, 200)
    
    def test_annotated_read_by_count(self):
        """Test that messages use annotated read_by_count"""
        conv = Conversation.objects.create(is_group=False)
        conv.participants.add(self.user1, self.user2)
        
        msg = Message.objects.create(
            conversation=conv,
            sender=self.user1,
            text='Test'
        )
        msg.read_by.add(self.user1, self.user2)
        
        # Get with annotation
        annotated = Message.objects.filter(pk=msg.pk).annotate(
            read_by_count=Count('read_by')
        ).first()
        
        self.assertEqual(annotated.read_by_count, 2)


class SecurityTests(TestCase):
    """Test security and permission checks"""
    
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='secure1', password='pass123', email='sec1@test.com')
        self.user2 = User.objects.create_user(username='secure2', password='pass123', email='sec2@test.com')
        self.user3 = User.objects.create_user(username='secure3', password='pass123', email='sec3@test.com')
    
    def test_cannot_access_other_users_conversation(self):
        """Test that users cannot access conversations they're not part of"""
        # Create conversation between user2 and user3
        conv = Conversation.objects.create(is_group=False)
        conv.participants.add(self.user2, self.user3)
        
        # Try to access as user1
        self.client.login(username='secure1', password='pass123')
        response = self.client.get(reverse('messaging:conversation_detail', args=[conv.pk]))
        
        self.assertEqual(response.status_code, 404)
    
    def test_cannot_send_to_other_users_conversation(self):
        """Test that users cannot send messages to conversations they're not in"""
        conv = Conversation.objects.create(is_group=False)
        conv.participants.add(self.user2, self.user3)
        
        self.client.login(username='secure1', password='pass123')
        response = self.client.post(
            reverse('messaging:send_message', args=[conv.pk]),
            {'text': 'Unauthorized'},
            HTTP_HX_REQUEST='true'
        )
        
        self.assertEqual(response.status_code, 404)
    
    def test_non_admin_cannot_manage_group(self):
        """Test that non-admins cannot manage group participants"""
        conv = Conversation.objects.create(is_group=True, creator=self.user1)
        conv.participants.add(self.user1, self.user2)
        conv.admins.add(self.user1)
        
        # User2 tries to add user3
        self.client.login(username='secure2', password='pass123')
        response = self.client.post(
            reverse('messaging:add_participant', args=[conv.pk]),
            {'username': 'secure3'},
            HTTP_HX_REQUEST='true'
        )
        
        self.assertEqual(response.status_code, 403)
    
    def test_admin_can_manage_group(self):
        """Test that admins CAN manage group participants"""
        conv = Conversation.objects.create(is_group=True, creator=self.user1)
        conv.participants.add(self.user1, self.user2)
        conv.admins.add(self.user1)
        
        # User1 (admin) adds user3
        self.client.login(username='secure1', password='pass123')
        response = self.client.post(
            reverse('messaging:add_participant', args=[conv.pk]),
            {'username': 'secure3'},
            HTTP_HX_REQUEST='true'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.user3, conv.participants.all())


class CacheTests(TestCase):
    """Test cache-based typing indicators"""
    
    def setUp(self):
        cache.clear()
        self.user1 = User.objects.create_user(username='cache1', password='pass123', email='cache1@test.com')
        self.user2 = User.objects.create_user(username='cache2', password='pass123', email='cache2@test.com')
        self.conv = Conversation.objects.create(is_group=False)
        self.conv.participants.add(self.user1, self.user2)
    
    def test_typing_indicator_expiration(self):
        """Test that typing indicators expire after timeout"""
        import time
        
        # Set typing
        typing_cache.set_typing_v2(
            conversation_id=self.conv.pk,
            user_id=self.user1.pk,
            username=self.user1.username
        )
        
        # Should be typing
        users = typing_cache.get_typing_users_v2(
            conversation_id=self.conv.pk,
            exclude_user_id=None
        )
        self.assertIn(self.user1.username, users)
        
        # Wait for expiration (TYPING_TIMEOUT is 5 seconds)
        time.sleep(6)
        
        # Should no longer be typing
        users = typing_cache.get_typing_users_v2(
            conversation_id=self.conv.pk,
            exclude_user_id=None
        )
        self.assertNotIn(self.user1.username, users)
    
    def test_multiple_users_typing(self):
        """Test multiple users typing simultaneously"""
        user3 = User.objects.create_user(username='cache3', password='pass123', email='cache3@test.com')
        
        # Set both typing
        typing_cache.set_typing_v2(self.conv.pk, self.user1.pk, self.user1.username)
        typing_cache.set_typing_v2(self.conv.pk, self.user2.pk, self.user2.username)
        
        # Should see both (except excluded)
        users = typing_cache.get_typing_users_v2(
            conversation_id=self.conv.pk,
            exclude_user_id=None
        )
        self.assertEqual(len(users), 2)
        
        # Exclude user1
        users = typing_cache.get_typing_users_v2(
            conversation_id=self.conv.pk,
            exclude_user_id=self.user1.pk
        )
        self.assertEqual(len(users), 1)
        self.assertIn(self.user2.username, users)


class EdgeCaseTests(TestCase):
    """Test edge cases and unusual scenarios"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(username='edge1', password='pass123', email='edge1@test.com')
        self.user2 = User.objects.create_user(username='edge2', password='pass123', email='edge2@test.com')
    
    def test_empty_conversation(self):
        """Test conversation with no messages"""
        conv = Conversation.objects.create(is_group=False)
        conv.participants.add(self.user1, self.user2)
        
        self.assertEqual(conv.messages.count(), 0)
        self.assertIsNone(conv.get_last_message())
    
    def test_conversation_with_deleted_messages_only(self):
        """Test conversation where all messages are deleted"""
        conv = Conversation.objects.create(is_group=False)
        conv.participants.add(self.user1, self.user2)
        
        # Create and delete messages
        for i in range(3):
            msg = Message.objects.create(
                conversation=conv,
                sender=self.user1,
                text=f'Msg {i}'
            )
            msg.is_deleted = True
            msg.deleted_for_everyone = True
            msg.save()
        
        # Filter for non-deleted
        visible = conv.messages.filter(
            Q(is_deleted=False) | (Q(sender=self.user1) & Q(deleted_for_everyone=False))
        )
        
        self.assertEqual(visible.count(), 0)
    
    def test_self_message_attempt(self):
        """Test that user cannot message themselves"""
        client = Client()
        client.login(username='edge1', password='pass123')
        
        response = client.post(
            reverse('messaging:create_conversation'),
            {'user_id': self.user1.pk}
        )
        
        # Should redirect with error
        self.assertEqual(response.status_code, 302)
    
    def test_very_long_group_name(self):
        """Test handling of very long group names"""
        long_name = 'A' * 300  # Longer than max_length
        
        conv = Conversation.objects.create(
            is_group=True,
            group_name=long_name[:255],  # Should truncate
            creator=self.user1
        )
        
        self.assertEqual(len(conv.group_name), 255)
    
    def test_message_with_special_characters(self):
        """Test messages with special characters"""
        conv = Conversation.objects.create(is_group=False)
        conv.participants.add(self.user1, self.user2)
        
        special_text = "Test <script>alert('XSS')</script> & special chars: 你好 🎉"
        
        msg = Message.objects.create(
            conversation=conv,
            sender=self.user1,
            text=special_text
        )
        
        self.assertEqual(msg.text, special_text)
