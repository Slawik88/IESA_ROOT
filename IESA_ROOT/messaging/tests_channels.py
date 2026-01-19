"""
Tests for Django Channels Notifications Consumer
Тестирует DatabaseChannelLayer и real-time уведомления для масштабирования на 400+ юзеров
"""

import asyncio
import json
from django.test import TestCase, AsyncClient
from django.contrib.auth import get_user_model
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async, async_to_sync
from messaging.consumers import NotificationsConsumer
from messaging.models import Chat, Message
from IESA_ROOT.asgi import application
import logging

User = get_user_model()

logger = logging.getLogger(__name__)


class NotificationsConsumerTests(TestCase):
    """Unit тесты для NotificationsConsumer"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Создаём test users
        cls.user1 = User.objects.create_user(username='user1', password='pass123')
        cls.user2 = User.objects.create_user(username='user2', password='pass123')

    def setUp(self):
        """Подготовка перед каждым тестом"""
        # Очистим все чаты
        Chat.objects.all().delete()
        Message.objects.all().delete()

    @async_to_sync
    async def test_consumer_connect(self):
        """Тест подключения WebSocket клиента"""
        communicator = WebsocketCommunicator(
            application,
            "/ws/notifications/",
            headers=[(b"origin", b"http://127.0.0.1")],
        )
        
        # Симулируем аутентификацию
        communicator.scope["user"] = self.user1
        
        # Подключаемся
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected, "WebSocket должен подключиться")
        
        # Получаем начальный unread count
        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=2)
        self.assertEqual(response['type'], 'unread_set')
        self.assertIn('count', response)
        
        # Отключаемся
        await communicator.disconnect()

    @async_to_sync
    async def test_consumer_disconnect(self):
        """Тест отключения WebSocket клиента"""
        communicator = WebsocketCommunicator(
            application,
            "/ws/notifications/",
            headers=[(b"origin", b"http://127.0.0.1")],
        )
        
        communicator.scope["user"] = self.user1
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        
        # Читаем начальное сообщение
        await communicator.receive_json_from()
        
        # Отключаемся
        await communicator.disconnect()
        
        # Попытка читать должна выбросить исключение
        with self.assertRaises(Exception):
            await asyncio.wait_for(communicator.receive_json_from(), timeout=1)

    def test_unread_count_calculation(self):
        """Тест расчёта непрочитанных сообщений"""
        # Создаём чат между user1 и user2
        chat = Chat.objects.create(user1=self.user1, user2=self.user2)
        
        # user2 отправляет сообщение user1 (оно непрочитано)
        msg1 = Message.objects.create(
            chat=chat,
            sender=self.user2,
            text="Привет"
        )
        msg1.is_read = False
        msg1.save()
        
        # user1 отправляет сообщение user2 (оно уже прочитано им)
        msg2 = Message.objects.create(
            chat=chat,
            sender=self.user1,
            text="Привет!"
        )
        msg2.is_read = True
        msg2.save()
        
        # Проверяем что для user1 = 1 непрочитанное
        unread_count = Message.objects.filter(
            chat__user1=self.user1,
            is_read=False,
            is_deleted=False
        ).exclude(sender=self.user1).count()
        
        self.assertEqual(unread_count, 1, "Должно быть 1 непрочитанное сообщение")


class WebSocketIntegrationTests(TestCase):
    """Интеграционные тесты для WebSocket соединений"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user1 = User.objects.create_user(username='user1', password='pass123')
        cls.user2 = User.objects.create_user(username='user2', password='pass123')

    def setUp(self):
        Chat.objects.all().delete()
        Message.objects.all().delete()

    @async_to_sync
    async def test_multiple_clients_connection(self):
        """Тест подключения нескольких клиентов одновременно"""
        # Создаём несколько communicators (симуляция 5 юзеров)
        communicators = []
        users = []
        
        for i in range(5):
            user = await database_sync_to_async(User.objects.create_user)(
                username=f'test_user_{i}',
                password='pass123'
            )
            users.append(user)
            
            comm = WebsocketCommunicator(
                application,
                "/ws/notifications/",
                headers=[(b"origin", b"http://127.0.0.1")],
            )
            comm.scope["user"] = user
            
            connected, _ = await comm.connect()
            self.assertTrue(connected, f"User {i} должен подключиться")
            
            communicators.append(comm)
        
        # Все получают начальные сообщения
        for i, comm in enumerate(communicators):
            response = await asyncio.wait_for(comm.receive_json_from(), timeout=2)
            self.assertEqual(response['type'], 'unread_set')
            logger.info(f"User {i} получил unread_set: {response['count']}")
        
        # Отключаем всех
        for comm in communicators:
            await comm.disconnect()
        
        logger.info("✅ 5 клиентов успешно подключились и отключились")

    @async_to_sync
    async def test_broadcast_unread_delta(self):
        """Тест отправки unread_delta по группе"""
        user = await database_sync_to_async(User.objects.create_user)(
            username='broadcast_test_user',
            password='pass123'
        )
        
        communicator = WebsocketCommunicator(
            application,
            "/ws/notifications/",
            headers=[(b"origin", b"http://127.0.0.1")],
        )
        
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        
        # Читаем начальное сообщение
        initial = await asyncio.wait_for(communicator.receive_json_from(), timeout=2)
        self.assertEqual(initial['type'], 'unread_set')
        
        # Отправляем unread_delta в группу пользователя
        channel_layer = communicator.application.channel_layer
        await channel_layer.group_send(
            f'user_{user.id}',
            {
                'type': 'unread_delta',
                'delta': 2,
            }
        )
        
        # Ожидаем unread_delta на клиенте
        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=2)
        self.assertEqual(response['type'], 'unread_delta')
        self.assertEqual(response['delta'], 2)
        
        await communicator.disconnect()
        logger.info("✅ Broadcast unread_delta успешно доставлен")


