/* ──────────────────────────────────────────────────────────────
   Inventory.tsx v3 — Полноценный RPG-инвентарь
   GET  /api/inventory?chat_id=X
   POST /api/equip, /api/inventory, /api/batch_sell,
   POST /api/inventory/sell_junk, /api/enhance, /api/consume_potion
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import {
  Backpack, Trash2, ChevronUp, ChevronDown, Loader2,
  Shield, Swords, Heart, Crosshair, X, RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { useToast } from "../components/ToastContext";
import {
  fetchInventory, equipItem, toggleEquip,
  sellJunk, batchSell, enhanceItem, consumePotion, activateTheme, renamePet, buyShopItem,
  boostExpedition,
} from "../lib/api";
import type { InventoryItem, InventoryRpg } from "../types";
import { RARITY_COLOR } from "./Gacha";

const RARITY_LABEL: Record<string, string> = {
  junk: "Хлам", common: "Обычный", rare: "Редкий", legendary: "Легендарный",
};

const SLOT_LABEL: Record<string, string> = {
  weapon: "Оружие", helmet: "Шлем", armor: "Броня",
  boots: "Сапоги", artifact: "Артефакт", flair: "Косметика",
  consumable: "Расходник", potion: "Зелье", consume: "Расходник", coupon: "Купон",
  frame: "Рамка",
};

const SLOT_ICON: Record<string, string> = {
  weapon: "⚔️", helmet: "⛑", armor: "🛡",
  boots: "👢", artifact: "💎", flair: "🎨",
  consumable: "⚗️", potion: "🧪", consume: "⚗️", coupon: "🎫",
  frame: "🖼",
};



function getEnhanceChance(level: number, useStone: boolean): number {
  if (useStone) return 100;
  if (level < 5) return 100;
  return Math.max(10, 100 - (level - 4) * 15);
}

function getEnhanceCost(level: number): number {
  return 50 + level * 30;
}

const EQUIPPABLE_SLOTS = ["weapon", "helmet", "armor", "boots", "artifact"];

function isConsumable(item: InventoryItem): boolean {
  if (item.slot === "potion" || item.slot === "consume") return true;
  if (item.slot === "coupon" && item.key !== "pet_rename") return true;
  if (!item.slot || item.slot === "flair") {
    return !item.is_cosmetic && !item.key.startsWith("junk_");
  }
  return false;
}

function isEquippable(item: InventoryItem): boolean {
  return !item.is_cosmetic && !!item.slot && EQUIPPABLE_SLOTS.includes(item.slot);
}

// ── UX helpers: answer the 4 questions ─────────────────────────────────────

/** ① ЧТО ДЕЛАЕТ — description with smart fallback */
function getEffectDesc(item: InventoryItem): string {
  if (item.desc) return item.desc;
  if (item.rarity === "junk") return "Бесполезный хлам путешественника. Никакого применения нет — только продать за мору кнопкой ниже.";
  if (item.slot === "potion") return "Временный бафф характеристик. Исчезает по истечении времени.";
  if (item.slot === "consume") return "Мгновенный расходник — эффект применяется сразу при использовании.";
  if (item.slot === "coupon") return "Одноразовый купон для специального действия.";
  if (item.slot === "frame") return "Декоративная рамка вокруг аватара в профиле.";
  if (item.slot === "flair" && item.id < 0) return "Изменяет оформление всего профиля (заголовок, разделители).";
  if (item.slot === "flair" && item.id > 0) return "Визуальный эффект рядом с именем в профиле Mini App.";
  if (item.slot && EQUIPPABLE_SLOTS.includes(item.slot)) return "Экипируй, чтобы улучшить характеристики персонажа в PvP и рейдах.";
  return "Предмет из инвентаря.";
}

