"""Правка и удаление записанного, управление домом и файлы в чат — через настоящий HTTP-слой."""
from datetime import date, timedelta
from types import SimpleNamespace

import httpx
import pytest
from aiogram.exceptions import TelegramForbiddenError

from core import config
from core.constants import JOURNAL_MAX_SPAN
from infrastructure.repositories import schedule, transactions
from services import cleaning, households, money, settings
from test_web import TOKEN, headers
from web.app import create_app

OWNER, NEIGHBOR, STRANGER = 100, 200, 300


class FakeBot:
    def __init__(self, forbidden=False):
        self.forbidden, self.messages, self.documents = forbidden, [], []

    async def me(self):
        return SimpleNamespace(username="Domovskii_bot")

    async def send_message(self, chat_id, text, **_):
        self.messages.append((chat_id, text))

    async def send_document(self, chat_id, document, caption=None):
        if self.forbidden:
            raise TelegramForbiddenError(method=None, message="blocked")
        self.documents.append((chat_id, document.filename, caption))


@pytest.fixture
def make_client(monkeypatch, database):
    monkeypatch.setattr(config, "BOT_TOKEN", TOKEN)
    clients = []

    def build(bot=None):
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(bot=bot)), base_url="http://test")
        clients.append(client)
        return client
    yield build


@pytest.fixture
async def house(database):
    house_id = await households.create_house(OWNER, "Хозяин", "Дом")
    await households.join_house(await households.get_house(house_id), NEIGHBOR, "Жилец")
    return house_id


def today() -> str:
    return date.today().isoformat()


async def overview(client, house, actor=OWNER, query=""):
    response = await client.get(f"/api/houses/{house}{query}", headers=headers(actor))
    assert response.status_code == 200, response.text
    return response.json()


async def row_of(client, house, kind, actor=OWNER):
    rows = (await overview(client, house, actor, "?all_months=true"))["rows"]
    return next(row for row in rows if row["kind"] == kind)


async def post(client, path, actor, payload=None):
    return await client.post(path, headers=headers(actor), json=payload)


def contribution_edit(row, **changes):
    return {"amount": "150,50", "date": row["date"], "month": row["month"], "version": row["version"], **changes}


async def test_author_edits_and_deletes_own_pending_contribution_only(make_client, house):
    client = make_client()
    await money.declare_contribution(house, NEIGHBOR, 10000, today())
    row = await row_of(client, house, "contribution", NEIGHBOR)
    assert row["can_edit"]
    path = f"/api/houses/{house}/contributions/{row['id']}"
    stale = contribution_edit(row, version="0" * 64)
    assert (await client.post(path + "/edit", headers=headers(NEIGHBOR), json=stale)).status_code == 422
    assert (await post(client, path + "/edit", STRANGER, contribution_edit(row))).status_code == 422
    result = await client.post(path + "/edit", headers=headers(NEIGHBOR), json=contribution_edit(row))
    assert result.status_code == 200 and result.json()["unchanged"] is False
    changed = await row_of(client, house, "contribution", NEIGHBOR)
    assert changed["amount_kop"] == 15050 and changed["status"] == "declared" and changed["version"] != row["version"]
    same = await post(client, path + "/edit", NEIGHBOR, contribution_edit(changed, amount="150.50"))
    assert same.json()["unchanged"] is True
    assert (await post(client, path + "/delete", NEIGHBOR, {"version": changed["version"]})).status_code == 200
    assert (await overview(client, house, NEIGHBOR, "?all_months=true"))["total"] == 0


async def test_confirmed_contribution_is_frozen_for_the_author_but_not_for_the_approver(make_client, house):
    client = make_client()
    created = await money.declare_contribution(house, NEIGHBOR, 10000, today())
    await money.resolve_contribution(created["id"], True, OWNER, house_id=house)
    row = await row_of(client, house, "contribution", NEIGHBOR)
    assert row["status"] == "confirmed"
    assert not row["can_edit"] and (await row_of(client, house, "contribution", OWNER))["can_edit"]
    path = f"/api/houses/{house}/contributions/{row['id']}"
    assert (await post(client, path + "/edit", NEIGHBOR, contribution_edit(row))).status_code == 422
    assert (await post(client, path + "/delete", NEIGHBOR, {"version": row["version"]})).status_code == 422
    assert (await client.post(path + "/edit", headers=headers(OWNER), json=contribution_edit(row))).status_code == 200
    assert (await overview(client, house))["balance"]["confirmed_total"] == 15050
    assert (await client.post(path + "/delete", headers=headers(OWNER), json={"version": "0" * 64})).status_code == 422
    fresh = await row_of(client, house, "contribution")
    assert (await post(client, path + "/delete", OWNER, {"version": fresh["version"]})).status_code == 200
    assert (await overview(client, house))["balance"]["confirmed_total"] == 0


