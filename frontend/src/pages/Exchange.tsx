/* ──────────────────────────────────────────────────────────────
   Exchange.tsx — Биржа 2.0 (спарклайны + шторка покупки/продажи)
   GET  /api/bonds?chat_id=X
   POST /api/bonds/buy  { chat_id, bond_key, amount, wallet }
   POST /api/bonds/sell { chat_id, bond_key, amount }
   GET  /api/treasury?chat_id=X  (developer / owner / co_owner)
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import {
  TrendingUp, TrendingDown, Minus, RefreshCw, Landmark, ArrowRightLeft, Coins,
  Wallet, AlertCircle, Loader2, X, ChevronUp, ChevronDown,
} from "lucide-react";
import { fetchBonds, buyBond, sellBond, fetchTreasury, fetchMembers, treasuryPayout } from "../lib/api";
import { useToast } from "../components/ToastContext";
import type { BondsResponse, BondPrice, TreasuryResponse, ChatMember } from "../types";

interface Props {
  userId: number;
  chatId: number;
  isDev?: boolean;
  userRank?: string;
}

type ExTab = "market" | "portfolio" | "treasury";
const BOND_MAX = 50;
const fmt = (n: number) => n.toLocaleString("ru-RU");
const TREASURY_MANAGER_RANKS = new Set(["co_owner", "owner", "developer"]);

// ── Sparkline SVG ─────────────────────────────────────────────
function Sparkline({ data, color, width = 80, height = 32, timestamps, interactive }: {
  data: number[];
  color: string;
  width?: number;
  height?: number;
  timestamps?: string[];
  interactive?: boolean;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const rafRef = useRef<number | null>(null);

  if (data.length < 2) return <div style={{ width, height }} />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const px = (v: number) => ((v - min) / range) * (height - 4) + 2;
  const xi = (i: number) => (i / (data.length - 1)) * (width - 2) + 1;
  const pts = data.map((v, i) => `${xi(i)},${height - px(v)}`).join(" ");
  const fillId = `sg${color.replace(/[^a-z0-9]/gi, "")}${width}`;

  const getIdxFromX = useCallback((clientX: number): number | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const relX = clientX - rect.left;
    const pct = relX / rect.width;
    const idx = Math.round(pct * (data.length - 1));
    return Math.max(0, Math.min(data.length - 1, idx));
  }, [data.length]);

  const handleMove = useCallback((clientX: number) => {
    if (!interactive) return;
    if (rafRef.current !== null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      setHoverIdx(getIdxFromX(clientX));
    });
  }, [interactive, getIdxFromX]);
  const handleLeave = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    setHoverIdx(null);
  }, []);

  const hVal = hoverIdx !== null ? data[hoverIdx] : null;
  const hTs = hoverIdx !== null && timestamps?.[hoverIdx] ? timestamps[hoverIdx] : null;
  const hX = hoverIdx !== null ? xi(hoverIdx) : 0;
  const hY = hoverIdx !== null ? height - px(data[hoverIdx]) : 0;

  const onSvgMouseMove = useMemo(() => interactive ? (e: React.MouseEvent) => handleMove(e.clientX) : undefined, [interactive, handleMove]);
  const onSvgTouchMove = useMemo(() => interactive ? (e: React.TouchEvent) => { e.preventDefault(); handleMove(e.touches[0].clientX); } : undefined, [interactive, handleMove]);

  return (
    <div className="relative" style={{ width, height: interactive ? height + 28 : height }}>
      {interactive && hoverIdx !== null && hVal !== null && (
        <div
          className="absolute -top-1 text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded-md whitespace-nowrap pointer-events-none z-10"
          style={{
            left: Math.max(0, Math.min(width - 80, hX - 40)),
            backgroundColor: "var(--bg-secondary)",
            color,
            border: "1px solid var(--border)",
          }}
        >
          {fmt(hVal)} 🪙{hTs ? ` · ${hTs}` : ""}
        </div>
      )}
      <svg
        ref={svgRef}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        fill="none"
        style={{ marginTop: interactive ? 24 : 0, touchAction: "none" }}
        onMouseMove={onSvgMouseMove}
        onMouseLeave={interactive ? handleLeave : undefined}
        onTouchMove={onSvgTouchMove}
        onTouchEnd={interactive ? handleLeave : undefined}
      >
        <defs>
          <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={`1,${height} ${pts} ${xi(data.length - 1)},${height}`} fill={`url(#${fillId})`} />
        <polyline points={pts} stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" fill="none" />
        {interactive && hoverIdx !== null && (
          <>
            <line x1={hX} y1={0} x2={hX} y2={height} stroke={color} strokeWidth={0.75} strokeDasharray="2,2" opacity={0.6} />
            <circle cx={hX} cy={hY} r={3} fill={color} stroke="#fff" strokeWidth={1} />
          </>
        )}
      </svg>
    </div>
  );
}

// ── Trade Bottom Sheet ────────────────────────────────────────

function extractErr(e: unknown): string {
  if (!(e instanceof Error)) return "Ошибка";
  const match = e.message.match(/API \d+: (.*)/s);
  if (match) {
    try { return (JSON.parse(match[1]) as { error?: string }).error ?? match[1]; }
    catch { return match[1]; }
  }
  return e.message;
}
interface TradeSheetProps {
  bond: BondPrice;
  balance: number;
  onClose: () => void;
  onDone: () => void;
  chatId: number;
  taxCapPct: number;
}
function TradeSheet({ bond, balance, onClose, onDone, chatId, taxCapPct }: TradeSheetProps) {
  const [amount, setAmount] = useState("1");
  const [busy, setBusy]     = useState<"buy" | "sell" | null>(null);
  const { toast } = useToast();
  const showOk = useCallback((m: string) => toast(m, "success"), [toast]);
  const showErr = useCallback((m: string) => toast(m, "error"), [toast]);

  const histPrices = (bond.history ?? []).map(h => h.price);
  const histTimestamps = (bond.history ?? []).map(h => {
    try { return new Date(h.ts).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); }
    catch { return ""; }
  });
  const isUp = histPrices.length >= 2
    ? histPrices[histPrices.length - 1] >= histPrices[histPrices.length - 2]
    : true;
  const color = isUp ? "#22c55e" : "#ef4444";

  const amt     = Math.max(1, Math.min(BOND_MAX, Math.round(Number(amount)) || 1));
  const totalCost = amt * bond.current_price;
  const canBuy  = balance >= totalCost;
  const canSell = bond.amount > 0;
  const maxBuy  = Math.min(BOND_MAX - bond.amount, Math.floor(balance / bond.current_price));

  const doBuy = async () => {
    if (busy || amt <= 0 || !canBuy) return;
    setBusy("buy");
    try {
      const res = await buyBond(chatId, bond.key, amt);
      if (res.ok) {
        showOk(`✅ Куплено ${amt} шт. «${bond.name}»`);
        setTimeout(() => { onDone(); onClose(); }, 1200);
      } else {
        showErr((res as { error?: string }).error ?? "Ошибка покупки");
      }
    } catch (e) { showErr(extractErr(e)); }
    finally { setBusy(null); }
  };

  const doSell = async () => {
    if (busy || !canSell) return;
    const sellAmt = Math.min(amt, bond.amount);
    setBusy("sell");
    try {
      const res = await sellBond(chatId, bond.key, sellAmt);
      if (res.ok) {
        showOk(`💰 Продано ${sellAmt} шт. · Баланс: ${(res.new_balance ?? 0).toLocaleString("ru-RU")} 🪙`);
        setTimeout(() => { onDone(); onClose(); }, 1200);
      } else {
        showErr((res as { error?: string }).error ?? "Ошибка продажи");
      }
    } catch (e) { showErr(extractErr(e)); }
    finally { setBusy(null); }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        className="fixed bottom-0 inset-x-0 z-50 rounded-t-3xl p-5 space-y-4 animate-slideUp glass-card"
        style={{ maxHeight: "90vh", overflowY: "auto" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-lg font-bold">{bond.name}</p>
            <p className="text-sm tabular-nums font-bold" style={{ color }}>
              {fmt(bond.current_price)} 🪙
              {bond.amount > 0 && bond.pnl_pct !== 0 && (
                <span className="ml-2 text-xs">
                  ({bond.pnl_pct > 0 ? "+" : ""}{bond.pnl_pct}%)
                </span>
              )}
            </p>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl" style={{ color: "var(--text-hint)" }}>
            <X size={20} />
          </button>
        </div>

        {/* Big sparkline — interactive */}
        {histPrices.length >= 2 && (
          <div className="rounded-2xl p-3 flex items-center justify-center"
            style={{ backgroundColor: "var(--bg-primary)" }}>
            <Sparkline data={histPrices} color={color} width={280} height={80} timestamps={histTimestamps} interactive />
          </div>
        )}

        {/* Portfolio stats if holding */}
        {bond.amount > 0 && (
          <div className="rounded-xl p-3 grid grid-cols-3 gap-2 text-center"
            style={{ backgroundColor: "var(--bg-primary)" }}>
            <div>
              <p className="text-xs" style={{ color: "var(--text-hint)" }}>Кол-во</p>
              <p className="text-sm font-bold tabular-nums">{bond.amount} шт.</p>
            </div>
            <div>
              <p className="text-xs" style={{ color: "var(--text-hint)" }}>Ср. цена</p>
              <p className="text-sm font-bold tabular-nums">{fmt(bond.avg_price)} 🪙</p>
            </div>
            <div>
              <p className="text-xs" style={{ color: "var(--text-hint)" }}>PNL</p>
              <p className="text-sm font-bold tabular-nums"
                style={{ color: bond.pnl_mora >= 0 ? "#22c55e" : "#ef4444" }}>
                {bond.pnl_mora >= 0 ? "+" : ""}{fmt(bond.pnl_mora)}
              </p>
            </div>
          </div>
        )}

        {/* Amount input */}
        <div>
          <p className="text-xs font-medium mb-1.5" style={{ color: "var(--text-hint)" }}>
            Количество (макс. {BOND_MAX})
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setAmount(String(Math.max(1, amt - 1)))}
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: "var(--bg-primary)" }}>
              <ChevronDown size={16} />
            </button>
            <input
              type="number" value={amount}
              onChange={e => setAmount(e.target.value)}
              min={1} max={BOND_MAX}
              className="flex-1 text-center rounded-xl px-3 py-2 text-base font-bold outline-none"
              style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
            />
            <button
              onClick={() => setAmount(String(Math.min(BOND_MAX, amt + 1)))}
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: "var(--bg-primary)" }}>
              <ChevronUp size={16} />
            </button>
          </div>
          {/* Quick buttons */}
          <div className="flex gap-2 mt-2">
            {[1, 5, 10, 25].map(n => (
              <button key={n}
                onClick={() => setAmount(String(n))}
                className="flex-1 py-1 rounded-lg text-xs font-semibold"
                style={{ backgroundColor: amt === n ? "var(--accent)" : "var(--bg-primary)", color: amt === n ? "#fff" : "var(--text-hint)" }}>
                {n}
              </button>
            ))}
            <button
              onClick={() => {
                const target = maxBuy > 0 ? maxBuy : bond.amount;
                if (target > 0) setAmount(String(target));
              }}
              className="flex-1 py-1 rounded-lg text-xs font-semibold"
              style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-hint)" }}>
              MAX
            </button>
          </div>
        </div>

        {/* Total cost */}
        <div className="flex items-center justify-between rounded-xl p-3"
          style={{ backgroundColor: "var(--bg-primary)" }}>
          <span className="text-sm" style={{ color: "var(--text-hint)" }}>Стоимость</span>
          <span className="text-base font-bold tabular-nums">{fmt(totalCost)} 🪙</span>
        </div>

        {/* Tax info for sell */}
        {bond.amount > 0 && (
          <p className="text-xs text-center" style={{ color: "var(--text-hint)" }}>
            Прогрессивный налог на прибыль: 10–20–30–{taxCapPct}% (зависит от размера прибыли)
          </p>
        )}

        {/* Buy / Sell */}
        <div className="grid grid-cols-2 gap-3 pb-2">
          <button
            onClick={doBuy}
            disabled={!!busy || !canBuy || maxBuy <= 0}
            className="py-3 rounded-xl text-sm font-bold disabled:opacity-40 flex items-center justify-center gap-2"
            style={{ backgroundColor: "#16a34a", color: "#fff" }}>
            {busy === "buy" ? <Loader2 size={16} className="animate-spin" /> : <><TrendingUp size={16} /> Купить</>}
          </button>
          <button
            onClick={doSell}
            disabled={!!busy || !canSell}
            className="py-3 rounded-xl text-sm font-bold disabled:opacity-40 flex items-center justify-center gap-2"
            style={{ backgroundColor: "#dc2626", color: "#fff" }}>
            {busy === "sell" ? <Loader2 size={16} className="animate-spin" /> : <><TrendingDown size={16} /> Продать</>}
          </button>
        </div>
      </div>
    </>
  );
}

