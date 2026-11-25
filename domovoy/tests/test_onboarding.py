"""Вход нового жильца через сайт и закрытый предпросмотр приглашения."""
import hashlib
import hmac
import json
import time
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetMe
from aiogram.types import CallbackQuery, Chat, Message, User

from bot import cb, keyboards
from bot.handlers import start, settings as settings_handlers
from bot.dispatcher import PrivateCallbacks
from core import config
from infrastructure.repositories import users
from services import households
from web.app import create_app

TOKEN = "123456:TEST_HOME_BOT"
PRIVATE_URL = "https://example.invalid/predvestnik/_h/private-entry/"


def headers(actor):
    values = {"auth_date": str(int(time.time())), "user": json.dumps({"id": actor, "first_name": "Жилец"})}
    key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{name}={value}" for name, value in sorted(values.items()))
    values["hash"] = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    return {"Authorization": "tma " + urlencode(values)}


@pytest.fixture
async def telegram():
    bot = Bot(TOKEN)

    async def request(session_bot, method, **kwargs):
        if isinstance(method, GetMe):
            return User(id=123456, is_bot=True, first_name="Домовой", username="Domovskii_bot")
        return True

    bot.session.make_request = AsyncMock(side_effect=request)
    yield bot
    await bot.session.close()


@pytest.fixture
async def identities(database, request):
    # У общей session-БД уже могут быть дома из других тестов: свои ID на каждый сценарий.
    base = 8_000_000_000_000 + int(hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:10], 16) * 4
    result = {"owner": base, "member": base + 1, "newcomer": base + 2}
    for key in ("owner", "member"):
        await users.upsert_user(result[key], "Тестовый жилец", None)
    return result


@pytest.fixture
async def state(identities):
    storage = MemoryStorage()
    actor = identities["member"]
    yield FSMContext(storage, StorageKey(bot_id=123456, chat_id=actor, user_id=actor))
    await storage.close()


@pytest.fixture
async def house(identities):
    house_id = await households.create_house(identities["owner"], "Хозяин", "Дом приглашения")
    return await households.get_house(house_id)


@pytest.fixture
async def client(monkeypatch, telegram):
    monkeypatch.setattr(config, "BOT_TOKEN", TOKEN)
    app = create_app(bot=telegram)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


def message(bot, actor):
    return Message(message_id=1, date=datetime(2026, 11, 3), chat=Chat(id=actor, type="private"),
                   from_user=User(id=actor, is_bot=False, first_name="Жилец"), text="/start").as_(bot)


def sent_messages(bot):
    return [call.args[1] for call in bot.session.make_request.await_args_list
            if call.args[1].__api_method__ == "sendMessage"]


def group_message(bot, actor):
    return Message(message_id=2, date=datetime(2026, 11, 3), chat=Chat(id=-1001234567890, type="supergroup"),
                   from_user=User(id=actor, is_bot=False, first_name="Жилец"), text="/start").as_(bot)


def group_callback(bot, actor, data):
    return CallbackQuery(id="group-binding", from_user=User(id=actor, is_bot=False, first_name="Жилец"),
                         chat_instance="group", data=data, message=group_message(bot, actor)).as_(bot)


async def test_new_start_opens_private_site_before_creating_house(database, state, telegram, monkeypatch):
    monkeypatch.setattr(start, "public_url", lambda: PRIVATE_URL)
    actor = state.key.user_id
    assert not await households.houses_of_user(actor)
    await start.cmd_start(message(telegram, actor), CommandObject(command="start"), state)
    sent = sent_messages(telegram)[-1]
    buttons = [button for row in sent.reply_markup.inline_keyboard for button in row]
    assert len(buttons) == 1 and buttons[0].web_app.url == PRIVATE_URL
    assert not await households.houses_of_user(actor)


async def test_start_with_multiple_unselected_homes_still_opens_site(database, state, telegram, monkeypatch):
    monkeypatch.setattr(start, "public_url", lambda: PRIVATE_URL)
    actor = state.key.user_id
    await households.create_house(actor, "Жилец", "Первый дом")
    await households.create_house(actor, "Жилец", "Второй дом")
    await users.set_active_house(actor, None)
    await start.cmd_start(message(telegram, actor), CommandObject(command="start"), state)
    buttons = [button for row in sent_messages(telegram)[-1].reply_markup.inline_keyboard for button in row]
    assert len(buttons) == 1 and buttons[0].web_app.url == PRIVATE_URL