async def test_author_may_edit_confirmed_contribution_when_the_house_needs_no_confirmation(make_client, house):
    from services import settings
    client = make_client()
    await settings.set_house_setting(house, "confirm_contributions", False)
    await money.declare_contribution(house, NEIGHBOR, 10000, today())
    row = await row_of(client, house, "contribution", NEIGHBOR)
    assert row["status"] == "confirmed" and row["can_edit"]


async def test_reimbursement_can_be_undone_only_by_an_approver_and_unfreezes_the_expense(make_client, house):
    client = make_client()
    await money.add_expense(house, NEIGHBOR, 5000, None, today(), "personal", "Лампы", [])
    row = await row_of(client, house, "expense", NEIGHBOR)
    assert (await overview(client, house))["waiting"] == {"total": 5000, "mine": 0}
    assert (await overview(client, house, NEIGHBOR))["waiting"] == {"total": 5000, "mine": 5000}
    reimburse = await client.post(f"/api/houses/{house}/expenses/{row['id']}/reimburse", headers=headers(OWNER),
                                  json={"version": row["version"]})
    assert reimburse.status_code == 200
    paid = await row_of(client, house, "expense", NEIGHBOR)
    assert paid["reimbursed"] and not paid["can_edit"] and (await overview(client, house))["waiting"]["total"] == 0
    path = f"/api/houses/{house}/expenses/{row['id']}/unreimburse"
    assert (await client.post(path, headers=headers(NEIGHBOR), json={"version": paid["version"]})).status_code == 422
    assert (await client.post(path, headers=headers(OWNER), json={"version": row["version"]})).status_code == 422
    assert (await client.post(path, headers=headers(OWNER), json={"version": paid["version"]})).status_code == 200
    reopened = await row_of(client, house, "expense", NEIGHBOR)
    assert not reopened["reimbursed"] and reopened["can_edit"]
    assert (await overview(client, house))["waiting"]["total"] == 5000
    again = await client.post(path, headers=headers(OWNER), json={"version": reopened["version"]})
    assert again.status_code == 422


async def test_done_cleaning_day_can_be_reopened_by_its_author_or_a_manager(make_client, house):
    client = make_client()
    await households.join_house(await households.get_house(house), STRANGER, "Третий")
    day = date.today()
    await cleaning.save_weekday_map(house, {OWNER: day.weekday(), NEIGHBOR: day.weekday()}, day.isoformat())
    mine, theirs = [dict(row) for row in await schedule.days_on(house, day.isoformat())]
    assert mine["tg_id"] == OWNER
    await cleaning.close_day_for(house, mine["id"], OWNER, day.isoformat())
    await cleaning.close_day_for(house, theirs["id"], OWNER, day.isoformat())
    reopen = lambda day_id, actor: client.post(f"/api/houses/{house}/cleaning/{day_id}/reopen", headers=headers(actor))  # noqa: E731
    assert (await reopen(theirs["id"], STRANGER)).status_code == 422
    assert (await reopen(mine["id"], NEIGHBOR)).status_code == 422  # чужой день без права
    assert (await reopen(theirs["id"], NEIGHBOR)).status_code == 200  # свой день вправе вернуть сам жилец
    assert (await reopen(mine["id"], OWNER)).status_code == 200
    assert (await reopen(mine["id"], OWNER)).status_code == 422  # уже ждёт отметки
    assert {row["status"] for row in await schedule.days_on(house, day.isoformat())} == {"open"}


async def test_category_can_be_renamed_by_a_manager_without_duplicates(make_client, house):
    client = make_client()
    categories = (await client.get(f"/api/houses/{house}/management", headers=headers(OWNER))).json()["categories"]
    first, second = categories[0], categories[1]
    path = f"/api/houses/{house}/categories/{first['id']}/rename"
    assert (await client.post(path, headers=headers(NEIGHBOR), json={"name": "Новое"})).status_code == 422
    assert (await client.post(path, headers=headers(OWNER), json={"name": second["name"].lower()})).status_code == 422
    assert (await client.post(path, headers=headers(OWNER), json={"name": first["name"]})).status_code == 200
    assert (await client.post(path, headers=headers(OWNER), json={"name": "  Для кухни "})).status_code == 200
    listing = (await client.get(f"/api/houses/{house}/management", headers=headers(OWNER))).json()
    names = [row["name"] for row in listing["categories"]]
    assert "Для кухни" in names and first["name"] not in names
    missing = f"/api/houses/{house}/categories/99999/rename"
    assert (await client.post(missing, headers=headers(OWNER), json={"name": "Что-то"})).status_code == 422