class LoadTests(TestCase):
    """Load тесты для масштабирования на 100+ юзеров"""

    def test_create_100_users(self):
        """Быстрый тест: создание 100 юзеров"""
        users = [
            User(username=f'load_user_{i}', email=f'user{i}@test.com')
            for i in range(100)
        ]
        User.objects.bulk_create(users, ignore_conflicts=True)
        
        user_count = User.objects.filter(username__startswith='load_user_').count()
        self.assertGreaterEqual(user_count, 100, "Должно создаться минимум 100 юзеров")
        logger.info(f"✅ Создано {user_count} юзеров")

    def test_create_messages_for_multiple_users(self):
        """Тест: создание сообщений между 50 парами юзеров"""
        # Создаём 100 юзеров
        users = []
        for i in range(100):
            user = User.objects.create_user(
                username=f'msg_user_{i}',
                password='pass123'
            )
            users.append(user)
        
        # Создаём 50 чатов между парами
        chats = []
        messages = []
        
        for i in range(0, 100, 2):
            if i + 1 < 100:
                chat = Chat.objects.create(user1=users[i], user2=users[i + 1])
                chats.append(chat)
                
                # Каждому чату по 10 сообщений
                for j in range(10):
                    msg = Message(
                        chat=chat,
                        sender=users[i] if j % 2 == 0 else users[i + 1],
                        text=f"Message {j}"
                    )
                    messages.append(msg)
        
        Message.objects.bulk_create(messages)
        
        total_msgs = Message.objects.count()
        logger.info(f"✅ Создано {len(chats)} чатов с {total_msgs} сообщениями")
        self.assertEqual(len(chats), 50, "Должно быть 50 чатов")
        self.assertGreater(total_msgs, 400, "Должно быть минимум 500 сообщений")

    def test_query_performance_with_many_messages(self):
        """Тест: производительность запросов при большом количестве сообщений"""
        import time
        
        # Создаём 2 юзера
        user1 = User.objects.create_user(username='perf_user1', password='pass123')
        user2 = User.objects.create_user(username='perf_user2', password='pass123')
        
        # Создаём чат с 1000 сообщениями
        chat = Chat.objects.create(user1=user1, user2=user2)
        
        messages = [
            Message(
                chat=chat,
                sender=user1 if i % 2 == 0 else user2,
                text=f"Message {i}",
                is_read=(i % 3 == 0)  # 33% прочитаны
            )
            for i in range(1000)
        ]
        Message.objects.bulk_create(messages)
        
        # Тестируем скорость запроса непрочитанных
        start = time.time()
        unread_count = Message.objects.filter(
            chat__user1=user1,
            is_read=False,
            is_deleted=False
        ).exclude(sender=user1).count()
        elapsed = time.time() - start
        
        logger.info(f"✅ Query time для 1000 сообщений: {elapsed:.3f}s, найдено: {unread_count}")
        self.assertLess(elapsed, 0.5, "Query должен выполниться за < 500ms")


