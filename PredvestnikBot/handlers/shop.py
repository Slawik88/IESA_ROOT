"""
РњР°РіР°Р·РёРЅ РџСЂРµРґРІРµСЃС‚РЅРёРєР° вЂ” РїРѕРєСѓРїРєР° СЌРєСЃРєР»СЋР·РёРІРЅС‹С… С‚РѕРІР°СЂРѕРІ Р·Р° РјРѕСЂСѓ.

РљРѕРјР°РЅРґС‹:
  Р±РѕС‚ РјР°РіР°Р·РёРЅ / Р±РѕС‚ Р»Р°РІРєР° / Р±РѕС‚ shop  вЂ” РєР°С‚Р°Р»РѕРі С‚РѕРІР°СЂРѕРІ
"""

import html

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import (
    ANON_MSG_PRICE,
    BANK_PLANS,
    GACHA_MULTI_PRICE,
    GACHA_SINGLE_PRICE,
    LOTTERY_TICKET_PRICE,
    MARRIAGE_GIFTS,
    MINI_APP_TG_URL,
    PET_ADOPT_PRICE,
    PET_MORA_SKIP_PRICE,
    PET_RENAME_PRICE,
    QUEST_REROLL_PRICE,
    SECRET_MSG_PRICE,
    SHOP_ITEMS,
)
from shared_prices import PRICE_VIP
from database.db import (
    buy_shop_item,
    get_mora,
    has_shop_item,
    set_pet_color,
    set_pet_emoji_status,
    set_custom_title_in_chat,
)
from filters.bot_command import BotCommand
from utils.helpers import not_your_button
from handlers.economy import TOP_FRAMES, XP_BOOST_OPTIONS, deduct_wallet

from filters.chat_mode import MainChatOnly
import logging
_log = logging.getLogger(__name__)
router = Router()
router.message.filter(MainChatOnly())


_PET_COLORS = {
    "red":    "рџ”ґ РљСЂР°СЃРЅС‹Р№",
    "blue":   "рџ”µ РЎРёРЅРёР№",
    "green":  "рџџў Р—РµР»С‘РЅС‹Р№",
    "purple": "рџџЈ Р¤РёРѕР»РµС‚РѕРІС‹Р№",
    "gold":   "рџџЎ Р—РѕР»РѕС‚РѕР№",
    "cyan":   "рџ©µ Р‘РёСЂСЋР·РѕРІС‹Р№",
}

_SHOP_SECTIONS = {
    "all": "рџ§ѕ Р’СЃС‘",
    "economy": "рџЄ™ Р­РєРѕРЅРѕРјРёРєР°",
    "pets": "рџђѕ РџРёС‚РѕРјС†С‹",
    "gacha": "рџЋІ РњРѕР»РёС‚РІС‹",
    "bank": "рџЏ¦ Р‘Р°РЅРє",
    "gifts": "рџЋЃ РџРѕРґР°СЂРєРё",
    "casino": "рџЋ° РљР°Р·РёРЅРѕ",
    "cosmetics": "рџЋЁ РљРѕСЃРјРµС‚РёРєР°",
}