async def test_receipt_can_be_removed_until_the_expense_is_reimbursed(make_client, house):
    client = make_client()
    expense = await money.add_expense(house, NEIGHBOR, 700, None, today(), "personal", "Чек", ["file-1", "file-2"])
    base = f"/api/houses/{house}/expenses/{expense}/receipts"
    listing = (await client.get(base, headers=headers(NEIGHBOR))).json()
    assert listing["can_edit"] is True and len(listing["receipts"]) == 2
    first = listing["receipts"][0]["id"]
    assert (await client.post(f"{base}/{first}/delete", headers=headers(STRANGER))).status_code == 422
    assert (await client.post(f"{base}/{first}/delete", headers=headers(NEIGHBOR))).status_code == 200
    assert (await client.post(f"{base}/{first}/delete", headers=headers(NEIGHBOR))).status_code == 422
    await money.reimburse_expense(house, expense, OWNER)
    frozen = (await client.get(base, headers=headers(NEIGHBOR))).json()
    assert frozen["can_edit"] is False
    last = frozen["receipts"][0]["id"]
    assert (await client.post(f"{base}/{last}/delete", headers=headers(NEIGHBOR))).status_code == 422


async def test_only_the_owner_deletes_a_house_and_only_with_its_exact_name(make_client, house):
    bot = FakeBot()
    client = make_client(bot)
    other = await households.create_house(OWNER, "Хозяин", "Дача")
    await money.add_expense(house, NEIGHBOR, 700, None, today(), "house", "Чек", ["file-1"])
    path = f"/api/houses/{house}/delete"
    assert (await client.post(path, headers=headers(NEIGHBOR), json={"confirm_name": "Дом"})).status_code == 422
    assert (await client.post(path, headers=headers(OWNER), json={"confirm_name": "дом"})).status_code == 422
    assert (await client.post(path, headers=headers(OWNER), json={"confirm_name": "Дача"})).status_code == 422
    assert (await households.get_house(house)) is not None
    assert (await client.post(path, headers=headers(OWNER), json={"confirm_name": " Дом "})).status_code == 200
    assert await households.get_house(house) is None and await transactions.all_rows(house) == []
    assert (await client.get(f"/api/houses/{house}", headers=headers(OWNER))).status_code == 422
    owner_houses = [row["id"] for row in (await client.get("/api/houses", headers=headers(OWNER))).json()["houses"]]
    assert other in owner_houses and house not in owner_houses
    neighbor_list = (await client.get("/api/houses", headers=headers(NEIGHBOR))).json()["houses"]
    neighbor_houses = [row["id"] for row in neighbor_list]
    assert house not in neighbor_houses
    assert [chat for chat, _ in bot.messages] == [NEIGHBOR] and "удалён" in bot.messages[0][1]


async def test_ownership_moves_to_another_member_and_the_old_owner_can_then_leave(make_client, house):
    bot = FakeBot()
    client = make_client(bot)
    path = f"/api/houses/{house}/owner"
    assert (await client.post(path, headers=headers(NEIGHBOR), json={"target": NEIGHBOR})).status_code == 422
    assert (await client.post(path, headers=headers(OWNER), json={"target": OWNER})).status_code == 422
    assert (await client.post(path, headers=headers(OWNER), json={"target": STRANGER})).status_code == 422
    assert (await client.post(f"/api/houses/{house}/leave", headers=headers(OWNER))).status_code == 422
    assert (await client.post(path, headers=headers(OWNER), json={"target": NEIGHBOR})).status_code == 200
    roles = {row["tg_id"]: row["role"] for row in await households.members(house)}
    assert roles == {OWNER: "member", NEIGHBOR: "owner"}
    assert await households.can(house, NEIGHBOR, "manage_house_settings")
    assert not await households.can(house, OWNER, "manage_house_settings")
    assert [chat for chat, _ in bot.messages] == [NEIGHBOR]
    assert (await client.post(f"/api/houses/{house}/leave", headers=headers(OWNER))).status_code == 200
    again = await post(client, f"/api/houses/{house}/delete", OWNER, {"confirm_name": "Дом"})
    assert again.status_code == 422


