/* ──────────────────────────────────────────────────────────────
   Admin.tsx — God Mode Panel v3
   Ranks synced with backend utils/ranks.py:
     user(0) < moderator(1) < admin_junior(2) < admin_senior(3) < co_owner(4) < owner(5) < developer(6)
   Chat selector from /api/dev/chats (ecosystem grouping)
   Feature toggles load current DB state on mount
   Treasury tab with payout
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import {
  ShieldAlert, Search, ChevronDown, X, Loader2,
  Coins, Star, Users, Zap, ToggleLeft, ToggleRight,
  Crown, Gem, Landmark, ArrowRightLeft,
} from "lucide-react";
import {
  fetchDevUsers, devMemberUpdate, devAddMora, devAddXp,
  devGiveItem, devGiveCrystals, devFeatureToggle, fetchDevChats, fetchFeatureFlags,
  fetchTreasury, treasuryPayout, fetchMembers,
  fetchPromocodes, createPromocode, deactivatePromocode,
  fetchMegaphones, reviewMegaphone,
  fetchErrorLogs, clearErrorLogs,
  type MegaphoneMessage,
} from "../lib/api";
import type { DevUserEntry, DevChat, TreasuryResponse, ChatMember } from "../types";
import type { PromoRecord } from "../lib/api";
import type { ErrorLogEntry } from "../types";

interface Props {
  userId: number;
  chatId: number;
  isDev?: boolean;
}

type AdminTab = "users" | "give" | "features" | "treasury" | "promos" | "megaphone" | "error_logs";

/* ── Жёсткая иерархия рангов (синхронизировано с utils/ranks.py) ── */
const RANK_HIERARCHY = [
  { key: "user",          label: "User",         color: "var(--text-hint)", level: 0 },
  { key: "moderator",     label: "Moderator",    color: "#2ed573", level: 1 },
  { key: "admin_junior",  label: "Junior Admin", color: "#3b82f6", level: 2 },
  { key: "admin_senior",  label: "Senior Admin", color: "#e84393", level: 3 },
  { key: "co_owner",      label: "Co-owner",     color: "#a855f7", level: 4 },
  { key: "owner",         label: "Owner",        color: "#f59e0b", level: 5 },
  { key: "developer",     label: "Developer",    color: "#ef4444", level: 6 },
];

/* ── Backend _ALLOWED_FEATURE_KEYS (synced with miniapp_views.py) ── */
const FEATURE_LIST = [
  { key: "feat_website",       label: "Сайт",           desc: "Ссылка на сайт" },
  { key: "feat_antispam",      label: "Антиспам",       desc: "Автомодерация" },
  { key: "feat_marriages",     label: "Браки",          desc: "Система браков" },
  { key: "feat_pets",          label: "Питомцы",        desc: "Система питомцев" },
  { key: "feat_casino",        label: "Казино",         desc: "Дуэли и лотерея" },
  { key: "feat_random_events", label: "Ивенты",         desc: "Случайные события" },
  { key: "feat_roulette",      label: "Рулетка",        desc: "Рулетка за мору" },
  { key: "feat_chest",         label: "Сундуки",        desc: "Случайные сундуки" },
  { key: "feat_coin_flip",     label: "Монетка",        desc: "Орёл/решка" },
  { key: "feat_xp_gain",       label: "XP Gain",        desc: "Начисление опыта" },
  { key: "feat_auto_welcome",  label: "Автоприветствие", desc: "Welcome-сообщение" },
  { key: "bot_disabled",       label: "Бот отключён",   desc: "Полностью отключить бота" },
  { key: "antiflood_mode",     label: "Антифлуд",       desc: "Режим антифлуда" },
];

function getRankInfo(key: string) {
  return RANK_HIERARCHY.find(r => r.key === key) ?? RANK_HIERARCHY[0];
}

/* ── Пул предметов для поиска при выдаче ── */
const ITEM_DB = [
  { name: "Меч Бури", rarity: "legendary", slot: "weapon" },
  { name: "Клинок Рассвета", rarity: "legendary", slot: "weapon" },
  { name: "Коса Жнеца", rarity: "legendary", slot: "weapon" },
  { name: "Щит Титана", rarity: "legendary", slot: "armor" },
  { name: "Корона Теней", rarity: "legendary", slot: "helmet" },
  { name: "Стальной меч", rarity: "rare", slot: "weapon" },
  { name: "Кольчуга", rarity: "rare", slot: "armor" },
  { name: "Берет разведчика", rarity: "rare", slot: "helmet" },
  { name: "Железные сапоги", rarity: "rare", slot: "boots" },
  { name: "Кулон удачи", rarity: "rare", slot: "artifact" },
  { name: "Деревянный меч", rarity: "common", slot: "weapon" },
  { name: "Кожаная броня", rarity: "common", slot: "armor" },
  { name: "Тканевая шапка", rarity: "common", slot: "helmet" },
  { name: "Сандалии", rarity: "common", slot: "boots" },
  { name: "Камень заточки", rarity: "rare", slot: "consumable" },
  { name: "Зелье атаки", rarity: "common", slot: "consumable" },
  { name: "Зелье защиты", rarity: "common", slot: "consumable" },
  { name: "Свиток гарантии", rarity: "legendary", slot: "consumable" },
];