/** ③ КАК ПРИМЕНИТЬ — context-aware primary action label */
function getMainActionLabel(item: InventoryItem): string {
  if (item.key === "pet_rename") return "✏️ Переименовать питомца";
  if (item.key === "quest_reroll") return "🎯 Сменить задание дня";
  if (item.key === "exp_boost_sm") return "🗺️ Ускорить экспедицию (+30 мин)";
  if (item.key === "exp_boost_md") return "🗺️ Ускорить экспедицию (+2 часа)";
  if (item.key === "exp_boost_lg") return "🗺️ Ускорить экспедицию (−50% времени)";
  if (item.slot === "potion") {
    if (item.key.includes("hp")) return "🧪 Выпить зелье здоровья";
    if (item.key.includes("str")) return "🧪 Выпить зелье силы";
    if (item.key.includes("def")) return "🧪 Выпить зелье защиты";
    return "🧪 Выпить зелье";
  }
  if (item.slot === "consume") {
    if (item.key === "vip_lottery_ticket") return "🎟️ Активировать VIP-билет (+3 участия в лотерее)";
    if (item.key.includes("xp")) return "⚡ Применить → получить XP";
    if (item.key.includes("mora")) return "💰 Применить → получить Мору";
    return "⚡ Применить расходник";
  }
  if (isEquippable(item)) {
    if (item.equipped) return `Снять (слот: ${SLOT_LABEL[item.slot!] ?? item.slot})`;
    return `⚔️ Экипировать → ${SLOT_LABEL[item.slot!] ?? item.slot}`;
  }
  if (item.is_cosmetic && item.slot === "flair" && item.id < 0) {
    return item.equipped ? "✅ Тема активна" : "🎨 Применить тему профиля";
  }
  if (item.is_cosmetic && item.slot === "frame" && item.id < 0) {
    return item.equipped ? "✅ Рамка активна" : "🖼 Надеть рамку профиля";
  }
  if (item.is_cosmetic && item.slot === "flair" && item.id > 0) {
    return item.equipped ? "✨ Снять косметику" : "✨ Надеть косметику";
  }
  return "⚡ Использовать";
}

/** ④ ГДЕ ВЗЯТЬ — source tags */
function getItemSources(item: InventoryItem): string[] {
  const k = item.key;
  if (k.startsWith("junk_")) return ["🎰 Гача"];
  if (k === "str_potion" || k === "def_potion" || k === "hp_potion")
    return ["🛒 Магазин Моры", "🎰 Гача", "🎲 Рулетка"];
  if (k === "str_superior" || k === "def_superior") return ["🎰 Гача • легенд. пул"];
  if (k.startsWith("cmn_")) return ["🎰 Гача • обычный пул"];
  if (k.startsWith("rare_")) return ["🎰 Гача • редкий пул"];
  if (k.startsWith("lego_")) return ["🎰 Гача • легенд. пул"];
  if (k.startsWith("shard_")) return ["📈 Повышение уровней (×10)", "📋 Задания дня", "🏆 Достижения"];
  if (k === "exp_boost_sm" || k === "exp_boost_md") return ["🎰 Гача", "🎲 Рулетка", "🔨 Крафт (осколки)"];
  if (k === "exp_boost_lg") return ["🎰 Гача • легенд. пул"];
  if (k === "quest_reroll") return ["🎰 Гача", "🔨 Крафт (осколки)"];
  if (k === "pet_rename") return ["🎰 Гача • редкий пул"];
  if (k === "boss_coupon") return ["🎰 Гача", "💎 7 кристаллов"];
  if (k === "vip_lottery_ticket") return ["💎 Магазин кристаллов (100 💎)"];
  if (item.slot === "frame") return ["🛒 Магазин Моры", "🎰 Гача"];
  if (item.slot === "flair" && item.id < 0) return ["🎰 Гача • легенд. пул"];
  return ["🎰 Гача"];
}

interface Props {
  userId: number;
  chatId: number;
}

