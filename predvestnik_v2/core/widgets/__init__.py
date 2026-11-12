"""HTML-виджеты в сообщениях (Bot API 10.4, сессии S30): пределы Telegram, реестр, сборка HTML, протокол запросов.

Виджет — живой HTML-блок прямо в сообщении. Его код не меняется после отправки; меняется только состояние
(chat_data), и пишет его только бот. Виджет просит бота коротким запросом (1–64 байта) и рисует ответ.
В проде Telegram показывает виджеты **только в личке с ботом**: не в группах, не inline, не в переписках
Business; отправленные виджеты защищены от пересылки.

Игроку виджеты — окна в те же сервисы, что у мини-приложения и текстовых команд (S30b): «Табло» (hub) заменяет
в личке текстовые «план», «квесты» и «пропуск», «Сапёр» (mines) — игра прямо в сообщении. Оба собираются под
надетый образ целиком (core/widgets/skin.py): фон-сцена, цвета, рамка, узоры и значки — та же косметика, что в чате
и приложении; HTML «вшивает» образ при отправке, в состоянии едет только его подпись `k`.
Если виджет недоступен (выключен, игрок выбрал текст, Telegram отказал) — уходит прежний текст.

Как добавить виджет:
1. Шаблон `core/widgets/html/<key>.html`: разметка, `<style>` и один `<script>`, в котором объявлены
   `var KEY='<key>'` и `function draw(s)`. Общие стили (`_base.css`) и общий загрузчик (`_boot.js`) подставляет
   `html()`: загрузчик рисует первое состояние сразу, при `LIVE` просит свежее (`SNAP()` или `<key>:s`)
   и даёт `ask(data, tap)`. У Spec.themed в скрипт попадает `var L={…}` — подписи и узоры образа (skin.Look).
2. Строка в REGISTRY ниже.
3. Модуль `services/widgets/<key>.py`: `SAMPLE` (самое длинное правдоподобное состояние),
   `async state(db, user_id, view)`, при нажатиях — `async act(db, user_id, verb, args, *, action_id)`.
   Проверка: `tools/test_telegram_widgets_contract.py`, скрипты: `node tools/test_telegram_widgets.js`,
   живой вид — вкладка «Виджеты» в админке создателя.
"""
from __future__ import annotations

import json
import time
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

# Пределы Bot API 10.4 (https://core.telegram.org/bots/widgets.md, «Limits» и методы sendWidget/answerWidgetQuery).
MAX_HTML_BYTES: Final = 32768          # байт UTF-8 исходного HTML
MAX_PACKED_BYTES: Final = 4096         # байт после zlib.compress(html, 9) — так считает сервер
PACKED_BUDGET: Final = 4064            # наш потолок под предел Telegram (тот же zlib 9); проверяется для каждого образа и уровня
MAX_STATE_BYTES: Final = 1024          # chat_data / public_data
MAX_ANSWER_BYTES: Final = 1024         # data в answerWidgetQuery
MAX_QUERY_BYTES: Final = 64            # data запроса виджета
MAX_CAPTION_CHARS: Final = 1024
ANSWER_DEADLINE_SEC: Final = 15.0      # Telegram ждёт ответа на запрос столько, потом виджет видит TIMEOUT
ANSWER_BUDGET_SEC: Final = 12.0        # сами укладываемся с запасом на сеть
WORK_BUDGET_SEC: Final = 6.0          # база и обработчик оставляют время на ответ Telegram
PERSIST_BUDGET_SEC: Final = 3.0       # сохранение сообщения не держит задачу после ответа
UPDATE_TYPES: Final = ("widget_query", "shared_widget_query")   # их нужно явно просить в allowed_updates

SNAPSHOT_VERB: Final = "s"             # «дай свежее состояние» (`<key>:s[:<вид>]`): виджет шлёт при появлении на экране
CREATOR: Final = "creator"             # показывать только создателю бота (вкладка «Виджеты» в админке)
PLAYERS: Final = "players"             # создателю всегда, остальным — когда включён PLAYERS_FLAG
PLAYERS_FLAG: Final = "widgets_players_v1"   # system_flags: «Виджеты для всех игроков» (админка → «Функции»)
ROWS_KEY: Final = "l"                  # строки «Табло»: при нехватке места fit() убирает пояснения, затем хвост
ROOM_FOR_REVISION: Final = 24          # `,"r":1762862400000` дописывается после подгонки

HTML_DIR: Final = Path(__file__).resolve().parent / "html"


@dataclass(frozen=True)
class Spec:
    key: str             # префикс запросов виджета и имя шаблона; [a-z]{2,8}
    icon: str
    title: str           # плитка во вкладке «Виджеты»
    hint: str            # строка под названием плитки: что внутри
    caption: str         # подпись под виджетом: её видят старые версии Telegram и список чатов
    queries: bool = True     # виджет спрашивает бота (allow_queries); без этого он только рисует состояние
    audience: str = CREATOR  # кто может получить виджет и спрашивать бота
    themed: bool = False     # собирается под надетый образ (core/widgets/skin.py), подпись образа `k` в состоянии
    views: tuple[str, ...] = ()   # экраны виджета (`<key>:s:<вид>`); первый — по умолчанию
    section: str = ""        # раздел мини-приложения для кнопки под виджетом (core.miniapp_links)


