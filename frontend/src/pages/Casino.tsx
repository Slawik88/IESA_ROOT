/* ──────────────────────────────────────────────────────────────
   Casino.tsx — Казино (Монетка, Рулетка, Лотерея)
   POST /api/casino/coin      { chat_id, amount }
   POST /api/casino/roulette  { chat_id, bet_type, amount }
   GET  /api/casino/lottery?chat_id=X
   POST /api/casino/lottery   { chat_id }
   ────────────────────────────────────────────────────────────── */
import { useState, useCallback, useEffect } from "react";
import { Coins, CircleDot, Ticket, AlertCircle, Wallet } from "lucide-react";
import {
  casinoCoinFlip,
  casinoRoulette,
  fetchLotteryStatus,
  buyLotteryTicket,
  trackEvent,
  fetchUserData,
} from "../lib/api";
import type { CoinFlipResult, RouletteResult, LotteryStatusResult } from "../types";
import { useToast } from "../components/ToastContext";

// ── Constants ─────────────────────────────────────────────────
const ROULETTE_MIN = 10;
const ROULETTE_MAX = 500;
const COIN_MAX     = 50_000;

// Roulette colour for each number 0-36
const RED_NUMS = new Set([1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]);
function wheelColor(n: number): "red" | "black" | "green" {
  if (n === 0) return "green";
  return RED_NUMS.has(n) ? "red" : "black";
}
const WHEEL_DOT: Record<string, string> = {
  red:   "#ef4444",
  black: "#1f2937",
  green: "#22c55e",
};

// Bet type groups
type BetKey = "red" | "black" | "even" | "odd" | "low" | "high";

const SIMPLE_BETS: { key: BetKey; label: string; payout: string }[] = [
  { key: "red",   label: "🔴 Красное", payout: "до ×1.8" },
  { key: "black", label: "⚫ Чёрное",  payout: "до ×1.8" },
  { key: "even",  label: "Чётное",     payout: "до ×1.8" },
  { key: "odd",   label: "Нечётное",   payout: "до ×1.8" },
  { key: "low",   label: "1–18",       payout: "до ×1.8" },
  { key: "high",  label: "19–36",      payout: "до ×1.8" },
];

// ── Sub-tab type ───────────────────────────────────────────────
type SubTab = "coin" | "roulette" | "lottery";

interface Props {
  userId: number;
  chatId: number;
}

// ── Helper: extract error message from API error ──────────────
function extractErr(e: unknown): string {
  if (!(e instanceof Error)) return "Ошибка";
  const m = e.message;
  const match = m.match(/API \d+: (.*)/s);
  if (match) {
    try { return (JSON.parse(match[1]) as { error?: string }).error ?? match[1]; }
    catch { return match[1]; }
  }
  return m;
}

// ── Section card ──────────────────────────────────────────────
function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="glass-card p-4 mb-4 animate-fadeIn">
      {children}
    </div>
  );
}

// ── Numeric input ─────────────────────────────────────────────
function NumInput({
  label, value, onChange, min, max, placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  min?: number;
  max?: number;
  placeholder?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium" style={{ color: "var(--text-hint)" }}>{label}</label>
      <input
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        className="input-field w-full px-3 py-2 text-sm"
      />
    </div>
  );
}