export default function Inventory({ userId: _userId, chatId }: Props) {
  const [data, setData]         = useState<{ items: InventoryItem[]; rpg: InventoryRpg; pity: number } | null>(null);
  const [error, setError]       = useState("");
  const [selected, setSelected] = useState<InventoryItem | null>(null);
  const [busy, setBusy]         = useState<string | null>(null);
  const { toast } = useToast();
  const [activeFilter, setActiveFilter] = useState("all");
  const [statsOpen, setStatsOpen] = useState(false);

  const showToast = useCallback((msg: string) => toast(msg, "info"), [toast]);

  const load = useCallback(() => {
    if (!chatId) return;
    setError("");
    fetchInventory(chatId)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [chatId]);

  useEffect(() => { load(); }, [load]);

  /* ── Действия ── */
  const doEquip = useCallback(async (item: InventoryItem) => {
    if (!item.slot) return;
    setBusy("equip");
    try {
      if (item.equipped || item.slot === "flair") {
        // Flair (crystal cosmetics) and unequip always use toggleEquip
        const res = await toggleEquip(chatId, item.id);
        showToast(res.ok ? (item.equipped ? `Снято: ${item.name}` : `Надето: ${item.name}`) : (res.error ?? "Ошибка"));
      } else {
        const res = await equipItem(chatId, item.id, item.slot);
        showToast(res.ok ? `Экипировано: ${res.equipped} → ${SLOT_LABEL[res.slot] ?? res.slot}` : (res.error ?? "Ошибка"));
      }
      setSelected(null);
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? extractApiError(e.message) : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast]);

  const [sellConfirm, setSellConfirm] = useState<InventoryItem | null>(null);
  const [enhanceDetail, setEnhanceDetail] = useState<InventoryItem | null>(null);
  const [renameItem, setRenameItem] = useState<InventoryItem | null>(null);

  const doSell = useCallback(async (item: InventoryItem) => {
    // Для предметов rare и legendary — требуется подтверждение!
    if ((item.rarity === "rare" || item.rarity === "legendary") && !sellConfirm) {
      setSellConfirm(item);
      return;
    }
    setSellConfirm(null);
    setBusy("sell");
    try {
      const res = await batchSell(chatId, [{ id: item.id, qty: 1 }]);
      showToast(`Продано за +${res.mora} 🪙 (баланс: ${res.balance} 🪙)`);
      setSelected(null);
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? extractApiError(e.message) : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast, sellConfirm]);

  const doSellAllJunk = useCallback(async () => {
    setBusy("sell_junk");
    try {
      const res = await sellJunk(chatId);
      showToast(res.sold > 0 ? `Продано ${res.sold} хлама за +${res.mora} 🪙` : "Хлам не найден");
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast]);

  const doEnhance = useCallback(async (item: InventoryItem, useStone = false) => {
    setBusy("enhance");
    try {
      const res = await enhanceItem(chatId, item.id, useStone);
      showToast(res.success ? `✅ ${res.message} (ур. ${res.enhancement_level})` : `❌ ${res.message}`);
      setEnhanceDetail(null);
      setSelected(null);
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? extractApiError(e.message) : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast]);

  const doConsume = useCallback(async (item: InventoryItem) => {
    setBusy("consume");
    try {
      if (item.key.startsWith("exp_boost_")) {
        const res = await boostExpedition(chatId, item.id);
        showToast(res.ok ? `✅ Экспедиция ускорена!` : `❌ ${res.error ?? "Ошибка"}`);
      } else {
        const res = await consumePotion(chatId, item.id);
        showToast(res.success ? "✅ " + res.message : "❌ " + res.message);
      }
      setSelected(null);
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? extractApiError(e.message) : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast]);

  const doRename = useCallback(async (item: InventoryItem, newName: string) => {
    setBusy("rename");
    try {
      const res = await renamePet(chatId, newName, item.id);
      showToast(res.ok ? `✏️ Питомец переименован в «${newName}»!` : (res.error ?? "Ошибка"));
      setRenameItem(null);
      setSelected(null);
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? extractApiError(e.message) : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast]);

  const doActivateTheme = useCallback(async (item: InventoryItem) => {
    if (item.equipped) return; // already active
    setBusy("theme");
    try {
      const res = await activateTheme(chatId, item.key);
      if (res.ok) {
        showToast(`🎨 Тема «${item.name}» активирована!`);
        document.documentElement.setAttribute("data-theme", item.key);
      } else {
        showToast((res as { error?: string }).error ?? "Ошибка");
      }
      setSelected(null);
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast]);

  const doActivateFrame = useCallback(async (item: InventoryItem) => {
    if (item.equipped) return; // already active
    setBusy("frame");
    try {
      const res = await buyShopItem(chatId, "frame", item.key, true, "personal");
      if ((res as { ok?: boolean }).ok || (res as { already_owned?: boolean }).already_owned) {
        showToast(`🖼 Рамка «${item.name}» активирована!`);
      } else {
        showToast((res as { error?: string }).error ?? "Ошибка");
      }
      setSelected(null);
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast]);

  /* ── Error & Loading ── */
  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <p className="font-medium">Ошибка</p>
        <p className="text-sm mt-1 break-all">{error}</p>
        <button onClick={load} className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}>Обновить</button>
      </div>
    );
  }

  if (!data) return <InvSkeleton />;

  const { items, rpg } = data;

  const RARITY_ORDER: Record<string, number> = { legendary: 4, rare: 3, common: 2, junk: 1 };

  const filtered = items
    .filter(it => {
      switch (activeFilter) {
        case "all":        return true;
        case "equipped":   return it.equipped;
        case "legendary":  return it.rarity === "legendary";
        case "rare":       return it.rarity === "rare";
        case "common":     return it.rarity === "common";
        case "junk":       return it.rarity === "junk";
        case "equipment":  return it.category === "equipment";
        case "consumable": return it.category === "consumable" || isConsumable(it);
        case "cosmetic":   return it.category === "cosmetic" || it.is_cosmetic;
        case "coupon":     return it.slot === "coupon";
        case "frame":      return it.slot === "frame";
        case "flair":      return it.slot === "flair";
        default:           return true;
      }
    })
    .sort((a, b) => {
      const rarityDiff = (RARITY_ORDER[b.rarity] ?? 0) - (RARITY_ORDER[a.rarity] ?? 0);
      if (rarityDiff !== 0) return rarityDiff;
      return b.enhancement_level - a.enhancement_level;
    });

  const junkCount = items.filter(i => i.rarity === "junk").length;

  return (
    <div className="animate-fadeIn pb-24">
      {/* ── Заголовок + RPG-статы ── */}
      <div className="p-4 pb-2">
        <div className="glass-hero p-3">
          <button
            className="w-full flex items-center justify-between"
            onClick={() => setStatsOpen(v => !v)}
          >
            <span className="text-sm font-bold flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: "var(--accent-soft)" }}>
                <Backpack size={14} style={{ color: "var(--accent)" }} />
              </div>
              Инвентарь
              <span className="badge badge-accent text-[10px]">{items.length}</span>
            </span>
            {statsOpen
              ? <ChevronUp size={16} style={{ color: "var(--text-hint)" }} />
              : <ChevronDown size={16} style={{ color: "var(--text-hint)" }} />}
          </button>

          {statsOpen && (
            <div className="mt-3 grid grid-cols-4 gap-2">
              <StatBadge icon={<Swords size={14} />}    label="ATK"  value={rpg.atk}  color="#ef4444" />
              <StatBadge icon={<Shield size={14} />}    label="DEF"  value={rpg.def}  color="#3b82f6" />
              <StatBadge icon={<Heart size={14} />}     label="HP"   value={rpg.hp}   color="#22c55e" />
              <StatBadge icon={<Crosshair size={14} />} label="CRIT" value={`${(rpg.crit * 100).toFixed(1)}%`} color="#f59e0b" />
            </div>
          )}
        </div>
      </div>

      {/* ── Быстрые действия ── */}
      <div className="flex items-center gap-2 px-4 py-2">
        {junkCount > 0 && (
          <button
            onClick={doSellAllJunk}
            disabled={busy === "sell_junk"}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50"
            style={{ backgroundColor: "#e74c3c22", color: "#e74c3c", border: "1px solid #e74c3c44" }}
          >
            {busy === "sell_junk"
              ? <Loader2 size={12} className="animate-spin" />
              : <Trash2 size={12} />}
            Продать хлам ({junkCount})
          </button>
        )}
        <button
          onClick={load}
          className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs ml-auto"
          style={{ color: "var(--text-hint)" }}
        >
          <RefreshCw size={12} />
        </button>
      </div>

      {/* ── Единый фильтр ── */}
      <div className="flex gap-2 px-4 pb-3 overflow-x-auto hide-scrollbar">
        {([
          { key: "all",        label: "🗂 Все" },
          { key: "equipped",   label: "★ Надетые" },
          { key: "equipment",  label: "⚔️ Экипировка" },
          { key: "consumable", label: "🧪 Расходники" },
          { key: "cosmetic",   label: "🎨 Косметика" },
          { key: "frame",      label: "🖼 Рамки" },
          { key: "coupon",     label: "🎫 Купоны" },
          { key: "legendary",  label: "✨ Легенд." },
          { key: "rare",       label: "💙 Редкие" },
          { key: "junk",       label: "🗑 Хлам" },
        ]).map(f => (
          <button
            key={f.key}
            onClick={() => setActiveFilter(f.key)}
            className="px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-all"
            style={{
              backgroundColor: activeFilter === f.key ? "var(--accent)" : "var(--bg-secondary)",
              color: activeFilter === f.key ? "#fff" : "var(--text-hint)",
              border: activeFilter === f.key ? "1px solid var(--accent)" : "1px solid transparent",
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* ── Пустой инвентарь ── */}
      {filtered.length === 0 && (
        <div className="flex flex-col items-center mt-12 gap-3" style={{ color: "var(--text-hint)" }}>
          <Backpack size={44} strokeWidth={1.2} />
          <p className="text-sm">Пусто</p>
        </div>
      )}

      {/* ── Сетка предметов ── */}
      <div className="grid grid-cols-2 gap-3 px-4">
        {filtered.map(item => (
          <ItemTile key={item.id} item={item} onClick={() => setSelected(item)} />
        ))}
      </div>

      {/* ── BottomSheet ── */}
      {selected && (
        <BottomSheet
          item={selected}
          busy={busy}
          onClose={() => setSelected(null)}
          onEquip={doEquip}
          onSell={doSell}
          onEnhance={(item) => setEnhanceDetail(item)}
          onConsume={doConsume}
          onActivateTheme={doActivateTheme}
          onActivateFrame={doActivateFrame}
          onRename={(item) => setRenameItem(item)}
        />
      )}

      {/* ── Rename Modal ── */}
      {renameItem && (
        <RenameModal
          item={renameItem}
          busy={busy === "rename"}
          onClose={() => setRenameItem(null)}
          onConfirm={(name) => doRename(renameItem, name)}
        />
      )}

      {/* ── Confirm Sell Modal (rare+) ── */}
      {sellConfirm && (
        <>
          <div className="fixed inset-0 z-[60] bg-black/60" onClick={() => setSellConfirm(null)} />
          <div className="fixed inset-x-4 top-1/2 -translate-y-1/2 z-[61] rounded-2xl p-5" style={{ backgroundColor: "var(--bg-primary)" }}>
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle size={20} style={{ color: "#ef4444" }} />
              <h3 className="font-bold text-base">Подтверждение продажи</h3>
            </div>
            <p className="text-sm mb-1" style={{ color: "var(--text-hint)" }}>
              Вы действительно хотите продать
            </p>
            <div className="rounded-xl p-3 my-3 flex items-center gap-2" style={{ backgroundColor: "var(--bg-secondary)" }}>
              <span className="text-xl">{SLOT_ICON[sellConfirm.slot ?? ""] ?? "📦"}</span>
              <div>
                <p className="text-sm font-semibold" style={{ color: RARITY_COLOR[sellConfirm.rarity] }}>
                  {sellConfirm.rarity === "legendary" && "✨ "}{sellConfirm.name}
                  {sellConfirm.enhancement_level > 0 && ` +${sellConfirm.enhancement_level}`}
                </p>
                <p className="text-xs" style={{ color: "var(--text-hint)" }}>за {sellConfirm.sell_price} 🪙</p>
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setSellConfirm(null)}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold"
                style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-hint)" }}>Отмена</button>
              <button onClick={() => doSell(sellConfirm)}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold"
                style={{ backgroundColor: "#ef4444", color: "#fff" }}>Продать</button>
            </div>
          </div>
        </>
      )}

      {/* ── Enhance Detail Panel ── */}
      {enhanceDetail && (
        <>
          <div className="fixed inset-0 z-[60] bg-black/60" onClick={() => setEnhanceDetail(null)} />
          <div className="fixed inset-x-4 top-1/2 -translate-y-1/2 z-[61] rounded-2xl p-5" style={{ backgroundColor: "var(--bg-primary)" }}>
            <h3 className="font-bold text-base mb-3 flex items-center gap-2">
              🔨 Заточка: {enhanceDetail.name}
              {enhanceDetail.enhancement_level > 0 && <span style={{ color: "#f59e0b" }}>+{enhanceDetail.enhancement_level}</span>}
            </h3>
            <div className="space-y-2 mb-4">
              <div className="flex justify-between text-sm">
                <span style={{ color: "var(--text-hint)" }}>Текущий уровень</span>
                <span className="font-bold">+{enhanceDetail.enhancement_level}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span style={{ color: "var(--text-hint)" }}>Шанс успеха</span>
                <span className="font-bold" style={{ color: getEnhanceChance(enhanceDetail.enhancement_level, false) === 100 ? "#22c55e" : "#f59e0b" }}>
                  {getEnhanceChance(enhanceDetail.enhancement_level, false)}%
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span style={{ color: "var(--text-hint)" }}>Стоимость</span>
                <span className="font-bold">{getEnhanceCost(enhanceDetail.enhancement_level)} 🪙</span>
              </div>
              {enhanceDetail.enhancement_level >= 5 && (
                <div className="rounded-lg p-2 text-xs" style={{ backgroundColor: "#f59e0b18", color: "#f59e0b" }}>
                  ⚠️ При неудаче уровень снижается на 1
                </div>
              )}
            </div>
            {/* Progress bar visual */}
            <div className="h-2 rounded-full overflow-hidden mb-4" style={{ backgroundColor: "var(--border)" }}>
              <div className="h-full rounded-full transition-all" style={{
                width: `${getEnhanceChance(enhanceDetail.enhancement_level, false)}%`,
                backgroundColor: getEnhanceChance(enhanceDetail.enhancement_level, false) >= 70 ? "#22c55e" : getEnhanceChance(enhanceDetail.enhancement_level, false) >= 40 ? "#f59e0b" : "#ef4444",
              }} />
            </div>
            <div className="space-y-2">
              <button onClick={() => doEnhance(enhanceDetail, false)} disabled={busy === "enhance"}
                className="w-full py-3 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
                style={{ backgroundColor: "#f59e0b", color: "#fff" }}>
                {busy === "enhance" ? <Loader2 size={14} className="animate-spin" /> : `Заточить за ${getEnhanceCost(enhanceDetail.enhancement_level)} 🪙`}
              </button>
              <button onClick={() => doEnhance(enhanceDetail, true)} disabled={busy === "enhance"}
                className="w-full py-3 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
                style={{ backgroundColor: "#8b5cf6", color: "#fff" }}>
                {busy === "enhance" ? <Loader2 size={14} className="animate-spin" /> : "⚒️ Камень заточки (100%)"}
              </button>
              <button onClick={() => setEnhanceDetail(null)}
                className="w-full py-2 rounded-xl text-sm font-medium"
                style={{ color: "var(--text-hint)" }}>Отмена</button>
            </div>
          </div>
        </>
      )}

    </div>
  );
}

/* ── Плитка предмета ── */
function ItemTile({ item, onClick }: { item: InventoryItem; onClick: () => void }) {
  const color = RARITY_COLOR[item.rarity] ?? "#9ca3af";
  return (
    <button
      onClick={onClick}
      className="rounded-xl p-3 text-left transition-all active:scale-95 relative"
      style={{ backgroundColor: "var(--bg-secondary)", border: `1.5px solid ${item.equipped ? color : "transparent"}` }}
    >
      {item.equipped && (
        <span className="absolute top-1.5 right-1.5 text-[9px] px-1 py-0.5 rounded font-bold"
          style={{ backgroundColor: color + "33", color }}>★</span>
      )}
      {item.stack_count > 1 && (
        <span className="absolute top-1.5 left-1.5 text-[9px] px-1 py-0.5 rounded font-bold"
          style={{ backgroundColor: "var(--border)", color: "var(--text-hint)" }}>×{item.stack_count}</span>
      )}
      
      {/* ✨ Category badge */}
      {item.readable_category && (
        <div className="text-[8px] px-1.5 py-0.5 rounded-full mb-1.5 font-bold truncate"
             style={{ backgroundColor: color + "15", color: color }}>
          {item.readable_category}
        </div>
      )}
      
      <div className="w-8 h-8 rounded-lg flex items-center justify-center mb-2 text-sm"
        style={{ backgroundColor: color + "22" }}>
        {item.emoji || (SLOT_ICON[item.slot ?? ""] ?? "📦")}
      </div>
      <p className="text-xs font-semibold leading-tight truncate" style={{ color: "var(--text-primary)" }}>
        {item.name}
      </p>
      <p className="text-[10px] mt-0.5 capitalize" style={{ color }}>
        {RARITY_LABEL[item.rarity] ?? item.rarity}
        {item.enhancement_level > 0 && ` +${item.enhancement_level}`}
      </p>
    </button>
  );
}

/* ── BottomSheet ── */
interface BSProps {
  item: InventoryItem;
  busy: string | null;
  onClose: () => void;
  onEquip: (item: InventoryItem) => void;
  onSell:  (item: InventoryItem) => void;
  onEnhance: (item: InventoryItem) => void;
  onConsume: (item: InventoryItem) => void;
  onActivateTheme: (item: InventoryItem) => void;
  onActivateFrame: (item: InventoryItem) => void;
  onRename: (item: InventoryItem) => void;
}

function BottomSheet({ item, busy, onClose, onEquip, onSell, onEnhance, onConsume, onActivateTheme, onActivateFrame, onRename }: BSProps) {
  const color = RARITY_COLOR[item.rarity] ?? "#9ca3af";

  // Coloured stats list
  const stats: { label: string; value: string; color: string }[] = [];
  if (item.atk)              stats.push({ label: "⚔️ ATK",  value: `+${item.atk}`,    color: "#ef4444" });
  if (item.def_val)          stats.push({ label: "🛡 DEF",  value: `+${item.def_val}`, color: "#3b82f6" });
  if (item.hp)               stats.push({ label: "❤️ HP",   value: `+${item.hp}`,      color: "#22c55e" });
  if (item.crit_rate)        stats.push({ label: "🎯 CRIT", value: `+${(item.crit_rate * 100).toFixed(1)}%`, color: "#f59e0b" });
  if (item.enhancement_level > 0) stats.push({ label: "✨ Улучш.", value: `+${item.enhancement_level}`, color });

  const canEquip         = isEquippable(item);
  const canConsume       = isConsumable(item);
  const canSell          = item.sell_price > 0 && !item.equipped;
  const canActivateTheme = item.is_cosmetic && item.slot === "flair" && item.id < 0;
  const canActivateFrame = item.is_cosmetic && item.slot === "frame" && item.id < 0;
  const canEquipFlair    = item.is_cosmetic && item.slot === "flair" && item.id > 0 && item.key !== "pet_rename";
  const canRename        = item.key === "pet_rename";
  const isJunk           = item.rarity === "junk";

  const hasPrimaryAction = canEquip || canConsume || canActivateTheme || canActivateFrame || canEquipFlair || canRename;
  const primaryDisabled  = !!busy || ((canActivateTheme || canActivateFrame) && item.equipped);

  const handlePrimary = () => {
    if (canEquip)         return onEquip(item);
    if (canActivateTheme) return !item.equipped && onActivateTheme(item);
    if (canActivateFrame) return !item.equipped && onActivateFrame(item);
    if (canEquipFlair)    return onEquip(item);
    if (canRename)        return onRename(item);
    if (canConsume)       return onConsume(item);
  };

  const effectDesc  = getEffectDesc(item);
  const sources     = getItemSources(item);
  const actionLabel = getMainActionLabel(item);

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <div
        className="fixed bottom-0 inset-x-0 z-50 rounded-t-2xl pb-10 animate-slideUp"
        style={{ backgroundColor: "var(--bg-primary)", maxHeight: "90vh", overflowY: "auto" }}
      >
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full" style={{ backgroundColor: "var(--border)" }} />
        </div>

        {/* ① ЧТО ЭТО — header with emoji, name, badges */}
        <div className="flex items-start gap-3 px-4 pt-2 pb-4" style={{ borderBottom: "1px solid var(--border)" }}>
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center flex-shrink-0 text-2xl"
            style={{ backgroundColor: color + "22", border: `2px solid ${color}55` }}
          >
            {item.emoji || (SLOT_ICON[item.slot ?? ""] ?? "📦")}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <h2 className="font-bold text-base leading-tight" style={{ color: "var(--text-primary)" }}>
                {item.name}
                {item.enhancement_level > 0 && (
                  <span className="ml-1.5 text-sm font-bold" style={{ color: "#f59e0b" }}>
                    +{item.enhancement_level}
                  </span>
                )}
              </h2>
              <button onClick={onClose} className="flex-shrink-0 mt-0.5" style={{ color: "var(--text-hint)" }}>
                <X size={18} />
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
              <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                style={{ backgroundColor: color + "22", color }}>
                {item.rarity === "legendary" ? "✨ " : ""}{RARITY_LABEL[item.rarity] ?? item.rarity}
              </span>
              {item.slot && (
                <span className="text-xs px-2 py-0.5 rounded-full"
                  style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-hint)" }}>
                  {SLOT_ICON[item.slot] ?? ""} {SLOT_LABEL[item.slot] ?? item.slot}
                </span>
              )}
              {item.equipped && (
                <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                  style={{ backgroundColor: color + "33", color }}>
                  ★ Надет
                </span>
              )}
              {item.stack_count > 1 && (
                <span className="text-xs px-2 py-0.5 rounded-full"
                  style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-hint)" }}>
                  ×{item.stack_count}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="px-4 pt-4 space-y-4">
          {/* ② ЧТО ДЕЛАЕТ — effect / description block (always shown) */}
          <div className="rounded-xl p-3" style={{ backgroundColor: "var(--bg-secondary)" }}>
            <p className="text-[10px] font-bold uppercase tracking-wider mb-1.5" style={{ color: "var(--text-hint)" }}>
              📖 Эффект
            </p>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>{effectDesc}</p>
          </div>

          {/* Stats row */}
          {stats.length > 0 && (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider mb-2" style={{ color: "var(--text-hint)" }}>
                ⚡ Характеристики
              </p>
              <div className="flex flex-wrap gap-2">
                {stats.map(s => (
                  <div key={s.label}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-sm font-bold"
                    style={{ backgroundColor: s.color + "18", color: s.color, border: `1px solid ${s.color}33` }}>
                    {s.label} {s.value}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ③ КАК ПРИМЕНИТЬ — action buttons */}
          <div className="space-y-2">
            {hasPrimaryAction && (
              <button
                onClick={handlePrimary}
                disabled={primaryDisabled}
                className="w-full py-3.5 rounded-xl font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 transition-all active:scale-[0.98]"
                style={{
                  backgroundColor: (canActivateTheme || canActivateFrame) && item.equipped ? "#6b7280" : color,
                  color: "#fff",
                }}
              >
                {busy && ["equip", "consume", "theme", "frame", "rename"].includes(busy)
                  ? <Loader2 size={16} className="animate-spin" />
                  : actionLabel}
              </button>
            )}
            {/* Enhance — secondary, only for equippable gear */}
            {canEquip && (
              <button
                onClick={() => onEnhance(item)}
                disabled={!!busy}
                className="w-full py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-50 transition-all active:scale-[0.98]"
                style={{ backgroundColor: "#f59e0b18", color: "#f59e0b", border: "1px solid #f59e0b44" }}
              >
                {busy === "enhance"
                  ? <Loader2 size={14} className="animate-spin" />
                  : `🔨 Улучшить${item.enhancement_level > 0 ? ` (ур. ${item.enhancement_level} → ${item.enhancement_level + 1})` : ""}`}
              </button>
            )}
            {/* Sell — red solid for junk, outline for normal items */}
            {canSell && (
              <button
                onClick={() => onSell(item)}
                disabled={busy === "sell"}
                className="w-full py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-50 transition-all active:scale-[0.98]"
                style={isJunk
                  ? { backgroundColor: "#e74c3c", color: "#fff" }
                  : { border: "1.5px solid #e74c3c55", color: "#e74c3c", backgroundColor: "#e74c3c0d" }}
              >
                {busy === "sell"
                  ? <Loader2 size={14} className="animate-spin" />
                  : `🗑 Продать за ${item.sell_price} 🪙`}
              </button>
            )}
            {!hasPrimaryAction && !canSell && (
              <p className="text-center text-xs py-2" style={{ color: "var(--text-hint)" }}>
                Нет доступных действий
              </p>
            )}
          </div>

          {/* ④ ГДЕ ВЗЯТЬ — source tags */}
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: "14px", paddingBottom: "4px" }}>
            <p className="text-[10px] font-bold uppercase tracking-wider mb-2.5" style={{ color: "var(--text-hint)" }}>
              📍 Как получить
            </p>
            <div className="flex flex-wrap gap-1.5">
              {sources.map((src, i) => (
                <span key={i}
                  className="text-xs px-2.5 py-1 rounded-lg font-medium"
                  style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--border)" }}>
                  {src}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

/* ── Stat Badge ── */
function StatBadge({ icon, label, value, color }: {
  icon: React.ReactNode; label: string; value: string | number; color: string;
}) {
  return (
    <div className="flex flex-col items-center gap-1 p-2 rounded-xl" style={{ backgroundColor: color + "18" }}>
      <div style={{ color }}>{icon}</div>
      <span className="text-[10px] font-semibold tabular-nums" style={{ color: "var(--text-primary)" }}>{value}</span>
      <span className="text-[9px]" style={{ color: "var(--text-hint)" }}>{label}</span>
    </div>
  );
}

/* ── Skeleton ── */
function InvSkeleton() {
  return (
    <div className="p-4 space-y-3 animate-pulse">
      <div className="skeleton h-14 rounded-2xl" />
      <div className="grid grid-cols-2 gap-3 mt-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton h-24 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

function extractApiError(msg: string): string {
  try { return JSON.parse(msg.split(": ").slice(1).join(": ")).error ?? msg; } catch { return msg; }
}

/* ── Rename Modal ── */
function RenameModal({
  item, busy, onClose, onConfirm,
}: {
  item: InventoryItem;
  busy: boolean;
  onClose: () => void;
  onConfirm: (name: string) => void;
}) {
  const [name, setName] = useState("");
  return (
    <>
      <div className="fixed inset-0 z-[60] bg-black/60" onClick={onClose} />
      <div className="fixed inset-x-4 top-1/2 -translate-y-1/2 z-[61] rounded-2xl p-5" style={{ backgroundColor: "var(--bg-primary)" }}>
        <h3 className="font-bold text-base mb-1 flex items-center gap-2">✏️ Переименовать питомца</h3>
        <p className="text-xs mb-4" style={{ color: "var(--text-hint)" }}>Купон: {item.name} будет использован</p>
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value.slice(0, 24))}
          onKeyDown={e => { if (e.key === "Enter" && name.trim() && !busy) onConfirm(name.trim()); }}
          placeholder="Новое имя питомца"
          maxLength={24}
          className="w-full px-3 py-2.5 rounded-xl text-sm mb-4 outline-none"
          style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
          autoFocus
        />
        <div className="flex gap-2">
          <button onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold"
            style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-hint)" }}>Отмена</button>
          <button
            onClick={() => name.trim() && onConfirm(name.trim())}
            disabled={!name.trim() || busy}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
            style={{ backgroundColor: "#8b5cf6", color: "#fff" }}
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : "Сохранить"}
          </button>
        </div>
      </div>
    </>
  );
}
