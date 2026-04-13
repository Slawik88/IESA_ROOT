/* ──────────────────────────────────────────────────────────────
   Promo.tsx — Страница активации промокода
   Анимация: сундук открывается → награды вылетают
   ────────────────────────────────────────────────────────────── */
import { useState, useRef } from "react";
import { activatePromocode } from "../lib/api";
import { useTelegram } from "../hooks/useTelegram";
import { Loader2 } from "lucide-react";

// Emoji for reward types
function rewardIcon(text: string): string {
  if (text.includes("мора")  || text.includes("Мора"))   return "🪙";
  if (text.includes("кристалл") || text.includes("Кристалл")) return "💎";
  if (text.includes("XP")    || text.includes("xp"))     return "⚡";
  if (text.includes("камн")  || text.includes("заточк")) return "⚒️";
  if (text.includes("тем")   || text.includes("Тем"))    return "🎨";
  if (text.includes("предм") || text.includes("Предм"))  return "🎁";
  return "✨";
}

type Phase = "idle" | "loading" | "shaking" | "opening" | "rewards" | "error";

interface Props {
  userId: number | null;
  chatId: number | null;
}

export default function Promo({ userId: _userId, chatId }: Props) {
  const { chatId: tgChatId } = useTelegram();
  const effectiveChatId = chatId ?? tgChatId;

  const [code, setCode] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [rewards, setRewards] = useState<string[]>([]);
  const [errorMsg, setErrorMsg] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const doActivate = async () => {
    if (!effectiveChatId || !code.trim()) {
      inputRef.current?.focus();
      return;
    }
    setPhase("loading");
    setErrorMsg("");
    try {
      const res = await activatePromocode(effectiveChatId, code.trim().toUpperCase());
      if (!res.ok) {
        setErrorMsg(res.error ?? "Промокод недействителен");
        setPhase("error");
        return;
      }
      setRewards(res.rewards ?? []);
      // Chest animation sequence
      setPhase("shaking"); // 600ms shake
      setTimeout(() => setPhase("opening"), 600); // lid opens
      setTimeout(() => setPhase("rewards"), 1100); // rewards fly in
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "Ошибка сети");
      setPhase("error");
    }
  };

  const doReset = () => {
    setCode("");
    setPhase("idle");
    setRewards([]);
    setErrorMsg("");
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "var(--bg-primary)" }}>
      {/* Header */}
      <div className="px-4 pt-safe pb-2 glass-heavy" style={{ borderBottom: "1px solid var(--border-accent)" }}>
        <h1 className="text-lg font-bold flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
          <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: "var(--accent-soft)" }}>🎟️</div>
          Промокод
        </h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>Введи код и получи награды</p>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-4 gap-6">

        {/* Chest area */}
        <div className="relative flex items-center justify-center w-40 h-40">
          {phase === "idle" || phase === "loading" || phase === "error" ? (
            <div className="text-8xl select-none" style={{ filter: "drop-shadow(0 4px 16px color-mix(in srgb, var(--accent) 40%, transparent))" }}>
              📦
            </div>
          ) : phase === "shaking" ? (
            <div className="text-8xl select-none animate-chest-shake" style={{ filter: "drop-shadow(0 4px 16px color-mix(in srgb, var(--accent) 50%, transparent))" }}>
              📦
            </div>
          ) : (
            /* Opening / rewards */
            <div className="relative text-8xl select-none">
              <span style={{ filter: "drop-shadow(0 4px 24px color-mix(in srgb, var(--accent) 80%, transparent))" }}>
                🎁
              </span>
              {/* Sparkle burst */}
              {phase === "opening" || phase === "rewards" ? (
                <>
                  {["✨","💫","⭐","🌟"].map((s, i) => (
                    <span
                      key={i}
                      className="absolute text-2xl animate-reward-fly pointer-events-none"
                      style={{
                        top: "50%", left: "50%",
                        transform: "translate(-50%, -50%)",
                        animationDelay: `${i * 80}ms`,
                        "--fly-x": `${[-60, 60, -40, 40][i]}px`,
                        "--fly-y": `${[-80, -80, -120, -100][i]}px`,
                      } as React.CSSProperties}
                    >
                      {s}
                    </span>
                  ))}
                </>
              ) : null}
            </div>
          )}
        </div>

        {/* Rewards list (visible after opening) */}
        {phase === "rewards" && rewards.length > 0 && (
          <div className="w-full max-w-xs space-y-2">
            <p className="text-center text-sm font-semibold" style={{ color: "var(--accent)" }}>
              Получено!
            </p>
            {rewards.map((r, i) => (
              <div
                key={i}
                className="glass-card rounded-xl px-3 py-2 flex items-center gap-2 animate-reward-fly"
                style={{
                  animationDelay: `${i * 120}ms`,
                  "--fly-x": "0px",
                  "--fly-y": "-20px",
                } as React.CSSProperties}
              >
                <span className="text-xl">{rewardIcon(r)}</span>
                <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{r}</span>
              </div>
            ))}
            <button
              onClick={doReset}
              className="w-full mt-3 py-2.5 rounded-xl text-sm font-semibold"
              style={{ backgroundColor: "var(--accent)", color: "#fff" }}
            >
              Ввести ещё один
            </button>
          </div>
        )}

        {/* Input + button (idle / error states) */}
        {(phase === "idle" || phase === "loading" || phase === "error") && (
          <div className="w-full max-w-xs space-y-3">
            {phase === "error" && (
              <div
                className="rounded-xl px-3 py-2 text-sm text-center font-medium animate-danger"
                style={{ backgroundColor: "#ef444420", color: "#f87171", border: "1px solid #ef444440" }}
              >
                {errorMsg}
              </div>
            )}
            <div
              className="glass-card rounded-2xl p-1 flex items-center gap-2"
            >
              <span className="pl-3 text-lg">🔑</span>
              <input
                ref={inputRef}
                type="text"
                placeholder="VIPTOP2025"
                value={code}
                onChange={e => setCode(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === "Enter" && doActivate()}
                className="flex-1 bg-transparent outline-none text-base font-mono tracking-widest py-3 pr-2"
                style={{ color: "var(--text-primary)" }}
                maxLength={32}
                disabled={phase === "loading"}
                autoCapitalize="characters"
                spellCheck={false}
              />
            </div>
            <button
              onClick={doActivate}
              disabled={phase === "loading" || !code.trim()}
              className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 disabled:opacity-50 transition-transform active:scale-95"
              style={{ backgroundColor: "var(--accent)", color: "#fff" }}
            >
              {phase === "loading"
                ? <><Loader2 size={16} className="animate-spin" /> Проверяем...</>
                : "🎁 Активировать"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
