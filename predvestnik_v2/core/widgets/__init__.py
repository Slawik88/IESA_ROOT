"""HTML-виджеты в сообщениях (Bot API 10.4, сессии S30): пределы Telegram, реестр, сборка HTML, протокол запросов.

Виджет — живой HTML-блок прямо в сообщении. Его код не меняется после отправки; меняется только состояние
(chat_data), и пишет его только бот. Виджет просит бота коротким запросом (1–64 байта) и рисует ответ.
В проде Telegram показывает виджеты **только в личке с ботом**: не в группах, не inline, не в переписках
Business; отправленные виджеты защищены от пересылки.

Как добавить виджет:
1. Шаблон `core/widgets/html/<key>.html`: разметка, `<style>` и один `<script>`, в котором объявлены
   `var KEY='<key>'` и `function draw(s)`. Общие стили (`_base.css`) и общий загрузчик (`_boot.js`) подставляет
   `html()`: загрузчик рисует первое состояние сразу, просит свежее (`<key>:s`) и даёт `ask(data, tap)`.
2. Строка в REGISTRY ниже.
3. Модуль `services/widgets/<key>.py`: `SAMPLE` (самое длинное правдоподобное состояние), `async state(db, user_id)`,
   при нажатиях — `async act(db, user_id, verb, args)`. Проверка: `tools/test_telegram_widgets_contract.py`,
   скрипты: `node tools/test_telegram_widgets.js`, живой вид — вкладка «Виджеты» в админке создателя.
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
PACKED_BUDGET: Final = 3900            # наш потолок с запасом: правка в одну строку не должна упереться в отказ
MAX_STATE_BYTES: Final = 1024          # chat_data / public_data
MAX_ANSWER_BYTES: Final = 1024         # data в answerWidgetQuery
MAX_QUERY_BYTES: Final = 64            # data запроса виджета
MAX_CAPTION_CHARS: Final = 1024
ANSWER_DEADLINE_SEC: Final = 15.0      # Telegram ждёт ответа на запрос столько, потом виджет видит TIMEOUT
ANSWER_BUDGET_SEC: Final = 12.0        # сами укладываемся с запасом на сеть
WORK_BUDGET_SEC: Final = 6.0          # база и обработчик оставляют время на ответ Telegram
PERSIST_BUDGET_SEC: Final = 3.0       # сохранение сообщения не держит задачу после ответа
UPDATE_TYPES: Final = ("widget_query", "shared_widget_query")   # их нужно явно просить в allowed_updates

SNAPSHOT_VERB: Final = "s"             # «дай свежее состояние»: виджет шлёт при появлении на экране
CREATOR: Final = "creator"             # показывать только создателю бота (вкладка «Виджеты» в админке)
PLAYERS: Final = "players"

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


REGISTRY: dict[str, Spec] = {s.key: s for s in (
    Spec("ping", "📡", "Проверка связи", "Тема, отклик бота, вибрация, копирование",
         "📡 Проверка связи: виджет сам спросит бота и покажет, за сколько пришёл ответ."),
    Spec("ttt", "❌", "Крестики-нолики", "Партия с ботом прямо в сообщении",
         "❌ Крестики-нолики с ботом. Ты ходишь первым."),
)}


def spec(key: str) -> Spec | None:
    return REGISTRY.get(key)


@lru_cache(maxsize=32)
def _read(name: str) -> str:
    return (HTML_DIR / name).read_text(encoding="utf-8").strip()


def html(key: str) -> str:
    """Готовый HTML виджета: общие стили, шаблон и общий загрузчик в конце его скрипта."""
    template = _read(f"{key}.html")
    end = template.rfind("</script>")
    if end < 0:
        raise ValueError(f"widget {key}: template has no <script>")
    body = template[:end] + ";" + _read("_boot.js") + template[end:]
    return f"<style>{_read('_base.css')}</style>{body}"


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