// ════════════════════════════════════════════
//  COIN FLIP SECTION
// ════════════════════════════════════════════
function CoinSection({ chatId, balance }: { chatId: number; balance: number | null }) {
  const { toast } = useToast();
  const showToast = useCallback((t: string) => toast(t, "info"), [toast]);
  const [amount, setAmount]   = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState<CoinFlipResult | null>(null);

  const handleFlip = useCallback(async () => {
    const amt = parseInt(amount, 10);
    if (!amt || amt <= 0) { showToast("Введи сумму ставки"); return; }
    if (amt > COIN_MAX)   { showToast(`Максимум ${COIN_MAX.toLocaleString("ru")} 🪙`); return; }
    if (balance !== null && amt > balance) { showToast(`Недостаточно Моры. У тебя ${balance.toLocaleString("ru")} 🪙`); return; }
    setLoading(true);
    setResult(null);
    try {
      const r = await casinoCoinFlip(chatId, amt);
      trackEvent("casino_coinflip");
      setResult(r);
      if (r.quest_done) showToast("🎯 Квест выполнен!");
    } catch (e) {
      showToast(extractErr(e));
    } finally {
      setLoading(false);
    }
  }, [chatId, amount, showToast]);

  return (
    <div className="animate-fadeIn">
      <Card>
        <p className="text-sm mb-3" style={{ color: "var(--text-hint)" }}>
          47% шанс выигрыша. Максимальная ставка {COIN_MAX.toLocaleString("ru")} 🪙
        </p>
        <NumInput
          label="Ставка 🪙"
          value={amount}
          onChange={setAmount}
          min={1}
          max={COIN_MAX}
          placeholder="Введи сумму"
        />
        <button
          onClick={handleFlip}
          disabled={loading}
          className="w-full mt-3 btn-primary btn-press py-3 text-sm font-bold"
          style={{ opacity: loading ? 0.6 : 1 }}
        >
          {loading ? "Подбрасываем…" : "🪙 Подбросить монету"}
        </button>
      </Card>

      {result && (
        <Card>
          <div className="flex flex-col items-center gap-2 py-2">
            <span className="text-5xl">{result.win ? "🎉" : "😓"}</span>
            <p
              className="text-lg font-bold"
              style={{ color: result.win ? "#22c55e" : "#ef4444" }}
            >
              {result.win ? `+${result.prize.toLocaleString("ru")} 🪙` : `−${result.bet.toLocaleString("ru")} 🪙`}
            </p>
            {result.win && result.win_tax > 0 && (
              <p className="text-xs" style={{ color: "var(--text-hint)" }}>
                (налог {result.win_tax} 🪙)
              </p>
            )}
            <p className="text-xs" style={{ color: "var(--text-hint)" }}>
              Баланс: {result.new_balance.toLocaleString("ru")} 🪙
            </p>
            {result.quest_done && (
              <span
                className="text-xs px-2 py-0.5 rounded-full font-semibold"
                style={{ backgroundColor: "#22c55e22", color: "#22c55e" }}
              >
                🎯 Квест выполнен!
              </span>
            )}
          </div>
        </Card>
      )}

    </div>
  );
}

// ════════════════════════════════════════════
//  ROULETTE SECTION
// ════════════════════════════════════════════

// Generates the classic European wheel visual ring (simplified)
const WHEEL_SEQUENCE = [
  0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,
  5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26,
];

function RouletteWheel({ number, spinning }: { number: number | null; spinning: boolean }) {
  const totalSlots = WHEEL_SEQUENCE.length;
  const slotDeg = 360 / totalSlots;

  return (
    <div
      className="relative mx-auto my-4 rounded-full overflow-hidden"
      style={{ width: 180, height: 180, border: "4px solid var(--border)" }}
    >
      {/* Coloured slots ring */}
      <svg viewBox="0 0 180 180" width="180" height="180">
        {WHEEL_SEQUENCE.map((n, i) => {
          const startAngle = (i * slotDeg - 90) * (Math.PI / 180);
          const endAngle   = ((i + 1) * slotDeg - 90) * (Math.PI / 180);
          const x1 = 90 + 90 * Math.cos(startAngle);
          const y1 = 90 + 90 * Math.sin(startAngle);
          const x2 = 90 + 90 * Math.cos(endAngle);
          const y2 = 90 + 90 * Math.sin(endAngle);
          const col = wheelColor(n);
          const fill = WHEEL_DOT[col];
          const isWinner = n === number;
          return (
            <path
              key={i}
              d={`M90,90 L${x1},${y1} A90,90 0 0,1 ${x2},${y2} Z`}
              fill={fill}
              opacity={spinning ? 0.5 : isWinner ? 1 : 0.75}
              stroke="#111"
              strokeWidth="0.5"
            />
          );
        })}
        {/* Centre circle */}
        <circle cx="90" cy="90" r="28" fill="var(--bg-primary)" stroke="var(--border)" strokeWidth="2" />
        <text
          x="90" y="96"
          textAnchor="middle"
          fontSize={number !== null ? "22" : "14"}
          fontWeight="bold"
          fill="var(--text-primary)"
        >
          {spinning ? "…" : number !== null ? number : "🎡"}
        </text>
      </svg>
    </div>
  );
}

