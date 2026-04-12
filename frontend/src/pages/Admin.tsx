/* ──────────────────────────────────────────────────────────────
   Admin.tsx — God Mode Panel v2
   Иерархия: User < Moderator < Jr.Admin < Admin < Sr.Admin < Co-owner < Owner < Developer
   Кросс-чат: переключение chat_id для управления любым чатом
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import {
  ShieldAlert, Search, ChevronDown, X, Loader2,
  Coins, Star, Users, Zap, ToggleLeft, ToggleRight,
  Crown, Gem, Hash,
} from "lucide-react";
import {
  fetchDevUsers, devMemberUpdate, devAddMora, devAddXp,
  devGiveItem, devFeatureToggle,
} from "../lib/api";
import type { DevUserEntry } from "../types";

interface Props {
  userId: number;
  chatId: number;
  isDev?: boolean;
}

type AdminTab = "users" | "give" | "features";

/* ── Жёсткая иерархия рангов ── */
const RANK_HIERARCHY = [
  { key: "user",         label: "User",         color: "var(--text-hint)", level: 0 },
  { key: "moderator",    label: "Moderator",    color: "#2ed573", level: 1 },
  { key: "jr_admin",     label: "Junior Admin", color: "#3b82f6", level: 2 },
  { key: "admin",        label: "Admin",        color: "#ffa502", level: 3 },
  { key: "sr_admin",     label: "Senior Admin", color: "#e84393", level: 4 },
  { key: "co_owner",     label: "Co-owner",     color: "#a855f7", level: 5 },
  { key: "owner",        label: "Owner",        color: "#f59e0b", level: 6 },
  { key: "developer",    label: "Developer",    color: "#ef4444", level: 7 },
];

const FEATURE_LIST = [
  { key: "feat_exchange",  label: "Биржа",     desc: "Облигации и торговля" },
  { key: "feat_gacha",     label: "Гача",      desc: "Система призыва" },
  { key: "feat_website",   label: "Сайт",      desc: "Ссылка на сайт" },
  { key: "feat_miniapp",   label: "Mini App",  desc: "Telegram Mini App" },
  { key: "feat_boss",      label: "Боссы",     desc: "Мировые боссы" },
  { key: "feat_casino",    label: "Казино",    desc: "Дуэли и лотерея" },
  { key: "feat_shop",      label: "Магазин",   desc: "Покупки за мору" },
  { key: "feat_bank",      label: "Банк",      desc: "Вклады и проценты" },
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
  const [activeChatId, setActiveChatId] = useState(defaultChatId);
  const [chatIdInput, setChatIdInput]   = useState(String(defaultChatId));

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

  const handleChatSwitch = () => {
    const val = parseInt(chatIdInput, 10);
    if (val && val !== 0) setActiveChatId(val);
  };

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-24">
      {/* Header */}
      <div
        className="rounded-2xl p-4"
        style={{ backgroundColor: "#1a0a0a", border: "1px solid #ef444466" }}
      >
        <div className="flex items-center gap-2 mb-2">
          <ShieldAlert size={20} style={{ color: "#ef4444" }} />
          <div>
            <p className="font-bold text-base" style={{ color: "#ef4444" }}>God Mode</p>
            <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
              UID: {userId} · Developer Immunity
            </p>
          </div>
          <Crown size={16} style={{ color: "#f59e0b" }} className="ml-auto" />
        </div>

        {/* Кросс-чат селектор */}
        <div className="flex gap-2 mt-2">
          <div className="flex items-center gap-1.5 flex-1 rounded-lg px-2.5 py-1.5"
            style={{ backgroundColor: "#0a0505", border: "1px solid #ef444433" }}>
            <Hash size={12} style={{ color: "#ef4444" }} />
            <input
              type="number"
              value={chatIdInput}
              onChange={e => setChatIdInput(e.target.value)}
              className="flex-1 bg-transparent text-sm outline-none tabular-nums"
              placeholder="Chat ID"
              style={{ color: "var(--text-primary)" }}
            />
          </div>
          <button
            onClick={handleChatSwitch}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold shrink-0"
            style={{ backgroundColor: "#ef4444", color: "#fff" }}
          >
            Перейти
          </button>
        </div>
        <p className="text-[10px] mt-1.5 tabular-nums" style={{ color: "#ef444488" }}>
          Активный чат: {activeChatId}
        </p>
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

      {tab === "users"    && <UsersSection    chatId={activeChatId} />}
      {tab === "give"     && <GiveSection     chatId={activeChatId} />}
      {tab === "features" && <FeaturesSection chatId={activeChatId} />}
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

  const [balance, setBalance]   = useState("");
  const [xp, setXp]             = useState("");
  const [rank, setRank]         = useState("");
  const [crystals, setCrystals] = useState("");
  const [saving, setSaving]     = useState(false);
  const [toast, setToast]       = useState<string | null>(null);

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
    setCrystals("0");
  };

  const save = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const r = await devMemberUpdate(chatId, selected.user_id, parseFloat(balance), parseInt(xp), rank);
      if (r.ok) {
        showOk("✅ " + (r.message ?? "Сохранено"));
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
        <div className="rounded-xl px-3 py-2 text-sm font-medium animate-fadeIn"
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
                  🪙{u.balance} · Ур.{u.level ?? "?"} · XP:{u.xp}
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
            <InputField icon={<Gem size={10} />} label="Кристаллы (±)" value={crystals} onChange={setCrystals} type="number" />
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
            className="flex items-center justify-between rounded-xl px-3 py-2.5"
            style={{ backgroundColor: "var(--bg-secondary)" }}
          >
            <div>
              <p className="text-sm font-medium">{label}</p>
              <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>{desc}</p>
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
