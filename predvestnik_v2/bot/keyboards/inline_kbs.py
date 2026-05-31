from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_shop_kb(items, has_discount):
    builder = InlineKeyboardBuilder()
    for item in items:
        price = item.price * 0.95 if has_discount else item.price
        builder.button(text=f"🛒 {item.name} - {price}", callback_data=...)
    return builder.as_markup()