REGISTRY: dict[str, Spec] = {s.key: s for s in (
    Spec("ping", "📡", "Проверка связи", "Тема, отклик бота, вибрация, копирование",
         "📡 Проверка связи: виджет сам спросит бота и покажет, за сколько пришёл ответ."),
    Spec("ttt", "❌", "Крестики-нолики", "Партия с ботом прямо в сообщении",
         "❌ Крестики-нолики с ботом. Ты ходишь первым."),
    Spec("hub", "🎛", "Табло", "Я, день, задания, Пропуск и питомцы в цветах образа",
         "🎛 Табло Предвестника. Не видно табло — обнови Telegram или нажми «Текстом».",
         audience=PLAYERS, themed=True, views=("day", "me", "q", "qw", "pass", "pets"), section="home"),
    Spec("mines", "💣", "Сапёр", "Партия прямо в сообщении, опыт Пропуска и задания как в приложении",
         "💣 Сапёр в чате. Не видно поля — обнови Telegram или открой Сапёр в приложении.",
         audience=PLAYERS, themed=True, section="games"),
)}


def spec(key: str) -> Spec | None:
    return REGISTRY.get(key)


@lru_cache(maxsize=32)
def _read(name: str) -> str:
    return (HTML_DIR / name).read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1024)
def html(key: str, skin_id: str | None = None, tier: str = "D") -> str:
    """Готовый HTML виджета: общие стили, образ (у Spec.themed), шаблон и общий загрузчик в конце его скрипта."""
    template = _read(f"{key}.html")
    start, end = template.find("<script>"), template.rfind("</script>")
    if start < 0 or end < 0:
        raise ValueError(f"widget {key}: template has no <script>")
    css, data = _read("_base.css"), ""
    if REGISTRY[key].themed:
        from core.widgets.skin import look
        dressed = look(skin_id, tier)
        css, data = css + dressed.css, dressed.data
    start += len("<script>")
    body = template[:start] + data + template[start:end] + ";" + _read("_boot.js") + template[end:]
    return f"<style>{css}</style>{body}"


def packed_size(source: str) -> int:
    return len(zlib.compress(source.encode("utf-8"), 9))


def size_problems(source: str) -> list[str]:
    """Почему Telegram откажет в этом HTML (пусто — примет). Проверяется перед каждой отправкой."""
    raw = source.encode("utf-8")
    out = []
    if not 1 <= len(raw) <= MAX_HTML_BYTES:
        out.append(f"HTML {len(raw)} B, допустимо 1–{MAX_HTML_BYTES}")
    if "\x00" in source:
        out.append("NUL в HTML (INPUT_MEDIA_WIDGET_HTML_INVALID)")
    packed = packed_size(source)
    if packed > MAX_PACKED_BYTES:
        out.append(f"после сжатия {packed} B > {MAX_PACKED_BYTES}")
    return out


def revision() -> int:
    """Номер состояния: растёт со временем, виджет не рисует ответ старше уже нарисованного (см. «Keep the newest state»)."""
    return int(time.time() * 1000)


def view_of(spec: Spec, requested: str | None) -> str | None:
    """Известный экран виджета или экран по умолчанию; у виджета без экранов — None."""
    if not spec.views:
        return None
    return requested if requested in spec.views else spec.views[0]


def size_of(payload: dict) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def fit(payload: dict, *, limit: int = min(MAX_STATE_BYTES, MAX_ANSWER_BYTES) - ROOM_FOR_REVISION) -> dict:
    """Уложить строки «Табло» в предел: сначала без пояснений с конца, потом без хвоста со строкой-отсылкой.

    Строки — тексты из игры (названия заданий, имена питомцев), и их длину заранее не угадать; отказ виджету
    из-за лишнего байта хуже, чем короче список. Не строки (подпись образа, вкладка) не трогаются."""
    rows = payload.get(ROWS_KEY)
    if size_of(payload) <= limit or not isinstance(rows, list):
        return payload
    out = {**payload, ROWS_KEY: [dict(row) for row in rows]}
    for row in reversed(out[ROWS_KEY]):
        if size_of(out) <= limit:
            return out
        row.pop("s", None)
    more = {"i": "…", "t": "Остальное — в приложении"}
    while size_of(out) > limit and len(out[ROWS_KEY]) > 1:
        out[ROWS_KEY].pop(-2 if out[ROWS_KEY][-1] is more else -1)
        if out[ROWS_KEY][-1] is not more:
            out[ROWS_KEY].append(more)
    return out


def encode(payload: dict, *, limit: int = MAX_STATE_BYTES) -> str:
    """Состояние или ответ в короткий JSON; больше предела — ошибка в коде виджета, а не обрезка молча."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    size = len(text.encode("utf-8"))
    if size > limit:
        raise ValueError(f"widget payload {size} B > {limit} B")
    return text


def error(text: str) -> str:
    """Ответ-отказ: виджет покажет текст в строке состояния."""
    return encode({"e": text[:200]}, limit=MAX_ANSWER_BYTES)


def parse_query(data: str) -> tuple[str, str, list[str]] | None:
    """`<key>:<verb>[:<arg>…]` → (key, verb, args); мусор → None. Данные запроса — недоверенный ввод."""
    if not isinstance(data, str) or not 1 <= len(data.encode("utf-8")) <= MAX_QUERY_BYTES:
        return None
    parts = data.split(":")
    if len(parts) < 2 or parts[0] not in REGISTRY or not parts[1]:
        return None
    return parts[0], parts[1], parts[2:]