def _section_keyboard(uid: int, active: str, owned_keys: set[str] | None = None) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for key in ("all", "economy", "pets", "gacha", "bank", "gifts", "casino", "cosmetics"):
        label = _SHOP_SECTIONS[key]
        text = f"В· {label} В·" if key == active else label
        row.append(InlineKeyboardButton(text=text, callback_data=f"shop_nav:{uid}:{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if active == "cosmetics":
        owned = owned_keys or set()
        for key, item in SHOP_ITEMS.items():
            if key in owned:
                buttons.append([InlineKeyboardButton(
                    text=f"вњ… {item['name']} (РєСѓРїР»РµРЅРѕ)",
                    callback_data=f"shop_buy:{uid}:{key}:personal",
                )])
            else:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"рџ’° {item['name']} вЂ” {item['price']} рџЄ™",
                        callback_data=f"shop_buy:{uid}:{key}:personal",
                    ),
                    InlineKeyboardButton(
                        text="рџ‘ЁвЂЌрџ‘©вЂЌрџ‘§",
                        callback_data=f"shop_buy:{uid}:{key}:family",
                    ),
                ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _shop_text(section: str, bal: int) -> str:
    from shared_prices import CLEANUP_PASS_PRICE
    boost_prices = " В· ".join(f"{label}={price} рџЄ™" for _key, _hours, price, label in XP_BOOST_OPTIONS)
    frame_lines = "\n".join(
        f"  вЂў {emoji} <b>{name}</b> вЂ” {price} рџЄ™"
        for _key, emoji, name, price, _desc in TOP_FRAMES
        if price > 0
    )
    bank_lines = "\n".join(
        f"  вЂў <b>{entry['label']}</b>"
        for entry in BANK_PLANS.values()
    )
    gift_lines = "\n".join(
        f"  вЂў {gift['name']} вЂ” <b>{gift['price']} рџЄ™</b>"
        for gift in MARRIAGE_GIFTS.values()
    )
    cosmetics_lines = "\n".join(
        f"  вЂў {item['name']} вЂ” <b>{item['price']} рџЄ™</b>\n    <i>{item['desc']}</i>"
        for item in SHOP_ITEMS.values()
    )

    sections = {
        "all": (
            "рџ›Ќ <b>Р•РґРёРЅС‹Р№ РјР°РіР°Р·РёРЅ РџСЂРµРґРІРµСЃС‚РЅРёРєР°</b>\n\n"
            f"рџ’° РўРІРѕР№ Р±Р°Р»Р°РЅСЃ: <b>{bal} рџЄ™</b>\n\n"
            "рџЄ™ <b>Р­РєРѕРЅРѕРјРёРєР°</b>\n"
            f"  вЂў VIP вЂ” <b>{PRICE_VIP} рџЄ™</b> В· <code>Р±РѕС‚ РєСѓРїРёС‚СЊ РІРёРї</code>\n"
            f"  вЂў РћС‚РєСѓРї РѕС‚ С‡РёСЃС‚РєРё вЂ” <b>{CLEANUP_PASS_PRICE} рџЄ™</b> В· РљР”: 12 РґРЅ. В· <code>Р±РѕС‚ РѕС‚РєСѓРї</code>\n"
            f"  вЂў Р‘СѓСЃС‚ XP Г—2 вЂ” {boost_prices} В· <code>Р±РѕС‚ РєСѓРїРёС‚СЊ Р±СѓСЃС‚</code>\n"
            "  вЂў Р Р°РјРєРё РїСЂРѕС„РёР»СЏ вЂ” <code>Р±РѕС‚ СЂР°РјРєРё</code> / <code>Р±РѕС‚ РєСѓРїРёС‚СЊ СЂР°РјРєСѓ</code>\n"
            f"  вЂў РђРЅРѕРЅРёРјРєР° вЂ” <b>{ANON_MSG_PRICE} рџЄ™</b> В· <code>Р±РѕС‚ Р°РЅРѕРЅРёРјРєР° С‚РµРєСЃС‚</code>\n"
            f"  вЂў РЎРµРєСЂРµС‚РЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ вЂ” <b>{SECRET_MSG_PRICE} рџЄ™</b> В· <code>Р±РѕС‚ СЃРµРєСЂРµС‚ @user С‚РµРєСЃС‚</code>\n"
            f"  вЂў РџРµСЂРµР±СЂРѕСЃ Р·Р°РґР°РЅРёСЏ вЂ” <b>{QUEST_REROLL_PRICE} рџЄ™</b> В· <code>Р±РѕС‚ РїРµСЂРµР±СЂРѕСЃРёС‚СЊ Р·Р°РґР°РЅРёРµ</code>\n\n"
            "рџђѕ <b>РџРёС‚РѕРјС†С‹</b>\n"
            f"  вЂў Р—Р°РІРµСЃС‚Рё РїРёС‚РѕРјС†Р° вЂ” <b>{PET_ADOPT_PRICE} рџЄ™</b> В· <code>Р±РѕС‚ Р·Р°РІРµСЃС‚Рё РїРёС‚РѕРјС†Р°</code>\n"
            f"  вЂў РџСЂРѕРїСѓСЃРє РѕР¶РёРґР°РЅРёСЏ Р±СЂР°РєР° вЂ” <b>{PET_MORA_SKIP_PRICE} рџЄ™</b> В· <code>Р±РѕС‚ РїРёС‚РѕРјРµС†</code>\n"
            f"  вЂў РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ вЂ” <b>{PET_RENAME_PRICE} рџЄ™</b> В· <code>Р±РѕС‚ РЅР°Р·РІР°С‚СЊ РїРёС‚РѕРјС†Р° РРјСЏ</code>\n"
            "  вЂў Р­РєСЃРїРµРґРёС†РёРё вЂ” <code>Р±РѕС‚ СЌРєСЃРїРµРґРёС†РёСЏ</code>\n\n"
            "рџЋІ <b>РњРѕР»РёС‚РІС‹</b>\n"
            f"  вЂў РљСЂСѓС‚РєР° x1 вЂ” <b>{GACHA_SINGLE_PRICE} рџЄ™</b>\n"
            f"  вЂў РљСЂСѓС‚РєР° x10 вЂ” <b>{GACHA_MULTI_PRICE} рџЄ™</b>\n"
            "  вЂў РРЅРІРµРЅС‚Р°СЂСЊ / РїСЂРѕРґР°Р¶Р° РјСѓСЃРѕСЂР° вЂ” <code>Р±РѕС‚ РёРЅРІРµРЅС‚Р°СЂСЊ</code>, <code>Р±РѕС‚ РїСЂРѕРґР°С‚СЊ РјСѓСЃРѕСЂ</code>\n\n"
            "рџЏ¦ <b>Р‘Р°РЅРє</b>\n"
            f"{bank_lines}\n"
            "  вЂў РћС‚РєСЂС‹С‚СЊ РІРєР»Р°Рґ вЂ” <code>Р±РѕС‚ Р±Р°РЅРє</code>\n\n"
            "рџЋЃ <b>РџР°СЂР° Рё РїРѕРґР°СЂРєРё</b>\n"
            f"{gift_lines}\n"
            "  вЂў РљСѓРїРёС‚СЊ/РїРѕРґР°СЂРёС‚СЊ вЂ” <code>Р±РѕС‚ РїРѕРґР°СЂРєРё</code>\n\n"
            "рџЋЁ <b>РљРѕСЃРјРµС‚РёРєР°</b>\n"
            f"{cosmetics_lines}\n\n"
            "рџЋ° <b>РљР°Р·РёРЅРѕ</b>\n"
            f"  вЂў Р›РѕС‚РµСЂРµР№РЅС‹Р№ Р±РёР»РµС‚ вЂ” <b>{LOTTERY_TICKET_PRICE} рџЄ™</b> В· <code>Р±РѕС‚ РєСѓРїРёС‚СЊ Р»РѕС‚РµСЂРµСЋ</code>\n\n"
            "<i>РџРµСЂРµРєР»СЋС‡Р°Р№ РєР°С‚РµРіРѕСЂРёРё РєРЅРѕРїРєР°РјРё РЅРёР¶Рµ.</i>"
        ),
        "economy": (
            "рџЄ™ <b>РњР°РіР°Р·РёРЅ</b> вЂє <b>Р­РєРѕРЅРѕРјРёРєР°</b>\n\n"
            f"рџ’° Р‘Р°Р»Р°РЅСЃ: <b>{bal} рџЄ™</b>\n\n"
            f"рџ’Ћ VIP вЂ” <b>{PRICE_VIP} рџЄ™</b>\n  <code>Р±РѕС‚ РєСѓРїРёС‚СЊ РІРёРї</code>\n\n"
            f"рџЋ« РћС‚РєСѓРї РѕС‚ С‡РёСЃС‚РєРё вЂ” <b>{CLEANUP_PASS_PRICE} рџЄ™</b> В· РљР”: 12 РґРЅ.\n  <code>Р±РѕС‚ РѕС‚РєСѓРї</code>\n\n"
            f"вљЎ Р‘СѓСЃС‚ XP Г—2\n  {boost_prices}\n  <code>Р±РѕС‚ РєСѓРїРёС‚СЊ Р±СѓСЃС‚</code>\n\n"
            "рџ–ј Р Р°РјРєРё РїСЂРѕС„РёР»СЏ\n"
            f"{frame_lines}\n"
            "  <code>Р±РѕС‚ СЂР°РјРєРё</code> В· <code>Р±РѕС‚ РєСѓРїРёС‚СЊ СЂР°РјРєСѓ РЅР°Р·РІР°РЅРёРµ</code>\n\n"
            f"рџ“Ё РђРЅРѕРЅРёРјРєР° вЂ” <b>{ANON_MSG_PRICE} рџЄ™</b>\n  <code>Р±РѕС‚ Р°РЅРѕРЅРёРјРєР° С‚РµРєСЃС‚</code>\n\n"
            f"рџ”ђ РЎРµРєСЂРµС‚РЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ вЂ” <b>{SECRET_MSG_PRICE} рџЄ™</b>\n  <code>Р±РѕС‚ СЃРµРєСЂРµС‚ @user С‚РµРєСЃС‚</code>\n\n"
            f"рџЋЇ РџРµСЂРµР±СЂРѕСЃ Р·Р°РґР°РЅРёСЏ вЂ” <b>{QUEST_REROLL_PRICE} рџЄ™</b>\n  <code>Р±РѕС‚ РїРµСЂРµР±СЂРѕСЃРёС‚СЊ Р·Р°РґР°РЅРёРµ</code>"
        ),
        "pets": (
            "рџђѕ <b>РњР°РіР°Р·РёРЅ</b> вЂє <b>РџРёС‚РѕРјС†С‹</b>\n\n"
            f"рџ’° Р‘Р°Р»Р°РЅСЃ: <b>{bal} рџЄ™</b>\n\n"
            f"рџђ± Р—Р°РІРµСЃС‚Рё РїРёС‚РѕРјС†Р° вЂ” <b>{PET_ADOPT_PRICE} рџЄ™</b>\n"
            "  <code>Р±РѕС‚ Р·Р°РІРµСЃС‚Рё РїРёС‚РѕРјС†Р°</code>\n\n"
            f"вЏ© РџСЂРѕРїСѓСЃРє РѕР¶РёРґР°РЅРёСЏ Р±СЂР°РєР° вЂ” <b>{PET_MORA_SKIP_PRICE} рџЄ™</b>\n"
            "  <code>Р±РѕС‚ РїРёС‚РѕРјРµС†</code>\n\n"
            f"вњЏпёЏ РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ РїРёС‚РѕРјС†Р° вЂ” <b>{PET_RENAME_PRICE} рџЄ™</b>\n"
            "  <code>Р±РѕС‚ РЅР°Р·РІР°С‚СЊ РїРёС‚РѕРјС†Р° РРјСЏ</code>\n\n"
            "рџ—є Р­РєСЃРїРµРґРёС†РёРё РїРёС‚РѕРјС†Р°\n"
            "  <code>Р±РѕС‚ СЌРєСЃРїРµРґРёС†РёСЏ</code>"
        ),
        "gacha": (
            "рџЋІ <b>РњР°РіР°Р·РёРЅ</b> вЂє <b>РњРѕР»РёС‚РІС‹</b>\n\n"
            f"рџ’° Р‘Р°Р»Р°РЅСЃ: <b>{bal} рџЄ™</b>\n\n"
            f"рџ™Џ РћРґРЅР° РјРѕР»РёС‚РІР° вЂ” <b>{GACHA_SINGLE_PRICE} рџЄ™</b>\n"
            f"рџ™Џ Р”РµСЃСЏС‚СЊ РјРѕР»РёС‚РІ вЂ” <b>{GACHA_MULTI_PRICE} рџЄ™</b>\n\n"
            "рџ“¦ РЎРѕРїСѓС‚СЃС‚РІСѓСЋС‰РёРµ РєРѕРјР°РЅРґС‹\n"
            "  <code>Р±РѕС‚ РјРѕР»РёС‚РІР°</code>\n"
            "  <code>Р±РѕС‚ РёРЅРІРµРЅС‚Р°СЂСЊ</code>\n"
            "  <code>Р±РѕС‚ РїСЂРѕРґР°С‚СЊ РјСѓСЃРѕСЂ</code>\n"
            "  <code>Р±РѕС‚ СЌРєРёРїРёСЂРѕРІР°С‚СЊ #ID</code>"
        ),
        "bank": (
            "рџЏ¦ <b>РњР°РіР°Р·РёРЅ</b> вЂє <b>Р‘Р°РЅРє</b>\n\n"
            f"рџ’° Р‘Р°Р»Р°РЅСЃ: <b>{bal} рџЄ™</b>\n\n"
            "Р’РєР»Р°РґС‹ РґРѕСЃС‚СѓРїРЅС‹ С‡РµСЂРµР· <code>Р±РѕС‚ Р±Р°РЅРє</code>.\n\n"
            f"{bank_lines}\n\n"
            "<i>Р”РѕСЃСЂРѕС‡РЅРѕРµ СЃРЅСЏС‚РёРµ СѓРјРµРЅСЊС€Р°РµС‚ РІС‹РїР»Р°С‚Сѓ.</i>"
        ),
        "gifts": (
            "рџЋЃ <b>РњР°РіР°Р·РёРЅ</b> вЂє <b>РџРѕРґР°СЂРєРё РїР°СЂС‚РЅС‘СЂСѓ</b>\n\n"
            f"рџ’° Р‘Р°Р»Р°РЅСЃ: <b>{bal} рџЄ™</b>\n\n"
            f"{gift_lines}\n\n"
            "РљСѓРїРёС‚СЊ Рё РѕС‚РїСЂР°РІРёС‚СЊ: <code>Р±РѕС‚ РїРѕРґР°СЂРєРё</code>\n"
            "РџРѕРґР°СЂРєРё СЃ Р±Р°С„С„Р°РјРё СѓСЃРёР»РёРІР°СЋС‚ РґРѕР±С‹С‡Сѓ РјРѕСЂС‹ РґР»СЏ РїР°СЂС‹."
        ),
        "casino": (
            "рџЋ° <b>РњР°РіР°Р·РёРЅ</b> вЂє <b>РљР°Р·РёРЅРѕ</b>\n\n"
            f"рџ’° Р‘Р°Р»Р°РЅСЃ: <b>{bal} рџЄ™</b>\n\n"
            f"рџЋџ Р›РѕС‚РµСЂРµР№РЅС‹Р№ Р±РёР»РµС‚ вЂ” <b>{LOTTERY_TICKET_PRICE} рџЄ™</b>\n"
            "  <code>Р±РѕС‚ РєСѓРїРёС‚СЊ Р»РѕС‚РµСЂРµСЋ</code>\n\n"
            "РњРѕРЅРµС‚РєР° Рё РєСѓР±РёРє РЅРµ РїСЂРѕРґР°СЋС‚СЃСЏ Р·Р°СЂР°РЅРµРµ вЂ” С‚Р°Рј СЃС‚Р°РІРєР° СЃРїРёСЃС‹РІР°РµС‚СЃСЏ РІ РјРѕРјРµРЅС‚ РёРіСЂС‹."
        ),
        "cosmetics": (
            "рџЋЁ <b>РњР°РіР°Р·РёРЅ</b> вЂє <b>РљРѕСЃРјРµС‚РёРєР°</b>\n\n"
            f"рџ’° Р‘Р°Р»Р°РЅСЃ: <b>{bal} рџЄ™</b>\n\n"
            f"{cosmetics_lines}\n\n"
            "Р”Р»СЏ РїРѕРєСѓРїРєРё РёСЃРїРѕР»СЊР·СѓР№ РєРЅРѕРїРєРё РЅРёР¶Рµ."
        ),
    }
    return sections.get(section, sections["all"])


async def _get_owned_keys(uid: int, chat_id: int) -> set[str]:
    """Return set of SHOP_ITEMS keys the user already purchased."""
    owned = set()
    for key in SHOP_ITEMS:
        if await has_shop_item(uid, chat_id, key):
            owned.add(key)
    return owned


# в”Ђв”Ђв”Ђ Р±РѕС‚ РјР°РіР°Р·РёРЅ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.message(BotCommand("РјР°РіР°Р·РёРЅ", "Р»Р°РІРєР°", "shop", "store", "РјР°СЂРєРµС‚", "РєР°С‚Р°Р»РѕРі РїРѕРєСѓРїРѕРє"))
async def cmd_shop(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("вќЊ РњР°РіР°Р·РёРЅ РґРѕСЃС‚СѓРїРµРЅ С‚РѕР»СЊРєРѕ РІ РіСЂСѓРїРїР°С….")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0

    arg = (cmd_args or "").strip().lower()
    section = "all"
    arg_map = {
        "РІСЃРµ": "all",
        "РІСЃС‘": "all",
        "СЌРєРѕРЅРѕРјРёРєР°": "economy",
        "РїРёС‚РѕРјС†С‹": "pets",
        "РјРѕР»РёС‚РІС‹": "gacha",
        "РіР°С‡Р°": "gacha",
        "Р±Р°РЅРє": "bank",
        "РїРѕРґР°СЂРєРё": "gifts",
        "РєР°Р·РёРЅРѕ": "casino",
        "РєРѕСЃРјРµС‚РёРєР°": "cosmetics",
    }
    if arg in arg_map:
        section = arg_map[arg]

    owned = await _get_owned_keys(uid, chat_id) if section == "cosmetics" else None
    kb = _section_keyboard(uid, section, owned)
    # Use t.me Mini App link with startapp=abs(chat_id) so the app knows which chat context
    abs_cid = abs(message.chat.id)
    kb.inline_keyboard.append([
        InlineKeyboardButton(
            text="рџ“± РћС‚РєСЂС‹С‚СЊ РІ Mini App",
            url=f"{MINI_APP_TG_URL}?startapp={abs_cid}_shop",
        )
    ])
    await message.answer(
        _shop_text(section, bal),
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("shop_nav:"))
async def cb_shop_nav(callback: CallbackQuery):
    _prefix, owner_str, section = callback.data.split(":", 2)
    owner = int(owner_str)

    if await not_your_button(callback, owner, "вќЊ Р­С‚Рѕ РЅРµ С‚РІРѕР№ РјР°РіР°Р·РёРЅ!"):
        return

    chat_id = callback.message.chat.id
    mora = await get_mora(owner, chat_id)
    bal = mora["balance"] if mora else 0
    owned = await _get_owned_keys(owner, chat_id) if section == "cosmetics" else None

    try:
        await callback.message.edit_text(
            _shop_text(section, bal),
            parse_mode="HTML",
            reply_markup=_section_keyboard(owner, section, owned),
        )
    except Exception as _e:
        _log.debug("%s", _e, exc_info=True)
    await callback.answer()


# в”Ђв”Ђв”Ђ РџРѕРєСѓРїРєР° в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.callback_query(lambda c: c.data and c.data.startswith("shop_buy:"))
async def cb_shop_buy(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    item_key = parts[2]
    wallet = parts[3] if len(parts) > 3 else "personal"

    if await not_your_button(callback, owner, "вќЊ Р­С‚Рѕ РЅРµ С‚РІРѕР№ РјР°РіР°Р·РёРЅ!"):
        return

    item = SHOP_ITEMS.get(item_key)
    if not item:
        await callback.answer("вќЊ РўРѕРІР°СЂ РЅРµ РЅР°Р№РґРµРЅ.", show_alert=True)
        return

    uid = owner
    chat_id = callback.message.chat.id
    price = item["price"]

    already_owned = await has_shop_item(uid, chat_id, item_key)
    if already_owned:
        await callback.answer("вњ… РЈ С‚РµР±СЏ СѓР¶Рµ РµСЃС‚СЊ СЌС‚РѕС‚ С‚РѕРІР°СЂ!", show_alert=True)
        return

    ok, new_bal = await deduct_wallet(uid, chat_id, price, wallet)
    if not ok:
        await callback.answer(f"вќЊ РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РњРѕСЂС‹ ({new_bal} / {price})", show_alert=True)
        return

    # Р”Р»СЏ РєР°Р¶РґРѕРіРѕ С‚РѕРІР°СЂР° вЂ” СЃРІРѕР№ flow
    if item_key == "custom_title":
        await buy_shop_item(uid, chat_id, "custom_title", "pending")
        try:
            await callback.message.edit_text(
                f"вњ… <b>РљР°СЃС‚РѕРјРЅС‹Р№ С‚РёС‚СѓР» РєСѓРїР»РµРЅ!</b>\n\n"
                f"РўРµРїРµСЂСЊ РЅР°РїРёС€Рё: <code>Р±РѕС‚ С‚РёС‚СѓР» &lt;С‚РµРєСЃС‚&gt;</code>\n"
                f"рџ’° Р‘Р°Р»Р°РЅСЃ: {new_bal} рџЄ™",
                parse_mode="HTML",
            )
        except Exception as _e:
            _log.debug("%s", _e, exc_info=True)
        # Block 4: Add season XP for shop purchase
        try:
            from database.db import add_season_xp
            await add_season_xp(uid, 2)  # +2 season XP
        except Exception as _e:
            _log.debug("%s", _e, exc_info=True)
    elif item_key == "pet_color":
        await buy_shop_item(uid, chat_id, "pet_color", "pending")
        # РџСЂРµРґР»Р°РіР°РµРј РІС‹Р±СЂР°С‚СЊ С†РІРµС‚
        buttons = []
        row = []
        for ckey, cname in _PET_COLORS.items():
            row.append(InlineKeyboardButton(
                text=cname,
                callback_data=f"shop_color:{uid}:{ckey}",
            ))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        try:
            await callback.message.edit_text(
                "рџЋЁ <b>Р’С‹Р±РµСЂРё С†РІРµС‚ РёРјРµРЅРё РїРёС‚РѕРјС†Р°:</b>",
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception as _e:
            _log.debug("%s", _e, exc_info=True)
    elif item_key == "pet_emoji_status":
        await buy_shop_item(uid, chat_id, "pet_emoji_status", "pending")
        try:
            await callback.message.edit_text(
                f"вњ… <b>Р­РјРѕРґР·Рё-СЃС‚Р°С‚СѓСЃ РїРёС‚РѕРјС†Р° РєСѓРїР»РµРЅ!</b>\n\n"
                f"РўРµРїРµСЂСЊ РЅР°РїРёС€Рё: <code>Р±РѕС‚ СЌРјРѕРґР·Рё-СЃС‚Р°С‚СѓСЃ рџђѕ</code>\n"
                f"(РЈРєР°Р¶Рё РѕРґРёРЅ СЌРјРѕРґР·Рё)\n"
                f"рџ’° Р‘Р°Р»Р°РЅСЃ: {new_bal} рџЄ™",
                parse_mode="HTML",
            )
        except Exception as _e:
            _log.debug("%s", _e, exc_info=True)
    else:
        # РќРµРёР·РІРµСЃС‚РЅС‹Р№ С‚РѕРІР°СЂ вЂ” РІРѕР·РІСЂР°С‰Р°РµРј РґРµРЅСЊРіРё
        from database.db import add_mora
        await add_mora(uid, chat_id, price)
        await callback.answer("вќЊ РћС€РёР±РєР°: С‚РѕРІР°СЂ РЅРµ РѕР±СЂР°Р±РѕС‚Р°РЅ.", show_alert=True)
        return

    await callback.answer("вњ… РџРѕРєСѓРїРєР° СЃРѕРІРµСЂС€РµРЅР°!")


# в”Ђв”Ђв”Ђ Р’С‹Р±РѕСЂ С†РІРµС‚Р° РїРёС‚РѕРјС†Р° в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.callback_query(lambda c: c.data and c.data.startswith("shop_color:"))
async def cb_shop_color(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    color = parts[2]

    if await not_your_button(callback, owner, "вќЊ РќРµ РґР»СЏ С‚РµР±СЏ!"):
        return

    if color not in _PET_COLORS:
        await callback.answer("вќЊ РќРµРёР·РІРµСЃС‚РЅС‹Р№ С†РІРµС‚.", show_alert=True)
        return

    uid = owner
    chat_id = callback.message.chat.id

    await set_pet_color(uid, chat_id, color)
    await buy_shop_item(uid, chat_id, "pet_color", color)

    try:
        await callback.message.edit_text(
            f"вњ… Р¦РІРµС‚ РёРјРµРЅРё РїРёС‚РѕРјС†Р° РёР·РјРµРЅС‘РЅ РЅР° {_PET_COLORS[color]}!",
            parse_mode="HTML",
        )
    except Exception as _e:
        _log.debug("%s", _e, exc_info=True)
# в”Ђв”Ђв”Ђ РџСЂРѕРїСѓСЃРє С‡РёСЃС‚РєРё в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.message(BotCommand("РѕС‚РєСѓРї", "РїСЂРѕРїСѓСЃРє С‡РёСЃС‚РєРё", "cleanup_pass"))
async def cmd_buy_cleanup_pass(message: Message, bot, cmd_args: str):
    """РљСѓРїРёС‚СЊ РѕС‚РєСѓРї РѕС‚ 1 С‡РёСЃС‚РєРё (РјР°РєСЃ. 1 Р°РєС‚РёРІРЅС‹Р№). РўСЂРµР±СѓРµС‚ РѕРґРѕР±СЂРµРЅРёСЏ РІР»Р°РґРµР»СЊС†Р°."""
    if message.chat.type == "private":
        await message.answer("вќЊ РљРѕРјР°РЅРґР° СЂР°Р±РѕС‚Р°РµС‚ С‚РѕР»СЊРєРѕ РІ С‡Р°С‚Рµ.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    from shared_prices import CLEANUP_PASS_PRICE
    from database.db import buy_cleanup_pass, get_mora as _gm
    from handlers.economy import deduct_wallet as _dw

    mora = await _gm(uid, chat_id)
    bal = mora["balance"] if mora else 0
    if bal < CLEANUP_PASS_PRICE:
        await message.answer(
            f"вќЊ РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РњРѕСЂС‹. РќСѓР¶РЅРѕ <b>{CLEANUP_PASS_PRICE} рџЄ™</b>, Сѓ С‚РµР±СЏ <b>{bal} рџЄ™</b>.",
            parse_mode="HTML",
        )
        return

    try:
        ok, new_bal = await _dw(uid, chat_id, CLEANUP_PASS_PRICE)
        if not ok:
            await message.answer("вќЊ РќРµ СѓРґР°Р»РѕСЃСЊ СЃРїРёСЃР°С‚СЊ РњРѕСЂСѓ.")
            return
        pass_id = await buy_cleanup_pass(uid, chat_id, CLEANUP_PASS_PRICE)
    except ValueError as ve:
        await message.answer(f"вќЊ {ve}")
        return

    # Log to wallet ledger
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "expense", CLEANUP_PASS_PRICE, "cleanup_pass",
                            "РћС‚РєСѓРї РѕС‚ С‡РёСЃС‚РєРё")
    except Exception as _e:
        _log.debug("%s", _e, exc_info=True)
    user_name = html.escape(message.from_user.full_name)
    chat_title = html.escape(message.chat.title or "С‡Р°С‚")

    await message.answer(
        f"вњ… Р—Р°СЏРІРєР° РЅР° РїСЂРѕРїСѓСЃРє С‡РёСЃС‚РєРё РѕС‚РїСЂР°РІР»РµРЅР°!\n"
        f"РЎРїРёСЃР°РЅРѕ: <b>{CLEANUP_PASS_PRICE} рџЄ™</b>\n"
        f"РћР¶РёРґР°Р№ РѕРґРѕР±СЂРµРЅРёСЏ РѕС‚ РІР»Р°РґРµР»СЊС†Р°/СЂР°Р·СЂР°Р±РѕС‚С‡РёРєР°.",
        parse_mode="HTML",
    )

    # РЈРІРµРґРѕРјР»РµРЅРёРµ РІР»Р°РґРµР»СЊС†Сѓ Рё СЂР°Р·СЂР°Р±РѕС‚С‡РёРєСѓ
    from config import DEVELOPER_ID
    from database.db import get_staff_in_chat

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="вњ… РћРґРѕР±СЂРёС‚СЊ", callback_data=f"cpass:approve:{pass_id}:{uid}:{chat_id}"),
            InlineKeyboardButton(text="вќЊ РћС‚РєР»РѕРЅРёС‚СЊ", callback_data=f"cpass:reject:{pass_id}:{uid}:{chat_id}"),
        ]
    ])
    notify_text = (
        f"рџЋ« <b>Р—Р°СЏРІРєР° РЅР° РїСЂРѕРїСѓСЃРє С‡РёСЃС‚РєРё</b>\n\n"
        f"рџ‘¤ {user_name} (<code>{uid}</code>)\n"
        f"рџ’¬ {chat_title}\n"
        f"рџ’° РћРїР»Р°С‡РµРЅРѕ: <b>{CLEANUP_PASS_PRICE} рџЄ™</b>\n"
        f"рџ“‹ Р—Р°СЏРІРєР° #{pass_id}"
    )

    # РЈРІРµРґРѕРјРёС‚СЊ РІР»Р°РґРµР»СЊС†РµРІ С‡Р°С‚Р° + СЂР°Р·СЂР°Р±РѕС‚С‡РёРєР° (РІ Р›РЎ)
    notified = set()
    staff = await get_staff_in_chat(chat_id)
    for s in staff:
        if s["rank"] in ("owner", "developer"):
            try:
                await bot.send_message(s["user_id"], notify_text, parse_mode="HTML", reply_markup=kb)
                notified.add(s["user_id"])
            except Exception as _e:
                _log.debug("cleanup_pass DM failed uid=%s: %s", s["user_id"], _e)
    if DEVELOPER_ID and DEVELOPER_ID not in notified:
        try:
            await bot.send_message(DEVELOPER_ID, notify_text, parse_mode="HTML", reply_markup=kb)
            notified.add(DEVELOPER_ID)
        except Exception as _e:
            _log.debug("cleanup_pass DM to DEV failed: %s", _e)

    # Р“Р°СЂР°РЅС‚РёСЂРѕРІР°РЅРЅС‹Р№ С„РѕР»Р±СЌРє: РѕС‚РїСЂР°РІРёС‚СЊ РїСЂСЏРјРѕ РІ С‡Р°С‚ (РІРёРґРЅРѕ РІСЃРµРј РІР»Р°РґРµР»СЊС†Р°Рј)
    # РµСЃР»Рё РЅРёРєС‚Рѕ РЅРµ РїРѕР»СѓС‡РёР» Р›РЎ (Р±РѕС‚ РЅРµ Р·Р°РїСѓСЃС‚РёР»Рё РІ Р»РёС‡РєРµ) РёР»Рё РІ Р»СЋР±РѕРј СЃР»СѓС‡Р°Рµ РґР»СЏ РЅР°РґС‘Р¶РЅРѕСЃС‚Рё
    if not notified:
        try:
            await bot.send_message(
                chat_id,
                f"рџ“ў <b>Р’Р»Р°РґРµР»СЊС†Р°Рј С‡Р°С‚Р°:</b>\n{notify_text}\n\n"
                f"вљ пёЏ РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РїСЂР°РІРёС‚СЊ СѓРІРµРґРѕРјР»РµРЅРёРµ РІ Р»РёС‡РєСѓ. РћРґРѕР±СЂРёС‚Рµ Р·Р°СЏРІРєСѓ Р·РґРµСЃСЊ:",
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception as _e:
            _log.debug("cleanup_pass chat fallback failed: %s", _e)
@router.callback_query(lambda c: c.data and c.data.startswith("cpass:"))
async def cb_cleanup_pass(callback: CallbackQuery):
    """РћР±СЂР°Р±РѕС‚РєР° РѕРґРѕР±СЂРµРЅРёСЏ/РѕС‚РєР»РѕРЅРµРЅРёСЏ РїСЂРѕРїСѓСЃРєР° С‡РёСЃС‚РєРё."""
    from database.db import resolve_cleanup_pass, add_mora as _am
    from utils.ranks import is_developer as _is_dev

    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer("вќЊ РќРµРєРѕСЂСЂРµРєС‚РЅС‹Рµ РґР°РЅРЅС‹Рµ", show_alert=True)
        return

    action = parts[1]  # approve / reject
    pass_id = int(parts[2])
    buyer_uid = int(parts[3])
    chat_id = int(parts[4])

    admin_uid = callback.from_user.id

    # РџСЂРѕРІРµСЂСЏРµРј РїСЂР°РІР°: С‚РѕР»СЊРєРѕ owner РёР»Рё developer
    from database.db import get_user_stats
    stats = await get_user_stats(admin_uid, chat_id)
    admin_rank = stats["rank"] if stats else None
    if admin_rank not in ("owner", "co_owner") and not _is_dev(admin_uid):
        await callback.answer("вќЊ РўРѕР»СЊРєРѕ РІР»Р°РґРµР»РµС† РёР»Рё СЂР°Р·СЂР°Р±РѕС‚С‡РёРє РјРѕР¶РµС‚ СЂРµС€Р°С‚СЊ.", show_alert=True)
        return

    result = await resolve_cleanup_pass(pass_id, "approve" if action == "approve" else "reject", admin_uid)
    if not result:
        await callback.answer("вљ пёЏ Р—Р°СЏРІРєР° СѓР¶Рµ РѕР±СЂР°Р±РѕС‚Р°РЅР° РёР»Рё РЅРµ РЅР°Р№РґРµРЅР°.", show_alert=True)
        return

    if action == "approve":
        try:
            await callback.message.edit_text(
                callback.message.text + "\n\nвњ… <b>РћРґРѕР±СЂРµРЅРѕ</b>",
                parse_mode="HTML",
            )
        except Exception as _e:
            _log.debug("%s", _e, exc_info=True)
        # РЈРІРµРґРѕРјРёС‚СЊ РїРѕРєСѓРїР°С‚РµР»СЏ
        try:
            await callback.bot.send_message(
                buyer_uid,
                f"вњ… РўРІРѕСЏ Р·Р°СЏРІРєР° РЅР° РїСЂРѕРїСѓСЃРє С‡РёСЃС‚РєРё <b>РѕРґРѕР±СЂРµРЅР°</b>!\n"
                f"РџСЂРё СЃР»РµРґСѓСЋС‰РµР№ С‡РёСЃС‚РєРµ С‚С‹ Р±СѓРґРµС€СЊ Р·Р°С‰РёС‰С‘РЅ.",
                parse_mode="HTML",
            )
        except Exception as _e:
            _log.debug("%s", _e, exc_info=True)
        await callback.answer("вњ… РџСЂРѕРїСѓСЃРє РѕРґРѕР±СЂРµРЅ!", show_alert=True)
    else:
        # Р’РµСЂРЅСѓС‚СЊ РґРµРЅСЊРіРё
        price = result["price"]
        await _am(buyer_uid, chat_id, price)
        # Log refund
        try:
            from api.economy import log_wallet_tx
            await log_wallet_tx(buyer_uid, chat_id, "income", price, "cleanup_pass_refund",
                                "Р’РѕР·РІСЂР°С‚ Р·Р° РѕС‚РєР»РѕРЅС‘РЅРЅС‹Р№ РїСЂРѕРїСѓСЃРє С‡РёСЃС‚РєРё")
        except Exception as _e:
            _log.debug("%s", _e, exc_info=True)
        try:
            await callback.message.edit_text(
                callback.message.text + "\n\nвќЊ <b>РћС‚РєР»РѕРЅРµРЅРѕ</b> (РґРµРЅСЊРіРё РІРѕР·РІСЂР°С‰РµРЅС‹)",
                parse_mode="HTML",
            )
        except Exception as _e:
            _log.debug("%s", _e, exc_info=True)
        # РЈРІРµРґРѕРјРёС‚СЊ РїРѕРєСѓРїР°С‚РµР»СЏ
        try:
            await callback.bot.send_message(
                buyer_uid,
                f"вќЊ Р—Р°СЏРІРєР° РЅР° РїСЂРѕРїСѓСЃРє С‡РёСЃС‚РєРё <b>РѕС‚РєР»РѕРЅРµРЅР°</b>.\n"
                f"Р’РѕР·РІСЂР°С‚: <b>{price} рџЄ™</b>",
                parse_mode="HTML",
            )
        except Exception as _e:
            _log.debug("%s", _e, exc_info=True)
        await callback.answer("вќЊ Р—Р°СЏРІРєР° РѕС‚РєР»РѕРЅРµРЅР°, РґРµРЅСЊРіРё РІРѕР·РІСЂР°С‰РµРЅС‹.", show_alert=True)
    await callback.answer()


# в”Ђв”Ђв”Ђ Р±РѕС‚ РїСЂРѕРїСѓСЃРєРё вЂ” СЃРїРёСЃРѕРє РѕР¶РёРґР°СЋС‰РёС… Р·Р°СЏРІРѕРє (РґР»СЏ Р°РґРјРёРЅРѕРІ) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.message(BotCommand("РїСЂРѕРїСѓСЃРєРё", "Р·Р°СЏРІРєРё_С‡РёСЃС‚РєРё"))
async def cmd_list_passes(message: Message):
    """РџРѕРєР°Р·Р°С‚СЊ РІСЃРµ pending Р·Р°СЏРІРєРё РЅР° РїСЂРѕРїСѓСЃРє С‡РёСЃС‚РєРё. РўРѕР»СЊРєРѕ owner/developer."""
    if message.chat.type == "private":
        await message.answer("вќЊ РљРѕРјР°РЅРґР° СЂР°Р±РѕС‚Р°РµС‚ С‚РѕР»СЊРєРѕ РІ С‡Р°С‚Рµ.")
        return
    from utils.ranks import is_developer as _is_dev
    from database.db import get_user_stats, postgres_connect as _pg
    uid = message.from_user.id
    chat_id = message.chat.id
    stats = await get_user_stats(uid, chat_id)
    rank = stats["rank"] if stats else None
    if rank not in ("owner", "co_owner", "developer") and not _is_dev(uid):
        await message.answer("вќЊ РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РїСЂР°РІ.")
        return

    from database.postgres import connect as _pgc
    async with _pgc() as db:
        async with db.execute(
            "SELECT cp.id, cp.user_id, cp.price, cp.created_at, u.full_name "
            "FROM cleanup_passes cp LEFT JOIN users u ON u.user_id = cp.user_id "
            "WHERE cp.chat_id=? AND cp.status='pending' ORDER BY cp.created_at",
            (chat_id,),
        ) as c:
            rows = await c.fetchall()

    if not rows:
        await message.answer("вњ… РќРµС‚ РѕР¶РёРґР°СЋС‰РёС… Р·Р°СЏРІРѕРє РЅР° РїСЂРѕРїСѓСЃРє С‡РёСЃС‚РєРё.")
        return

    from config import CLEANUP_PASS_PRICE as _CPP
    for row in rows:
        pid, buyer_uid, price, created_at, full_name = row[0], row[1], row[2], row[3], row[4]
        name = html.escape(full_name or str(buyer_uid))
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="вњ… РћРґРѕР±СЂРёС‚СЊ", callback_data=f"cpass:approve:{pid}:{buyer_uid}:{chat_id}"),
            InlineKeyboardButton(text="вќЊ РћС‚РєР»РѕРЅРёС‚СЊ", callback_data=f"cpass:reject:{pid}:{buyer_uid}:{chat_id}"),
        ]])
        await message.answer(
            f"рџЋ« <b>Р—Р°СЏРІРєР° #{pid}</b>\n"
            f"рџ‘¤ {name} (<code>{buyer_uid}</code>)\n"
            f"рџ’° РћРїР»Р°С‡РµРЅРѕ: <b>{price} рџЄ™</b>\n"
            f"рџ“… {str(created_at)[:16]}",
            parse_mode="HTML",
            reply_markup=kb,
        )


