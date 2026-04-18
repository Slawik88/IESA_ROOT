/* ──────────────────────────────────────────────────────────────

   Season.tsx — Боевой Пропуск (Battle Pass) — Редизайн

   GET /api/season/data

   POST /api/season/claim  { season_id, level, is_premium }

   POST /api/season/premium { season_id }

   ────────────────────────────────────────────────────────────── */

import { useEffect, useState, useCallback, useRef } from "react";

import { Gift, Crown, Lock, CheckCircle2, Loader2, AlertCircle, Star, Sparkles, Zap } from "lucide-react";

import { fetchSeasonData, claimSeasonReward, buySeasonPremium, trackEvent } from "../lib/api";

import type { SeasonDataResponse, SeasonReward } from "../types";

import { useToast } from "../components/ToastContext";



export default function Season() {

  const [data, setData]   = useState<SeasonDataResponse | null>(null);

  const [error, setError] = useState("");

  const [busy, setBusy]   = useState<string | null>(null);

  const [justClaimed, setJustClaimed] = useState<string | null>(null);

  const { toast } = useToast();

  const xpBarRef = useRef<HTMLDivElement>(null);



  useEffect(() => {

    fetchSeasonData()

      .then(setData)

      .catch((e: Error) => setError(e.message));

  }, []);



  // Animate XP bar on load

  useEffect(() => {

    if (!data || !xpBarRef.current) return;

    const xp    = data.progress.xp ?? 0;

    const perLv = data.progress.xp_per_level ?? 100;

    const pct   = Math.min(100, Math.round((xp % perLv) / perLv * 100));

    setTimeout(() => {

      if (xpBarRef.current) xpBarRef.current.style.width = `${pct}%`;

    }, 300);

  }, [data]);



  const handleClaim = useCallback(async (level: number, isPremium: boolean) => {

    if (!data || busy) return;

    const key = `claim:${level}:${isPremium ? "prem" : "free"}`;

    setBusy(key);

    try {

      const res = await claimSeasonReward(data.season.id, level, isPremium);

      if (res.ok) {
        trackEvent(isPremium ? "season_claim_premium" : "season_claim_free");
        setJustClaimed(key);

        setTimeout(() => setJustClaimed(null), 800);

        toast(`🎁 Награда Ур.${level}${isPremium ? " (Premium)" : ""} получена!`, "success");

        setData(prev => {

          if (!prev) return prev;

          const prog = { ...prev.progress };

          if (isPremium) prog.claimed_premium = [...(prog.claimed_premium ?? []), level];

          else prog.claimed_free = [...(prog.claimed_free ?? []), level];

          return { ...prev, progress: prog };

        });

      } else {

        toast(res.error ?? "Недоступно", "warning");

      }

    } catch (e: unknown) {

      toast(e instanceof Error ? e.message : "Ошибка", "error");

    } finally {

      setBusy(null);

    }

  }, [data, busy, toast]);



  const handleBuyPremium = useCallback(async () => {

    if (!data || busy) return;

    setBusy("premium");

    try {

      const res = await buySeasonPremium(data.season.id);

      if (res.ok) {

        toast("👑 Premium пропуск активирован!", "success");

        setData(prev => prev ? { ...prev, progress: { ...prev.progress, has_premium: true } } : prev);

      } else {

        toast(res.error ?? "Недостаточно средств", "error");

      }

    } catch (e: unknown) {

      toast(e instanceof Error ? e.message : "Ошибка", "error");

    } finally {

      setBusy(null);

    }

  }, [data, busy, toast]);



  /* ── Состояния ── */

  if (error === "No active season" || (error && error.includes("404"))) {

    return (

      <div className="flex flex-col items-center justify-center min-h-[70vh] gap-4 p-6 text-center"

        style={{ color: "var(--text-hint)" }}>

        <div className="w-20 h-20 rounded-full flex items-center justify-center"

          style={{ backgroundColor: "var(--bg-secondary)" }}>

          <Star size={36} strokeWidth={1} />

        </div>

        <p className="font-semibold text-lg" style={{ color: "var(--text-primary)" }}>Сезон не активен</p>

        <p className="text-sm max-w-[240px]">Следите за анонсами — новый сезон скоро начнётся!</p>

      </div>

    );

  }



  if (error) {

    return (

      <div className="p-6 text-center" style={{ color: "#e74c3c" }}>

        <AlertCircle size={32} className="mx-auto mb-3" />

        <p className="font-semibold mb-1">Ошибка</p>

        <p className="text-sm break-all">{error}</p>

        <button

          onClick={() => { setError(""); fetchSeasonData().then(setData).catch((e: Error) => setError(e.message)); }}

          className="mt-4 text-sm underline"

          style={{ color: "var(--accent)" }}

        >Попробовать снова</button>

      </div>

    );

  }



  if (!data) return <SeasonSkeleton />;



  const { season, progress, rewards } = data;

  const hasPremium   = progress.has_premium;

  const userLevel    = progress.level ?? 0;

  const xp           = progress.xp ?? 0;

  const perLevel     = progress.xp_per_level ?? 100;

  const xpInLevel    = xp % perLevel;

  const xpPct        = Math.min(100, Math.round(xpInLevel / perLevel * 100));

  const claimedTotal = (progress.claimed_free?.length ?? 0) + (progress.claimed_premium?.length ?? 0);

  const maxRewards   = rewards.length * (hasPremium ? 2 : 1);



  return (

    <div className="animate-fadeIn pb-4" style={{ backgroundColor: "var(--bg-primary)" }}>



      {/* ── HERO — Шапка сезона ─────────────────────────────── */}

      <div className="relative overflow-hidden glass-hero px-4 pt-safe pb-4">

        {/* Фоновый декор */}

        <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden>

          <div className="absolute -top-8 -right-8 w-40 h-40 rounded-full opacity-10"

            style={{ background: "radial-gradient(circle, var(--accent) 0%, transparent 70%)" }} />

          <div className="absolute -bottom-4 -left-4 w-32 h-32 rounded-full opacity-8"

            style={{ background: "radial-gradient(circle, #f59e0b 0%, transparent 70%)" }} />

        </div>



        {/* Заголовок */}

        <div className="flex items-start justify-between mb-4 relative">

          <div>

            <div className="flex items-center gap-2 mb-1">

              <div className="w-7 h-7 rounded-lg flex items-center justify-center"

                style={{ background: "var(--accent-soft)" }}>

                <Sparkles size={14} style={{ color: "var(--accent)" }} />

              </div>

              <span className="text-[11px] font-semibold uppercase tracking-widest"

                style={{ color: "var(--accent)" }}>Battle Pass</span>

            </div>

            <h2 className="text-xl font-black" style={{ color: "var(--text-primary)" }}>

              {season.name}

            </h2>

            {season.end_date && (

              <p className="text-[11px] mt-0.5" style={{ color: "var(--text-hint)" }}>

                До: {new Date(season.end_date).toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}

              </p>

            )}

          </div>

          {!hasPremium ? (

            <button

              onClick={handleBuyPremium}

              disabled={busy === "premium"}

              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold disabled:opacity-50 btn-primary shrink-0"

            >

              {busy === "premium"

                ? <Loader2 size={13} className="animate-spin" />

                : <Crown size={13} />}

              Premium

            </button>

          ) : (

            <span className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl text-xs font-bold shrink-0"

              style={{ backgroundColor: "rgba(245,158,11,0.18)", color: "#f59e0b",

                       border: "1px solid rgba(245,158,11,0.3)" }}>

              <Crown size={12} /> Premium

            </span>

          )}

        </div>



        {/* Уровень + XP бар */}

        <div className="relative">

          <div className="flex items-end justify-between mb-2">

            <div className="flex items-baseline gap-1.5">

              <span className="text-3xl font-black tabular-nums" style={{ color: "var(--accent)" }}>

                {userLevel}

              </span>

              <span className="text-sm font-semibold" style={{ color: "var(--text-hint)" }}>уровень</span>

            </div>

            <div className="text-right">

              <p className="text-[11px] font-semibold" style={{ color: "var(--text-hint)" }}>

                {xpInLevel.toLocaleString("ru")} / {perLevel.toLocaleString("ru")} XP

              </p>

              <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>

                {claimedTotal} / {maxRewards} наград

              </p>

            </div>

          </div>



          <div className="h-3 rounded-full overflow-hidden relative"

            style={{ backgroundColor: "color-mix(in srgb, var(--border) 80%, var(--bg-primary))" }}>

            <div

              ref={xpBarRef}

              className="h-full rounded-full bp-xp-bar"

              style={{

                width: "0%",

                transition: "width 1.2s cubic-bezier(0.4,0,0.2,1)",

                background: "linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 70%, #fff))",

                boxShadow: "0 0 10px 2px var(--accent-glow)",

              }}

            />

          </div>

          <p className="text-[10px] mt-1 text-right" style={{ color: "var(--text-hint)" }}>{xpPct}%</p>

        </div>

      </div>



      {/* ── Легенда ─────────────────────────────────────────── */}

      <div className="flex items-center gap-4 px-4 py-2.5">

        <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-hint)" }}>

          <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: "#22c55e" }} />

          <span>Бесплатный</span>

        </div>

        <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-hint)" }}>

          <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: "#f59e0b" }} />

          <span>Premium</span>

        </div>

      </div>



      {/* ── Трек наград ─────────────────────────────────────── */}

      <div className="px-3 space-y-2">

        {rewards.map((reward, i) => (

          <BPRewardCard

            key={reward.level}

            reward={reward}

            userLevel={userLevel}

            hasPremium={hasPremium}

            claimedFree={progress.claimed_free ?? []}

            claimedPremium={progress.claimed_premium ?? []}

            onClaim={handleClaim}

            busy={busy}

            justClaimed={justClaimed}

            index={i}

          />

        ))}

      </div>

    </div>

  );

}



