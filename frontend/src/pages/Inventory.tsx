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
import {
  fetchInventory, equipItem, toggleEquip,
  sellJunk, batchSell, enhanceItem, consumePotion, activateTheme,
} from "../lib/api";
import type { InventoryItem, InventoryRpg } from "../types";
import { RARITY_COLOR } from "./Gacha";

const RARITY_LABEL: Record<string, string> = {
  junk: "Хлам", common: "Обычный", rare: "Редкий", legendary: "Легендарный",
};

const SLOT_LABEL: Record<string, string> = {
  weapon: "Оружие", helmet: "Шлем", armor: "Броня",
  boots: "Сапоги", artifact: "Артефакт", flair: "Косметика",
  consumable: "Расходник",
};

const SLOT_ICON: Record<string, string> = {
  weapon: "⚔️", helmet: "⛑", armor: "🛡",
  boots: "👢", artifact: "💎", flair: "🎨",
  consumable: "⚗️",
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
  if (!item.slot || item.slot === "flair") {
    return !item.is_cosmetic && !item.key.startsWith("junk_");
  }
  return false;
}

function isEquippable(item: InventoryItem): boolean {
  return !item.is_cosmetic && !!item.slot && EQUIPPABLE_SLOTS.includes(item.slot);
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
  const [toast, setToast]       = useState<string | null>(null);
  const [rarityF, setRarityF]   = useState<"all" | "junk" | "common" | "rare" | "legendary">("all");
  const [slotF, setSlotF]       = useState<"all" | "equipped" | "weapon" | "helmet" | "armor" | "boots" | "artifact" | "consumable" | "flair">("all");
  const [statsOpen, setStatsOpen] = useState(false);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }, []);

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
      if (item.equipped) {
        const res = await toggleEquip(chatId, item.id);
        showToast(res.ok ? `Снято: ${item.name}` : (res.error ?? "Ошибка"));
      } else {
        const res = await equipItem(chatId, item.id, item.slot);
        showToast(res.ok ? `Экипировано: ${res.equipped} → ${SLOT_LABEL[res.slot] ?? res.slot}` : (res.error ?? "Ошибка"));
      }
      setSelected(null);
      load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? extractApiError(e.message) : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast]);

  const [sellConfirm, setSellConfirm] = useState<InventoryItem | null>(null);
  const [enhanceDetail, setEnhanceDetail] = useState<InventoryItem | null>(null);

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
      load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? extractApiError(e.message) : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast, sellConfirm]);

  const doSellAllJunk = useCallback(async () => {
    setBusy("sell_junk");
    try {
      const res = await sellJunk(chatId);
      showToast(res.sold > 0 ? `Продано ${res.sold} хлама за +${res.mora} 🪙` : "Хлам не найден");
      load();
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
      load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? extractApiError(e.message) : "Ошибка");
    } finally { setBusy(null); }
  }, [chatId, load, showToast]);

  const doConsume = useCallback(async (item: InventoryItem) => {
    setBusy("consume");
    try {
      const res = await consumePotion(chatId, item.id);
      showToast(res.success ? res.message : res.message);
      setSelected(null);
      load();
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
      load();
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

  const { items, rpg, pity } = data;

  const RARITY_ORDER: Record<string, number> = { legendary: 4, rare: 3, common: 2, junk: 1 };

  const filtered = items
    .filter(it => {
      if (rarityF !== "all" && it.rarity !== rarityF) return false;
      if (slotF === "equipped") return it.equipped;
      if (slotF === "consumable") return isConsumable(it);
      if (slotF !== "all") return it.slot === slotF;
      return true;
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
        <div className="rounded-2xl p-3" style={{ backgroundColor: "var(--bg-secondary)" }}>
          <button
            className="w-full flex items-center justify-between"
            onClick={() => setStatsOpen(v => !v)}
          >
            <span className="text-sm font-semibold flex items-center gap-2">
              <Backpack size={16} style={{ color: "var(--accent)" }} />
              Инвентарь
              <span className="text-xs font-normal" style={{ color: "var(--text-hint)" }}>
                ({items.length}) · Pity: {pity}
              </span>
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

      {/* ── Фильтры по редкости ── */}
      <div className="flex gap-2 px-4 pb-1.5 overflow-x-auto hide-scrollbar">
        {(["all", "legendary", "rare", "common", "junk"] as const).map(f => (
          <button
            key={f}
            onClick={() => setRarityF(f)}
            className="px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-all"
            style={{
              backgroundColor: rarityF === f ? (f === "all" ? "var(--accent)" : (RARITY_COLOR[f] ?? "var(--accent)")) : "var(--bg-secondary)",
              color: rarityF === f ? "#fff" : "var(--text-hint)",
            }}
          >
            {{ all: "Все", legendary: "✨ Легенд.", rare: "💙 Редкие", common: "⬜ Обычные", junk: "🗑 Хлам" }[f]}
          </button>
        ))}
      </div>

      {/* ── Фильтры по слоту ── */}
      <div className="flex gap-2 px-4 pb-3 overflow-x-auto hide-scrollbar">
        {(["all", "equipped", "weapon", "helmet", "armor", "boots", "artifact", "consumable", "flair"] as const).map(f => (
          <button
            key={f}
            onClick={() => setSlotF(f)}
            className="px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-all"
            style={{
              backgroundColor: slotF === f ? "var(--accent)" : "var(--bg-secondary)",
              color: slotF === f ? "#fff" : "var(--text-hint)",
            }}
          >
            {{ all: "Все типы", equipped: "★ Надетые", weapon: "⚔️ Оружие", helmet: "⛑ Шлем", armor: "🛡 Броня", boots: "👢 Сапоги", artifact: "💎 Артефакт", consumable: "⚗️ Расходники", flair: "🎨 Косметика" }[f]}
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

      {/* ── Тост ── */}
      {toast && (
        <div
          className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-[90vw] px-4 py-2.5 rounded-xl text-sm font-medium shadow-lg pointer-events-none"
          style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--accent)" }}
        >
          {toast}
        </div>
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
      <div className="w-8 h-8 rounded-lg flex items-center justify-center mb-2 text-sm"
        style={{ backgroundColor: color + "22" }}>
        {SLOT_ICON[item.slot ?? ""] ?? "📦"}
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
}

function BottomSheet({ item, busy, onClose, onEquip, onSell, onEnhance, onConsume, onActivateTheme }: BSProps) {
  const color = RARITY_COLOR[item.rarity] ?? "#9ca3af";
  const stats: { label: string; value: string | number }[] = [];
  if (item.atk)              stats.push({ label: "ATK",    value: `+${item.atk}` });
  if (item.def_val)          stats.push({ label: "DEF",    value: `+${item.def_val}` });
  if (item.hp)               stats.push({ label: "HP",     value: `+${item.hp}` });
  if (item.crit_rate)        stats.push({ label: "CRIT",   value: `+${item.crit_rate}%` });
  if (item.enhancement_level > 0) stats.push({ label: "Улучш.", value: `+${item.enhancement_level}` });

  const canEquip        = isEquippable(item);
  const canConsume      = isConsumable(item);
  const canSell         = item.sell_price > 0;
  const canActivateTheme = item.is_cosmetic && item.slot === "flair";

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <div
        className="fixed bottom-0 inset-x-0 z-50 rounded-t-2xl pb-8 animate-slideUp"
        style={{ backgroundColor: "var(--bg-primary)", maxHeight: "85vh", overflowY: "auto" }}
      >
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full" style={{ backgroundColor: "var(--border)" }} />
        </div>

        <div className="flex items-start justify-between px-4 pb-3 pt-1">
          <div className="flex-1 min-w-0 pr-3">
            <h2 className="font-bold text-base" style={{ color: "var(--text-primary)" }}>{item.name}</h2>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              <span className="text-xs font-semibold capitalize" style={{ color }}>
                {item.rarity === "legendary" && "✨ "}{RARITY_LABEL[item.rarity] ?? item.rarity}
              </span>
              {item.slot && (
                <span className="text-xs" style={{ color: "var(--text-hint)" }}>
                  {SLOT_LABEL[item.slot] ?? item.slot}
                </span>
              )}
              {item.equipped && (
                <span className="text-xs font-bold px-1.5 py-0.5 rounded"
                  style={{ backgroundColor: color + "22", color }}>Экипировано ★</span>
              )}
            </div>
          </div>
          <button onClick={onClose} style={{ color: "var(--text-hint)" }}><X size={20} /></button>
        </div>

        {item.desc && (
          <p className="px-4 text-sm mb-3" style={{ color: "var(--text-hint)" }}>{item.desc}</p>
        )}

        {stats.length > 0 && (
          <div className="flex flex-wrap gap-2 px-4 mb-4">
            {stats.map(s => (
              <div key={s.label} className="px-2.5 py-1 rounded-lg text-xs font-semibold"
                style={{ backgroundColor: color + "22", color }}>
                {s.label}: {s.value}
              </div>
            ))}
          </div>
        )}

        <div className="px-4 pb-6 space-y-2">
          {canEquip && (
            <ActionBtn loading={busy === "equip"} onClick={() => onEquip(item)}
              label={item.equipped ? "Снять" : `Экипировать (${SLOT_LABEL[item.slot!] ?? item.slot})`}
              color={item.equipped ? "#6b7280" : color} />
          )}
          {canEquip && (
            <ActionBtn loading={busy === "enhance"} onClick={() => onEnhance(item)}
              label={`Улучшить${item.enhancement_level > 0 ? ` (ур. ${item.enhancement_level})` : ""} 🔨`}
              color="#f59e0b" />
          )}
          {canActivateTheme && (
            <ActionBtn loading={busy === "theme"} onClick={() => onActivateTheme(item)}
              label={item.equipped ? "✅ Активная тема" : "🎨 Применить тему"}
              color={item.equipped ? "#6b7280" : "#a855f7"} />
          )}
          {canConsume && (
            <ActionBtn loading={busy === "consume"} onClick={() => onConsume(item)}
              label="Использовать ⚡" color="#22c55e" />
          )}
          {canSell && !item.equipped && (
            <ActionBtn loading={busy === "sell"} onClick={() => onSell(item)}
              label={`Продать за ${item.sell_price} 🪙`} color="#e74c3c" outline />
          )}
          {!canEquip && !canConsume && !canSell && !canActivateTheme && (
            <p className="text-center text-xs py-2" style={{ color: "var(--text-hint)" }}>Нет доступных действий</p>
          )}
        </div>
      </div>
    </>
  );
}

/* ── Action Button ── */
function ActionBtn({
  label, color, loading, onClick, outline = false,
}: {
  label: string; color: string; loading: boolean; onClick: () => void; outline?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="w-full py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-50 transition-all active:scale-95"
      style={outline
        ? { border: `1.5px solid ${color}`, color, backgroundColor: "transparent" }
        : { backgroundColor: color, color: "#fff" }}
    >
      {loading ? <Loader2 size={16} className="animate-spin" /> : label}
    </button>
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
