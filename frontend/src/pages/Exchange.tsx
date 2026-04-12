/* ──────────────────────────────────────────────────────────────
   Exchange.tsx — Биржа (облигации) + Казна
   GET /api/bonds?chat_id=X
   POST /api/bonds/buy  { chat_id, bond_key, amount, wallet }
   POST /api/bonds/sell { chat_id, bond_key, amount }
   GET /api/treasury?chat_id=X  (только admin/dev)
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import {
  TrendingUp, TrendingDown, Minus, RefreshCw, Landmark,
  ArrowUpCircle, ArrowDownCircle, Wallet, AlertCircle, Loader2,
} from "lucide-react";
import { fetchBonds, buyBond, sellBond, fetchTreasury } from "../lib/api";
import type { BondsResponse, BondPrice, UserBond, TreasuryResponse } from "../types";

interface Props {
  userId: number;
  chatId: number;
  isDev?: boolean;
}

type ExTab = "market" | "portfolio" | "treasury";

const fmt = (n: number) => n.toLocaleString("ru-RU");

export default function Exchange({ chatId, isDev }: Props) {
  const [data, setData]         = useState<BondsResponse | null>(null);
  const [treasury, setTreasury] = useState<TreasuryResponse | null>(null);
  const [error, setError]       = useState("");
  const [tab, setTab]           = useState<ExTab>("market");
  const [busy, setBusy]         = useState<string | null>(null);
  const [toast, setToast]       = useState<string | null>(null);
  const [toastErr, setToastErr] = useState<string | null>(null);

  const showOk  = useCallback((m: string) => { setToast(m);    setTimeout(() => setToast(null), 3500); }, []);
  const showErr = useCallback((m: string) => { setToastErr(m); setTimeout(() => setToastErr(null), 4000); }, []);

  const load = useCallback(() => {
    if (!chatId) return;
    setError("");
    fetchBonds(chatId).then(setData).catch((e: Error) => setError(e.message));
  }, [chatId]);

  const loadTreasury = useCallback(() => {
    if (!chatId) return;
    fetchTreasury(chatId).then(setTreasury).catch(() => { /* not accessible */ });
  }, [chatId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (tab === "treasury") loadTreasury();
  }, [tab, loadTreasury]);

  if (!chatId) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 p-6 text-center">
        <TrendingUp size={48} strokeWidth={1.2} style={{ color: "var(--text-hint)" }} />
        <div>
          <p className="font-semibold">Нет контекста чата</p>
          <p className="text-sm mt-1" style={{ color: "var(--text-hint)" }}>
            Откройте Mini App из чата группы.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <AlertCircle size={32} className="mx-auto mb-2" />
        <p className="font-medium">Ошибка загрузки биржи</p>
        <p className="text-sm mt-1 break-all">{error}</p>
        <button onClick={load} className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}>
          Повторить
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 space-y-3 animate-pulse">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton h-20 rounded-xl" />
        ))}
      </div>
    );
  }

  const tabs: { key: ExTab; label: string }[] = [
    { key: "market",    label: "📈 Рынок" },
    { key: "portfolio", label: "💼 Портфель" },
    ...(isDev || treasury ? [{ key: "treasury" as ExTab, label: "🏛 Казна" }] : []),
  ];

  const doBuy = async (bond: BondPrice) => {
    if (busy) return;
    const amtStr = window.prompt(`Купить облигацию «${bond.name}»\nЦена: ${fmt(bond.current_price)} 🪙/шт.\nКоличество:`);
    const amt = parseInt(amtStr ?? "", 10);
    if (!amt || amt <= 0) return;
    setBusy(bond.key + ":buy");
    try {
      const res = await buyBond(chatId, bond.key, amt);
      if (res.ok) {
        showOk(`Куплено ${amt} шт. «${bond.name}». Баланс: ${fmt(res.new_balance ?? 0)} 🪙`);
        load();
      } else {
        showErr(res.error ?? "Ошибка покупки");
      }
    } catch (e: unknown) {
      showErr(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(null);
    }
  };

  const doSell = async (holding: UserBond) => {
    if (busy) return;
    const amtStr = window.prompt(
      `Продать облигацию «${holding.bond_key}»\nУ вас: ${holding.amount} шт.\nКоличество:`,
    );
    const amt = parseInt(amtStr ?? "", 10);
    if (!amt || amt <= 0) return;
    setBusy(holding.bond_key + ":sell");
    try {
      const res = await sellBond(chatId, holding.bond_key, amt);
      if (res.ok) {
        showOk(`Продано ${amt} шт. Баланс: ${fmt(res.new_balance ?? 0)} 🪙`);
        load();
      } else {
        showErr(res.error ?? "Ошибка продажи");
      }
    } catch (e: unknown) {
      showErr(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-24">

      {/* ── Заголовок ── */}
      <div
        className="rounded-2xl p-4 flex items-center justify-between"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        <div className="flex items-center gap-2">
          <TrendingUp size={20} style={{ color: "var(--accent)" }} />
          <span className="font-bold text-base">Биржа</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-base font-bold tabular-nums">{fmt(data.balance)} 🪙</p>
            {(data.family_balance ?? 0) > 0 && (
              <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                Семья: {fmt(data.family_balance!)} 🪙
              </p>
            )}
          </div>
          <button onClick={load} style={{ color: "var(--text-hint)" }}>
            <RefreshCw size={15} />
          </button>
        </div>
      </div>

      {/* ── Вкладки ── */}
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
                backgroundColor: active ? "var(--accent)" : "transparent",
                color: active ? "#fff" : "var(--text-hint)",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* ── Рынок ── */}
      {tab === "market" && (
        <BondMarket bonds={data.bonds} busy={busy} onBuy={doBuy} />
      )}

      {/* ── Портфель ── */}
      {tab === "portfolio" && (
        <Portfolio holdings={data.holdings} busy={busy} onSell={doSell} />
      )}

      {/* ── Казна ── */}
      {tab === "treasury" && (
        <TreasuryPanel treasury={treasury} onLoad={loadTreasury} />
      )}

      {/* ── Тосты ── */}
      {toast && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-[90vw] px-4 py-2.5 rounded-xl text-sm font-medium shadow-lg pointer-events-none"
          style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--accent)" }}>
          {toast}
        </div>
      )}
      {toastErr && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-[90vw] px-4 py-2.5 rounded-xl text-sm font-medium shadow-lg pointer-events-none"
          style={{ backgroundColor: "#450a0a", color: "#fca5a5", border: "1px solid #ef4444" }}>
          {toastErr}
        </div>
      )}
    </div>
  );
}