/* ── Карточка одного уровня ─────────────────────────────────── */

interface BPRewardCardProps {

  reward: SeasonReward;

  userLevel: number;

  hasPremium: boolean;

  claimedFree: number[];

  claimedPremium: number[];

  onClaim: (level: number, isPremium: boolean) => void;

  busy: string | null;

  justClaimed: string | null;

  index: number;

}



function BPRewardCard({

  reward, userLevel, hasPremium,

  claimedFree, claimedPremium, onClaim, busy, justClaimed, index,

}: BPRewardCardProps) {

  const unlocked    = userLevel >= reward.level;

  const freeClaimed = claimedFree.includes(reward.level);

  const premClaimed = claimedPremium.includes(reward.level);

  const freeKey     = `claim:${reward.level}:free`;

  const premKey     = `claim:${reward.level}:prem`;



  const freeMora  = reward.free_mora     ?? 0;

  const premMora  = reward.premium_mora  ?? 0;

  const freeXp    = reward.free_xp       ?? 0;

  const premXp    = reward.premium_xp    ?? 0;



  const freeLabel = reward.free_reward    ?? (freeMora > 0 ? `+${freeMora} 🪙` : freeXp > 0 ? `+${freeXp} XP` : null);

  const premLabel = reward.premium_reward ?? (premMora > 0 ? `+${premMora} 🪙` : premXp > 0 ? `+${premXp} XP` : null);

  const hasPremReward = premLabel != null || premXp > 0;



  const allDone = freeClaimed && (!hasPremReward || !hasPremium || premClaimed);



  return (

    <div

      className={`glass-card overflow-hidden transition-all duration-300 ${!unlocked ? "opacity-50" : ""}`}

      style={{

        animationDelay: `${index * 40}ms`,

        border: allDone ? "1px solid rgba(34,197,94,0.35)" : undefined,

      }}

    >

      {/* Шапка карточки */}

      <div className="flex items-center gap-3 px-3 pt-3 pb-2.5">

        <div

          className={`w-9 h-9 rounded-xl flex items-center justify-center text-xs font-black shrink-0 transition-all ${allDone ? "bp-level-pop" : ""}`}

          style={{

            background: allDone

              ? "linear-gradient(135deg, #22c55e, #16a34a)"

              : unlocked

              ? "linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 70%, #fff))"

              : "var(--bg-secondary)",

            color: unlocked ? "#fff" : "var(--text-hint)",

            boxShadow: allDone ? "0 0 12px rgba(34,197,94,0.5)" : unlocked ? "0 0 8px var(--accent-glow)" : "none",

          }}

        >

          {allDone ? <CheckCircle2 size={15} /> : reward.level}

        </div>

        <p className="flex-1 text-[11px] font-semibold" style={{ color: "var(--text-hint)" }}>

          Уровень {reward.level}

        </p>

        {!unlocked && <Lock size={13} style={{ color: "var(--text-hint)" }} />}

      </div>



      {/* Треки */}

      <div className="px-3 pb-3 grid grid-cols-2 gap-2">

        {freeLabel ? (

          <TrackCell

            label={freeLabel}

            xp={freeXp}

            claimed={freeClaimed}

            unlocked={unlocked}

            available

            color="#22c55e"

            icon={<Gift size={12} />}

            busy={busy === freeKey}

            justClaimed={justClaimed === freeKey}

            onClaim={() => onClaim(reward.level, false)}

          />

        ) : (

          <EmptyCell />

        )}



        {hasPremReward ? (

          <TrackCell

            label={premLabel ?? "—"}

            xp={premXp}

            claimed={premClaimed}

            unlocked={unlocked}

            available={hasPremium}

            color="#f59e0b"

            icon={hasPremium ? <Crown size={12} /> : <Lock size={12} />}

            busy={busy === premKey}

            justClaimed={justClaimed === premKey}

            onClaim={() => onClaim(reward.level, true)}

          />

        ) : (

          <EmptyCell />

        )}

      </div>

    </div>

  );

}