async def test_join_deep_link_has_single_site_action(house, state, telegram, monkeypatch):
    monkeypatch.setattr(start, "public_url", lambda: PRIVATE_URL)
    command = CommandObject(command="start", args=f"join_{house['invite_token']}")
    await start.cmd_start(message(telegram, state.key.user_id), command, state)
    sent = sent_messages(telegram)[-1]
    buttons = [button for row in sent.reply_markup.inline_keyboard for button in row]
    assert len(buttons) == 1
    target = urlsplit(buttons[0].web_app.url)
    assert target.path == urlsplit(PRIVATE_URL).path
    assert parse_qs(target.query) == {"house": [str(house["id"])]}
    assert "«Сегодня»" not in sent.text and "«Баланс»" not in sent.text and "«Траты»" not in sent.text
    assert (await households.membership(house["id"], state.key.user_id))["status"] == "active"


async def test_existing_start_targets_current_house(house, state, telegram, monkeypatch):
    monkeypatch.setattr(start, "public_url", lambda: PRIVATE_URL)
    actor = state.key.user_id
    await households.join_house(house, actor, "Жилец")
    await users.set_active_house(actor, house["id"])
    await start.cmd_start(message(telegram, actor), CommandObject(command="start"), state)
    button = sent_messages(telegram)[-1].reply_markup.inline_keyboard[0][0]
    assert parse_qs(urlsplit(button.web_app.url).query) == {"house": [str(house["id"])]}


def test_legacy_onboarding_callback_remains_available_without_site():
    assert keyboards.onboarding().inline_keyboard[0][0].callback_data == cb.house_create()


async def test_invite_share_url_and_rotation_use_cached_current_bot(client, house, telegram):
    path = f"/api/houses/{house['id']}/invite"
    first = (await client.get(path, headers=headers(house["created_by"]))).json()
    assert first == {"invite_token": house["invite_token"],
                     "share_url": f"https://t.me/Domovskii_bot?start=join_{house['invite_token']}"}
    rotated = (await client.post(path + "/rotate", headers=headers(house["created_by"]))).json()
    assert rotated["invite_token"] != first["invite_token"]
    assert rotated["share_url"] == f"https://t.me/Domovskii_bot?start=join_{rotated['invite_token']}"
    lookups = [call for call in telegram.session.make_request.await_args_list if isinstance(call.args[1], GetMe)]
    assert len(lookups) == 1


async def test_share_url_degrades_to_code_when_bot_not_available(monkeypatch, house):
    monkeypatch.setattr(config, "BOT_TOKEN", TOKEN)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as client:
        result = await client.get(f"/api/houses/{house['id']}/invite", headers=headers(house["created_by"]))
    assert result.json() == {"invite_token": house["invite_token"], "share_url": None}


async def test_share_url_degrades_on_telegram_failure(client, house, telegram):
    telegram.session.make_request.side_effect = TelegramNetworkError(method=GetMe(), message="offline")
    result = await client.get(f"/api/houses/{house['id']}/invite", headers=headers(house["created_by"]))
    assert result.status_code == 200
    assert result.json() == {"invite_token": house["invite_token"], "share_url": None}


async def test_invite_requires_house_permission_before_resolving_bot(client, house, telegram, identities):
    actor = identities["member"]
    await households.join_house(house, actor, "Жилец")
    result = await client.get(f"/api/houses/{house['id']}/invite", headers=headers(actor))
    assert result.status_code == 422
    telegram.session.make_request.assert_not_awaited()


async def test_preview_exposes_only_house_name_and_does_not_join(client, house, identities):
    token = house["invite_token"]
    actor = identities["member"]
    for invitation in (token, f"join_{token}", f"https://t.me/Domovskii_bot?start=join_{token}"):
        result = await client.post("/api/invitations/preview", headers=headers(actor),
                                   json={"invite_token": invitation})
        assert result.status_code == 200
        assert result.json() == {"name": "Дом приглашения", "already_member": False}
    assert await households.membership(house["id"], actor) is None
    owner = await client.post("/api/invitations/preview", headers=headers(house["created_by"]),
                              json={"invite_token": token})
    assert owner.json() == {"name": "Дом приглашения", "already_member": True}


async def test_new_telegram_identity_can_preview_without_creating_account(client, house, identities):
    actor = identities["newcomer"]
    assert await users.get_user(actor) is None
    result = await client.post("/api/invitations/preview", headers=headers(actor),
                               json={"invite_token": house["invite_token"]})
    assert result.json() == {"name": "Дом приглашения", "already_member": False}
    assert await users.get_user(actor) is None
    assert await households.membership(house["id"], actor) is None


async def test_preview_requires_auth_and_rejects_invalid_or_rotated_invite(client, house, identities):
    payload = {"invite_token": house["invite_token"]}
    actor = identities["member"]
    assert (await client.post("/api/invitations/preview", json=payload)).status_code == 404
    await households.new_invite_token(house["id"])
    assert (await client.post("/api/invitations/preview", headers=headers(actor), json=payload)).status_code == 422
    for token in ("???", "join_", "https://t.me/Domovskii_bot?start=bad!"):
        result = await client.post("/api/invitations/preview", headers=headers(actor), json={"invite_token": token})
        assert result.status_code == 422


