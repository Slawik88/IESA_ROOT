"""
Comprehensive tests for messaging app
Tests models, views, forms, permissions, and edge cases
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Count

from messaging.models import Conversation, Message, TypingIndicator
from messaging.forms import ConversationForm
from messaging import typing_cache

User = get_user_model()


class ConversationModelTests(TestCase):
    """Test Conversation model"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass123', email='user1@test.com')
        self.user2 = User.objects.create_user(username='user2', password='pass123', email='user2@test.com')
        self.user3 = User.objects.create_user(username='user3', password='pass123', email='user3@test.com')
    
    def test_create_1on1_conversation(self):
        """Test creating a 1-on-1 conversation"""
        conv = Conversation.objects.create(is_group=False)
        conv.participants.add(self.user1, self.user2)
        
        self.assertEqual(conv.participants.count(), 2)
        self.assertFalse(conv.is_group)
        self.assertIn(self.user1, conv.participants.all())
    
    def test_create_group_conversation(self):
        """Test creating a group conversation"""
        conv = Conversation.objects.create(
            is_group=True, 
            group_name='Test Group',
            creator=self.user1
        )
        conv.participants.add(self.user1, self.user2, self.user3)
        conv.admins.add(self.user1)
        
        self.assertEqual(conv.participants.count(), 3)
        self.assertTrue(conv.is_group)
        self.assertEqual(conv.group_name, 'Test Group')
        self.assertTrue(conv.is_admin(self.user1))
    
    def test_get_other_participant(self):
        """Test getting other participant in 1-on-1 chat"""
        conv = Conversation.objects.create(is_group=False)
        conv.participants.add(self.user1, self.user2)
        
        other = conv.get_other_participant(self.user1)
        self.assertEqual(other, self.user2)
    
    def test_is_admin_creator(self):
        """Test that creator is admin"""
        conv = Conversation.objects.create(is_group=True, creator=self.user1)
        conv.participants.add(self.user1, self.user2)
        
        self.assertTrue(conv.is_admin(self.user1))
        self.assertFalse(conv.is_admin(self.user2))
    
    def test_is_admin_explicit(self):
        """Test explicit admin assignment"""
        conv = Conversation.objects.create(is_group=True, creator=self.user1)
        conv.participants.add(self.user1, self.user2, self.user3)
        conv.admins.add(self.user2)
        
        self.assertTrue(conv.is_admin(self.user1))  # creator
        self.assertTrue(conv.is_admin(self.user2))  # explicit admin
        self.assertFalse(conv.is_admin(self.user3))  # regular participant
    
    def test_get_unread_count(self):
        """Test unread message count"""
        conv = Conversation.objects.create(is_group=False)
        conv.participants.add(self.user1, self.user2)
        
        # User2 sends 3 messages
        for i in range(3):
            msg = Message.objects.create(
                conversation=conv,
                sender=self.user2,
                text=f'Message {i}'
            )
        
        # User1 should have 3 unread
        unread = conv.get_unread_count(self.user1)
        self.assertEqual(unread, 3)
        
        # User2 should have 0 unread (their own messages)
        unread = conv.get_unread_count(self.user2)
        self.assertEqual(unread, 0)


