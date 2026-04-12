/* ──────────────────────────────────────────────────────────────
   Gacha.tsx — Призыв (Гача)
   POST /api/gacha/roll  { chat_id, count: 1|10, wallet_type }
   Prices: single=80🪙  multi=700🪙
   ────────────────────────────────────────────────────────────── */
import { useState, useCallback } from "react";
import { Sparkles, Star, AlertCircle, ChevronLeft } from "lucide-react";
import { rollGacha } from "../lib/api";
import type { GachaItem, GachaRollResult } from "../types";

const SINGLE_PRICE = 80;
const MULTI_PRICE  = 700;

export const RARITY_COLOR: Record<string, string> = {
  junk:      "#9ca3af",
  common:    "#22c55e",
  rare:      "#3b82f6",
  legendary: "#f59e0b",
};

const RARITY_LABEL: Record<string, string> = {
  junk:      "Хлам",
  common:    "Обычный",
  rare:      "Редкий",
  legendary: "Легендарный",
};

const RARITY_BG: Record<string, string> = {
  junk:      "#9ca3af18",
  common:    "#22c55e18",
  rare:      "#3b82f618",
  legendary: "#f59e0b18",
};

type Phase = "idle" | "rolling" | "result";

interface Props {
  userId: number;
  chatId: number;
}