function RouletteSection({ chatId, balance }: { chatId: number; balance: number | null }) {
  const { toast } = useToast();
  const showToast = useCallback((t: string) => toast(t, "info"), [toast]);
  const [betType, setBetType] = useState<BetKey>("red");
  const [amount, setAmount]   = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState<RouletteResult | null>(null);

  const handleSpin = useCallback(async () => {
    const amt = parseInt(amount, 10);
    if (!amt || amt < ROULETTE_MIN) { showToast(`Минимальная ставка ${ROULETTE_MIN} 🪙`); return; }
    if (amt > ROULETTE_MAX)         { showToast(`Максимальная ставка ${ROULETTE_MAX} 🪙`); return; }
    if (balance !== null && amt > balance) { showToast(`Недостаточно Моры. У тебя ${balance.toLocaleString("ru")} 🪙`); return; }
    setLoading(true);
    setResult(null);
    try {
      const r = await casinoRoulette(chatId, betType, amt);
      trackEvent("casino_roulette");
      setResult(r);
    } catch (e) {
      showToast(extractErr(e));
    } finally {
      setLoading(false);
    }
  }, [chatId, betType, amount, showToast]);

  return (
    <div className="animate-fadeIn">
      <Card>
        <p className="text-xs mb-2 font-medium" style={{ color: "var(--text-hint)" }}>
          Ставка: {ROULETTE_MIN}–{ROULETTE_MAX} 🪙
        </p>

        {/* Simple bet buttons */}
        <p className="text-xs mb-1 font-semibold" style={{ color: "var(--text-hint)" }}>Простые ставки:</p>
        <div className="grid grid-cols-3 gap-1.5 mb-3">
          {SIMPLE_BETS.map(b => (
            <button
              key={b.key}
              onClick={() => { setBetType(b.key); }}
              className="rounded-xl py-2 px-1 text-xs font-semibold transition-all"
              style={{
                backgroundColor: betType === b.key ? "var(--accent)" : "var(--bg-primary)",
                color: betType === b.key ? "#fff" : "var(--text-primary)",
                border: "1px solid var(--border)",
              }}
            >
              {b.label}<br />
              <span className="opacity-60 text-[10px]">{b.payout}</span>
            </button>
          ))}
        </div>

        <p className="text-[11px] mb-3" style={{ color: "var(--text-hint)" }}>
          Прямые ставки на число и зеро отключены: рулетка больше не даёт взрывных выплат и не ломает экономику.
        </p>

        <NumInput
          label="Ставка 🪙"
          value={amount}
          onChange={setAmount}
          min={ROULETTE_MIN}
          max={ROULETTE_MAX}
          placeholder={`${ROULETTE_MIN}–${ROULETTE_MAX}`}
        />
        <button
          onClick={handleSpin}
          disabled={loading}
          className="w-full mt-3 rounded-xl py-3 text-sm font-bold transition-opacity"
          style={{
            backgroundColor: loading ? "var(--border)" : "#7c3aed",
            color: "#fff",
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? "Крутим…" : "🎡 Крутить рулетку"}
        </button>
      </Card>

      {/* Result */}
      {result && (
        <Card>
          <RouletteWheel number={result.number} spinning={false} />
          <div className="flex flex-col items-center gap-1">
            <span className="text-xs font-medium" style={{ color: "var(--text-hint)" }}>
              Выпало{" "}
              <span style={{ color: WHEEL_DOT[result.color] ?? "var(--text-primary)", fontWeight: "bold" }}>
                {result.number}
              </span>
              {" "}({result.color === "green" ? "зеро" : result.color === "red" ? "красное" : "чёрное"})
            </span>
            <p
              className="text-lg font-bold mt-1"
              style={{ color: result.win ? "#22c55e" : "#ef4444" }}
            >
              {result.win
                ? `+${result.net_prize.toLocaleString("ru")} 🪙`
                : `−${(parseInt(amount, 10) || 0).toLocaleString("ru")} 🪙`}
            </p>
            {result.win && result.win_tax > 0 && (
              <p className="text-xs" style={{ color: "var(--text-hint)" }}>
                (налог {result.win_tax} 🪙)
              </p>
            )}
            <p className="text-xs" style={{ color: "var(--text-hint)" }}>
              Баланс: {result.new_balance.toLocaleString("ru")} 🪙
            </p>
            {result.item_prize && (
              <span
                className="text-xs px-2 py-0.5 rounded-full font-semibold mt-1"
                style={{ backgroundColor: "#f59e0b22", color: "#f59e0b" }}
              >
                🎁 {result.item_prize.item_name}
              </span>
            )}
          </div>
        </Card>
      )}

    </div>
  );
}

// ════════════════════════════════════════════
//  LOTTERY SECTION
// ════════════════════════════════════════════
function LotterySection({ chatId }: { chatId: number }) {
  const { toast } = useToast();
  const showToast = useCallback((t: string) => toast(t, "info"), [toast]);
  const [status, setStatus]   = useState<LotteryStatusResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [lastBalance, setLastBalance] = useState<number | null>(null);

  useEffect(() => {
    fetchLotteryStatus(chatId)
      .then(s => setStatus(s))
      .catch(e => showToast(extractErr(e)))
      .finally(() => setFetching(false));
  }, [chatId, showToast]);

  const handleBuy = useCallback(async () => {
    setLoading(true);
    try {
      const r = await buyLotteryTicket(chatId);
      trackEvent("casino_lottery");
      setLastBalance(r.new_balance);
      setStatus(prev => prev ? { ...prev, tickets: r.tickets } : null);
      showToast(`🎟 Куплен билет #${r.tickets}!`);
    } catch (e) {
      showToast(extractErr(e));
    } finally {
      setLoading(false);
    }
  }, [chatId, showToast]);

  if (fetching) {
    return (
      <div className="flex justify-center py-10">
        <div className="skeleton w-16 h-16 rounded-full" />
      </div>
    );
  }

  return (
    <div className="animate-fadeIn">
      <Card>
        <div className="flex flex-col items-center gap-3 py-2">
          <span className="text-5xl">🎟</span>
          <p className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
            Лотерея недели
          </p>
          {status && (
            <>
              <p className="text-sm" style={{ color: "var(--text-hint)" }}>
                Неделя: <b style={{ color: "var(--text-primary)" }}>{status.week}</b>
              </p>
              <p className="text-2xl font-bold" style={{ color: "var(--accent)" }}>
                {status.tickets} {status.tickets === 1 ? "билет" : status.tickets < 5 ? "билета" : "билетов"}
              </p>
              <p className="text-xs" style={{ color: "var(--text-hint)" }}>
                Цена билета: {status.ticket_price} 🪙 · ~5% шанс выигрыша
              </p>
            </>
          )}
          {lastBalance !== null && (
            <p className="text-xs" style={{ color: "var(--text-hint)" }}>
              Баланс: {lastBalance.toLocaleString("ru")} 🪙
            </p>
          )}
        </div>
        <button
          onClick={handleBuy}
          disabled={loading || !status}
          className="w-full mt-4 rounded-xl py-3 text-sm font-bold transition-opacity"
          style={{
            backgroundColor: loading ? "var(--border)" : "#0ea5e9",
            color: "#fff",
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? "Покупаем…" : `🎟 Купить билет (${status?.ticket_price ?? 40} 🪙)`}
        </button>
      </Card>

      <Card>
        <div className="flex items-start gap-2">
          <AlertCircle size={16} style={{ color: "var(--text-hint)", flexShrink: 0, marginTop: 2 }} />
          <p className="text-xs leading-relaxed" style={{ color: "var(--text-hint)" }}>
            Розыгрыш проходит раз в неделю. Выигрыш зачисляется автоматически.
            Чем больше билетов — тем выше шанс. Выигрыш: 120–300 🪙 за билет.
          </p>
        </div>
      </Card>

    </div>
  );
}

// ════════════════════════════════════════════
//  ROOT EXPORT
// ════════════════════════════════════════════
export default function Casino({ userId: _userId, chatId }: Props) {
  const [sub, setSub] = useState<SubTab>("coin");
  const [balance, setBalance] = useState<number | null>(null);

  useEffect(() => {
    if (!chatId) return;
    fetchUserData(chatId).then(d => setBalance(d.balance)).catch(() => {});
  }, [chatId]);

  const SUBS: { key: SubTab; label: string; Icon: typeof Coins }[] = [
    { key: "coin",     label: "Монетка", Icon: Coins     },
    { key: "roulette", label: "Рулетка", Icon: CircleDot },
    { key: "lottery",  label: "Лотерея", Icon: Ticket    },
  ];

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "var(--bg-primary)" }}>
      {/* Header */}
      <div
        className="px-4 pt-4 pb-3 glass-heavy"
        style={{ borderBottom: "1px solid var(--border-accent)" }}
      >
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-xl font-bold flex items-center gap-2.5" style={{ color: "var(--text-primary)" }}>
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "linear-gradient(135deg, #f59e0b22, #ef444422)" }}>
              🎰
            </div>
            Казино
          </h1>
          {balance !== null && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl glass-card-sm">
              <Wallet size={14} style={{ color: "var(--accent)" }} />
              <span className="text-sm font-bold tabular-nums stat-value">{balance.toLocaleString("ru-RU")} 🪙</span>
            </div>
          )}
        </div>
        {/* Sub-tabs */}
        <div className="flex gap-2">
          {SUBS.map(({ key, label, Icon }) => {
            const active = sub === key;
            return (
              <button
                key={key}
                onClick={() => setSub(key)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-semibold transition-all"
                style={{
                  backgroundColor: active ? "var(--accent)" : "transparent",
                  color: active ? "#fff" : "var(--text-hint)",
                  border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
                  boxShadow: active ? "0 0 12px var(--accent-glow)" : "none",
                }}
              >
                <Icon size={14} />
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 pt-4 pb-4">
        {sub === "coin"     && <CoinSection     chatId={chatId} balance={balance} />}
        {sub === "roulette" && <RouletteSection chatId={chatId} balance={balance} />}
        {sub === "lottery"  && <LotterySection  chatId={chatId} />}
      </div>
    </div>
  );
}
