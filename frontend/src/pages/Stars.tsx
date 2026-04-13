/* ──────────────────────────────────────────────────────────────
   Stars.tsx — Покупка кристаллов за Telegram Stars
   POST /api/stars/invoice { pack_key, chat_id }
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Gem, Star, Loader2, CheckCircle2, AlertCircle, Info } from "lucide-react";
import { createStarsInvoice, fetchUserData } from "../lib/api";

interface Props {
  userId: number;
  chatId: number;
}

interface Pack {
  key: string;
  label: string;
  stars: number;
  crystals: number;
  bonus_pct: number;
}

const PACKS: Pack[] = [
  { key: "starter",  label: "Стартовый",  stars: 50,   crystals: 100,  bonus_pct: 0  },
  { key: "basic",    label: "Базовый",    stars: 150,  crystals: 330,  bonus_pct: 10 },
  { key: "advanced", label: "Продвинутый",stars: 500,  crystals: 1200, bonus_pct: 20 },
  { key: "premium",  label: "Премиум",    stars: 1000, crystals: 2600, bonus_pct: 30 },
  { key: "ultimate", label: "Абсолютный", stars: 2500, crystals: 7000, bonus_pct: 40 },
];

const fmt = (n: number) => n.toLocaleString("ru-RU");

// ── Toast ──────────────────────────────────────────────────────
function useToast() {
  const [ok, setOk]   = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const showOk  = useCallback((msg: string) => { setOk(msg);  setTimeout(() => setOk(null),  3500); }, []);
  const showErr = useCallback((msg: string) => { setErr(msg); setTimeout(() => setErr(null), 4000); }, []);
  return { ok, err, showOk, showErr };
}

// ── Extract API error ──────────────────────────────────────────
function extractErr(e: unknown): string {
  if (!(e instanceof Error)) return "Ошибка";
  const match = e.message.match(/API \d+: (.*)/s);
  if (match) {
    try { return (JSON.parse(match[1]) as { error?: string }).error ?? match[1]; }
    catch { return match[1]; }
  }
  return e.message;
}

// ── Main ───────────────────────────────────────────────────────
export default function Stars({ chatId }: Props) {
  const [crystals, setCrystals] = useState<number | null>(null);
  const [buying, setBuying]     = useState<string | null>(null);
  const { ok, err, showOk, showErr } = useToast();

  // Load current crystal balance
  useEffect(() => {
    if (!chatId) return;
    fetchUserData(chatId).then(d => setCrystals(d.crystals)).catch(() => {});
  }, [chatId]);

  const handleBuy = useCallback(async (pack: Pack) => {
    if (buying) return;
    setBuying(pack.key);
    try {
      const res = await createStarsInvoice(pack.key, chatId);
      if (!res.ok || !res.link) {
        showErr(res.error ?? "Не удалось создать инвойс");
        setBuying(null);
        return;
      }
      // Open Telegram Stars invoice
      const tg = (window as unknown as { Telegram?: { WebApp?: { openInvoice?: (link: string, cb: (s: string) => void) => void } } }).Telegram?.WebApp;
      if (!tg?.openInvoice) {
        showErr("Оплата недоступна (только в Telegram)");
        setBuying(null);
        return;
      }
      tg.openInvoice(res.link, (status: string) => {
        setBuying(null);
        if (status === "paid") {
          showOk(`✅ Куплено ${fmt(pack.crystals)} 💎! Баланс обновится через секунду.`);
          // Refetch balance after a short delay (bot webhook will credit the crystals)
          setTimeout(() => {
            fetchUserData(chatId).then(d => setCrystals(d.crystals)).catch(() => {});
          }, 2500);
        } else if (status === "cancelled") {
          // user cancelled — no error needed
        } else if (status === "failed") {
          showErr("Оплата не прошла. Попробуйте ещё раз.");
        }
      });
    } catch (e) {
      showErr(extractErr(e));
      setBuying(null);
    }
  }, [buying, chatId, showOk, showErr]);

  return (
    <div className="flex flex-col gap-4 p-4 pb-6">

      {/* ── Toasts ──────────────────────────────── */}
      {ok && (
        <div className="fixed top-4 left-4 right-4 z-50 flex items-center gap-2 rounded-2xl px-4 py-3 text-sm font-medium shadow-lg"
             style={{ backgroundColor: "#16a34a", color: "#fff" }}>
          <CheckCircle2 size={16} /> {ok}
        </div>
      )}
      {err && (
        <div className="fixed top-4 left-4 right-4 z-50 flex items-center gap-2 rounded-2xl px-4 py-3 text-sm font-medium shadow-lg"
             style={{ backgroundColor: "#dc2626", color: "#fff" }}>
          <AlertCircle size={16} /> {err}
        </div>
      )}

      {/* ── Header ──────────────────────────────── */}
      <div
        className="glass-hero p-5 flex flex-col items-center text-center gap-2"
        style={{
          background: "linear-gradient(135deg, rgba(124,58,237,0.3) 0%, rgba(79,70,229,0.25) 50%, rgba(37,99,235,0.2) 100%)",
          borderColor: "#7c3aed44",
        }}
      >
        <div className="flex items-center gap-2 text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          <Star size={28} fill="#fbbf24" color="#fbbf24" />
          <span>Кристаллы</span>
          <Gem size={28} style={{ color: "#a78bfa" }} />
        </div>
        <p className="text-sm max-w-xs" style={{ color: "var(--text-secondary)" }}>
          Покупай кристаллы 💎 за Telegram Stars ⭐ и трать на темы, рамки и другие премиум-возможности
        </p>

        {/* Crystal balance */}
        {crystals !== null && (
          <div
            className="mt-2 flex items-center gap-2 rounded-xl px-4 py-2 text-base font-bold glass-card-sm"
          >
            <Gem size={18} style={{ color: "#a78bfa" }} />
            <span className="stat-value">Баланс: {fmt(crystals)} 💎</span>
          </div>
        )}
      </div>

      {/* ── Packs ───────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold px-1" style={{ color: "var(--text-hint)" }}>
          НАБОРЫ КРИСТАЛЛОВ
        </h2>

        {PACKS.map(pack => (
          <PackCard
            key={pack.key}
            pack={pack}
            buying={buying === pack.key}
            disabled={!!buying}
            onBuy={() => handleBuy(pack)}
          />
        ))}
      </div>

      {/* ── How to spend ────────────────────────── */}
      <SpendInfo />

      {/* ── Info footer ─────────────────────────── */}
      <div
        className="flex items-start gap-2 rounded-2xl p-4 text-xs"
        style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-hint)", border: "1px solid var(--border)" }}
      >
        <Info size={14} className="mt-0.5 shrink-0" />
        <span>
          Оплата происходит через Telegram Stars. Кристаллы зачисляются автоматически
          после подтверждения платежа (обычно &lt;5 секунд). Возврат Stars не предусмотрен.
        </span>
      </div>
    </div>
  );
}