async def test_preview_existing_then_departed_member(client, house, identities):
    actor = identities["member"]
    await households.join_house(house, actor, "Жилец")
    await households.leave_house(house["id"], actor)
    result = await client.post("/api/invitations/preview", headers=headers(actor),
                               json={"invite_token": house["invite_token"]})
    assert result.json() == {"name": "Дом приглашения", "already_member": False}


async def test_management_provides_house_specific_group_link_only_to_settings_manager(client, house, identities):
    path = f"/api/houses/{house['id']}/management"
    owner = (await client.get(path, headers=headers(identities["owner"]))).json()
    assert owner["house"]["chat_connect_url"] == f"https://t.me/Domovskii_bot?startgroup=house_{house['id']}"
    await households.join_house(house, identities["member"], "Жилец")
    member = (await client.get(path, headers=headers(identities["member"]))).json()
    assert member["house"]["chat_connect_url"] is None


async def test_group_request_and_button_bind_requested_house_not_active_house(house, state, telegram, identities):
    actor = identities["owner"]
    other_id = await households.create_house(actor, "Хозяин", "Другой выбранный дом")
    await users.set_active_house(actor, other_id)
    await start.cmd_start(group_message(telegram, actor),
                          CommandObject(command="start", args=f"house_{house['id']}"), state)
    prompt = sent_messages(telegram)[-1]
    assert house["name"] in prompt.text and "Другой выбранный дом" not in prompt.text
    button = prompt.reply_markup.inline_keyboard[0][0]
    assert button.callback_data == cb.settings_bind_chat(house["id"])
    assert (await households.get_house(house["id"]))["chat_id"] is None
    assert (await households.get_house(other_id))["chat_id"] is None
    await settings_handlers.bind_chat(group_callback(telegram, actor, button.callback_data))
    assert (await households.get_house(house["id"]))["chat_id"] == -1001234567890
    assert (await households.get_house(other_id))["chat_id"] is None


async def test_group_link_and_button_reject_nonmember(house, state, telegram, identities):
    actor = identities["member"]
    await start.cmd_start(group_message(telegram, actor),
                          CommandObject(command="start", args=f"house_{house['id']}"), state)
    assert house["name"] not in sent_messages(telegram)[-1].text
    assert sent_messages(telegram)[-1].reply_markup is None
    await settings_handlers.bind_chat(group_callback(telegram, actor, cb.settings_bind_chat(house["id"])))
    assert (await households.get_house(house["id"]))["chat_id"] is None


async def test_group_binding_rechecks_revoked_permission(house, state, telegram, identities):
    actor = identities["member"]
    await households.join_house(house, actor, "Жилец")
    await households.set_grant(house["id"], actor, "manage_house_settings", True)
    await start.cmd_start(group_message(telegram, actor),
                          CommandObject(command="start", args=f"house_{house['id']}"), state)
    button = sent_messages(telegram)[-1].reply_markup.inline_keyboard[0][0]
    await households.set_grant(house["id"], actor, "manage_house_settings", False)
    await settings_handlers.bind_chat(group_callback(telegram, actor, button.callback_data))
    assert (await households.get_house(house["id"]))["chat_id"] is None


@pytest.mark.parametrize("chat_type", ["private", "channel"])
async def test_specific_binding_only_accepts_groups(house, telegram, identities, chat_type):
    actor = identities["owner"]
    event = group_callback(telegram, actor, cb.settings_bind_chat(house["id"]))
    scoped_message = event.message.model_copy(update={"chat": Chat(id=actor, type=chat_type)})
    await settings_handlers.bind_chat(event.model_copy(update={"message": scoped_message}))
    assert (await households.get_house(house["id"]))["chat_id"] is None


@pytest.mark.parametrize("suffix", [" extra", "_extra", ":extra"])
async def test_group_link_rejects_extra_payload_without_falling_back(house, state, telegram, identities, suffix):
    actor = identities["owner"]
    await users.set_active_house(actor, house["id"])
    await start.cmd_start(group_message(telegram, actor),
                          CommandObject(command="start", args=f"house_{house['id']}{suffix}"), state)
    assert sent_messages(telegram)[-1].reply_markup is None
    assert (await households.get_house(house["id"]))["chat_id"] is None


async def test_group_callback_allowlist_accepts_specific_house_and_legacy(telegram, identities):
    middleware = PrivateCallbacks()
    for callback_data in (cb.settings_bind_chat(123), cb.settings_bind_chat()):
        handler = AsyncMock()
        event = group_callback(telegram, identities["owner"], callback_data)
        await middleware(handler, event, {})
        handler.assert_awaited_once_with(event, {})
    handler = AsyncMock()
    await middleware(handler, group_callback(telegram, identities["owner"], "st_chat:123:extra"), {})
    handler.assert_not_awaited()