function EmptyCell() {

  return (

    <div className="rounded-xl p-2.5 flex items-center justify-center"

      style={{ backgroundColor: "var(--bg-secondary)", opacity: 0.4 }}>

      <span className="text-[10px]" style={{ color: "var(--text-hint)" }}>—</span>

    </div>

  );

}



/* ── Ячейка трека ───────────────────────────────────────────── */

interface TrackCellProps {

  label: string;

  xp: number;

  claimed: boolean;

  unlocked: boolean;

  available: boolean;

  color: string;

  icon: React.ReactNode;

  busy: boolean;

  justClaimed: boolean;

  onClaim: () => void;

}



function TrackCell({ label, xp, claimed, unlocked, available, color, icon, busy, justClaimed, onClaim }: TrackCellProps) {

  const canClaim = unlocked && available && !claimed;



  return (

    <div

      className={`rounded-xl p-2.5 flex flex-col gap-1.5 transition-all duration-300 ${justClaimed ? "bp-level-pop" : ""}`}

      style={{

        backgroundColor: claimed

          ? `color-mix(in srgb, ${color} 12%, var(--bg-secondary))`

          : "var(--bg-secondary)",

        border: `1px solid ${claimed ? color + "40" : canClaim ? color + "30" : "var(--border)"}`,

        opacity: !available && !claimed ? 0.55 : 1,

      }}

    >

      <div className="flex items-center gap-1 min-w-0">

        <span style={{ color }}>{icon}</span>

        <p className="text-[11px] font-semibold truncate leading-tight"

          style={{ color: available ? "var(--text-primary)" : "var(--text-hint)" }}>

          {label}

        </p>

      </div>

      {xp > 0 && (

        <div className="flex items-center gap-1">

          <Zap size={9} style={{ color }} />

          <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>+{xp} XP</p>

        </div>

      )}



      {claimed ? (

        <div className="flex items-center gap-1 mt-0.5">

          <CheckCircle2 size={12} style={{ color }} />

          <span className="text-[10px] font-semibold" style={{ color }}>Получено</span>

        </div>

      ) : canClaim ? (

        <button

          onClick={onClaim}

          disabled={busy}

          className="w-full py-1 rounded-lg text-[11px] font-bold transition-all disabled:opacity-50 active:scale-95"

          style={{ backgroundColor: color, color: "#fff", boxShadow: `0 0 8px ${color}55` }}

        >

          {busy ? <Loader2 size={10} className="animate-spin inline" /> : "Взять"}

        </button>

      ) : (

        <span className="text-[10px]" style={{ color: "var(--text-hint)" }}>

          {!available && unlocked ? "👑 Premium" : "🔒"}

        </span>

      )}

    </div>

  );

}



/* ── Скелетон ── */

function SeasonSkeleton() {

  return (

    <div className="p-4 space-y-3 animate-pulse">

      <div className="skeleton h-36 rounded-2xl" />

      <div className="skeleton h-6 rounded-full w-1/2 mx-auto" />

      {Array.from({ length: 6 }).map((_, i) => (

        <div key={i} className="skeleton h-24 rounded-xl" />

      ))}

    </div>

  );

}

