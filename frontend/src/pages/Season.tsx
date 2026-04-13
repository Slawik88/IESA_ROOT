/* ──────────────────────────────────────────────────────────────
   Season.tsx — Сезонный пропуск
   GET /api/season/data
   POST /api/season/claim  { season_id, level, is_premium }
   POST /api/season/premium { season_id }
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Gift, Crown, Lock, CheckCircle2, Loader2, AlertCircle, Star } from "lucide-react";
import { fetchSeasonData, claimSeasonReward, buySeasonPremium } from "../lib/api";
import type { SeasonDataResponse, SeasonReward } from "../types";

export default function Season() {
  const [data, setData]       = useState<SeasonDataResponse | null>(null);
  const [error, setError]     = useState("");
  const [busy, setBusy]       = useState<string | null>(null); // "claim:5:free" | "premium"
  const [toast, setToast]     = useState<string | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }, []);

  useEffect(() => {
    fetchSeasonData()
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

  const handleClaim = useCallback(async (level: number, isPremium: boolean) => {
    if (!data || busy) return;
    const key = `claim:${level}:${isPremium ? "prem" : "free"}`;
    setBusy(key);
    try {
      const res = await claimSeasonReward(data.season.id, level, isPremium);
      if (res.ok) {
        showToast(`Награда ${isPremium ? "Premium" : "Free"} (ур. ${level}) получена! 🎁`);
        // обновляем локальный claimed список
        setData(prev => {
          if (!prev) return prev;
          const prog = { ...prev.progress };
          if (isPremium) {
            prog.claimed_premium = [...(prog.claimed_premium ?? []), level];
          } else {
            prog.claimed_free = [...(prog.claimed_free ?? []), level];
          }
          return { ...prev, progress: prog };
        });
      } else {
        showToast(res.error ?? "Недоступно");
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(null);
    }
  }, [data, busy, showToast]);

  const handleBuyPremium = useCallback(async () => {
    if (!data || busy) return;
    setBusy("premium");
    try {
      const res = await buySeasonPremium(data.season.id);
      if (res.ok) {
        showToast("Premium пропуск активирован! 👑");
        setData(prev => prev ? { ...prev, progress: { ...prev.progress, has_premium: true } } : prev);
      } else {
        showToast(res.error ?? "Недостаточно средств");
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(null);
    }
  }, [data, busy, showToast]);

  /* ── Состояния загрузки/ошибки ── */
  if (error === "No active season" || (error && error.includes("404"))) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3 p-6 text-center" style={{ color: "var(--text-hint)" }}>
        <Star size={40} strokeWidth={1.2} />
        <p className="font-medium">Сезон не активен</p>
        <p className="text-sm">Следите за анонсами — новый сезон скоро начнётся!</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <AlertCircle size={32} className="mx-auto mb-2" />
        <p className="font-medium">Ошибка</p>
        <p className="text-sm mt-1 break-all">{error}</p>
      </div>
    );
  }

  if (!data) return <SeasonSkeleton />;

  const { season, progress, rewards } = data;
  const hasPremium = progress.has_premium;
  const userLevel  = progress.level ?? 0;

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-2">

      {/* ── Шапка сезона ── */}
      <div className="glass-hero p-4">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h2 className="text-lg font-bold flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: "var(--accent-soft)" }}>
                <Star size={16} style={{ color: "var(--accent)" }} />
              </div>
              {season.name}
            </h2>
            {season.end_date && (
              <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>
                До: {new Date(season.end_date).toLocaleDateString("ru-RU")}
              </p>
            )}
          </div>
          {!hasPremium && (
            <button
              onClick={handleBuyPremium}
              disabled={busy === "premium"}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-bold transition-opacity disabled:opacity-50 btn-primary"
            >
              {busy === "premium" ? <Loader2 size={14} className="animate-spin" /> : <Crown size={14} />}
              Premium 💎
            </button>
          )}
          {hasPremium && (
            <span className="flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-full"
              style={{ backgroundColor: "#f59e0b22", color: "#f59e0b" }}>
              <Crown size={12} /> Premium
            </span>
          )}
        </div>

        {/* Прогресс уровня */}
        <div className="flex items-center justify-between text-xs mb-1" style={{ color: "var(--text-hint)" }}>
          <span>Уровень сезона</span>
          <span className="tabular-nums font-semibold" style={{ color: "var(--text-primary)" }}>
            {userLevel}
          </span>
        </div>
        <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: "var(--border)" }}>
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: `${Math.min(100, Math.round(((progress.xp ?? 0) % (progress.xp_per_level ?? 100)) / (progress.xp_per_level ?? 100) * 100))}%`, backgroundColor: "var(--accent)" }}
          />
        </div>
      </div>

      {/* ── Легенда треков ── */}
      <div className="flex items-center gap-3 px-1">
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-hint)" }}>
          <Gift size={12} style={{ color: "#22c55e" }} />
          <span>Бесплатный</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-hint)" }}>
          <Crown size={12} style={{ color: "#f59e0b" }} />
          <span>Премиум (💎 Кристаллы)</span>
        </div>
      </div>

      {/* ── Трек наград ── */}
      <div className="space-y-2">
        {rewards.map((reward) => (
          <RewardRow
            key={reward.level}
            reward={reward}
            userLevel={userLevel}
            hasPremium={hasPremium}
            claimedFree={progress.claimed_free ?? []}
            claimedPremium={progress.claimed_premium ?? []}
            onClaim={handleClaim}
            busy={busy}
          />
        ))}
      </div>

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