/* ── Список облигаций на рынке ────────────────────────────────── */
function BondMarket({
  bonds, busy, onBuy,
}: {
  bonds: BondPrice[];
  busy: string | null;
  onBuy: (bond: BondPrice) => void;
}) {
  if (bonds.length === 0) {
    return (
      <div className="rounded-xl p-6 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <p className="text-sm" style={{ color: "var(--text-hint)" }}>Нет активных облигаций</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {bonds.map((b) => {
        const trend = b.prev_price == null
          ? null
          : b.current_price > b.prev_price
          ? "up"
          : b.current_price < b.prev_price
          ? "down"
          : "flat";

        return (
          <div
            key={b.key}
            className="rounded-xl p-3 flex items-center justify-between gap-3"
            style={{ backgroundColor: "var(--bg-secondary)" }}
          >
            <div className="flex items-center gap-3 min-w-0 flex-1">
              {/* Trend icon */}
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                style={{
                  backgroundColor:
                    trend === "up" ? "#14532d" : trend === "down" ? "#450a0a" : "var(--bg-primary)",
                }}
              >
                {trend === "up"   && <TrendingUp   size={18} style={{ color: "#22c55e" }} />}
                {trend === "down" && <TrendingDown size={18} style={{ color: "#ef4444" }} />}
                {(trend === "flat" || trend === null) && (
                  <Minus size={18} style={{ color: "var(--text-hint)" }} />
                )}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold truncate">{b.name ?? b.key}</p>
                {b.description && (
                  <p className="text-[11px] truncate" style={{ color: "var(--text-hint)" }}>
                    {b.description}
                  </p>
                )}
                <p className="text-xs tabular-nums font-bold mt-0.5" style={{ color: "var(--accent)" }}>
                  {fmt(b.current_price)} 🪙/шт.
                  {trend === "up" && (
                    <span style={{ color: "#22c55e" }}> ↑</span>
                  )}
                  {trend === "down" && (
                    <span style={{ color: "#ef4444" }}> ↓</span>
                  )}
                </p>
              </div>
            </div>
            <button
              onClick={() => onBuy(b)}
              disabled={!!busy}
              className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-40"
              style={{ backgroundColor: "#22c55e", color: "#fff" }}
            >
              {busy === b.key + ":buy"
                ? <Loader2 size={12} className="animate-spin" />
                : <><ArrowUpCircle size={12} /> Купить</>}
            </button>
          </div>
        );
      })}
    </div>
  );
}