// ── Market card ───────────────────────────────────────────────
function BondCard({ bond, onClick }: { bond: BondPrice; onClick: () => void }) {
  const histPrices = (bond.history ?? []).map(h => h.price);
  const isFlat = histPrices.length >= 2
    && histPrices[histPrices.length - 1] === histPrices[histPrices.length - 2];
  const isUp = histPrices.length >= 2
    ? histPrices[histPrices.length - 1] > histPrices[histPrices.length - 2]
    : true;
  const color = isFlat ? "#9ca3af" : isUp ? "#22c55e" : "#ef4444";
  const pctChange = histPrices.length >= 2
    ? ((histPrices[histPrices.length - 1] - histPrices[0]) / histPrices[0] * 100)
    : 0;

  return (
    <div
      className="rounded-2xl p-4 flex items-center gap-3 cursor-pointer transition-transform active:scale-[0.98] glass-card glass-card-hover"
      onClick={onClick}
    >
      <div className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0"
        style={{ backgroundColor: `${color}22` }}>
        {isFlat ? <Minus size={20} color={color} />
          : isUp ? <TrendingUp size={20} color={color} />
          : <TrendingDown size={20} color={color} />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold truncate">{bond.name}</p>
        <p className="text-base font-bold tabular-nums" style={{ color }}>
          {fmt(bond.current_price)} 🪙
        </p>
        {Math.abs(pctChange) > 0.1 && (
          <p className="text-[11px] font-medium tabular-nums" style={{ color }}>
            {pctChange >= 0 ? "+" : ""}{pctChange.toFixed(1)}% за период
          </p>
        )}
      </div>
      {histPrices.length >= 2 && (
        <Sparkline data={histPrices} color={color} width={72} height={36} />
      )}
      {bond.amount > 0 && (
        <div className="shrink-0 text-right">
          <div className="px-2 py-0.5 rounded-lg text-[11px] font-bold"
            style={{ backgroundColor: "var(--accent)", color: "#fff" }}>
            {bond.amount} шт.
          </div>
          {bond.pnl_mora !== 0 && (
            <p className="text-[10px] font-bold tabular-nums mt-0.5"
              style={{ color: bond.pnl_mora >= 0 ? "#22c55e" : "#ef4444" }}>
              {bond.pnl_mora >= 0 ? "+" : ""}{fmt(bond.pnl_mora)} 🪙
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Portfolio tab ─────────────────────────────────────────────
function PortfolioTab({ bonds, onOpenTrade }: { bonds: BondPrice[]; onOpenTrade: (b: BondPrice) => void }) {
  const heldBonds = bonds.filter(b => b.amount > 0);
  if (heldBonds.length === 0) {
    return (
      <div className="rounded-2xl p-8 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <Wallet size={40} strokeWidth={1.2} className="mx-auto mb-3" style={{ color: "var(--text-hint)" }} />
        <p className="font-semibold">Портфель пуст</p>
        <p className="text-sm mt-1" style={{ color: "var(--text-hint)" }}>
          Перейдите на вкладку Рынок, чтобы купить облигации
        </p>
      </div>
    );
  }

  const totalValue    = heldBonds.reduce((s, b) => s + b.value, 0);
  const totalInvested = heldBonds.reduce((s, b) => s + b.invested, 0);
  const totalPnl      = totalValue - totalInvested;
  const totalPnlPct   = totalInvested > 0 ? (totalPnl / totalInvested * 100) : 0;
  const summaryColor  = totalPnl >= 0 ? "#22c55e" : "#ef4444";

  return (
    <div className="space-y-3">
      {/* Summary */}
      <div className="rounded-2xl p-4 grid grid-cols-3 gap-3 text-center"
        style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
        <div>
          <p className="text-xs mb-1" style={{ color: "var(--text-hint)" }}>Стоимость</p>
          <p className="text-sm font-bold tabular-nums">{fmt(totalValue)} 🪙</p>
        </div>
        <div>
          <p className="text-xs mb-1" style={{ color: "var(--text-hint)" }}>Вложено</p>
          <p className="text-sm font-bold tabular-nums">{fmt(totalInvested)} 🪙</p>
        </div>
        <div>
          <p className="text-xs mb-1" style={{ color: "var(--text-hint)" }}>PNL</p>
          <p className="text-sm font-bold tabular-nums" style={{ color: summaryColor }}>
            {totalPnl >= 0 ? "+" : ""}{fmt(totalPnl)}
          </p>
          <p className="text-[11px] tabular-nums" style={{ color: summaryColor }}>
            {totalPnlPct >= 0 ? "+" : ""}{totalPnlPct.toFixed(1)}%
          </p>
        </div>
      </div>

      {heldBonds.map(b => {
        const pnlColor = b.pnl_mora >= 0 ? "#22c55e" : "#ef4444";
        const histPrices = (b.history ?? []).map(h => h.price);
        return (
          <div key={b.key}
            className="rounded-2xl p-4 flex items-center gap-3 cursor-pointer active:scale-[0.98] transition-transform"
            style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
            onClick={() => onOpenTrade(b)}>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold">{b.name}</p>
              <p className="text-xs mt-0.5 tabular-nums" style={{ color: "var(--text-hint)" }}>
                {b.amount} шт. · ср. {fmt(b.avg_price)} · тек. {fmt(b.current_price)} 🪙
              </p>
            </div>
            {histPrices.length >= 2 && (
              <Sparkline data={histPrices} color={pnlColor} width={60} height={30} />
            )}
            <div className="text-right shrink-0">
              <p className="text-sm font-bold tabular-nums">{fmt(b.value)} 🪙</p>
              <p className="text-xs tabular-nums font-semibold" style={{ color: pnlColor }}>
                {b.pnl_mora >= 0 ? "+" : ""}{fmt(b.pnl_mora)}
                {" "}({b.pnl_pct >= 0 ? "+" : ""}{b.pnl_pct}%)
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────
export default function Exchange({ chatId, isDev, userRank }: Props) {
  const [data, setData]         = useState<BondsResponse | null>(null);
  const [treasury, setTreasury] = useState<TreasuryResponse | null>(null);
  const [error, setError]       = useState("");
  const [tab, setTab]           = useState<ExTab>("market");
  const [selected, setSelected] = useState<BondPrice | null>(null);
  const loadRef = useRef(0);
  const canManageTreasury = isDev || TREASURY_MANAGER_RANKS.has(userRank ?? "user");

  const load = useCallback(() => {
    if (!chatId) return;
    setError("");
    const seq = ++loadRef.current;
    fetchBonds(chatId)
      .then(d => { if (loadRef.current === seq) setData(d); })
      .catch((e: Error) => { if (loadRef.current === seq) setError(e.message); });
  }, [chatId]);

  const loadTreasury = useCallback(() => {
    if (!chatId) return;
    fetchTreasury(chatId).then(setTreasury).catch(() => {});
  }, [chatId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === "treasury") loadTreasury(); }, [tab, loadTreasury]);

  if (!chatId) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 p-6 text-center">
        <TrendingUp size={48} strokeWidth={1.2} style={{ color: "var(--text-hint)" }} />
        <p className="font-semibold">Нет контекста чата</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center">
        <AlertCircle size={32} className="mx-auto mb-2" style={{ color: "#ef4444" }} />
        <p className="font-medium">Ошибка загрузки биржи</p>
        <p className="text-sm mt-1 mb-3 break-all" style={{ color: "var(--text-hint)" }}>{error}</p>
        <button onClick={load} className="text-sm underline" style={{ color: "var(--accent)" }}>
          Повторить
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 space-y-3 animate-pulse">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton h-20 rounded-2xl" />
        ))}
      </div>
    );
  }

  const trend = data.market_trend ?? "neutral";
  const trendColor = trend === "bull" ? "#22c55e" : trend === "bear" ? "#ef4444" : "#9ca3af";
  const trendLabel = trend === "bull" ? "📈 Бычий рынок" : trend === "bear" ? "📉 Медвежий рынок" : "➡️ Нейтральный рынок";

  const tabs: { key: ExTab; label: string }[] = [
    { key: "market",    label: "📈 Рынок" },
    { key: "portfolio", label: "💼 Портфель" },
    ...(canManageTreasury ? [{ key: "treasury" as ExTab, label: "🏛 Казна" }] : []),
  ];

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-24">

      {/* Header */}
      <div className="glass-hero p-4 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "var(--accent-soft)" }}>
              <TrendingUp size={18} style={{ color: "var(--accent)" }} />
            </div>
            <span className="font-bold">Биржа</span>
          </div>
          <p className="text-[11px] mt-0.5 font-medium" style={{ color: trendColor }}>
            {trendLabel}
            {(data.market_ticks ?? 0) > 0 && ` · ${data.market_ticks} тика`}
          </p>
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
          <button onClick={load} className="p-2 rounded-xl"
            style={{ color: "var(--text-hint)", backgroundColor: "var(--bg-primary)" }}>
            <RefreshCw size={15} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="glass-card tab-scroll flex gap-1 rounded-xl p-1 overflow-x-auto">
        {tabs.map(({ key, label }) => {
          const active = tab === key;
          return (
            <button key={key} onClick={() => setTab(key)}
              className="flex-none px-3 py-1.5 text-sm font-semibold rounded-lg transition-all whitespace-nowrap"
              style={{
                backgroundColor: active ? "var(--accent)" : "transparent",
                color: active ? "#fff" : "var(--text-hint)",
                boxShadow: active ? "0 0 12px var(--accent-glow)" : "none",
              }}>
              {label}
            </button>
          );
        })}
      </div>

      {/* Market */}
      {tab === "market" && (
        <div className="space-y-2">
          {data.bonds.length === 0 ? (
            <div className="rounded-2xl p-6 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
              <p className="text-sm" style={{ color: "var(--text-hint)" }}>Нет активных облигаций</p>
            </div>
          ) : (
            data.bonds.map(b => (
              <BondCard key={b.key} bond={b} onClick={() => setSelected(b)} />
            ))
          )}
        </div>
      )}

      {/* Portfolio */}
      {tab === "portfolio" && (
        <PortfolioTab bonds={data.bonds} onOpenTrade={setSelected} />
      )}

      {/* Treasury */}
      {tab === "treasury" && (
        <TreasuryPanel treasury={treasury} onLoad={loadTreasury} chatId={chatId} canManageTreasury={canManageTreasury} />
      )}

      {/* Trade bottom sheet */}
      {selected && (
        <TradeSheet
          bond={selected}
          balance={data.balance}
          chatId={chatId}
          taxCapPct={data.bond_tax_cap_pct ?? 40}
          onClose={() => setSelected(null)}
          onDone={() => { load(); setSelected(null); }}
        />
      )}
    </div>
  );
}

// ── Treasury panel ────────────────────────────────────────────
function TreasuryPanel({
  treasury,
  onLoad,
  chatId,
  canManageTreasury,
}: {
  treasury: TreasuryResponse | null;
  onLoad: () => void;
  chatId: number;
  canManageTreasury: boolean;
}) {
  const [members, setMembers] = useState<ChatMember[]>([]);
  const [targetId, setTargetId] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!canManageTreasury || !chatId) return;
    fetchMembers(chatId)
      .then((res) => setMembers(res.members ?? []))
      .catch(() => setMembers([]));
  }, [chatId, canManageTreasury]);

  const doPayout = useCallback(async () => {
    const parsedTarget = parseInt(targetId, 10);
    const parsedAmount = parseInt(amount, 10);
    if (busy || !parsedTarget || !parsedAmount) return;

    setBusy(true);
    try {
      const res = await treasuryPayout(chatId, parsedTarget, parsedAmount, reason.trim() || "Выплата");
      if (res.ok) {
        setNotice(`✅ Выплачено. Новый баланс казны: ${fmt(res.new_balance ?? 0)} 🪙`);
        setTargetId("");
        setAmount("");
        setReason("");
        onLoad();
      } else {
        setNotice(`⚠️ ${res.error ?? "Ошибка выплаты"}`);
      }
    } catch (error) {
      setNotice(`⚠️ ${error instanceof Error ? error.message : "Ошибка выплаты"}`);
    } finally {
      setBusy(false);
    }
  }, [amount, busy, chatId, onLoad, reason, targetId]);

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
      <div className="rounded-2xl p-6 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <Landmark size={32} strokeWidth={1.2} className="mx-auto mb-2" style={{ color: "var(--text-hint)" }} />
        <p className="text-sm font-medium">Доступ ограничен</p>
        <p className="text-xs mt-1 mb-3" style={{ color: "var(--text-hint)" }}>
          Казна доступна только совладельцу, владельцу или разработчику
        </p>
        <button onClick={onLoad} className="text-xs underline" style={{ color: "var(--accent)" }}>
          Попробовать снова
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {notice && (
        <div className="rounded-2xl px-4 py-3 text-sm font-semibold animate-fadeIn"
          style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border-accent)" }}>
          {notice}
        </div>
      )}

      <div className="rounded-2xl p-5 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <Landmark size={28} className="mx-auto mb-2" style={{ color: "var(--accent)" }} />
        <p className="text-3xl font-bold tabular-nums">{fmt(treasury.balance)} 🪙</p>
        <p className="text-xs mt-1" style={{ color: "var(--text-hint)" }}>Баланс казны</p>
        {treasury.total_collected != null && (
          <p className="text-[11px] mt-1" style={{ color: "var(--text-hint)" }}>
            Всего собрано: {fmt(treasury.total_collected)} 🪙
          </p>
        )}
      </div>

      {canManageTreasury && (
        <div className="rounded-2xl p-4 space-y-3" style={{ backgroundColor: "var(--bg-secondary)" }}>
          <div className="flex items-center gap-2">
            <ArrowRightLeft size={16} style={{ color: "#ef4444" }} />
            <p className="text-sm font-semibold">Выплата из казны</p>
          </div>

          <div className="space-y-1.5">
            <label className="text-[11px] font-medium" style={{ color: "var(--text-hint)" }}>Получатель</label>
            <select
              value={targetId}
              onChange={(event) => setTargetId(event.target.value)}
              className="w-full rounded-xl px-3 py-2 text-sm outline-none appearance-none"
              style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
            >
              <option value="">Выберите...</option>
              {members.map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {member.name} (#{member.user_id})
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <div className="space-y-1.5">
              <label className="text-[11px] font-medium flex items-center gap-1" style={{ color: "var(--text-hint)" }}>
                <Coins size={12} /> Сумма
              </label>
              <input
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                type="number"
                inputMode="numeric"
                className="w-full rounded-xl px-3 py-2 text-sm outline-none"
                placeholder="0"
                style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-[11px] font-medium" style={{ color: "var(--text-hint)" }}>Причина</label>
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                className="w-full rounded-xl px-3 py-2 text-sm outline-none"
                placeholder="Причина выплаты"
                style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              />
            </div>
          </div>

          <button
            onClick={() => { void doPayout(); }}
            disabled={busy || !targetId || !amount}
            className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-opacity disabled:opacity-50"
            style={{ backgroundColor: "#ef4444", color: "#fff" }}
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : "💸 Выплатить"}
          </button>
        </div>
      )}

      {(treasury.recent ?? []).length > 0 && (
        <div className="rounded-2xl p-4" style={{ backgroundColor: "var(--bg-secondary)" }}>
          <p className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: "var(--text-hint)" }}>
            Последние операции
          </p>
          <div className="space-y-2">
            {treasury.recent!.map((entry, idx) => (
              <div key={idx} className="flex items-center justify-between gap-2 rounded-xl px-3 py-2"
                style={{ backgroundColor: "var(--bg-primary)" }}>
                <p className="text-xs truncate flex-1">{entry.description}</p>
                <p className="text-xs font-bold tabular-nums shrink-0"
                  style={{ color: entry.amount >= 0 ? "#22c55e" : "#ef4444" }}>
                  {entry.amount >= 0 ? "+" : ""}{fmt(entry.amount)} 🪙
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