export default function Admin({ chatId: defaultChatId, userId, isDev }: Props) {
  const [tab, setTab]                   = useState<AdminTab>("users");
  const [activeChatId, setActiveChatIdRaw] = useState<number>(() => {
    try {
      const saved = localStorage.getItem("admin_active_chat_id");
      return saved ? Number(saved) : defaultChatId;
    } catch { return defaultChatId; }
  });

  const setActiveChatId = (id: number) => {
    setActiveChatIdRaw(id);
    try { localStorage.setItem("admin_active_chat_id", String(id)); } catch { /* ignore */ }
  };

  /* ── Чат-селектор из БД ── */
  const [chats, setChats]         = useState<DevChat[]>([]);
  const [chatsLoading, setChatsL] = useState(false);
  const [chatOpen, setChatOpen]   = useState(false);

  useEffect(() => {
    setChatsL(true);
    fetchDevChats()
      .then(r => setChats([...(r.groups ?? []), ...(r.admin_chats ?? [])]))
      .catch(() => {})
      .finally(() => setChatsL(false));
  }, []);

  const currentChatTitle = chats.find(c => c.chat_id === activeChatId)?.title ?? String(activeChatId);

  if (!isDev) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 p-6 text-center">
        <ShieldAlert size={48} strokeWidth={1.2} style={{ color: "#ef4444" }} />
        <div>
          <p className="font-bold text-base">Доступ запрещён</p>
          <p className="text-sm mt-1" style={{ color: "var(--text-hint)" }}>
            Эта панель доступна только разработчикам.
          </p>
        </div>
      </div>
    );
  }

  const tabs: { key: AdminTab; label: string }[] = [
    { key: "users",      label: "👤 Участники"  },
    { key: "give",       label: "🎁 Выдать"     },
    { key: "promos",     label: "🎟️ Промокоды" },
    { key: "megaphone",  label: "📢 Рупор"      },
    { key: "features",   label: "⚙️ Функции"    },
    { key: "treasury",   label: "🏦 Казна"      },
    { key: "error_logs", label: "📋 Ошибки"     },
  ];

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-24">
      {/* Header */}
      <div className="glass-hero p-4" style={{ borderColor: "#ef444444" }}>
        <div className="flex items-center gap-2.5 mb-2">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "#ef444422" }}>
            <ShieldAlert size={18} style={{ color: "#ef4444" }} />
          </div>
          <div>
            <p className="font-bold text-base" style={{ color: "#ef4444" }}>God Mode</p>
            <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
              UID: {userId} · Developer Immunity
            </p>
          </div>
          <Crown size={16} style={{ color: "#f59e0b" }} className="ml-auto" />
        </div>

        {/* Chat selector dropdown */}
        <div className="relative mt-2">
          <button
            onClick={() => setChatOpen(!chatOpen)}
            className="w-full flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm"
            style={{ backgroundColor: "#0a0505", border: "1px solid #ef444433", color: "var(--text-primary)" }}
          >
            <span className="truncate">
              {chatsLoading ? "Загрузка чатов..." : currentChatTitle}
            </span>
            <ChevronDown size={14} style={{ color: "#ef4444", transform: chatOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
          </button>
          {chatOpen && chats.length > 0 && (
            <div className="absolute left-0 right-0 top-full mt-1 z-20 max-h-60 overflow-y-auto rounded-lg"
              style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)" }}>
              {chats.map(c => (
                <button
                  key={c.chat_id}
                  onClick={() => { setActiveChatId(c.chat_id); setChatOpen(false); }}
                  className="w-full text-left px-3 py-2 text-sm flex items-center justify-between gap-2 transition-colors"
                  style={{
                    backgroundColor: c.chat_id === activeChatId ? "#ef444422" : "transparent",
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{c.title}</p>
                    <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>
                      {c.chat_type} · {c.members} уч.
                      {c.ecosystem_role && ` · ${c.ecosystem_role === "main" ? "🏠 Основной" : "🛡 Админ-чат"}`}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
        <p className="text-[10px] mt-1.5 tabular-nums" style={{ color: "#ef444488" }}>
          ID: {activeChatId}
        </p>
      </div>

      {/* Tabs */}
      <div className="glass-card tab-scroll flex gap-1 rounded-xl p-1 overflow-x-auto">
        {tabs.map(({ key, label }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className="flex-none px-3 py-1.5 text-sm font-semibold rounded-lg transition-all whitespace-nowrap"
              style={{
                backgroundColor: active ? "#ef4444" : "transparent",
                color: active ? "#fff" : "var(--text-hint)",
                boxShadow: active ? "0 0 12px #ef444444" : "none",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {tab === "users"    && <UsersSection    chatId={activeChatId} />}
      {tab === "give"     && <GiveSection     chatId={activeChatId} />}
      {tab === "promos"   && <PromosSection />}
      {tab === "megaphone" && <MegaphoneSection />}
      {tab === "features" && <FeaturesSection chatId={activeChatId} />}
      {tab === "treasury" && <TreasurySection chatId={activeChatId} />}
      {tab === "error_logs" && <ErrorLogsSection />}
    </div>
  );
}

/* ── Input helper ── */
function InputField({ icon, label, value, onChange, type = "text" }: {
  icon: React.ReactNode; label: string; value: string; onChange: (v: string) => void; type?: string;
}) {
  return (
    <div>
      <label className="text-[11px] font-medium flex items-center gap-1" style={{ color: "var(--text-hint)" }}>
        {icon}{label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-1 rounded-lg px-2.5 py-1.5 text-sm bg-transparent outline-none"
        style={{ border: "1px solid var(--border)", color: "var(--text-primary)" }}
      />
    </div>
  );
}

/* ── Раздел участников ──────────────────────────────────────────── */
function UsersSection({ chatId }: { chatId: number }) {
  const [q, setQ] = useState("");
  const [users, setUsers] = useState<DevUserEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<DevUserEntry | null>(null);

  const [balance, setBalance]     = useState("");
  const [xp, setXp]               = useState("");
  const [rank, setRank]           = useState("");
  const [crystals, setCrystals]   = useState("");
  const [reputation, setReputation] = useState("");
  const [saving, setSaving]       = useState(false);
  const [toast, setToast]         = useState<string | null>(null);

  const showOk = (m: string) => { setToast(m); setTimeout(() => setToast(null), 3000); };

  const search = useCallback(() => {
    if (!chatId) return;
    setLoading(true);
    fetchDevUsers(chatId, q)
      .then((r) => setUsers(r.users ?? []))
      .finally(() => setLoading(false));
  }, [chatId, q]);

  useEffect(() => { search(); }, [search]);

  const select = (u: DevUserEntry) => {
    setSelected(u);
    setBalance(String(u.balance ?? 0));
    setXp(String(u.xp ?? 0));
    setRank(u.rank ?? "user");
    setCrystals(String(u.crystals ?? 0));
    setReputation(String(u.reputation ?? 0));
  };

  const save = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const r = await devMemberUpdate(chatId, selected.user_id, parseFloat(balance), parseInt(xp), rank, parseInt(reputation));
      if (!r.ok) {
        showOk("❌ " + (r.error ?? "Ошибка"));
        return;
      }
      const newCrystals = parseInt(crystals) || 0;
      const oldCrystals = selected.crystals ?? 0;
      const crystalDelta = newCrystals - oldCrystals;
      if (crystalDelta !== 0) {
        const cr = await devGiveCrystals(chatId, selected.user_id, crystalDelta);
        if (!cr.ok) {
          showOk("❌ Кристаллы: " + (cr.error ?? "Ошибка"));
          return;
        }
      }
      showOk("✅ Сохранено");
      search();
    } catch (e: unknown) {
      showOk("❌ " + (e instanceof Error ? e.message : "Ошибка сети"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      {toast && (
        <div className="rounded-xl px-3 py-2 text-sm font-medium animate-fadeIn"
          style={{
            backgroundColor: toast.startsWith("✅") ? "#22c55e18" : "#ef444418",
            color: toast.startsWith("✅") ? "#22c55e" : "#ef4444",
            border: `1px solid ${toast.startsWith("✅") ? "#22c55e50" : "#ef444450"}`,
          }}>
          {toast}
        </div>
      )}

      {/* Search */}
      <div
        className="flex items-center gap-2 rounded-xl px-3 py-2"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        <Search size={14} style={{ color: "var(--text-hint)" }} />
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск участника..."
          className="flex-1 bg-transparent text-sm outline-none"
          style={{ color: "var(--text-primary)" }}
        />
        {loading && <Loader2 size={14} className="animate-spin" style={{ color: "var(--text-hint)" }} />}
      </div>

      {/* User list */}
      <div className="space-y-1.5 max-h-64 overflow-y-auto rounded-xl hide-scrollbar">
        {users.map((u) => {
          const ri = getRankInfo(u.rank ?? "user");
          return (
            <button
              key={u.user_id}
              onClick={() => select(u)}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left transition-colors"
              style={{
                backgroundColor: selected?.user_id === u.user_id ? "#ef4444" : "var(--bg-secondary)",
                color: selected?.user_id === u.user_id ? "#fff" : "var(--text-primary)",
              }}
            >
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                style={{
                  backgroundColor: selected?.user_id === u.user_id ? "rgba(255,255,255,0.2)" : "var(--bg-primary)",
                  color: ri.color,
                }}
              >
                {(u.name ?? "?")[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <p className="text-sm font-medium truncate">{u.name ?? "—"}</p>
                  <span className="text-[9px] font-bold px-1 py-0.5 rounded shrink-0"
                    style={{ backgroundColor: ri.color + "22", color: ri.color }}>
                    {ri.label}
                  </span>
                </div>
                <p className="text-[11px] opacity-70">
                  🪙{u.balance} · Ур.{u.level ?? "?"} · XP:{u.xp} · 💬{u.message_count ?? 0}
                </p>
              </div>
            </button>
          );
        })}
        {users.length === 0 && !loading && (
          <p className="text-center text-sm py-4" style={{ color: "var(--text-hint)" }}>
            {q ? "Не найдено" : "Загрузка..."}
          </p>
        )}
      </div>

      {/* Editor */}
      {selected && (
        <div className="rounded-xl p-3 space-y-2.5 animate-fadeIn" style={{ backgroundColor: "var(--bg-secondary)" }}>
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">
              {selected.name}{" "}
              <span className="text-[11px] font-normal" style={{ color: "var(--text-hint)" }}>#{selected.user_id}</span>
            </p>
            <button onClick={() => setSelected(null)}>
              <X size={14} style={{ color: "var(--text-hint)" }} />
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <InputField icon={<Coins size={10} />} label="Баланс" value={balance} onChange={setBalance} type="number" />
            <InputField icon={<Zap size={10} />} label="XP" value={xp} onChange={setXp} type="number" />
            <InputField icon={<Gem size={10} />} label="Кристаллы" value={crystals} onChange={setCrystals} type="number" />
            <InputField icon={<ArrowRightLeft size={10} />} label="Репутация" value={reputation} onChange={setReputation} type="number" />
            <div>
              <label className="text-[11px] font-medium flex items-center gap-1" style={{ color: "var(--text-hint)" }}>
                <Star size={10} />Ранг
              </label>
              <div className="relative mt-1">
                <select
                  value={rank}
                  onChange={(e) => setRank(e.target.value)}
                  className="w-full rounded-lg px-2.5 py-1.5 text-sm appearance-none outline-none"
                  style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)", color: getRankInfo(rank).color }}
                >
                  {RANK_HIERARCHY.map((r) => (
                    <option key={r.key} value={r.key} style={{ color: r.color }}>{r.label}</option>
                  ))}
                </select>
                <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--text-hint)" }} />
              </div>
            </div>
            <div className="col-span-2 rounded-lg px-2.5 py-1.5 text-xs"
              style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)", color: "var(--text-hint)" }}>
              💬 Сообщений: <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{selected?.message_count ?? 0}</span>
              {" · "}⭐ Репутация: <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{selected?.reputation ?? 0}</span>
            </div>
          </div>

          <button
            onClick={save}
            disabled={saving}
            className="w-full py-2.5 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-opacity disabled:opacity-50"
            style={{ backgroundColor: "#ef4444", color: "#fff" }}
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : "💾 Сохранить"}
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Раздел выдачи ────────────────────────────────────────────── */
function GiveSection({ chatId }: { chatId: number }) {
  const [q, setQ]             = useState("");
  const [users, setUsers]     = useState<DevUserEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<DevUserEntry | null>(null);

  const [giveTab, setGiveTab]     = useState<"mora" | "xp" | "item">("mora");
  const [amount, setAmount]       = useState("");
  const [itemSearch, setItemSearch] = useState("");
  const [itemName, setItemName]   = useState("");
  const [rarity, setRarity]       = useState("common");
  const [busy, setBusy]           = useState(false);
  const [toast, setToast]         = useState<string | null>(null);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 3000); };

  const search = useCallback(() => {
    if (!chatId) return;
    setLoading(true);
    fetchDevUsers(chatId, q)
      .then((r) => setUsers(r.users ?? []))
      .finally(() => setLoading(false));
  }, [chatId, q]);

  useEffect(() => { search(); }, [search]);

  const filteredItems = itemSearch.length > 0
    ? ITEM_DB.filter(i => i.name.toLowerCase().includes(itemSearch.toLowerCase()))
    : [];

  const doGive = async () => {
    if (!selected || !chatId) return;
    setBusy(true);
    try {
      let r;
      if (giveTab === "mora")      r = await devAddMora(chatId, selected.user_id, parseFloat(amount));
      else if (giveTab === "xp")   r = await devAddXp(chatId, selected.user_id, parseInt(amount));
      else                         r = await devGiveItem(chatId, selected.user_id, itemName, rarity);

      if (r.ok) showToast("✅ " + (r.message ?? "Готово"));
      else      showToast("⚠️ " + (r.error ?? "Ошибка"));
      search();
    } catch (e: unknown) {
      showToast("⚠️ " + (e instanceof Error ? e.message : "Ошибка"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      {toast && (
        <div className="rounded-xl px-3 py-2 text-sm font-medium animate-fadeIn"
          style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--accent)" }}>
          {toast}
        </div>
      )}

      {/* Search */}
      <div
        className="flex items-center gap-2 rounded-xl px-3 py-2"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        <Search size={14} style={{ color: "var(--text-hint)" }} />
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск юзера..."
          className="flex-1 bg-transparent text-sm outline-none"
          style={{ color: "var(--text-primary)" }}
        />
        {loading && <Loader2 size={14} className="animate-spin" style={{ color: "var(--text-hint)" }} />}
      </div>

      {/* User list */}
      <div className="space-y-1 max-h-44 overflow-y-auto rounded-xl hide-scrollbar">
        {users.map((u) => {
          const ri = getRankInfo(u.rank ?? "user");
          return (
            <button
              key={u.user_id}
              onClick={() => setSelected(u)}
              className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-left text-sm transition-colors"
              style={{
                backgroundColor: selected?.user_id === u.user_id ? "#ef4444" : "var(--bg-secondary)",
                color: selected?.user_id === u.user_id ? "#fff" : "var(--text-primary)",
              }}
            >
              <Users size={12} />
              <span className="truncate">{u.name ?? u.user_id}</span>
              <span className="text-[10px] ml-auto opacity-60" style={{ color: ri.color }}>{ri.label}</span>
            </button>
          );
        })}
      </div>

      {/* Give form */}
      {selected && (
        <div className="rounded-xl p-3 space-y-2.5 animate-fadeIn" style={{ backgroundColor: "var(--bg-secondary)" }}>
          <p className="text-sm font-medium">→ {selected.name}</p>

          {/* Sub-tabs */}
          <div className="flex gap-1 rounded-lg p-1" style={{ backgroundColor: "var(--bg-primary)" }}>
            {(["mora", "xp", "item"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setGiveTab(t)}
                className="flex-1 py-1 text-xs font-medium rounded transition-colors"
                style={{
                  backgroundColor: giveTab === t ? "#ef4444" : "transparent",
                  color: giveTab === t ? "#fff" : "var(--text-hint)",
                }}
              >
                {t === "mora" ? "🪙 Мора" : t === "xp" ? "⚡ Опыт" : "🎲 Предмет"}
              </button>
            ))}
          </div>

          {(giveTab === "mora" || giveTab === "xp") && (
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={giveTab === "mora" ? "Мора (отриц. = забрать)" : "XP"}
              className="w-full rounded-lg px-2.5 py-1.5 text-sm bg-transparent outline-none"
              style={{ border: "1px solid var(--border)", color: "var(--text-primary)" }}
            />
          )}

          {giveTab === "item" && (
            <div className="space-y-1.5">
              {/* Поиск предмета по названию */}
              <div className="relative">
                <input
                  type="text"
                  value={itemSearch}
                  onChange={(e) => { setItemSearch(e.target.value); setItemName(e.target.value); }}
                  placeholder="🔍 Найти предмет по названию..."
                  className="w-full rounded-lg px-2.5 py-1.5 text-sm bg-transparent outline-none"
                  style={{ border: "1px solid var(--border)", color: "var(--text-primary)" }}
                />
                {filteredItems.length > 0 && (
                  <div className="absolute left-0 right-0 top-full mt-1 rounded-lg overflow-hidden z-10 max-h-40 overflow-y-auto"
                    style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)" }}>
                    {filteredItems.map((it) => (
                      <button
                        key={it.name}
                        onClick={() => { setItemName(it.name); setRarity(it.rarity); setItemSearch(""); }}
                        className="w-full text-left px-3 py-2 text-sm flex items-center justify-between"
                        style={{ borderBottom: "1px solid var(--border)" }}
                      >
                        <span>{it.name}</span>
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                          style={{
                            backgroundColor: it.rarity === "legendary" ? "#f59e0b22" : it.rarity === "rare" ? "#3b82f622" : "#22c55e22",
                            color: it.rarity === "legendary" ? "#f59e0b" : it.rarity === "rare" ? "#3b82f6" : "#22c55e",
                          }}>
                          {it.rarity}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {itemName && !itemSearch && (
                <div className="rounded-lg px-3 py-2 text-sm flex items-center justify-between"
                  style={{ backgroundColor: "var(--bg-primary)" }}>
                  <span>📦 {itemName}</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                    style={{
                      backgroundColor: rarity === "legendary" ? "#f59e0b22" : rarity === "rare" ? "#3b82f622" : "#22c55e22",
                      color: rarity === "legendary" ? "#f59e0b" : rarity === "rare" ? "#3b82f6" : "#22c55e",
                    }}>
                    {rarity}
                  </span>
                </div>
              )}
            </div>
          )}

          <button
            onClick={doGive}
            disabled={busy}
            className="w-full py-2 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-opacity disabled:opacity-50"
            style={{ backgroundColor: "#ef4444", color: "#fff" }}
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : "🎁 Выдать"}
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Раздел функций (загружает текущее состояние из БД) ────────── */
function FeaturesSection({ chatId }: { chatId: number }) {
  const [states, setStates] = useState<Record<string, boolean>>({});
  const [busy, setBusy]     = useState<string | null>(null);
  const [loading, setLoad]  = useState(true);

  useEffect(() => {
    if (!chatId) return;
    setLoad(true);
    fetchFeatureFlags(chatId)
      .then(r => {
        if (r.ok && r.flags) setStates(r.flags);
      })
      .catch(() => {})
      .finally(() => setLoad(false));
  }, [chatId]);

  const toggle = async (key: string) => {
    if (busy) return;
    const next = !states[key];
    setBusy(key);
    try {
      const r = await devFeatureToggle(chatId, key, next);
      if (r.ok) setStates((s) => ({ ...s, [key]: next }));
    } catch { /* ignore */ }
    finally { setBusy(null); }
  };

  if (loading) {
    return (
      <div className="space-y-2 animate-pulse">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton h-14 rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-hint)" }}>
        Переключение функций · Chat ID: {chatId}
      </p>
      <p className="text-[10px]" style={{ color: "#ef444488" }}>
        ⚠️ Developer имеет иммунитет — отключение Mini App не блокирует доступ
      </p>
      {FEATURE_LIST.map(({ key, label, desc }) => {
        const on = !!states[key];
        return (
          <div
            key={key}
            className="flex items-center justify-between rounded-xl px-3 py-2.5 transition-colors"
            style={{
              backgroundColor: on ? "#22c55e18" : "var(--bg-secondary)",
              border: `1px solid ${on ? "#22c55e44" : "transparent"}`,
            }}
          >
            <div>
              <p className="text-sm font-medium">{label}</p>
              <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>{desc}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span
                className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                style={{
                  backgroundColor: on ? "#22c55e22" : "var(--bg-primary)",
                  color: on ? "#22c55e" : "var(--text-hint)",
                }}
              >
                {on ? "ВКЛ" : "ВЫКЛ"}
              </span>
              <button
                onClick={() => toggle(key)}
                disabled={!!busy}
                className="transition-opacity disabled:opacity-50"
                style={{ color: on ? "#22c55e" : "var(--text-hint)" }}
              >
                {busy === key
                  ? <Loader2 size={22} className="animate-spin" />
                  : on
                  ? <ToggleRight size={28} />
                  : <ToggleLeft  size={28} />}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Раздел казны ──────────────────────────────────────────────── */
function TreasurySection({ chatId }: { chatId: number }) {
  const [data, setData]       = useState<TreasuryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [members, setMembers] = useState<ChatMember[]>([]);
  const [targetId, setTarget] = useState("");
  const [amount, setAmount]   = useState("");
  const [reason, setReason]   = useState("");
  const [busy, setBusy]       = useState(false);
  const [toast, setToast]     = useState<string | null>(null);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 3500); };

  const reload = useCallback(() => {
    if (!chatId) return;
    setLoading(true);
    fetchTreasury(chatId)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [chatId]);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    if (!chatId) return;
    fetchMembers(chatId).then(r => setMembers(r.members ?? [])).catch(() => {});
  }, [chatId]);

  const doPayout = async () => {
    if (busy || !targetId || !amount) return;
    setBusy(true);
    try {
      const r = await treasuryPayout(chatId, parseInt(targetId), parseInt(amount), reason || "Выплата");
      if (r.ok) {
        showToast("✅ Выплачено! Баланс казны: " + (r.new_balance ?? "?"));
        reload();
      } else {
        showToast("⚠️ " + (r.error ?? "Ошибка"));
      }
    } catch (e: unknown) {
      showToast("⚠️ " + (e instanceof Error ? e.message : "Ошибка"));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-3 animate-pulse">
        <div className="skeleton h-24 rounded-xl" />
        <div className="skeleton h-32 rounded-xl" />
      </div>
    );
  }

  const fmt = (n: number) => (n ?? 0).toLocaleString("ru-RU");

  return (
    <div className="space-y-3">
      {toast && (
        <div className="rounded-xl px-3 py-2 text-sm font-medium animate-fadeIn"
          style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--accent)" }}>
          {toast}
        </div>
      )}

      {/* Balance card */}
      <div className="rounded-xl p-4" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <div className="flex items-center gap-2 mb-2">
          <Landmark size={18} style={{ color: "#f59e0b" }} />
          <span className="text-sm font-semibold">Казна чата</span>
        </div>
        <p className="text-2xl font-bold tabular-nums">{fmt(data?.balance ?? 0)} 🪙</p>
        {data?.total_collected != null && (
          <p className="text-[11px] mt-1" style={{ color: "var(--text-hint)" }}>
            Всего собрано: {fmt(data.total_collected)}
          </p>
        )}
      </div>

      {/* Payout form */}
      <div className="rounded-xl p-3 space-y-2" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <p className="text-sm font-semibold flex items-center gap-1.5">
          <ArrowRightLeft size={14} style={{ color: "#ef4444" }} /> Выплата из казны
        </p>
        <div>
          <label className="text-[11px] font-medium" style={{ color: "var(--text-hint)" }}>Получатель</label>
          <select
            value={targetId}
            onChange={e => setTarget(e.target.value)}
            className="w-full mt-1 rounded-lg px-2.5 py-1.5 text-sm appearance-none outline-none"
            style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
          >
            <option value="">Выберите...</option>
            {members.map(m => (
              <option key={m.user_id} value={m.user_id}>{m.name} (#{m.user_id})</option>
            ))}
          </select>
        </div>
        <InputField icon={<Coins size={10} />} label="Сумма" value={amount} onChange={setAmount} type="number" />
        <InputField icon={<Star size={10} />} label="Причина" value={reason} onChange={setReason} />
        <button
          onClick={doPayout}
          disabled={busy || !targetId || !amount}
          className="w-full py-2 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-opacity disabled:opacity-50"
          style={{ backgroundColor: "#ef4444", color: "#fff" }}
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : "💸 Выплатить"}
        </button>
      </div>

      {/* Recent transactions */}
      {data?.recent && data.recent.length > 0 && (
        <div className="rounded-xl p-3 space-y-1.5" style={{ backgroundColor: "var(--bg-secondary)" }}>
          <p className="text-xs font-semibold uppercase" style={{ color: "var(--text-hint)" }}>Последние операции</p>
          {data.recent.map((e, i) => (
            <div key={i} className="flex justify-between items-center text-sm py-1"
              style={{ borderBottom: "1px solid var(--border)" }}>
              <span className="truncate flex-1">{e.description}</span>
              <span className="tabular-nums shrink-0 ml-2 font-medium"
                style={{ color: e.amount > 0 ? "#22c55e" : "#ef4444" }}>
                {e.amount > 0 ? "+" : ""}{fmt(e.amount)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── ErrorLogsSection ────────────────────────────────────────── */
function ErrorLogsSection() {
  const [logs, setLogs] = useState<ErrorLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [toast, setToast] = useState<string | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchErrorLogs();
      setLogs(res.logs ?? []);
    } catch {
      showToast("⚠️ Ошибка загрузки логов");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => { load(); }, [load]);

  const handleClear = async () => {
    if (!confirm("Очистить ВСЕ логи ошибок?")) return;
    try {
      await clearErrorLogs();
      setLogs([]);
      showToast("🗑️ Логи очищены");
    } catch {
      showToast("⚠️ Ошибка при очистке");
    }
  };

  const toggle = (id: number) =>
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const filtered = logs.filter(l =>
    !filter ||
    l.source.toLowerCase().includes(filter.toLowerCase()) ||
    l.error_msg.toLowerCase().includes(filter.toLowerCase()) ||
    l.context.toLowerCase().includes(filter.toLowerCase())
  );

  const SOURCE_COLORS: Record<string, string> = {
    frontend: "#60a5fa",
    backend: "#f97316",
    bot: "#a78bfa",
    views: "#22c55e",
  };

  return (
    <div className="space-y-3">
      {toast && <div className="glass-card rounded-xl px-3 py-2 text-sm font-medium animate-fadeIn">{toast}</div>}

      {/* Controls */}
      <div className="flex gap-2">
        <div className="flex-1 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-hint)" }} />
          <input
            className="input-field w-full pl-8 text-sm"
            placeholder="Фильтр по source / ошибке..."
            value={filter}
            onChange={e => setFilter(e.target.value)}
          />
        </div>
        <button onClick={load} disabled={loading} className="px-3 py-2 rounded-xl text-xs font-bold btn-ghost disabled:opacity-40">
          {loading ? <Loader2 size={14} className="animate-spin" /> : "🔄"}
        </button>
        <button onClick={handleClear} className="px-3 py-2 rounded-xl text-xs font-bold btn-danger" disabled={logs.length === 0}>
          🗑️ Clear
        </button>
      </div>

      {/* Stats */}
      <div className="flex gap-2 text-[11px]" style={{ color: "var(--text-hint)" }}>
        <span>Всего: <b style={{ color: "var(--text-primary)" }}>{logs.length}</b></span>
        <span>·</span>
        <span>Показано: <b style={{ color: "var(--text-primary)" }}>{filtered.length}</b></span>
      </div>

      {/* Logs */}
      {loading && logs.length === 0 ? (
        <div className="flex justify-center py-8"><Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} /></div>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-center py-6" style={{ color: "var(--text-hint)" }}>Логи пусты 🎉</p>
      ) : (
        <div className="space-y-2">
          {filtered.map(log => {
            const isOpen = expanded.has(log.id);
            const srcColor = SOURCE_COLORS[log.source] ?? "var(--text-hint)";
            return (
              <div key={log.id} className="glass-card p-3 space-y-1.5">
                <div className="flex items-start justify-between gap-2 cursor-pointer" onClick={() => toggle(log.id)}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="badge text-[10px] px-1.5 py-0.5" style={{ color: srcColor, borderColor: srcColor + "44", background: srcColor + "15" }}>
                        {log.source}
                      </span>
                      {log.context && (
                        <span className="text-[10px] truncate" style={{ color: "var(--text-hint)" }}>{log.context}</span>
                      )}
                    </div>
                    <p className="text-xs font-medium truncate" style={{ color: "#ef4444" }}>{log.error_msg}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-[10px] tabular-nums" style={{ color: "var(--text-hint)" }}>
                      {new Date(log.created_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                    </p>
                    <span className="text-[9px]" style={{ color: "var(--text-hint)" }}>{isOpen ? "▲" : "▼"}</span>
                  </div>
                </div>
                {isOpen && (
                  <div className="space-y-1.5 pt-1.5" style={{ borderTop: "1px solid var(--border)" }}>
                    {log.user_id && (
                      <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>
                        user_id: {log.user_id} · chat_id: {log.chat_id}
                      </p>
                    )}
                    {log.traceback && (
                      <pre className="text-[10px] p-2 rounded-lg overflow-x-auto whitespace-pre-wrap break-all"
                        style={{ background: "var(--bg-primary)", color: "#ef4444cc", fontFamily: "monospace" }}>
                        {log.traceback}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ── MegaphoneSection ────────────────────────────────────────── */
function MegaphoneSection() {
  const [messages, setMessages] = useState<MegaphoneMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast]     = useState<string | null>(null);
  const [filter, setFilter]   = useState<"pending" | "approved" | "rejected">("pending");
  const [acting, setActing]   = useState<number | null>(null);

  const showOk = (m: string) => { setToast(m); setTimeout(() => setToast(null), 3000); };

  const load = useCallback(() => {
    setLoading(true);
    fetchMegaphones(filter)
      .then(r => setMessages(r.messages ?? []))
      .catch(() => showOk("❌ Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const handleReview = async (id: number, action: "approve" | "reject") => {
    setActing(id);
    try {
      const r = await reviewMegaphone(id, action);
      if (r.ok) {
        showOk(action === "approve" ? "✅ Рупор одобрен" : "🔄 Рупор отклонён, 💎 возвращены");
        load();
      } else {
        showOk("❌ Ошибка");
      }
    } catch {
      showOk("❌ Ошибка сети");
    } finally {
      setActing(null);
    }
  };

  return (
    <div className="space-y-3">
      {toast && (
        <div className="rounded-xl px-3 py-2 text-sm font-medium animate-fadeIn"
          style={{
            backgroundColor: toast.startsWith("✅") ? "#22c55e18" : toast.startsWith("🔄") ? "#3b82f618" : "#ef444418",
            color: toast.startsWith("✅") ? "#22c55e" : toast.startsWith("🔄") ? "#60a5fa" : "#ef4444",
            border: `1px solid ${toast.startsWith("✅") ? "#22c55e50" : toast.startsWith("🔄") ? "#3b82f650" : "#ef444450"}`,
          }}>
          {toast}
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex gap-1 rounded-lg p-1" style={{ backgroundColor: "var(--bg-secondary)" }}>
        {(["pending", "approved", "rejected"] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className="flex-1 px-2 py-1 text-xs font-medium rounded-md transition-colors"
            style={{
              backgroundColor: filter === f ? "#ef4444" : "transparent",
              color: filter === f ? "#fff" : "var(--text-hint)",
            }}
          >
            {f === "pending" ? "⏳ Ожидают" : f === "approved" ? "✅ Одобрены" : "❌ Отклонены"}
          </button>
        ))}
      </div>

      {loading && <Loader2 size={16} className="animate-spin mx-auto" style={{ color: "var(--text-hint)" }} />}

      {!loading && messages.length === 0 && (
        <div className="rounded-xl p-6 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
          <p className="text-sm" style={{ color: "var(--text-hint)" }}>
            {filter === "pending" ? "Нет рупоров на модерации 🎉" : "Пусто"}
          </p>
        </div>
      )}

      {messages.map(msg => (
        <div key={msg.id} className="rounded-xl p-3 space-y-2" style={{ backgroundColor: "var(--bg-secondary)" }}>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">
              {msg.user_name} <span className="text-[10px]" style={{ color: "var(--text-hint)" }}>#{msg.user_id}</span>
            </p>
            <span className="text-[10px]" style={{ color: "var(--text-hint)" }}>
              {new Date(msg.created_at).toLocaleString("ru")}
            </span>
          </div>
          <div className="rounded-lg p-2 text-sm" style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}>
            {msg.message}
          </div>
          {filter === "pending" && (
            <div className="flex gap-2">
              <button
                onClick={() => handleReview(msg.id, "approve")}
                disabled={acting === msg.id}
                className="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-50"
                style={{ backgroundColor: "#22c55e", color: "#fff" }}
              >
                {acting === msg.id ? "..." : "✅ Одобрить"}
              </button>
              <button
                onClick={() => handleReview(msg.id, "reject")}
                disabled={acting === msg.id}
                className="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-50"
                style={{ backgroundColor: "#ef4444", color: "#fff" }}
              >
                {acting === msg.id ? "..." : "❌ Отклонить (возврат 💎)"}
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ── PromosSection ──────────────────────────────────────────────── */
function PromosSection() {
  const [promos, setPromos] = useState<PromoRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // Create form
  const [code, setCode] = useState("");
  const [maxUses, setMaxUses] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  // Payload fields
  const [mora, setMora] = useState("");
  const [crystals, setCrystals] = useState("");
  const [xp, setXp] = useState("");
  const [stones, setStones] = useState("");
  const [themeKey, setThemeKey] = useState("");
  const [itemName, setItemName] = useState("");
  const [itemRarity, setItemRarity] = useState("common");
  const [randRarity, setRandRarity] = useState("");
  const [creating, setCreating] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 3000); };

  const load = useCallback(() => {
    setLoading(true);
    fetchPromocodes()
      .then(r => { if (r.ok) setPromos(r.promos ?? []); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const doCreate = async () => {
    if (!code.trim()) { showToast("⚠️ Введи код"); return; }
    setCreating(true);
    const payload: Record<string, unknown> = {};
    if (mora)     payload.mora     = parseInt(mora);
    if (crystals) payload.crystals = parseInt(crystals);
    if (xp)       payload.xp       = parseInt(xp);
    if (stones)   payload.enhancement_stones = parseInt(stones);
    if (themeKey) payload.theme    = themeKey;
    if (itemName) { payload.item_name = itemName; payload.item_rarity = itemRarity; }
    if (randRarity) payload.random_item_rarity = randRarity;
    try {
      const r = await createPromocode({
        code: code.trim().toUpperCase(),
        payload,
        max_uses: maxUses ? parseInt(maxUses) : null,
        expires_at: expiresAt || null,
      });
      if (r.ok) {
        showToast("✅ Промокод создан");
        setCode(""); setMaxUses(""); setExpiresAt(""); setMora(""); setCrystals(""); setXp(""); setStones(""); setThemeKey(""); setItemName(""); setRandRarity("");
        load();
      } else { showToast("⚠️ " + (r.error ?? "Ошибка")); }
    } catch (e: unknown) { showToast("⚠️ " + (e instanceof Error ? e.message : "Ошибка")); }
    finally { setCreating(false); }
  };

  const doDeactivate = async (c: string) => {
    try {
      await deactivatePromocode(c);
      showToast("🔴 Деактивирован");
      load();
    } catch { showToast("⚠️ Ошибка"); }
  };

  return (
    <div className="space-y-3">
      {toast && <div className="rounded-xl px-3 py-2 text-sm font-medium animate-fadeIn glass-card">{toast}</div>}

      {/* Create form */}
      <div className="rounded-xl p-3 space-y-2 glass-card">
        <p className="text-sm font-semibold" style={{ color: "var(--accent)" }}>🎟️ Создать промокод</p>
        <div className="grid grid-cols-2 gap-2">
          <InputField icon="🔑" label="Код" value={code} onChange={setCode} />
          <InputField icon="♾️" label="Макс. активаций (пусто=∞)" value={maxUses} onChange={setMaxUses} type="number" />
          <div className="col-span-2">
            <label className="text-[11px] font-medium" style={{ color: "var(--text-hint)" }}>📅 Срок (пусто=∞)</label>
            <input type="datetime-local" value={expiresAt} onChange={e => setExpiresAt(e.target.value)}
              className="w-full mt-0.5 rounded-lg px-2 py-1.5 text-xs" style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
            />
          </div>
        </div>
        <p className="text-[10px] font-semibold uppercase mt-1" style={{ color: "var(--text-hint)" }}>Награды (payload)</p>
        <div className="grid grid-cols-2 gap-2">
          <InputField icon="🪙" label="Мора"     value={mora}     onChange={setMora}     type="number" />
          <InputField icon="💎" label="Кристаллы" value={crystals} onChange={setCrystals} type="number" />
          <InputField icon="⚡" label="XP"        value={xp}       onChange={setXp}       type="number" />
          <InputField icon="⚒️" label="Камни заточки" value={stones} onChange={setStones} type="number" />
          <InputField icon="🎨" label="Тема (ключ)" value={themeKey} onChange={setThemeKey} />
          <InputField icon="🎲" label="Предмет (имя)" value={itemName} onChange={setItemName} />
        </div>
        <div className="flex gap-2 items-center">
          <label className="text-[11px]" style={{ color: "var(--text-hint)" }}>Редкость предмета:</label>
          {(["common","rare","epic","legendary"] as const).map(r => (
            <button key={r} onClick={() => setItemRarity(r)}
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{ backgroundColor: itemRarity === r ? "var(--accent)" : "var(--bg-primary)", color: itemRarity === r ? "#fff" : "var(--text-hint)" }}>
              {r}
            </button>
          ))}
        </div>
        <div className="flex gap-2 items-center">
          <label className="text-[11px]" style={{ color: "var(--text-hint)" }}>Случайный предмет редкости:</label>
          {["", "common","rare","epic","legendary"].map(r => (
            <button key={r} onClick={() => setRandRarity(r)}
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{ backgroundColor: randRarity === r ? "var(--accent)" : "var(--bg-primary)", color: randRarity === r ? "#fff" : "var(--text-hint)" }}>
              {r || "—"}
            </button>
          ))}
        </div>
        <button onClick={doCreate} disabled={creating}
          className="w-full py-2 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
          style={{ backgroundColor: "var(--accent)", color: "#fff" }}>
          {creating ? <Loader2 size={14} className="animate-spin" /> : "✨ Создать"}
        </button>
      </div>

      {/* Existing promos */}
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase" style={{ color: "var(--text-hint)" }}>
          Все промокоды {loading && <Loader2 size={11} className="inline animate-spin ml-1" />}
        </p>
        {promos.map(p => (
          <div key={p.id} className="rounded-xl p-3 space-y-1 glass-card">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono font-bold text-sm" style={{ color: "var(--accent)" }}>{p.code}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded font-bold"
                style={{ backgroundColor: p.is_active ? "#22c55e22" : "#ef444422", color: p.is_active ? "#22c55e" : "#ef4444" }}>
                {p.is_active ? "АКТИВЕН" : "ВЫКЛ"}
              </span>
            </div>
            <div className="text-[11px]" style={{ color: "var(--text-hint)" }}>
              Использований: {p.uses}{p.max_uses ? ` / ${p.max_uses}` : " / ∞"}
              {p.expires_at && ` · До ${new Date(p.expires_at).toLocaleDateString("ru-RU")}`}
            </div>
            <div className="text-[11px] font-mono break-all" style={{ color: "var(--text-hint)" }}>
              {JSON.stringify(p.payload)}
            </div>
            {p.is_active && (
              <button onClick={() => doDeactivate(p.code)}
                className="text-[11px] px-2 py-0.5 rounded"
                style={{ backgroundColor: "#ef444422", color: "#ef4444" }}>
                Деактивировать
              </button>
            )}
          </div>
        ))}
        {!loading && promos.length === 0 && (
          <p className="text-sm text-center py-4" style={{ color: "var(--text-hint)" }}>Промокодов нет</p>
        )}
      </div>
    </div>
  );
}
