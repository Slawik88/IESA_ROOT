"""
items/equipment.py — все предметы экипировки из ITEM_METADATA.

Регистрирует всё оружие, броню, артефакты, шлемы, сапоги, кольца, щиты и т.д.
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Обычные (⚔️ Снаряжение — начальное) ─────────────────────────────────────

register(ItemDef(
    key="cmn_sword", name="Обычный меч", rarity=ItemRarity.COMMON, slot=ItemSlot.WEAPON,
    atk=15, crit_rate=0.02, emoji="⚔️", desc="Тупой, но вполне годится.",
    sell_price=20, category="Оружие-Меч", readable_category="Оружие"
))

register(ItemDef(
    key="cmn_bow", name="Простой лук", rarity=ItemRarity.COMMON, slot=ItemSlot.WEAPON,
    atk=12, crit_rate=0.02, emoji="🏹", desc="Стреляет куда-то туда.",
    sell_price=18, category="Оружие-Лук", readable_category="Оружие"
))

register(ItemDef(
    key="cmn_book", name="Гримуар начинающего", rarity=ItemRarity.COMMON, slot=ItemSlot.ARTIFACT,
    atk=8, crit_rate=0.03, emoji="📜", desc="Потрёпанный, с заклинанием на удачу.",
    sell_price=22, category="Артефакт-Книга", readable_category="Артефакт"
))

register(ItemDef(
    key="cmn_ring", name="Обычное кольцо", rarity=ItemRarity.COMMON, slot=ItemSlot.ARMOR,
    def_val=15, hp=30, emoji="💍", desc="Дешёвый, но надёжный браслет.",
    sell_price=20, category="Броня-Кольцо", readable_category="Броня"
))

register(ItemDef(
    key="cmn_shield", name="Обычный щит", rarity=ItemRarity.COMMON, slot=ItemSlot.ARMOR,
    def_val=20, emoji="🛡️", desc="Ржавый, но блокирует удары.",
    sell_price=25, category="Броня-Щит", readable_category="Броня"
))

register(ItemDef(
    key="cmn_helm", name="Шлем новичка", rarity=ItemRarity.COMMON, slot=ItemSlot.ARTIFACT,
    def_val=12, hp=50, crit_rate=0.01, emoji="🪖", desc="Потрёпанный шлем новичка.",
    sell_price=22, category="Шлем", readable_category="Шлем"
))

register(ItemDef(
    key="cmn_boots", name="Стоптанные сапоги", rarity=ItemRarity.COMMON, slot=ItemSlot.ARTIFACT,
    atk=10, hp=20, crit_rate=0.02, emoji="👢", desc="Стоптанные сапоги странника.",
    sell_price=18, category="Обувь", readable_category="Обувь"
))

# ─── Редкие (🎨 Среднее снаряжение) ──────────────────────────────────────────

register(ItemDef(
    key="rare_crown", name="Позолоченная корона", rarity=ItemRarity.RARE, slot=ItemSlot.ARTIFACT,
    atk=25, def_val=15, crit_rate=0.04, emoji="👑", desc="Позолоченная корона — власть и сила.",
    sell_price=100, category="Шлем-Корона", readable_category="Шлем"
))

register(ItemDef(
    key="rare_catalyst", name="Магический катализатор", rarity=ItemRarity.RARE, slot=ItemSlot.WEAPON,
    atk=30, crit_rate=0.04, emoji="💮", desc="Магический катализатор с рунами.",
    sell_price=90, category="Оружие-Магия", readable_category="Оружие"
))

register(ItemDef(
    key="rare_cape", name="Алый плащ", rarity=ItemRarity.RARE, slot=ItemSlot.ARMOR,
    def_val=25, hp=80, emoji="🧥", desc="Алый плащ с защитными чарами.",
    sell_price=95, category="Броня-Плащ", readable_category="Броня"
))

register(ItemDef(
    key="rare_gem", name="Сапфир полуночи", rarity=ItemRarity.RARE, slot=ItemSlot.ARTIFACT,
    def_val=20, crit_rate=0.06, emoji="🔷", desc="Сапфир полуночи — усиливает крит.",
    sell_price=80, category="Артефакт-Камень", readable_category="Артефакт"
))

register(ItemDef(
    key="rare_helm", name="Железный шлем рыцаря", rarity=ItemRarity.RARE, slot=ItemSlot.ARTIFACT,
    def_val=30, hp=90, crit_rate=0.04, emoji="🪖", desc="Железный шлем рыцаря.",
    sell_price=88, category="Шлем", readable_category="Шлем"
))

register(ItemDef(
    key="rare_boots", name="Сапоги вихря", rarity=ItemRarity.RARE, slot=ItemSlot.ARTIFACT,
    atk=22, def_val=8, hp=60, crit_rate=0.05, emoji="🩶", desc="Сапоги вихря — скорость и натиск.",
    sell_price=85, category="Обувь-Быстрая", readable_category="Обувь"
))

register(ItemDef(
    key="rare_lance", name="Лазурное копьё", rarity=ItemRarity.RARE, slot=ItemSlot.WEAPON,
    atk=35, crit_rate=0.05, emoji="🚪", desc="Лазурное копьё воина ветров.",
    sell_price=85, category="Оружие-Копьё", readable_category="Оружие"
))

register(ItemDef(
    key="rare_amulet", name="Кармин змеи", rarity=ItemRarity.RARE, slot=ItemSlot.ARTIFACT,
    def_val=20, crit_rate=0.08, emoji="🔴", desc="Кармин змеи — усиливает криты.",
    sell_price=85, category="Артефакт-Редкий", readable_category="Артефакт"
))

register(ItemDef(
    key="rare_mora_chest", name="Красный конверт", rarity=ItemRarity.RARE, slot=ItemSlot.ARTIFACT,
    emoji="🧧", desc="Красный конверт: мгновенно +250 🪙",
    sell_price=90, category="Мора-Конверт", readable_category="Расходник"
))

# ─── Легендарные (⚔️ Снаряжение — лучшее) ─────────────────────────────────────

register(ItemDef(
    key="lego_gnosis", name="Гнозис бездны", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.WEAPON,
    atk=60, crit_rate=0.08, emoji="🌌", desc="Гнозис Балладеера — мощь Архонта.",
    sell_price=0, category="Оружие-Архонт", readable_category="Оружие"
))

register(ItemDef(
    key="lego_scepter", name="Скипетр Дендро Архонта", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.WEAPON,
    atk=70, def_val=15, crit_rate=0.06, emoji="🪄", desc="Скипетр Дендро Архонта.",
    sell_price=0, category="Оружие-Скипетр", readable_category="Оружие"
))

register(ItemDef(
    key="lego_pantalone", name="Маска Панталоне", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.ARMOR,
    def_val=60, hp=300, emoji="🎭", desc="Маска Панталоне — абсолютная защита.",
    sell_price=0, category="Броня-Маска", readable_category="Броня"
))

register(ItemDef(
    key="lego_abyss", name="Корона Бездны", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.ARTIFACT,
    atk=45, crit_rate=0.12, emoji="🕸️", desc="Корона Бездны — усиливает крит.",
    sell_price=0, category="Артефакт-Корона", readable_category="Артефакт"
))

register(ItemDef(
    key="lego_fatui", name="Перст Предвестника", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.WEAPON,
    atk=55, hp=150, crit_rate=0.10, emoji="☝️", desc="Перст Предвестника — несёт смерть врагам.",
    sell_price=0, category="Оружие-Перст", readable_category="Оружие"
))

register(ItemDef(
    key="lego_helm", name="Корона Небесных Врат", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.ARTIFACT,
    def_val=55, hp=250, crit_rate=0.06, emoji="🎯", desc="Корона Небесных Врат.",
    sell_price=0, category="Шлем-Легенда", readable_category="Шлем"
))

register(ItemDef(
    key="lego_boots", name="Сапоги Странника Вечности", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.ARTIFACT,
    atk=45, def_val=20, hp=120, crit_rate=0.10, emoji="👠", desc="Сапоги Странника Вечности.",
    sell_price=0, category="Обувь-Легенда", readable_category="Обувь"
))

register(ItemDef(
    key="lego_raiden", name="Клинок Ей", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.WEAPON,
    atk=80, crit_rate=0.12, emoji="⚡", desc="Клинок Ей — мощь Инадзумы.",
    sell_price=0, category="Оружие-Личное", readable_category="Оружие"
))

register(ItemDef(
    key="lego_jade", name="Нефритовое зерцало Архонта", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.ARTIFACT,
    atk=20, def_val=40, crit_rate=0.15, emoji="🪚", desc="Нефритовое зерцало Архонта.",
    sell_price=0, category="Артефакт-Нефрит", readable_category="Артефакт"
))

# ─── Новые предметы гачи ──────────────────────────────────────────────────────

register(ItemDef(
    key="cmn_quill", name="Перо ученика", rarity=ItemRarity.COMMON, slot=ItemSlot.ARTIFACT,
    atk=8, hp=15, crit_rate=0.02, emoji="🪶", desc="Перо ученика с магическими чарами.",
    sell_price=20, category="Артефакт-Перо", readable_category="Артефакт"
))

register(ItemDef(
    key="cmn_talisman", name="Амулет удачи", rarity=ItemRarity.COMMON, slot=ItemSlot.ARTIFACT,
    def_val=5, crit_rate=0.015, emoji="🧿", desc="Амулет с рунами удачи.",
    sell_price=18, category="Артефакт-Амулет", readable_category="Артефакт"
))