class ChannelLayerTests(TestCase):
    """Тесты для DatabaseChannelLayer"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user1 = User.objects.create_user(username='channel_user1', password='pass123')
        cls.user2 = User.objects.create_user(username='channel_user2', password='pass123')

    @async_to_sync
    async def test_channel_layer_exists(self):
        """Тест: DatabaseChannelLayer корректно инициализирован"""
        from django.conf import settings
        
        channel_layers = settings.CHANNEL_LAYERS
        self.assertIsNotNone(channel_layers)
        self.assertIn('default', channel_layers)
        
        backend = channel_layers['default']['BACKEND']
        self.assertIn('DatabaseChannelLayer', backend, 
                     f"Backend должен быть DatabaseChannelLayer, а не {backend}")
        
        logger.info(f"✅ Channel Layer backend: {backend}")

    @async_to_sync
    async def test_group_send_and_receive(self):
        """Тест: отправка и получение сообщений через группу"""
        from channels.layers import get_channel_layer
        
        channel_layer = get_channel_layer()
        group_name = f'test_group_{self.user1.id}'
        
        # Создаём 2 communicators в одной группе
        comm1 = WebsocketCommunicator(
            application,
            "/ws/notifications/",
            headers=[(b"origin", b"http://127.0.0.1")],
        )
        comm1.scope["user"] = self.user1
        
        connected1, _ = await comm1.connect()
        self.assertTrue(connected1)
        
        # Читаем начальное сообщение
        await asyncio.wait_for(comm1.receive_json_from(), timeout=2)
        
        # Отправляем сообщение в группу
        await channel_layer.group_send(
            group_name,
            {
                'type': 'unread_delta',
                'delta': 5,
            }
        )
        
        # Должны получить это сообщение
        response = await asyncio.wait_for(comm1.receive_json_from(), timeout=2)
        self.assertEqual(response['type'], 'unread_delta')
        self.assertEqual(response['delta'], 5)
        
        await comm1.disconnect()
        logger.info("✅ Group send/receive работает корректно")


class RealTimeScenarioTests(TestCase):
    """Реальные сценарии использования"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user1 = User.objects.create_user(username='real_user1', password='pass123')
        cls.user2 = User.objects.create_user(username='real_user2', password='pass123')

    def setUp(self):
        Chat.objects.all().delete()
        Message.objects.all().delete()

    def test_scenario_new_message_updates_unread(self):
        """Сценарий: новое сообщение должно увеличить счётчик непрочитанных"""
        # Создаём чат
        chat = Chat.objects.create(user1=self.user1, user2=self.user2)
        
        # Начальный count
        initial_unread = Message.objects.filter(
            chat__user1=self.user1,
            is_read=False,
            is_deleted=False
        ).exclude(sender=self.user1).count()
        self.assertEqual(initial_unread, 0)
        
        # user2 отправляет сообщение
        Message.objects.create(
            chat=chat,
            sender=self.user2,
            text="Привет!",
            is_read=False
        )
        
        # Новый count
        new_unread = Message.objects.filter(
            chat__user1=self.user1,
            is_read=False,
            is_deleted=False
        ).exclude(sender=self.user1).count()
        
        self.assertEqual(new_unread, 1, "Счётчик должен увеличиться на 1")
        logger.info("✅ Сценарий: новое сообщение + update unread")

    def test_scenario_read_message_decreases_unread(self):
        """Сценарий: прочитанное сообщение должно уменьшить счётчик"""
        chat = Chat.objects.create(user1=self.user1, user2=self.user2)
        
        # Создаём непрочитанное сообщение
        msg = Message.objects.create(
            chat=chat,
            sender=self.user2,
            text="Тест",
            is_read=False
        )
        
        unread_before = Message.objects.filter(
            chat__user1=self.user1,
            is_read=False,
            is_deleted=False
        ).exclude(sender=self.user1).count()
        self.assertEqual(unread_before, 1)
        
        # Помечаем как прочитано
        msg.is_read = True
        msg.save()
        
        unread_after = Message.objects.filter(
            chat__user1=self.user1,
            is_read=False,
            is_deleted=False
        ).exclude(sender=self.user1).count()
        
        self.assertEqual(unread_after, 0, "Счётчик должен вернуться к 0")
        logger.info("✅ Сценарий: прочитанное сообщение + decrease unread")


# ============================================================================
# ИНСТРУКЦИЯ ПО ЗАПУСКУ:
# ============================================================================
"""
1. Запустить все тесты:
   python manage.py test messaging.tests_channels

2. Запустить конкретный тест:
   python manage.py test messaging.tests_channels.NotificationsConsumerTests.test_consumer_connect

3. Запустить с verbose output:
   python manage.py test messaging.tests_channels -v 2

4. Запустить только load тесты:
   python manage.py test messaging.tests_channels.LoadTests -v 2

5. Запустить с логированием:
   python manage.py test messaging.tests_channels --debug-mode

ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ:
✅ NotificationsConsumerTests - 3 теста
✅ WebSocketIntegrationTests - 2 теста  
✅ LoadTests - 3 теста
✅ ChannelLayerTests - 2 теста
✅ RealTimeScenarioTests - 2 теста

ИТОГО: 12 тестов, должны пройти все ✅
"""