async def test_members_are_removed_by_managers_but_never_the_owner_or_oneself(make_client, house):
    bot = FakeBot()
    client = make_client(bot)
    # дом живёт по своему часовому поясу, а не по часам машины: у полуночи эти даты расходятся
    house_today = settings.house_today(await settings.house_settings(house))
    day = date.fromisoformat(house_today) + timedelta(days=1)
    await cleaning.save_weekday_map(house, {NEIGHBOR: day.weekday()}, house_today)
    assert any(row["tg_id"] == NEIGHBOR for row in await schedule.days_on(house, day.isoformat()))
    remove = lambda actor, target: client.post(f"/api/houses/{house}/members/{target}/remove", headers=headers(actor))  # noqa: E731
    assert (await remove(NEIGHBOR, OWNER)).status_code == 422
    assert (await remove(OWNER, OWNER)).status_code == 422
    await households.set_grant(house, NEIGHBOR, "manage_members", True)
    assert (await remove(NEIGHBOR, OWNER)).status_code == 422 and (await remove(NEIGHBOR, NEIGHBOR)).status_code == 422
    assert (await remove(OWNER, NEIGHBOR)).status_code == 200
    assert (await client.get(f"/api/houses/{house}", headers=headers(NEIGHBOR))).status_code == 422
    assert not any(row["tg_id"] == NEIGHBOR for row in await schedule.days_on(house, day.isoformat()))
    assert (await remove(OWNER, NEIGHBOR)).status_code == 422
    assert [chat for chat, _ in bot.messages] == [NEIGHBOR] and "убрали" in bot.messages[0][1]


async def test_export_and_template_go_to_the_private_chat(make_client, house):
    bot = FakeBot()
    client = make_client(bot)
    sent = await client.post(f"/api/houses/{house}/export/csv/send", headers=headers(NEIGHBOR))
    assert sent.status_code == 200 and sent.json() == {"sent": True, "bot": "Domovskii_bot", "link": "https://t.me/Domovskii_bot"}
    assert bot.documents == [(NEIGHBOR, f"domovoy-{house}-all.csv", "Операции дома «Дом». Фото чеков остаются в боте.")]
    month = await client.post(f"/api/houses/{house}/export/xlsx/send?month=2026-10", headers=headers(OWNER))
    assert month.status_code == 200 and bot.documents[-1][1] == f"domovoy-{house}-2026-10.xlsx"
    assert (await client.post(f"/api/houses/{house}/template/csv/send", headers=headers(NEIGHBOR))).status_code == 422
    assert (await client.post(f"/api/houses/{house}/template/csv/send", headers=headers(OWNER))).status_code == 200
    assert bot.documents[-1][:2] == (OWNER, "domovoy-template.csv")
    assert (await client.post(f"/api/houses/{house}/export/csv/send", headers=headers(STRANGER))).status_code == 422


@pytest.mark.parametrize("bot, fragment", [
    (None, "Отправка в чат сейчас недоступна"), (FakeBot(forbidden=True), "Бот не может написать"),
])
async def test_chat_delivery_failures_explain_what_to_do(make_client, house, bot, fragment):
    client = make_client(bot)
    result = await client.post(f"/api/houses/{house}/export/csv/send", headers=headers(OWNER))
    assert result.status_code == 422 and fragment in result.json()["detail"]
    assert (await overview(make_client(bot), house))["can_send_files"] is (bot is not None)


async def test_one_response_can_carry_several_pages_of_the_journal(make_client, house):
    client = make_client()
    for index in range(25):
        await money.add_expense(house, OWNER, 100 + index, None, today(), "house", f"Запись {index}", [])
    first = await overview(client, house, query="?page=0")
    both = await overview(client, house, query="?page=0&span=2")
    assert len(first["rows"]) == 20 and len(both["rows"]) == 25 and both["total"] == 25
    assert [row["id"] for row in both["rows"][:20]] == [row["id"] for row in first["rows"]]
    assert first["max_span"] == JOURNAL_MAX_SPAN  # клиент не просит больше, чем отдаёт сервер
    for span in (0, JOURNAL_MAX_SPAN + 1):
        assert (await client.get(f"/api/houses/{house}?span={span}", headers=headers(OWNER))).status_code == 422
