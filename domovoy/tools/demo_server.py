"""Демо-стенд сайта Домового: тестовые данные, подпись входа и эмуляция Telegram — без бота и сети.

    python tools/demo_server.py [--port 8011] [--fresh]

Адрес: http://127.0.0.1:8011/?u=1001 — 1001 владелец, 1002 и 1003 жильцы без прав, 1004 дом без данных, 1005 нет домов.
Параметры &theme=light|dark и &platform=ios|android|tdesktop меняют среду Telegram.
Бот-заглушка принимает «отправку в чат», поэтому на ios и android файлы уходят только в чат, на tdesktop — и в чат, и на устройство.
Данные лежат в data/demo.db (в git не попадают). Токен тестовый: настоящий .env сюда не попадает.
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
DEMO_DB = ROOT / "data" / "demo.db"
DEMO_TOKEN = "123456:DEMO_HOME_BOT"
# Переменные заданы до импорта проекта: конфиг читает их один раз, а .env их не перекрывает.
os.environ["DOMOVOY_DATABASE_URL"] = f"sqlite://{DEMO_DB}"
os.environ["DOMOVOY_BOT_TOKEN"] = DEMO_TOKEN
sys.path.insert(0, str(ROOT))

NAMES = {1001: "Слава", 1002: "Аня", 1003: "Борис", 1004: "Новичок", 1005: "Гость"}
THEMES = {
    "dark": {"bg_color": "#17212b", "text_color": "#f5f5f5", "hint_color": "#708499", "button_color": "#5288c1"},
    "light": {"bg_color": "#ffffff", "text_color": "#000000", "hint_color": "#999999", "button_color": "#2481cc"},
}
TELEGRAM_SCRIPT = "https://telegram.org/js/telegram-web-app.js"
LONG_AMOUNT_KOP = 999_999_999


class DemoBot:
    """Вместо настоящего бота: документы и сообщения не уходят никуда, а фото чеков хранятся в памяти (как файлы Telegram)."""

    def __init__(self):
        self.photos = {}

    async def send_document(self, chat_id, document, caption=None, **_):
        return None

    async def send_message(self, chat_id, text, **_):
        return None

    async def send_photo(self, chat_id, photo, caption=None, **_):
        file_id = f"demo-photo-{len(self.photos) + 1}"
        self.photos[file_id] = photo.data
        return SimpleNamespace(photo=[SimpleNamespace(file_id=file_id)])

    async def get_file(self, file_id):
        return SimpleNamespace(file_path=file_id, file_size=len(self.photos[file_id]))

    async def download_file(self, file_path, destination, **_):
        destination.write(self.photos[file_path])

    async def me(self):
        return SimpleNamespace(username="domovoy_demo_bot")


def signed_init_data(tg_id: int) -> str:
    """Подписанные данные входа — так же, как их подписывает Telegram."""
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": tg_id, "first_name": NAMES.get(tg_id, "Гость")}, ensure_ascii=False)}
    secret = hmac.new(b"WebAppData", DEMO_TOKEN.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def telegram_shim(tg_id: int, theme: str, platform: str) -> str:
    """Скрипт вместо telegram-web-app.js: тот же интерфейс, а вызовы записываются в window.__tgcalls."""
    bottom_inset = 34 if platform == "ios" else 0
    return f"""(() => {{
  const calls = [];
  const rec = name => (...args) => {{ calls.push([name, args]); }};
  const bar = name => ({{ show: rec(name + '.show'), hide: rec(name + '.hide'), onClick: rec(name + '.onClick'), offClick: rec(name + '.offClick') }});
  window.Telegram = {{ WebApp: {{
    initData: {json.dumps(signed_init_data(tg_id))}, version: '8.0', platform: {json.dumps(platform)}, colorScheme: {json.dumps(theme)},
    initDataUnsafe: {{ user: {{ id: {tg_id}, first_name: {json.dumps(NAMES.get(tg_id, "Гость"), ensure_ascii=False)} }} }},
    themeParams: {json.dumps(THEMES[theme])}, safeAreaInset: {{ top: 0, bottom: {bottom_inset}, left: 0, right: 0 }},
    ...Object.fromEntries(['ready', 'expand', 'close', 'setHeaderColor', 'setBackgroundColor', 'setBottomBarColor', 'enableClosingConfirmation',
      'disableClosingConfirmation', 'enableVerticalSwipes', 'disableVerticalSwipes', 'openTelegramLink', 'openLink', 'onEvent'].map(name => [name, rec(name)])),
    HapticFeedback: {{ impactOccurred: rec('impactOccurred'), notificationOccurred: rec('notificationOccurred'), selectionChanged: rec('selectionChanged') }},
    BackButton: bar('BackButton'),
  }} }};
  window.__tgcalls = calls;
}})();
"""


async def seed() -> None:
    from infrastructure.db import db
    from infrastructure.repositories import users
    from services import cleaning, households, money, settings

    for tg_id in (1001, 1002, 1003, 1004):
        await users.upsert_user(tg_id, NAMES[tg_id], None)

    # Дом 1: обычная жизнь — взносы, траты (из котла и за свои), просроченные дни уборки, ожидающий взнос.
    house = await households.create_house(1001, "Слава", "Квартира на Садовой")
    row = await households.get_house(house)
    await households.join_house(row, 1002, "Аня")
    await households.join_house(row, 1003, "Борис")
    today = settings.house_today(await settings.house_settings(house))
    base = date.fromisoformat(today)
    day = lambda offset: (base + timedelta(days=offset)).isoformat()  # noqa: E731 — короткий помощник дат
    categories = {category["name"]: category["id"] for category in await money.categories(house)}
    last_month = (base.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    for member, kop, month, paid in ((1001, 40000, last_month, day(-33)), (1002, 35000, last_month, day(-31)),
                                     (1001, 30000, today[:7], day(-6)), (1002, 25050, today[:7], day(-4))):
        contribution = await money.declare_contribution(house, member, kop, paid, month=month)
        await money.resolve_contribution(contribution["id"], True, 1001, house_id=house)
    await money.declare_contribution(house, 1003, 20000, day(-1), month=today[:7])
    expenses = [
        (1001, 8745, "Продукты", day(0), "house", "Migros: молоко, хлеб, овощи"),
        (1002, 2390, "Бытовая химия", day(-1), "house", "Порошок и губки"),
        (1003, 14250, "Коммуналка", day(-2), "personal", "Интернет за месяц"),
        (1001, 5600, "Продукты", day(-3), "personal", ""),
        (1002, 31990, "Ремонт", day(-5), "house", "Смеситель в ванной, самый дорогой из магазина; ещё прокладки и фум-лента, чтобы больше не капало."),
        (1003, 1850, "Прочее", day(-6), "house", "Лампочки"),
        (1001, 12099, "Продукты", day(-9), "house", "Закупка на неделю"),
        (1002, 4320, "Бытовая химия", day(-12), "personal", "Средство для стёкол"),
        (1003, 9900, "Коммуналка", day(-20), "house", "Электричество"),
        (1001, 7650, "Продукты", day(-24), "house", "Прошлый месяц: продукты"),
        (1002, 15000, "Ремонт", day(-28), "house", "Полка в прихожей"),
        (1001, 3300, "Прочее", day(-35), "house", "Старая запись"),
    ]
    for member, kop, category, spent, mode, description in expenses:
        expense = await money.add_expense(house, member, kop, categories[category], spent, mode, description, [])
        if kop == 4320:
            await money.reimburse_expense(house, expense, 1001)
    weekday = base.weekday()
    await cleaning.save_weekday_map(house, {1001: weekday, 1002: (weekday + 2) % 7, 1003: (weekday + 4) % 7}, today)
    await cleaning.ensure_days(house, today)
    async with db.acquire() as conn:
        for offset in (-7, -14):
            await conn.execute("INSERT OR IGNORE INTO cleaning_days (house_id, tg_id, planned_date, status) VALUES (?, ?, ?, 'open')",
                               house, 1001, day(offset))

    # Дом 2: пустой — для переключателя и пустых состояний.
    second = await households.create_house(1001, "Слава", "Дача")
    await households.join_house(await households.get_house(second), 1004, "Новичок")

    # Дом 3: крайние значения — имя на 32 символа, описание на 200, огромная сумма, отрицательный баланс.
    third = await households.create_house(1001, "Слава", "Квартира у моря на Садовой улице"[:32])
    await households.join_house(await households.get_house(third), 1002, "Анастасия Александровна Прекрасная")
    await money.add_category(third, "Очень длинная категория"[:24])
    long_category = next(category["id"] for category in await money.categories(third) if category["name"].startswith("Очень"))
    await money.add_expense(third, 1001, LONG_AMOUNT_KOP, long_category, today, "house", ("Очень длинное описание покупки " * 8)[:200], [])
    await money.add_expense(third, 1002, 12345, None, day(-1), "personal", "Коротко", [])


async def serve(port: int, fresh: bool) -> None:
    import uvicorn
    from fastapi.responses import HTMLResponse, Response

    if fresh:
        for suffix in ("", "-wal", "-shm"):
            Path(f"{DEMO_DB}{suffix}").unlink(missing_ok=True)
    DEMO_DB.parent.mkdir(parents=True, exist_ok=True)
    existed = DEMO_DB.exists()

    from infrastructure.db import db
    from infrastructure.schema import ensure_schema
    from web.app import SECURITY_HEADERS, STATIC, asset_version, create_app

    await db.connect()
    await ensure_schema()
    if not existed:
        await seed()
    app = create_app(bot=DemoBot())

    async def index(u: int = 1001, theme: str = "dark", platform: str = "ios"):
        page = (STATIC / "index.html").read_text(encoding="utf-8").replace("__V__", asset_version())
        page = page.replace(TELEGRAM_SCRIPT, f"/__telegram.js?u={u}&theme={theme}&platform={platform}")
        return HTMLResponse(page, headers=SECURITY_HEADERS)

    async def telegram(u: int = 1001, theme: str = "dark", platform: str = "ios"):
        return Response(telegram_shim(u, theme, platform), media_type="text/javascript", headers={"Cache-Control": "no-store"})

    app.add_api_route("/", index, methods=["GET"])
    app.add_api_route("/__telegram.js", telegram, methods=["GET"])
    for _ in range(2):  # новые маршруты — первыми: обычная страница входа закрывается
        app.router.routes.insert(0, app.router.routes.pop())
    print(f"Демо-стенд: http://127.0.0.1:{port}/?u=1001", flush=True)
    await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")).serve()


if __name__ == "__main__":
    arguments = sys.argv[1:]
    asyncio.run(serve(int(arguments[arguments.index("--port") + 1]) if "--port" in arguments else 8011, "--fresh" in arguments))
