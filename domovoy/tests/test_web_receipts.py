"""Чеки сайта: границы дома, лимиты, повторы и версия удаления."""
import asyncio
import base64
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendPhoto

from core import config
from core.receipt_limits import MAX_RECEIPT_UPLOAD_BYTES
from core.transaction_versions import expense_version
from infrastructure.repositories import money as money_repo
from infrastructure.repositories import receipts
from infrastructure.db import db
from services import households, money
from web.app import create_app
from test_web import TOKEN, headers

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jK5kAAAAASUVORK5CYII=")


class FakeBot:
    def __init__(self):
        self.sent = []
        self.content = PNG
        self.failure = False

    async def send_photo(self, chat_id, photo, **kwargs):
        self.sent.append(chat_id)
        await asyncio.sleep(0)
        if self.failure:
            raise TelegramNetworkError(SendPhoto(chat_id=chat_id, photo="fake"), "network")
        return SimpleNamespace(photo=[SimpleNamespace(file_id="PRIVATE_FILE_ID")])

    async def get_file(self, file_id):
        assert file_id == "PRIVATE_FILE_ID"
        return SimpleNamespace(file_path="photos/private.jpg", file_size=len(self.content))

    async def download_file(self, path, *, destination, timeout):
        destination.write(self.content)


@pytest.fixture
async def receipts_client(monkeypatch, database):
    monkeypatch.setattr(config, "BOT_TOKEN", TOKEN)
    bot = FakeBot()
    app = create_app(bot=bot)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, bot


@pytest.fixture
async def receipt_house(database):
    house_id = await households.create_house(100, "Хозяин", "Чеки")
    await households.join_house(await households.get_house(house_id), 200, "Жилец")
    expense_id = await money.add_expense(house_id, 100, 12345, None, "2026-10-01", "house", "Продукты", [])
    return house_id, expense_id


def path(house_id, expense_id):
    return f"/api/houses/{house_id}/expenses/{expense_id}"


def upload(**values):
    return {"request_id": str(uuid4()), "content": base64.b64encode(PNG).decode(), **values}


async def test_receipt_upload_retry_and_private_download(receipts_client, receipt_house):
    client, bot = receipts_client
    house_id, expense_id = receipt_house
    url = path(house_id, expense_id) + "/receipts"
    payload = upload()
    first = await client.post(url, headers=headers(), json=payload)
    retry = await client.post(url, headers=headers(), json=payload)
    assert first.status_code == retry.status_code == 200
    assert not first.json()["duplicate"] and retry.json()["duplicate"]
    assert first.json()["id"] == retry.json()["id"]
    assert bot.sent == [100] and await money.photos_count(expense_id) == 1
    listing = await client.get(url, headers=headers(200))
    assert listing.status_code == 200 and len(listing.json()["receipts"]) == 1
    assert "PRIVATE_FILE_ID" not in listing.text and "api.telegram.org" not in listing.text
    photo_id = first.json()["id"]
    image = await client.get(url + f"/{photo_id}", headers=headers(200))
    assert image.status_code == 200 and image.content == PNG
    assert image.headers["content-type"] == "image/png" and image.headers["cache-control"] == "no-store"
    assert (await client.get(url + f"/{photo_id}")).status_code == 404


async def test_receipt_permissions_house_and_key_reuse(receipts_client, receipt_house):
    client, bot = receipts_client
    house_id, expense_id = receipt_house
    url = path(house_id, expense_id) + "/receipts"
    assert (await client.post(url, headers=headers(200), json=upload())).status_code == 422
    other = await households.create_house(100, "Хозяин", "Другое пространство")
    assert (await client.get(path(other, expense_id) + "/receipts", headers=headers())).status_code == 422
    await households.set_grant(house_id, 200, "manage_all_expenses", True)
    payload = upload()
    assert (await client.post(url, headers=headers(200), json=payload)).status_code == 200
    assert bot.sent == [200]
    assert (await client.post(url, headers=headers(), json=payload)).status_code == 422
    await households.leave_house(house_id, 200)
    assert (await client.get(url, headers=headers(200))).status_code == 422


@pytest.mark.parametrize("content", ["invalid base64!", base64.b64encode(b"<svg>script</svg>").decode()])
async def test_non_photos_never_reach_telegram(receipts_client, receipt_house, content):
    client, bot = receipts_client
    house_id, expense_id = receipt_house
    response = await client.post(path(house_id, expense_id) + "/receipts", headers=headers(),
                                 json=upload(content=content))
    assert response.status_code == 422 and bot.sent == []


async def test_upload_size_and_parallel_limit(receipts_client, receipt_house):
    client, bot = receipts_client
    house_id, expense_id = receipt_house
    url = path(house_id, expense_id) + "/receipts"
    oversized = base64.b64encode(PNG + b"x" * MAX_RECEIPT_UPLOAD_BYTES).decode()
    assert (await client.post(url, headers=headers(), json=upload(content=oversized))).status_code == 422
    assert bot.sent == []
    for _ in range(9):
        assert (await client.post(url, headers=headers(), json=upload())).status_code == 200
    results = await asyncio.gather(*(client.post(url, headers=headers(), json=upload()) for _ in range(2)))
    assert sorted(response.status_code for response in results) == [200, 422]
    assert len(bot.sent) == 10 and await money.photos_count(expense_id) == 10


