/* ──────────────────────────────────────────────────────────────
   Admin.tsx — Панель разработчика (God Mode)
   Только для пользователей с is_dev === true
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import {
  ShieldAlert, Search, ChevronDown, X, Loader2,
  Coins, Star, Users, Zap, ToggleLeft, ToggleRight,
} from "lucide-react";
import { fetchDevUsers, devMemberUpdate, devAddMora, devAddXp, devGiveItem, devFeatureToggle } from "../lib/api";
import type { DevUserEntry } from "../types";

interface Props {
  userId: number;
  chatId: number;
  isDev?: boolean;
}

type AdminTab = "users" | "give" | "features";

const RANKS = ["", "Новичок", "Ученик", "Воин", "Страж", "Ветеран", "Элита", "Мастер", "Легенда"];
const RARITIES = ["common", "uncommon", "rare", "epic", "legendary"];

const FEATURE_LIST = [
  { key: "feat_exchange", label: "Биржа" },
  { key: "feat_gacha",    label: "Гача"  },
  { key: "feat_website",  label: "Сайт"  },
];

export default function Admin({ chatId, userId, isDev }: Props) {
  const [tab, setTab] = useState<AdminTab>("users");

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
    { key: "users",    label: "👤 Участники"  },
    { key: "give",     label: "🎁 Выдать"     },
    { key: "features", label: "⚙️ Функции"    },
  ];

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-24">
      {/* Header */}
      <div
        className="rounded-2xl p-4 flex items-center gap-2"
        style={{ backgroundColor: "#1a0a0a", border: "1px solid #ef4444" }}
      >
        <ShieldAlert size={20} style={{ color: "#ef4444" }} />
        <div>
          <p className="font-bold text-base text-red-400">God Mode</p>
          <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
            UID: {userId} | Chat: {chatId}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div
        className="flex gap-1 rounded-xl p-1 overflow-x-auto hide-scrollbar"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        {tabs.map(({ key, label }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className="flex-none px-3 py-1.5 text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
              style={{
                backgroundColor: active ? "#ef4444" : "transparent",
                color: active ? "#fff" : "var(--text-hint)",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {tab === "users"    && <UsersSection    chatId={chatId} />}
      {tab === "give"     && <GiveSection     chatId={chatId} />}
      {tab === "features" && <FeaturesSection chatId={chatId} />}
    </div>
  );
}

/* ── Раздел участников ──────────────────────────────────────────── */
function UsersSection({ chatId }: { chatId: number }) {
  const [q, setQ] = useState("");
  const [users, setUsers] = useState<DevUserEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<DevUserEntry | null>(null);

  const [balance, setBalance] = useState("");
  const [xp, setXp]           = useState("");
  const [rank, setRank]       = useState("");
  const [saving, setSaving]   = useState(false);
  const [toast, setToast]     = useState<string | null>(null);

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
    setRank(u.rank ?? "");
  };

  const save = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const r = await devMemberUpdate(chatId, selected.user_id, parseFloat(balance), parseInt(xp), rank);
      if (r.ok) {
        showOk(r.message ?? "Сохранено");
        search();
      } else {
        showOk("⚠️ " + (r.error ?? "Ошибка"));
      }
    } catch (e: unknown) {
      showOk("⚠️ " + (e instanceof Error ? e.message : "Ошибка"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      {toast && (
        <div className="rounded-xl px-3 py-2 text-sm font-medium"
          style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--accent)" }}>
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
        />
        {loading && <Loader2 size={14} className="animate-spin" style={{ color: "var(--text-hint)" }} />}
      </div>

      {/* User list */}
      <div className="space-y-1.5 max-h-56 overflow-y-auto rounded-xl hide-scrollbar">
        {users.map((u) => (
          <button
            key={u.user_id}
            onClick={() => select(u)}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left transition-colors"
            style={{
              backgroundColor: selected?.user_id === u.user_id ? "var(--accent)" : "var(--bg-secondary)",
              color: selected?.user_id === u.user_id ? "#fff" : "var(--text-primary)",
            }}
          >
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
              style={{
                backgroundColor: selected?.user_id === u.user_id ? "rgba(255,255,255,0.25)" : "var(--bg-primary)",
              }}
            >
              {(u.name ?? "?")[0].toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{u.name ?? "—"}</p>
              <p className="text-[11px] opacity-70">🪙 {u.balance} · XP {u.xp} · {u.rank ?? "—"}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Editor */}
      {selected && (
        <div className="rounded-xl p-3 space-y-2.5" style={{ backgroundColor: "var(--bg-secondary)" }}>
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">{selected.name}</p>
            <button onClick={() => setSelected(null)}>
              <X size={14} style={{ color: "var(--text-hint)" }} />
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {/* Balance */}
            <div>
              <label className="text-[11px] font-medium" style={{ color: "var(--text-hint)" }}>
                <Coins size={10} className="inline mr-1" />Баланс
              </label>
              <input
                type="number"
                value={balance}
                onChange={(e) => setBalance(e.target.value)}
                className="w-full mt-1 rounded-lg px-2.5 py-1.5 text-sm bg-transparent outline-none"
                style={{ border: "1px solid var(--border-color)" }}
              />
            </div>
            {/* XP */}
            <div>
              <label className="text-[11px] font-medium" style={{ color: "var(--text-hint)" }}>
                <Zap size={10} className="inline mr-1" />Опыт (XP)
              </label>
              <input
                type="number"
                value={xp}
                onChange={(e) => setXp(e.target.value)}
                className="w-full mt-1 rounded-lg px-2.5 py-1.5 text-sm bg-transparent outline-none"
                style={{ border: "1px solid var(--border-color)" }}
              />
            </div>
          </div>

          {/* Rank */}
          <div>
            <label className="text-[11px] font-medium" style={{ color: "var(--text-hint)" }}>
              <Star size={10} className="inline mr-1" />Ранг
            </label>
            <div className="relative mt-1">
              <select
                value={rank}
                onChange={(e) => setRank(e.target.value)}
                className="w-full rounded-lg px-2.5 py-1.5 text-sm appearance-none outline-none"
                style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }}
              >
                {RANKS.map((r) => <option key={r} value={r}>{r || "—"}</option>)}
              </select>
              <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--text-hint)" }} />
            </div>
          </div>

          <button
            onClick={save}
            disabled={saving}
            className="w-full py-2 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-opacity disabled:opacity-50"
            style={{ backgroundColor: "#ef4444", color: "#fff" }}
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : "Сохранить изменения"}
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

  const [giveTab, setGiveTab] = useState<"mora" | "xp" | "item">("mora");
  const [amount, setAmount]   = useState("");
  const [itemName, setItemName] = useState("");
  const [rarity, setRarity]   = useState("common");
  const [busy, setBusy]       = useState(false);
  const [toast, setToast]     = useState<string | null>(null);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 3000); };

  const search = useCallback(() => {
    if (!chatId) return;
    setLoading(true);
    fetchDevUsers(chatId, q)
      .then((r) => setUsers(r.users ?? []))
      .finally(() => setLoading(false));
  }, [chatId, q]);

  useEffect(() => { search(); }, [search]);

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
        <div className="rounded-xl px-3 py-2 text-sm font-medium"
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
          placeholder="Поиск..."
          className="flex-1 bg-transparent text-sm outline-none"
        />
        {loading && <Loader2 size={14} className="animate-spin" style={{ color: "var(--text-hint)" }} />}
      </div>

      {/* User list */}
      <div className="space-y-1 max-h-44 overflow-y-auto rounded-xl hide-scrollbar">
        {users.map((u) => (
          <button
            key={u.user_id}
            onClick={() => setSelected(u)}
            className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-left text-sm transition-colors"
            style={{
              backgroundColor: selected?.user_id === u.user_id ? "var(--accent)" : "var(--bg-secondary)",
              color: selected?.user_id === u.user_id ? "#fff" : "var(--text-primary)",
            }}
          >
            <Users size={12} />
            <span className="truncate">{u.name ?? u.user_id}</span>
          </button>
        ))}
      </div>

      {/* Give form */}
      {selected && (
        <div className="rounded-xl p-3 space-y-2.5" style={{ backgroundColor: "var(--bg-secondary)" }}>
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
              placeholder={giveTab === "mora" ? "Кол-во моры (отриц. = забрать)" : "Кол-во опыта"}
              className="w-full rounded-lg px-2.5 py-1.5 text-sm bg-transparent outline-none"
              style={{ border: "1px solid var(--border-color)" }}
            />
          )}

          {giveTab === "item" && (
            <div className="space-y-1.5">
              <input
                type="text"
                value={itemName}
                onChange={(e) => setItemName(e.target.value)}
                placeholder="Название предмета"
                className="w-full rounded-lg px-2.5 py-1.5 text-sm bg-transparent outline-none"
                style={{ border: "1px solid var(--border-color)" }}
              />
              <div className="relative">
                <select
                  value={rarity}
                  onChange={(e) => setRarity(e.target.value)}
                  className="w-full rounded-lg px-2.5 py-1.5 text-sm appearance-none outline-none"
                  style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-color)", color: "var(--text-primary)" }}
                >
                  {RARITIES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
                <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--text-hint)" }} />
              </div>
            </div>
          )}

          <button
            onClick={doGive}
            disabled={busy}
            className="w-full py-2 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-opacity disabled:opacity-50"
            style={{ backgroundColor: "#ef4444", color: "#fff" }}
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : "Выдать"}
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Раздел функций ──────────────────────────────────────────────── */
function FeaturesSection({ chatId }: { chatId: number }) {
  const [states, setStates] = useState<Record<string, boolean>>({});
  const [busy, setBusy]     = useState<string | null>(null);

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

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-hint)" }}>
        Переключение функций чата
      </p>
      {FEATURE_LIST.map(({ key, label }) => {
        const on = !!states[key];
        return (
          <div
            key={key}
            className="flex items-center justify-between rounded-xl px-3 py-2.5"
            style={{ backgroundColor: "var(--bg-secondary)" }}
          >
            <div>
              <p className="text-sm font-medium">{label}</p>
              <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>{key}</p>
            </div>
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
        );
      })}
    </div>
  );
}