async def cmd_set_title(message: Message, cmd_args: str):
    if message.chat.type == "private":
        return

    title = (cmd_args or "").strip()
    if not title:
        await message.answer(
            "вќЊ РЈРєР°Р¶Рё С‚РµРєСЃС‚ С‚РёС‚СѓР»Р°.\nРџСЂРёРјРµСЂ: <code>Р±РѕС‚ С‚РёС‚СѓР» РђСЂС…РѕРЅС‚ РњСѓРґСЂРѕСЃС‚Рё</code>",
            parse_mode="HTML",
        )
        return
    if len(title) > 30:
        await message.answer("вќЊ РўРёС‚СѓР» СЃР»РёС€РєРѕРј РґР»РёРЅРЅС‹Р№ (РјР°РєСЃ. 30 СЃРёРјРІРѕР»РѕРІ).")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    if not await has_shop_item(uid, chat_id, "custom_title"):
        await message.answer(
            "вќЊ РЎРЅР°С‡Р°Р»Р° РєСѓРїРё РєР°СЃС‚РѕРјРЅС‹Р№ С‚РёС‚СѓР» РІ РјР°РіР°Р·РёРЅРµ: <code>Р±РѕС‚ РјР°РіР°Р·РёРЅ</code>",
            parse_mode="HTML",
        )
        return
    await set_custom_title_in_chat(uid, chat_id, title)
    await message.answer(f"вњ… РўРёС‚СѓР» СѓСЃС‚Р°РЅРѕРІР»РµРЅ: <b>{html.escape(title)}</b>", parse_mode="HTML")