class MessageModelTests(TestCase):
    """Test Message model"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass123', email='user1@test.com')
        self.user2 = User.objects.create_user(username='user2', password='pass123', email='user2@test.com')
        self.conv = Conversation.objects.create(is_group=False)
        self.conv.participants.add(self.user1, self.user2)
    
    def test_create_message_with_text(self):
        """Test creating message with text"""
        msg = Message.objects.create(
            conversation=self.conv,
            sender=self.user1,
            text='Hello World'
        )
        
        self.assertEqual(msg.text, 'Hello World')
        self.assertEqual(msg.sender, self.user1)
        self.assertFalse(msg.is_deleted)
    
    def test_create_message_with_empty_text(self):
        """Test creating message with empty text (БАГ #8 fix)"""
        msg = Message.objects.create(
            conversation=self.conv,
            sender=self.user1,
            text=''
        )
        
        self.assertEqual(msg.text, '')
        self.assertIsNotNone(msg)
    
    def test_mark_as_read(self):
        """Test marking message as read (БАГ #3 fix)"""
        msg = Message.objects.create(
            conversation=self.conv,
            sender=self.user1,
            text='Test'
        )
        
        # User2 marks as read
        msg.mark_as_read(self.user2)
        self.assertIn(self.user2, msg.read_by.all())
        
        # Sender should not be in read_by
        msg.mark_as_read(self.user1)
        self.assertNotIn(self.user1, msg.read_by.all())
    
    def test_mark_as_read_multiple_times(self):
        """Test that marking as read multiple times doesn't duplicate"""
        msg = Message.objects.create(
            conversation=self.conv,
            sender=self.user1,
            text='Test'
        )
        
        # Mark as read 3 times
        msg.mark_as_read(self.user2)
        msg.mark_as_read(self.user2)
        msg.mark_as_read(self.user2)
        
        # Should only appear once
        self.assertEqual(msg.read_by.filter(pk=self.user2.pk).count(), 1)
    
    def test_is_read_by(self):
        """Test checking if message was read"""
        msg = Message.objects.create(
            conversation=self.conv,
            sender=self.user1,
            text='Test'
        )
        
        self.assertFalse(msg.is_read_by(self.user2))
        msg.read_by.add(self.user2)
        self.assertTrue(msg.is_read_by(self.user2))


class ConversationFormTests(TestCase):
    """Test ConversationForm (БАГ #10 fix)"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass123', email='user1@test.com')
        self.user2 = User.objects.create_user(username='user2', password='pass123', email='user2@test.com')
        self.user3 = User.objects.create_user(username='user3', password='pass123', email='user3@test.com')
    
    def test_form_valid_with_one_participant(self):
        """Test form accepts minimum 1 participant (БАГ #10 fix)"""
        form = ConversationForm(data={
            'group_name': 'Test Group',
            'participants': [self.user2.pk]
        })
        
        self.assertTrue(form.is_valid())
    
    def test_form_valid_with_multiple_participants(self):
        """Test form with multiple participants"""
        form = ConversationForm(data={
            'group_name': 'Test Group',
            'participants': [self.user2.pk, self.user3.pk]
        })
        
        self.assertTrue(form.is_valid())
    
    def test_form_invalid_with_no_participants(self):
        """Test form rejects 0 participants"""
        form = ConversationForm(data={
            'group_name': 'Test Group',
            'participants': []
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn('participants', form.errors)


class TypingCacheTests(TestCase):
    """Test typing_cache utilities"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass123', email='user1@test.com')
        self.user2 = User.objects.create_user(username='user2', password='pass123', email='user2@test.com')
        self.conv = Conversation.objects.create(is_group=False)
        self.conv.participants.add(self.user1, self.user2)
    
    def test_set_typing_v2(self):
        """Test setting typing indicator"""
        typing_cache.set_typing_v2(
            conversation_id=self.conv.pk,
            user_id=self.user1.pk,
            username=self.user1.username
        )
        
        typing_users = typing_cache.get_typing_users_v2(
            conversation_id=self.conv.pk,
            exclude_user_id=None
        )
        
        self.assertIn(self.user1.username, typing_users)
    
    def test_get_typing_users_excludes_current_user(self):
        """Test that get_typing_users excludes current user"""
        typing_cache.set_typing_v2(
            conversation_id=self.conv.pk,
            user_id=self.user1.pk,
            username=self.user1.username
        )
        
        typing_users = typing_cache.get_typing_users_v2(
            conversation_id=self.conv.pk,
            exclude_user_id=self.user1.pk
        )
        
        self.assertNotIn(self.user1.username, typing_users)
    
    def test_clear_typing(self):
        """Test clearing typing indicator"""
        typing_cache.set_typing_v2(
            conversation_id=self.conv.pk,
            user_id=self.user1.pk,
            username=self.user1.username
        )
        
        typing_cache.clear_typing(
            conversation_id=self.conv.pk,
            user_id=self.user1.pk
        )
        
        typing_users = typing_cache.get_typing_users_v2(
            conversation_id=self.conv.pk,
            exclude_user_id=None
        )
        
        self.assertNotIn(self.user1.username, typing_users)