export default function Gacha({ chatId }: Props) {
  const [phase, setPhase]       = useState<Phase>("idle");
  const [result, setResult]     = useState<GachaRollResult | null>(null);
  const [toast, setToast]       = useState<string | null>(null);
  const [legendaryOverlay, setLegendaryOverlay] = useState(false);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }, []);

  const handleRoll = useCallback(async (count: 1 | 10) => {
    if (!chatId) { showToast("Нет chat_id"); return; }
    setPhase("rolling");
    try {
      const res = await rollGacha(chatId, count);
      setResult(res);
      if (res.items.some(i => i.rarity === "legendary")) setLegendaryOverlay(true);
      setPhase("result");
      if (res.quest_done) showToast(`🎯 Квест выполнен! +${res.quest_xp} XP +${res.quest_mora} 🪙`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка";
      showToast(msg.includes("400:") ? extractError(msg) : msg);
      setPhase("idle");
    }
  }, [chatId, showToast]);

  const hasLegendary = result?.items.some(i => i.rarity === "legendary");
  const hasRare      = result?.items.some(i => i.rarity === "rare");

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "var(--bg-primary)" }}>
      {/* ── Состояние: IDLE — баннер + кнопки ── */}
      {phase === "idle" && (
        <div className="animate-fadeIn flex flex-col flex-1">
          {/* Баннер */}
          <div
            className="relative overflow-hidden mx-4 mt-4 rounded-2xl p-6 flex flex-col items-center gap-2"
            style={{
              background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
              minHeight: 180,
            }}
          >
            {/* Звёздная пыль */}
            {[...Array(12)].map((_, i) => (
              <div
                key={i}
                className="absolute rounded-full"
                style={{
                  width:  Math.random() * 3 + 2 + "px",
                  height: Math.random() * 3 + 2 + "px",
                  left:   Math.random() * 100 + "%",
                  top:    Math.random() * 100 + "%",
                  backgroundColor: i % 3 === 0 ? "#f59e0b" : i % 3 === 1 ? "#3b82f6" : "#e879f9",
                  opacity: 0.6 + Math.random() * 0.4,
                  animation: `orbPulse ${1.2 + Math.random() * 1.5}s ease-in-out infinite`,
                  animationDelay: Math.random() * 2 + "s",
                }}
              />
            ))}
            <Sparkles size={36} className="animate-orb" style={{ color: "#f59e0b", zIndex: 1 }} />
            <h1 className="text-2xl font-bold text-white z-10 tracking-wide">Призыв</h1>
            <p className="text-xs z-10" style={{ color: "#94a3b8" }}>
              Шанс легендарки: 2% · Гарантия: 90 кручений
            </p>
          </div>

          {/* Кнопки */}
          <div className="p-4 space-y-3 mt-2">
            <RollButton
              label="Крутить 1 раз"
              price={SINGLE_PRICE}
              accent="#3b82f6"
              onClick={() => handleRoll(1)}
            />
            <RollButton
              label="Крутить 10 раз"
              price={MULTI_PRICE}
              accent="#a855f7"
              discount="-13%"
              onClick={() => handleRoll(10)}
            />
          </div>

          <div className="px-4">
            <div className="rounded-xl p-3 text-xs space-y-1" style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-hint)" }}>
              <p>⚪ Хлам · 🟢 Обычный · 🔵 Редкий · 🟡 Легендарный</p>
              <p>Pity счётчик защищает от длинной полосы неудач</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Состояние: ROLLING — улучшенная анимация ── */}
      {phase === "rolling" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6 p-8 relative overflow-hidden">
          {/* Фоновые лучи */}
          <div
            className="absolute inset-0 opacity-30"
            style={{
              background: "conic-gradient(from 0deg at 50% 50%, #f59e0b00, #f59e0b33, #a855f733, #3b82f633, #f59e0b00)",
              animation: "gachaRaysSpin 3s linear infinite",
            }}
          />
          {/* Центральный орб */}
          <div
            className="relative w-36 h-36 rounded-full flex items-center justify-center z-10"
            style={{
              background: "radial-gradient(circle, #f59e0b44 0%, #a855f744 40%, transparent 70%)",
              animation: "gachaOrbPulse 1.5s ease-in-out infinite",
            }}
          >
            <div
              className="w-24 h-24 rounded-full flex items-center justify-center"
              style={{
                background: "radial-gradient(circle, #f59e0b88 0%, #a855f744 100%)",
                border: "2px solid #f59e0b88",
                boxShadow: "0 0 60px #f59e0b44, 0 0 120px #a855f722",
              }}
            >
              <Star size={44} style={{ color: "#f59e0b" }} className="animate-spin" />
            </div>
          </div>
          <p className="text-lg font-semibold z-10" style={{ color: "var(--text-hint)" }}>
            Призываю...
          </p>
          {/* Орбитальные частицы */}
          {[...Array(12)].map((_, i) => (
            <div
              key={i}
              className="absolute w-1.5 h-1.5 rounded-full"
              style={{
                backgroundColor: ["#f59e0b", "#3b82f6", "#a855f7", "#22c55e", "#f472b6", "#ef4444"][i % 6],
                animation: `gachaParticleOrbit ${2 + i * 0.3}s ease-in-out infinite`,
                animationDelay: `${i * 0.15}s`,
                left: `${50 + Math.cos((i * Math.PI * 2) / 12) * 40}%`,
                top: `${50 + Math.sin((i * Math.PI * 2) / 12) * 40}%`,
              }}
            />
          ))}
        </div>
      )}

      {/* ── Состояние: RESULT — карточки ── */}
      {phase === "result" && result && (
        <div className="animate-fadeIn flex flex-col flex-1 pb-24">
          {/* Recap заголовок */}
          <div
            className="mx-4 mt-4 rounded-2xl p-4 text-center"
            style={{
              background: hasLegendary
                ? "linear-gradient(135deg, #78350f 0%, #92400e 100%)"
                : hasRare
                ? "linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 100%)"
                : "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
            }}
          >
            <p className="text-white font-bold text-lg">
              {hasLegendary ? "✨ ЛЕГЕНДАРНЫЙ ПРЕДМЕТ!" : hasRare ? "🔵 Редкий drop!" : "Результаты призыва"}
            </p>
            <p className="text-xs mt-1" style={{ color: "#94a3b8" }}>
              Потрачено: {result.spent} 🪙 · Баланс: {result.balance} 🪙 · Pity: {result.pity}
            </p>
          </div>

          {/* Карточки */}
          <div className={`p-4 ${result.items.length === 1 ? "flex justify-center" : "grid grid-cols-2 gap-3"}`}>
            {result.items.map((item, i) => (
              <ItemCard
                key={i}
                item={item}
                index={i}
                large={result.items.length === 1}
              />
            ))}
          </div>

          {/* Кнопки */}
          <div className="px-4 space-y-2 mt-2">
            <button
              onClick={() => handleRoll(result.items.length === 1 ? 1 : 10)}
              className="w-full py-3 rounded-xl font-semibold text-sm"
              style={{ backgroundColor: "var(--accent)", color: "#fff" }}
            >
              Крутить ещё
            </button>
            <button
              onClick={() => setPhase("idle")}
              className="w-full py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-1"
              style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-hint)" }}
            >
              <ChevronLeft size={16} />
              Назад
            </button>
          </div>

          {chatId === 0 && (
            <div className="mx-4 mt-2 p-3 rounded-xl flex items-center gap-2 text-xs" style={{ backgroundColor: "#e74c3c22", color: "#e74c3c" }}>
              <AlertCircle size={14} />
              Войдите через Telegram для сохранения результатов
            </div>
          )}
        </div>
      )}

      {/* ── Легендарный оверлей ── */}
      {legendaryOverlay && result && (() => {
        const legendaryItem = result.items.find(i => i.rarity === "legendary");
        if (!legendaryItem) return null;
        return (
          <div
            className="fixed inset-0 z-50 flex flex-col items-center justify-center"
            style={{ backgroundColor: "rgba(0,0,0,0.92)" }}
            onClick={() => setLegendaryOverlay(false)}
          >
            {/* Золотая вспышка */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                background: "radial-gradient(circle, #f59e0b44 0%, transparent 70%)",
                animation: "legendaryFlash 1.5s ease-out forwards",
              }}
            />
            {/* Лучи */}
            <div
              className="absolute pointer-events-none"
              style={{
                width: "150vw", height: "150vw",
                left: "50%", top: "50%",
                background: "conic-gradient(from 0deg, transparent, #f59e0b22, transparent, #f59e0b22, transparent, #f59e0b22, transparent, #f59e0b22, transparent)",
                animation: "gachaRaysSpin 6s linear infinite",
                borderRadius: "50%",
              }}
            />
            {/* Карточка */}
            <div
              className="relative z-10 animate-bounceIn rounded-2xl p-6 flex flex-col items-center gap-3 w-72"
              style={{
                backgroundColor: "#f59e0b18",
                border: "2px solid #f59e0b88",
                animation: "bounceIn 0.6s cubic-bezier(0.34,1.56,0.64,1) both, legendaryGlow 2s ease-in-out infinite",
              }}
            >
              <span className="text-5xl">{"⭐"}</span>
              <p className="text-xl font-bold" style={{ color: "#f59e0b" }}>{legendaryItem.name}</p>
              <span
                className="text-[11px] font-bold px-2 py-0.5 rounded-full"
                style={{ backgroundColor: "#f59e0b30", color: "#f59e0b" }}
              >
                ★ ЛЕГЕНДАРНЫЙ ★
              </span>
              {(legendaryItem.atk || legendaryItem.def_val || legendaryItem.hp) ? (
                <div className="flex gap-3 text-xs mt-1" style={{ color: "var(--text-hint)" }}>
                  {(legendaryItem.atk ?? 0) > 0 && <span>+{legendaryItem.atk} ATK</span>}
                  {(legendaryItem.def_val ?? 0) > 0 && <span>+{legendaryItem.def_val} DEF</span>}
                  {(legendaryItem.hp ?? 0) > 0 && <span>+{legendaryItem.hp} HP</span>}
                </div>
              ) : null}
            </div>
            <p className="text-xs mt-6 z-10" style={{ color: "#f59e0b88" }}>Нажмите, чтобы продолжить</p>
          </div>
        );
      })()}

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