# в”Ђв”Ђв”Ђ Р±РѕС‚ СЌРјРѕРґР·Рё-СЃС‚Р°С‚СѓСЃ (СѓСЃС‚Р°РЅРѕРІРєР° СЌРјРѕРґР·Рё РїРёС‚РѕРјС†Р°) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.message(BotCommand("СЌРјРѕРґР·Рё-СЃС‚Р°С‚СѓСЃ", "emoji-status", "СЌРјРѕРґР·Рё СЃС‚Р°С‚СѓСЃ"))
async def cmd_set_emoji_status(message: Message, cmd_args: str):
    if message.chat.type == "private":
        return

    emoji = (cmd_args or "").strip()
    if not emoji or len(emoji) > 4:
        await message.answer(
            "вќЊ РЈРєР°Р¶Рё РѕРґРёРЅ СЌРјРѕРґР·Рё.\nРџСЂРёРјРµСЂ: <code>Р±РѕС‚ СЌРјРѕРґР·Рё-СЃС‚Р°С‚СѓСЃ рџђѕ</code>",
            parse_mode="HTML",
        )
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    if not await has_shop_item(uid, chat_id, "pet_emoji_status"):
        await message.answer(
            "вќЊ РЎРЅР°С‡Р°Р»Р° РєСѓРїРё СЌРјРѕРґР·Рё-СЃС‚Р°С‚СѓСЃ РІ РјР°РіР°Р·РёРЅРµ: <code>Р±РѕС‚ РјР°РіР°Р·РёРЅ</code>",
            parse_mode="HTML",
        )
        return
    await set_pet_emoji_status(uid, chat_id, emoji)
    await message.answer(f"вњ… Р­РјРѕРґР·Рё-СЃС‚Р°С‚СѓСЃ РїРёС‚РѕРјС†Р°: {html.escape(emoji)}", parse_mode="HTML")
