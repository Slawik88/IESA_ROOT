"""
items/collectibles.py — коллекционные предметы и материалы.
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Материалы для крафта ─────────────────────────────────────────────────────

register(ItemDef(
    key="ore_iron", name="🪨 Железная руда", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    craft_mat_type="ore",
    sell_price=50,
    emoji="🪨", desc="Обычная руда для крафта. +1 прочность оружия.",
    category="Material", readable_category="Материал"
))

register(ItemDef(
    key="ore_silver", name="⚪ Серебряная руда", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    craft_mat_type="ore",
    sell_price=80,
    emoji="⚪", desc="Редкая серебряная руда. +2 прочность.",
    category="Material", readable_category="Материал"
))

register(ItemDef(
    key="ore_mithril", name="💎 Мифрил руда", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    craft_mat_type="ore",
    sell_price=300,
    emoji="💎", desc="Мифическая руда. +5 прочность оружия.",
    category="Material", readable_category="Материал"
))

# ─── Ткани и материалы брони ───────────────────────────────────────────────────

register(ItemDef(
    key="cloth_common", name="🧵 Простая ткань", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    craft_mat_type="cloth",
    sell_price=40,
    emoji="🧵", desc="Обычная ткань. Базовый материал.",
    category="Material", readable_category="Материал"
))

register(ItemDef(
    key="cloth_silk", name="🧴 Шёлк", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    craft_mat_type="cloth",
    sell_price=120,
    emoji="🧴", desc="Тонкий шёлк. Лучше ткани.",
    category="Material", readable_category="Материал"
))

register(ItemDef(
    key="leather_grade1", name="🎒 Кожа (1★)", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    craft_mat_type="leather",
    sell_price=60,
    emoji="🎒", desc="Высушенная кожа. +1 DEF материал.",
    category="Material", readable_category="Материал"
))

register(ItemDef(
    key="leather_grade2", name="🎒 Кожа (2★)", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    craft_mat_type="leather",
    sell_price=200,
    emoji="🎒", desc="Премиум кожа. +3 DEF материал.",
    category="Material", readable_category="Материал"
))

# ─── Герб и печати (рубки значков) ────────────────────────────────────────────

register(ItemDef(
    key="seal_beast", name="🐉 Печать зверя", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    collect_type="seal",
    sell_price=500,
    emoji="🐉", desc="Редкая печать. Коллекционный предмет (1/10).",
    category="Collectible", readable_category="Коллекция"
))

register(ItemDef(
    key="seal_dragon", name="🐲 Печать дракона", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    collect_type="seal",
    sell_price=500,
    emoji="🐲", desc="Редкая печать. Коллекционный предмет (2/10).",
    category="Collectible", readable_category="Коллекция"
))

register(ItemDef(
    key="seal_phoenix", name="🔥 Печать феникса", rarity=ItemRarity.EPIC, slot=ItemSlot.NONE,
    collect_type="seal",
    sell_price=1500,
    emoji="🔥", desc="Редкая печать. Коллекционный предмет (3/10).",
    category="Collectible", readable_category="Коллекция"
))

# ─── Артефакты ────────────────────────────────────────────────────────────────

register(ItemDef(
    key="artifact_ancient_coin", name="🪙 Древняя монета", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    artifact_type="ancient",
    sell_price=800,
    emoji="🪙", desc="Артефакт. Издаёт древний звон. Редкий артефакт.",
    category="Artifact", readable_category="Артефакт"
))

register(ItemDef(
    key="artifact_mystic_gem", name="🔮 Мистический кристалл", rarity=ItemRarity.EPIC, slot=ItemSlot.NONE,
    artifact_type="mystic",
    sell_price=2000,
    emoji="🔮", desc="Артефакт. Светится магией. Эпический артефакт.",
    category="Artifact", readable_category="Артефакт"
))

register(ItemDef(
    key="artifact_star_fragment", name="⭐ Осколок звезды", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.NONE,
    artifact_type="celestial",
    sell_price=5000,
    emoji="⭐", desc="Артефакт. Звёздный осколок. Легендарный артефакт.",
    category="Artifact", readable_category="Артефакт"
))

# ─── Книги и свитки ───────────────────────────────────────────────────────────

register(ItemDef(
    key="book_ancient", name="📕 Древняя книга", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    book_type="knowledge",
    sell_price=600,
    emoji="📕", desc="Волшебная книга. +5% XP при чтении.",
    category="Book", readable_category="Книга"
))

register(ItemDef(
    key="scroll_blessing", name="📜 Свиток благословения", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    book_type="spell",
    sell_price=150,
    emoji="📜", desc="Свиток с защитным заклятием. Разовый баф.",
    category="Book", readable_category="Книга"
))

register(ItemDef(
    key="manuscript_grimoire", name="📓 Рукопись гримуара", rarity=ItemRarity.EPIC, slot=ItemSlot.NONE,
    book_type="grimoire",
    sell_price=2500,
    emoji="📓", desc="Учебник магии. +10% MP восстановления.",
    category="Book", readable_category="Книга"
))

# ─── Трофеи и реликвии ─────────────────────────────────────────────────────────

register(ItemDef(
    key="trophy_victory", name="🏆 Трофей побед", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    trophy_type="pvp",
    sell_price=750,
    emoji="🏆", desc="Трофей за победу в рейде. Значок мастерства.",
    category="Trophy", readable_category="Трофей"
))

register(ItemDef(
    key="relic_ancient", name="⚱️ Древняя реликвия", rarity=ItemRarity.EPIC, slot=ItemSlot.NONE,
    relic_type="ancient",
    sell_price=1800,
    emoji="⚱️", desc="Артефакт из давних времён. Коллекционная ценность.",
    category="Relic", readable_category="Реликвия"
))

register(ItemDef(
    key="relic_godly", name="👑 Божественная реликвия", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.NONE,
    relic_type="divine",
    sell_price=8000,
    emoji="👑", desc="Реликвия богов. Высочайшая ценность.",
    category="Relic", readable_category="Реликвия"
))