/* ── Строка одного уровня награды ── */
interface RewardRowProps {
  reward: SeasonReward;
  userLevel: number;
  hasPremium: boolean;
  claimedFree: number[];
  claimedPremium: number[];
  onClaim: (level: number, isPremium: boolean) => void;
  busy: string | null;
}

function RewardRow({ reward, userLevel, hasPremium, claimedFree, claimedPremium, onClaim, busy }: RewardRowProps) {
  const unlocked       = userLevel >= reward.level;
  const freeClaimed    = claimedFree.includes(reward.level);
  const premClaimed    = claimedPremium.includes(reward.level);
  const freeKey        = `claim:${reward.level}:free`;
  const premKey        = `claim:${reward.level}:prem`;

  // Safe labels: avoid "+undefined 🪙" when mora is null/undefined
  const freeMora  = reward.free_mora  ?? 0;
  const premMora  = reward.premium_mora ?? 0;
  const freeXp    = reward.free_xp    ?? 0;
  const premXp    = reward.premium_xp ?? 0;

  const freeLabel = reward.free_reward
    ? reward.free_reward
    : freeMora > 0 ? `+${freeMora} 🪙` : null;

  const premLabel = reward.premium_reward
    ? reward.premium_reward
    : premMora > 0 ? `+${premMora} 🪙` : null;

  const hasPremReward = premLabel != null || premXp > 0;

  return (
    <div
      className={`rounded-xl overflow-hidden ${!unlocked ? "opacity-55" : ""}`}
      style={{ backgroundColor: "var(--bg-secondary)" }}
    >
      {/* Заголовок строки */}
      <div className="flex items-center gap-3 px-3 pt-3 pb-2">
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold shrink-0"
          style={{
            backgroundColor: unlocked ? "var(--accent)" : "var(--border)",
            color: unlocked ? "#fff" : "var(--text-hint)",
          }}
        >
          {reward.level}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: "var(--text-hint)" }}>
              Уровень {reward.level}
            </span>
            {!unlocked && <Lock size={10} style={{ color: "var(--text-hint)" }} />}
            {unlocked && freeClaimed && (!hasPremReward || !hasPremium || premClaimed) && (
              <CheckCircle2 size={12} style={{ color: "#22c55e" }} />
            )}
          </div>
        </div>
      </div>

      <div className="px-3 pb-3 space-y-1.5">
        {/* Трек: Бесплатный */}
        {freeLabel && (
          <div className="flex items-center justify-between gap-2 rounded-lg px-2.5 py-2"
            style={{ backgroundColor: "var(--bg-primary)" }}>
            <div className="flex items-center gap-1.5 min-w-0">
              <Gift size={13} style={{ color: "#22c55e" }} />
              <p className="text-xs truncate" style={{ color: "var(--text-primary)" }}>
                {freeLabel}
                {freeXp > 0 && <span style={{ color: "var(--text-hint)" }}>{` · +${freeXp} XP`}</span>}
              </p>
            </div>
            {unlocked && !freeClaimed && (
              <button
                onClick={() => onClaim(reward.level, false)}
                disabled={!!busy}
                className="text-[10px] font-semibold px-2 py-0.5 rounded-md transition-opacity disabled:opacity-50 shrink-0"
                style={{ backgroundColor: "#22c55e", color: "#fff" }}
              >
                {busy === freeKey ? <Loader2 size={10} className="animate-spin inline" /> : "Взять"}
              </button>
            )}
            {freeClaimed && <CheckCircle2 size={13} className="shrink-0" style={{ color: "#22c55e" }} />}
          </div>
        )}

        {/* Трек: Премиум (Кристаллы) */}
        {hasPremReward && (
          <div className="flex items-center justify-between gap-2 rounded-lg px-2.5 py-2"
            style={{ backgroundColor: "var(--bg-primary)", opacity: hasPremium ? 1 : 0.6 }}>
            <div className="flex items-center gap-1.5 min-w-0">
              {hasPremium
                ? <Crown size={13} style={{ color: "#f59e0b" }} />
                : <Lock size={13} style={{ color: "var(--text-hint)" }} />}
              <p className="text-xs truncate" style={{ color: hasPremium ? "#f59e0b" : "var(--text-hint)" }}>
                {premLabel ?? "—"}
                {premXp > 0 && <span style={{ color: hasPremium ? "#f59e0b88" : "var(--border)" }}>{` · +${premXp} XP`}</span>}
              </p>
            </div>
            {unlocked && hasPremium && !premClaimed && (
              <button
                onClick={() => onClaim(reward.level, true)}
                disabled={!!busy}
                className="text-[10px] font-semibold px-2 py-0.5 rounded-md transition-opacity disabled:opacity-50 shrink-0"
                style={{ backgroundColor: "#f59e0b", color: "#000" }}
              >
                {busy === premKey ? <Loader2 size={10} className="animate-spin inline" /> : "Взять"}
              </button>
            )}
            {premClaimed && <CheckCircle2 size={13} className="shrink-0" style={{ color: "#f59e0b" }} />}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Скелетон ── */
function SeasonSkeleton() {
  return (
    <div className="p-4 space-y-3 animate-pulse">
      <div className="skeleton h-28 rounded-2xl" />
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="skeleton h-14 rounded-xl" />
      ))}
    </div>
  );
}