// ── Pack card ──────────────────────────────────────────────────
function PackCard({
  pack, buying, disabled, onBuy,
}: {
  pack: Pack;
  buying: boolean;
  disabled: boolean;
  onBuy: () => void;
}) {
  // Colour accent per pack tier
  const ACCENT: Record<string, string> = {
    starter:  "#6b7280",
    basic:    "#3b82f6",
    advanced: "#8b5cf6",
    premium:  "#f59e0b",
    ultimate: "#ef4444",
  };
  const accent = ACCENT[pack.key] ?? "var(--accent)";

  return (
    <div
      className="rounded-2xl p-4 flex items-center gap-4"
      style={{
        backgroundColor: "var(--bg-secondary)",
        border: `1px solid var(--border)`,
        boxShadow: buying ? `0 0 0 2px ${accent}` : undefined,
      }}
    >
      {/* Icon + names */}
      <div
        className="w-12 h-12 rounded-xl flex items-center justify-center text-xl shrink-0"
        style={{ backgroundColor: `${accent}22` }}
      >
        <Gem size={22} color={accent} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
            💎 {pack.crystals.toLocaleString("ru-RU")}
          </span>
          {pack.bonus_pct > 0 && (
            <span
              className="text-xs font-bold px-1.5 py-0.5 rounded-lg"
              style={{ backgroundColor: `${accent}33`, color: accent }}
            >
              +{pack.bonus_pct}%
            </span>
          )}
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>
          {pack.label} · {pack.stars.toLocaleString("ru-RU")} ⭐
        </div>
      </div>

      <button
        onClick={onBuy}
        disabled={disabled}
        className="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-semibold shrink-0 transition-opacity"
        style={{
          backgroundColor: accent,
          color: "#fff",
          opacity: disabled ? 0.6 : 1,
        }}
      >
        {buying
          ? <Loader2 size={16} className="animate-spin" />
          : <><Star size={14} fill="#fbbf24" color="#fbbf24" /> {pack.stars}⭐</>
        }
      </button>
    </div>
  );
}

// ── What to spend crystals on ──────────────────────────────────
function SpendInfo() {
  const items = [
    { icon: "🎨", label: "Темы профиля",   desc: "Уникальные цветовые схемы для вашего профиля" },
    { icon: "🖼️", label: "Рамки аватара",  desc: "Эксклюзивные рамки для обрамления аватарки" },
    { icon: "👑", label: "Кастомный титул", desc: "Уникальный титул под вашим именем" },
    { icon: "🪄", label: "Анимированные эффекты", desc: "Анимации и спецэффекты в профиле" },
  ];

  return (
    <div
      className="rounded-2xl p-4"
      style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
    >
      <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
        На что потратить кристаллы?
      </h3>
      <div className="flex flex-col gap-3">
        {items.map(item => (
          <div key={item.label} className="flex items-start gap-3">
            <span className="text-xl">{item.icon}</span>
            <div>
              <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{item.label}</div>
              <div className="text-xs" style={{ color: "var(--text-hint)" }}>{item.desc}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