/* ── Кнопка крутки ── */
function RollButton({
  label, price, accent, discount, onClick,
}: {
  label: string;
  price: number;
  accent: string;
  discount?: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full rounded-xl p-4 flex items-center justify-between transition-all active:scale-95"
      style={{ backgroundColor: accent + "22", border: `1.5px solid ${accent}44` }}
    >
      <div className="text-left">
        <p className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>{label}</p>
        {discount && (
          <p className="text-xs mt-0.5" style={{ color: accent }}>Скидка {discount}</p>
        )}
      </div>
      <div
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-bold text-sm"
        style={{ backgroundColor: accent, color: "#fff" }}
      >
        <span>{price}</span>
        <span>🪙</span>
      </div>
    </button>
  );
}

/* ── Карточка предмета ── */
function ItemCard({ item, index, large }: { item: GachaItem; index: number; large: boolean }) {
  const color  = RARITY_COLOR[item.rarity] ?? "#9ca3af";
  const bg     = RARITY_BG[item.rarity]    ?? "#9ca3af18";
  const label  = RARITY_LABEL[item.rarity] ?? item.rarity;

  const stats: string[] = [];
  if (item.atk)       stats.push(`+${item.atk} ATK`);
  if (item.def_val)   stats.push(`+${item.def_val} DEF`);
  if (item.hp)        stats.push(`+${item.hp} HP`);
  if (item.crit_rate) stats.push(`+${item.crit_rate}% CRIT`);

  return (
    <div
      className={`animate-card-reveal rounded-2xl p-4 flex flex-col gap-2 ${large ? "w-full max-w-xs" : ""}`}
      style={{
        backgroundColor: bg,
        border: `1.5px solid ${color}66`,
        animationDelay: `${index * 80}ms`,
        boxShadow: item.rarity === "legendary" ? `0 4px 20px ${color}44` : undefined,
      }}
    >
      {/* Эмодзи + название */}
      <div>
        <p className={`font-bold leading-tight ${large ? "text-lg" : "text-sm"}`} style={{ color: "var(--text-primary)" }}>
          {item.name}
        </p>
        <p className="text-xs font-semibold mt-0.5" style={{ color }}>
          {item.rarity === "legendary" && "✨ "}{label}
        </p>
      </div>

      {/* Описание */}
      {item.desc && (
        <p className="text-xs leading-snug" style={{ color: "var(--text-hint)" }}>
          {item.desc}
        </p>
      )}

      {/* Статы */}
      {stats.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {stats.map(s => (
            <span
              key={s}
              className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
              style={{ backgroundColor: color + "33", color }}
            >
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function extractError(msg: string): string {
  try { return JSON.parse(msg.split("API 400: ")[1]).error ?? msg; } catch { return msg; }
}