/* ── Портфель пользователя ────────────────────────────────────── */
function Portfolio({
  holdings, busy, onSell,
}: {
  holdings: UserBond[];
  busy: string | null;
  onSell: (h: UserBond) => void;
}) {
  if (holdings.length === 0) {
    return (
      <div className="rounded-xl p-6 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <Wallet size={32} strokeWidth={1.2} className="mx-auto mb-2" style={{ color: "var(--text-hint)" }} />
        <p className="text-sm" style={{ color: "var(--text-hint)" }}>У вас нет облигаций</p>
        <p className="text-xs mt-1" style={{ color: "var(--text-hint)" }}>
          Перейдите на вкладку «Рынок» чтобы купить
        </p>
      </div>
    );
  }

  const totalValue = holdings.reduce((s, h) => s + h.total_value, 0);

  return (
    <div className="space-y-2">
      {/* Итого */}
      <div
        className="rounded-xl p-3 flex items-center justify-between"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        <span className="text-sm font-medium" style={{ color: "var(--text-hint)" }}>Итого портфель</span>
        <span className="text-base font-bold tabular-nums">{fmt(totalValue)} 🪙</span>
      </div>

      {holdings.map((h) => (
        <div
          key={h.bond_key}
          className="rounded-xl p-3 flex items-center justify-between gap-3"
          style={{ backgroundColor: "var(--bg-secondary)" }}
        >
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold truncate">{h.bond_key}</p>
            <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
              {h.amount} шт. × {fmt(h.current_price)} 🪙
            </p>
            <p className="text-xs font-bold mt-0.5" style={{ color: "var(--accent)" }}>
              = {fmt(h.total_value)} 🪙
            </p>
          </div>
          <button
            onClick={() => onSell(h)}
            disabled={!!busy}
            className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-40"
            style={{ backgroundColor: "#ef4444", color: "#fff" }}
          >
            {busy === h.bond_key + ":sell"
              ? <Loader2 size={12} className="animate-spin" />
              : <><ArrowDownCircle size={12} /> Продать</>}
          </button>
        </div>
      ))}
    </div>
  );
}

/* ── Казна ──────────────────────────────────────────────────────── */
function TreasuryPanel({
  treasury, onLoad,
}: {
  treasury: TreasuryResponse | null;
  onLoad: () => void;
}) {
  if (!treasury) {
    return (
      <div className="space-y-3 animate-pulse">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="skeleton h-16 rounded-xl" />
        ))}
      </div>
    );
  }

  if (treasury.error) {
    return (
      <div className="rounded-xl p-4 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <Landmark size={28} strokeWidth={1.2} className="mx-auto mb-2" style={{ color: "var(--text-hint)" }} />
        <p className="text-sm font-medium">Доступ ограничен</p>
        <p className="text-xs mt-1" style={{ color: "var(--text-hint)" }}>
          Только администраторы чата могут просматривать казну
        </p>
        <button onClick={onLoad} className="mt-3 text-xs underline" style={{ color: "var(--accent)" }}>
          Попробовать снова
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Баланс */}
      <div
        className="rounded-xl p-4 text-center"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        <Landmark size={24} className="mx-auto mb-1" style={{ color: "var(--accent)" }} />
        <p className="text-2xl font-bold tabular-nums">{fmt(treasury.balance)} 🪙</p>
        <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>Баланс казны</p>
        {treasury.total_collected != null && (
          <p className="text-[11px] mt-1" style={{ color: "var(--text-hint)" }}>
            Всего собрано: {fmt(treasury.total_collected)} 🪙
          </p>
        )}
      </div>

      {/* История транзакций */}
      {(treasury.recent ?? []).length > 0 && (
        <div
          className="rounded-xl p-3 space-y-1.5"
          style={{ backgroundColor: "var(--bg-secondary)" }}
        >
          <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-hint)" }}>
            Последние операции
          </p>
          {treasury.recent!.map((entry, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between gap-2 rounded-lg px-2.5 py-1.5"
              style={{ backgroundColor: "var(--bg-primary)" }}
            >
              <p className="text-xs truncate flex-1">{entry.description}</p>
              <p
                className="text-xs font-bold tabular-nums shrink-0"
                style={{ color: entry.amount >= 0 ? "#22c55e" : "#ef4444" }}
              >
                {entry.amount >= 0 ? "+" : ""}{fmt(entry.amount)} 🪙
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