async def test_uncertain_upload_never_resends_same_request(receipts_client, receipt_house):
    client, bot = receipts_client
    house_id, expense_id = receipt_house
    bot.failure = True
    payload = upload()
    url = path(house_id, expense_id) + "/receipts"
    assert (await client.post(url, headers=headers(), json=payload)).status_code == 422
    bot.failure = False
    assert (await client.post(url, headers=headers(), json=payload)).status_code == 422
    assert bot.sent == [100] and await money.photos_count(expense_id) == 0
    for _ in range(10):
        assert (await client.post(url, headers=headers(), json=upload())).status_code == 200
    assert await money.photos_count(expense_id) == 10


async def test_abandoned_lease_releases_capacity_but_keeps_tombstone(receipt_house):
    house_id, expense_id = receipt_house
    old_request = str(uuid4())
    reservation, created = await receipts.reserve_upload(house_id, expense_id, 100, old_request, "old", 1)
    assert created and reservation["state"] == "reserved"
    async with db.acquire() as conn:
        await conn.execute("UPDATE web_receipt_uploads SET created_at = ? WHERE request_id = ?",
                           "2000-01-01 00:00:00", old_request)
    assert await receipts.pending_count(expense_id) == 0
    new_request = str(uuid4())
    _, created = await receipts.reserve_upload(house_id, expense_id, 100, new_request, "new", 1)
    assert created
    old, created = await receipts.reserve_upload(house_id, expense_id, 100, old_request, "old", 1)
    assert not created and old["state"] == "expired"
    assert await receipts.complete_upload(old_request, expense_id, house_id, "PRIVATE_FILE_ID", 1) is None
    assert await receipts.complete_upload(new_request, expense_id, house_id, "PRIVATE_FILE_ID", 1)
    assert await money.photos_count(expense_id) == 1


async def test_completion_rechecks_limit_after_photo_arrives_from_another_adapter(receipt_house):
    house_id, expense_id = receipt_house
    request_id = str(uuid4())
    _, created = await receipts.reserve_upload(house_id, expense_id, 100, request_id, "fingerprint", 1)
    assert created
    async with db.acquire() as conn:
        await conn.insert("INSERT INTO expense_photos (expense_id, file_id) VALUES (?, ?)",
                          expense_id, "OTHER_ADAPTER_PHOTO")
    assert await receipts.complete_upload(request_id, expense_id, house_id, "LATE_UPLOAD", 1) is None
    assert await money.photos_count(expense_id) == 1


async def test_delete_requires_current_version_house_author_and_unreimbursed(receipts_client, receipt_house):
    client, _ = receipts_client
    house_id, expense_id = receipt_house
    url = path(house_id, expense_id) + "/delete"
    original = await money.get_expense(expense_id)
    version = expense_version(original)
    assert (await client.post(url, headers=headers(200), json={"version": version})).status_code == 422
    other = await households.create_house(100, "Хозяин", "Чужой расход")
    wrong_house = await client.post(path(other, expense_id) + "/delete", headers=headers(), json={"version": version})
    assert wrong_house.status_code == 422
    assert (await client.post(url, headers=headers(), json={"version": "0" * 64})).status_code == 422
    assert await money.get_expense(expense_id) is not None
    assert (await client.post(url, headers=headers(), json={"version": version})).status_code == 200
    assert await money.get_expense(expense_id) is None
    personal = await money.add_expense(house_id, 100, 500, None, "2026-10-01", "personal", "", [])
    await money.reimburse_expense(house_id, personal, 100)
    current = await money.get_expense(personal)
    assert (await client.post(path(house_id, personal) + "/delete", headers=headers(),
                              json={"version": expense_version(current)})).status_code == 422
    attached = await client.post(path(house_id, personal) + "/receipts", headers=headers(), json=upload())
    assert attached.status_code == 422


async def test_photo_id_cannot_be_used_for_different_expense(receipts_client, receipt_house):
    client, _ = receipts_client
    house_id, expense_id = receipt_house
    url = path(house_id, expense_id) + "/receipts"
    result = await client.post(url, headers=headers(), json=upload())
    photo_id = result.json()["id"]
    second = await money.add_expense(house_id, 100, 100, None, "2026-10-01", "house", "", [])
    assert (await client.get(path(house_id, second) + f"/receipts/{photo_id}", headers=headers())).status_code == 422
    assert len(await money_repo.expense_photos(expense_id)) == 1

async def test_receipt_lookup_timeout_is_bounded_and_retry_does_not_send_photo(
    receipts_client, receipt_house, monkeypatch,
):
    from services import web_receipts
    client, bot = receipts_client
    house, expense = receipt_house
    uploaded = await client.post(path(house, expense) + '/receipts', headers=headers(), json=upload())
    photo_id = uploaded.json()['id']

    async def never_returns(file_id):
        await asyncio.Event().wait()

    monkeypatch.setattr(bot, 'get_file', never_returns)
    monkeypatch.setattr(web_receipts, 'RECEIPT_TRANSFER_TIMEOUT', 0.01)
    result = await client.get(path(house, expense) + f'/receipts/{photo_id}', headers=headers())
    assert result.status_code == 422
    assert len(bot.sent) == 1
