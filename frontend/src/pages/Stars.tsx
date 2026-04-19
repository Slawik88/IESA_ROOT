/* ──────────────────────────────────────────────────────────────
   Stars.tsx — Покупка кристаллов за Telegram Stars (Premium UI)
   POST /api/stars/invoice { pack_key, chat_id }
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Gem, Star, Loader2, CheckCircle2, AlertCircle, Zap } from "lucide-react";
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
  popular?: boolean;
}

const PACKS: Pack[] = [
  { key: "starter",  label: "Стартовый",   stars: 50,   crystals: 100,  bonus_pct: 0  },
  { key: "basic",    label: "Базовый",      stars: 150,  crystals: 330,  bonus_pct: 10 },
  { key: "advanced", label: "Продвинутый",  stars: 500,  crystals: 1200, bonus_pct: 20, popular: true },
  { key: "premium",  label: "Премиум",      stars: 1000, crystals: 2600, bonus_pct: 30 },
  { key: "ultimate", label: "Абсолютный",   stars: 2500, crystals: 7000, bonus_pct: 40 },
];

const fmt = (n: number) => n.toLocaleString("ru-RU");

// ── Pack visual config ─────────────────────────────────────────
const PACK_THEME: Record<string, {
  gradient: string;
  border: string;
  glow: string;
  btnGradient: string;
  crystalColor: string;
}> = {
  starter:  { gradient: "linear-gradient(135deg,#1e1e2e,#2a2a3e)", border: "#6b728044", glow: "transparent", btnGradient: "#6b7280", crystalColor: "#9ca3af" },
  basic:    { gradient: "linear-gradient(135deg,#0f1f38,#1a3352)", border: "#3b82f644", glow: "#3b82f622", btnGradient: "linear-gradient(135deg,#2563eb,#3b82f6)", crystalColor: "#60a5fa" },
  advanced: { gradient: "linear-gradient(135deg,#1a0a3a,#2d1260)", border: "#8b5cf666", glow: "#8b5cf633", btnGradient: "linear-gradient(135deg,#7c3aed,#8b5cf6)", crystalColor: "#c4b5fd" },
  premium:  { gradient: "linear-gradient(135deg,#1f1000,#3d2000)", border: "#f59e0b66", glow: "#f59e0b22", btnGradient: "linear-gradient(135deg,#d97706,#f59e0b)", crystalColor: "#fbbf24" },
  ultimate: { gradient: "linear-gradient(135deg,#200010,#400020)", border: "#ef444466", glow: "#ef444422", btnGradient: "linear-gradient(135deg,#dc2626,#ef4444)", crystalColor: "#f87171" },
};

// ── Toast ──────────────────────────────────────────────────────
function useToast() {
  const [ok, setOk]   = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const showOk  = useCallback((msg: string) => { setOk(msg);  setTimeout(() => setOk(null),  3500); }, []);
  const showErr = useCallback((msg: string) => { setErr(msg); setTimeout(() => setErr(null), 4000); }, []);
  return { ok, err, showOk, showErr };
}

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
          setTimeout(() => {
            fetchUserData(chatId).then(d => setCrystals(d.crystals)).catch(() => {});
          }, 2500);
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
    <div className="flex flex-col pb-8" style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>

      {/* ── Toasts ──────────────────────────────── */}
      {ok && (
        <div className="fixed top-4 left-4 right-4 z-50 flex items-center gap-2 rounded-2xl px-4 py-3 text-sm font-medium shadow-xl"
             style={{ background: "linear-gradient(135deg,#15803d,#16a34a)", color: "#fff", boxShadow: "0 4px 24px #16a34a44" }}>
          <CheckCircle2 size={16} /> {ok}
        </div>
      )}
      {err && (
        <div className="fixed top-4 left-4 right-4 z-50 flex items-center gap-2 rounded-2xl px-4 py-3 text-sm font-medium shadow-xl"
             style={{ background: "linear-gradient(135deg,#991b1b,#dc2626)", color: "#fff", boxShadow: "0 4px 24px #dc262644" }}>
          <AlertCircle size={16} /> {err}
        </div>
      )}

      {/* ── Hero Header ─────────────────────────── */}
      <div
        className="relative overflow-hidden px-4 pt-8 pb-10 flex flex-col items-center text-center"
        style={{
          background: "linear-gradient(180deg, rgba(124,58,237,0.18) 0%, rgba(99,102,241,0.08) 60%, transparent 100%)",
        }}
      >
        {/* Glow orbs */}
        <div style={{
          position: "absolute", top: -40, left: "50%", transform: "translateX(-50%)",
          width: 280, height: 280, borderRadius: "50%",
          background: "radial-gradient(circle, rgba(139,92,246,0.18) 0%, transparent 70%)",
          pointerEvents: "none",
        }} />

        {/* Icon cluster */}
        <div className="relative flex items-center justify-center mb-4">
          <div style={{
            width: 80, height: 80, borderRadius: 24,
            background: "linear-gradient(135deg, rgba(124,58,237,0.35) 0%, rgba(99,102,241,0.25) 100%)",
            border: "1px solid rgba(139,92,246,0.4)",
            boxShadow: "0 0 32px rgba(139,92,246,0.3), inset 0 1px 0 rgba(255,255,255,0.1)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Gem size={36} style={{ color: "#c4b5fd", filter: "drop-shadow(0 0 8px #8b5cf6)" }} />
          </div>
          <Star size={22} fill="#fbbf24" color="#fbbf24"
            style={{ position: "absolute", top: -6, right: -8, filter: "drop-shadow(0 0 6px #fbbf24)" }} />
          <Star size={14} fill="#fbbf24" color="#fbbf24"
            style={{ position: "absolute", bottom: 2, left: -10, opacity: 0.7 }} />
        </div>

        <h1 className="text-2xl font-bold mb-1" style={{
          color: "#fff",
          textShadow: "0 0 24px rgba(139,92,246,0.6)",
          letterSpacing: "-0.02em",
        }}>
          Кристаллы
        </h1>
        <p className="text-sm max-w-xs" style={{ color: "rgba(238,238,244,0.65)", lineHeight: 1.5 }}>
          Покупай кристаллы 💎 за Telegram Stars ⭐<br/>и открывай эксклюзивные возможности
        </p>

        {/* Crystal balance pill */}
        {crystals !== null && (
          <div
            className="mt-4 flex items-center gap-2 rounded-2xl px-5 py-2.5"
            style={{
              background: "linear-gradient(135deg, rgba(124,58,237,0.25), rgba(99,102,241,0.15))",
              border: "1px solid rgba(139,92,246,0.35)",
              boxShadow: "0 2px 16px rgba(139,92,246,0.15)",
            }}
          >
            <Gem size={16} style={{ color: "#c4b5fd" }} />
            <span className="text-sm font-bold" style={{ color: "#e9d5ff" }}>
              Баланс: {fmt(crystals)} 💎
            </span>
          </div>
        )}
      </div>

      {/* ── Packs ───────────────────────────────── */}
      <div className="flex flex-col gap-3 px-4 -mt-2">
        <p className="text-xs font-bold tracking-widest px-1" style={{ color: "var(--text-hint)" }}>
          НАБОРЫ КРИСТАЛЛОВ
        </p>
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

      {/* ── Spend Info ──────────────────────────── */}
      <div className="px-4 mt-6">
        <SpendInfo />
      </div>

      {/* ── Footer ──────────────────────────────── */}
      <div className="mx-4 mt-4 rounded-2xl p-4 flex items-start gap-2 text-xs"
           style={{ background: "var(--bg-secondary)", color: "var(--text-hint)", border: "1px solid var(--border)" }}>
        <Star size={13} fill="#fbbf2488" color="#fbbf2488" className="mt-0.5 shrink-0" />
        <span style={{ lineHeight: 1.55 }}>
          Оплата через Telegram Stars. Кристаллы зачисляются автоматически после подтверждения (обычно &lt;5 сек). Возврат Stars не предусмотрен.
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
  const theme = PACK_THEME[pack.key];

  return (
    <div
      className="relative rounded-2xl overflow-hidden"
      style={{
        background: theme.gradient,
        border: `1px solid ${theme.border}`,
        boxShadow: buying
          ? `0 0 0 2px ${theme.border.replace("44","88")}, 0 8px 32px ${theme.glow}`
          : `0 2px 12px rgba(0,0,0,0.3)`,
        transition: "box-shadow 0.2s",
      }}
    >
      {/* Popular badge */}
      {pack.popular && (
        <div style={{
          position: "absolute", top: 0, right: 0,
          background: "linear-gradient(135deg,#7c3aed,#8b5cf6)",
          borderBottomLeftRadius: 12,
          padding: "3px 10px",
          fontSize: 10, fontWeight: 700, color: "#fff",
          letterSpacing: "0.05em",
        }}>
          ⚡ ХИТ
        </div>
      )}

      <div className="flex items-center gap-3 p-4">
        {/* Crystal icon */}
        <div
          className="w-14 h-14 rounded-xl flex flex-col items-center justify-center shrink-0 gap-0.5"
          style={{
            background: `radial-gradient(circle at 30% 30%, rgba(255,255,255,0.12), transparent 70%), rgba(0,0,0,0.2)`,
            border: `1px solid ${theme.border}`,
          }}
        >
          <Gem size={20} color={theme.crystalColor} style={{ filter: `drop-shadow(0 0 4px ${theme.crystalColor}88)` }} />
          <span className="text-[10px] font-bold" style={{ color: theme.crystalColor }}>
            {pack.crystals >= 1000 ? `${pack.crystals / 1000}K` : pack.crystals}
          </span>
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-base" style={{ color: "#fff" }}>
              {fmt(pack.crystals)} 💎
            </span>
            {pack.bonus_pct > 0 && (
              <span
                className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                style={{
                  background: `${theme.crystalColor}22`,
                  color: theme.crystalColor,
                  border: `1px solid ${theme.crystalColor}44`,
                }}
              >
                +{pack.bonus_pct}% бонус
              </span>
            )}
          </div>
          <div className="text-xs mt-0.5 flex items-center gap-1.5" style={{ color: "rgba(238,238,244,0.5)" }}>
            <span>{pack.label}</span>
            <span>·</span>
            <Star size={10} fill="#fbbf24" color="#fbbf24" />
            <span>{fmt(pack.stars)} Stars</span>
          </div>
          {pack.bonus_pct > 0 && (
            <div className="text-[10px] mt-1" style={{ color: "rgba(238,238,244,0.35)" }}>
              ≈ {(pack.crystals / pack.stars).toFixed(1)} 💎 за ⭐
            </div>
          )}
        </div>

        {/* Buy button */}
        <button
          onClick={onBuy}
          disabled={disabled}
          className="flex items-center gap-1.5 rounded-xl px-4 py-2.5 text-xs font-bold shrink-0 transition-all active:scale-95"
          style={{
            background: theme.btnGradient,
            color: "#fff",
            opacity: disabled ? 0.5 : 1,
            boxShadow: `0 2px 12px ${theme.glow}`,
            border: "none",
            whiteSpace: "nowrap",
          }}
        >
          {buying
            ? <Loader2 size={14} className="animate-spin" />
            : <><Star size={12} fill="#fbbf24" color="#fbbf24" /> {fmt(pack.stars)}⭐</>
          }
        </button>
      </div>
    </div>
  );
}

// ── What to spend crystals on ──────────────────────────────────
function SpendInfo() {
  const items = [
    { icon: "🎨", label: "Темы профиля",     desc: "Уникальные цветовые схемы" },
    { icon: "🖼️", label: "Рамки аватара",   desc: "Эксклюзивные рамки" },
    { icon: "👑", label: "VIP-статус",        desc: `Голубая метка + бонусы` },
    { icon: "⚡", label: "Буст XP ×2",        desc: "24 часа двойного опыта" },
  ];

  return (
    <div
      className="rounded-2xl p-4"
      style={{
        background: "linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.06))",
        border: "1px solid rgba(99,102,241,0.2)",
      }}
    >
      <div className="flex items-center gap-2 mb-3">
        <Zap size={14} style={{ color: "#818cf8" }} />
        <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>
          На что потратить кристаллы?
        </h3>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {items.map(item => (
          <div key={item.label} className="flex items-start gap-2 rounded-xl p-2.5"
               style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.05)" }}>
            <span className="text-base">{item.icon}</span>
            <div>
              <div className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>{item.label}</div>
              <div className="text-[10px] mt-0.5" style={{ color: "var(--text-hint)" }}>{item.desc}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
