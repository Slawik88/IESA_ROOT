/* ──────────────────────────────────────────────────────────────
   BossFight.tsx — Tactical Solo Boss Fight
   ATB Stamina + QTE (Telegraph + Weak Spots)
   ────────────────────────────────────────────────────────────── */
import { useState, useEffect, useRef, useCallback } from "react";
import {
  fetchBossStatus, startBoss, attackBoss, forfeitBoss, fetchInventory, consumePotion,
  type BossSession, type BossProgress,
} from "../lib/api";
import type { InventoryItem } from "../types";
import { Loader2, Shield, Zap, Sword, Swords, Pause, Play, Flag, FlaskConical } from "lucide-react";
import CoupleBoss from "./CoupleBoss";

// ─── Constants ────────────────────────────────────────────────
const STAMINA_MAX         = 100;
const STAMINA_REGEN       = 8;          // per second
const SKILL_FAST_COST     = 18;
const SKILL_HEAVY_COST    = 45;
const SKILL_BLOCK_COST    = 22;
const SKILL_HEAVY_CD      = 8000;       // ms
const BLOCK_DURATION      = 3000;       // ms
const WEAKSPOT_DURATION   = 1600;       // ms
const TELEGRAPH_WARN_MS   = 2200;       // boss warning before attack

const BOSS_NAMES: Record<number, string> = {
  1: "Страж Теней",   2: "Пожиратель Звёзд", 3: "Повелитель Бездны",
  4: "Отражение Хаоса", 5: "Разрушитель Мира",
};
function bossName(level: number) {
  return BOSS_NAMES[level] ?? `Тёмный Страж Ур. ${level}`;
}

const BOSS_ART: Record<number, string> = {
  1: "👹", 2: "🐉", 3: "💀", 4: "👾", 5: "🌑",
};
function bossArt(level: number) {
  return BOSS_ART[level] ?? "👾";
}

// ─── Types ────────────────────────────────────────────────────
interface WeakSpot { id: number; x: number; y: number; }
interface FloatText { id: number; text: string; x: number; y: number; color: string; }

interface Props {
  userId: number | null;
  chatId: number | null;
}

// ─── Helpers ──────────────────────────────────────────────────
function fmt(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(0) + "K";
  return String(n);
}

// ── Constants ──────────────────────────────────────────────────

// ─── Component ────────────────────────────────────────────────
export default function BossFight({ userId: _userId, chatId }: Props) {
  // Boss mode tabs
  const [mode, setMode] = useState<"solo" | "couple">("solo");

  // Remote state
  const [session, setSession]   = useState<BossSession | null>(null);
  const [progress, setProgress] = useState<BossProgress | null>(null);
  const [nextLevel, setNextLevel] = useState(1);
  const [dailyLimit, setDailyLimit] = useState(2);
  const [dailyUsed, setDailyUsed] = useState(0);
  const [resetText, setResetText] = useState<string>("");
  const [loading, setLoading]   = useState(true);
  const [starting, setStarting] = useState(false);
  const [toast, setToast]       = useState<string | null>(null);
  const [fightTimeLeft, setFightTimeLeft] = useState<number | null>(null);

  // Local fight state
  const [bossHp, setBossHp]       = useState(0);
  const [bossMaxHp, setBossMaxHp] = useState(1);
  const [playerHp, setPlayerHp]   = useState(100);
  const [stamina, setStamina]      = useState(STAMINA_MAX);
  const [blocking, setBlocking]    = useState(false);
  const [heavyCd, setHeavyCd]      = useState(0);    // ms remaining
  const [attacking, setAttacking]  = useState(false);

  // Boss telegraph
  const [telegraphing, setTelegraphing] = useState(false);
  const [telegraphPct, setTelegraphPct] = useState(100);

  // Weak spots
  const [weakSpots, setWeakSpots] = useState<WeakSpot[]>([]);
  const nextWsId = useRef(0);

  // Float damage texts
  const [floats, setFloats] = useState<FloatText[]>([]);
  const nextFid = useRef(0);

  // Pause + potions + equipment
  const [paused, setPaused]     = useState(false);
  const [potions, setPotions]   = useState<InventoryItem[]>([]);
  const [equipped, setEquipped] = useState<InventoryItem[]>([]);
  const [usingPotion, setUsingPotion] = useState<number | null>(null);
  const [showPotions, setShowPotions] = useState(false);

  // Fight active flag
  const fightActive = session != null && !session.is_completed && playerHp > 0;

  // Refs for intervals (avoid stale closures)
  const staminaRef  = useRef(stamina);
  const blockingRef = useRef(blocking);
  const playerHpRef = useRef(playerHp);
  staminaRef.current   = stamina;
  blockingRef.current  = blocking;
  playerHpRef.current  = playerHp;

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }, []);

  const addFloat = useCallback((text: string, x: number, y: number, color: string) => {
    const id = nextFid.current++;
    setFloats(f => [...f, { id, text, x, y, color }]);
    setTimeout(() => setFloats(f => f.filter(t => t.id !== id)), 900);
  }, []);

  // ── Load boss status ────────────────────────────────────────
  const loadStatus = useCallback(async () => {
    if (!chatId) return;
    try {
      const r = await fetchBossStatus(chatId);
      setSession(r.session);
      setProgress(r.progress);
      setNextLevel(r.next_level);
      setDailyLimit(r.daily_limit);
      setDailyUsed(r.daily_used);
      setResetText(r.reset_in_text);
      if (r.session && !r.session.is_completed) {
        setBossHp(r.session.boss_current_hp);
        setBossMaxHp(r.session.boss_max_hp);
        setPlayerHp(100);
        setStamina(STAMINA_MAX);
        setFightTimeLeft(r.session.fight_time_left_seconds ?? null);
      } else {
        setFightTimeLeft(null);
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [chatId]);

  const loadPotions = useCallback(async () => {
    if (!chatId) return;
    const COMBAT_SLOTS = ["weapon", "armor", "helmet", "boots", "artifact"];
    try {
      const inv = await fetchInventory(chatId);
      setPotions(inv.items.filter(i => i.slot === "potion"));
      setEquipped(inv.items.filter(i => i.equipped && COMBAT_SLOTS.includes(i.slot ?? "")));
    } catch { /* ignore */ }
  }, [chatId]);

  useEffect(() => { loadStatus(); }, [loadStatus]);
  useEffect(() => { loadPotions(); }, [loadPotions]);

  useEffect(() => {
    if (!fightActive || paused || fightTimeLeft == null) return;
    const id = setInterval(() => {
      setFightTimeLeft((prev) => {
        if (prev == null) return prev;
        return Math.max(0, prev - 1);
      });
    }, 1000);
    return () => clearInterval(id);
  }, [fightActive, paused, fightTimeLeft]);

  // ── Stamina regen ───────────────────────────────────────────
  useEffect(() => {
    if (!fightActive || paused) return;
    const id = setInterval(() => {
      setStamina(s => Math.min(STAMINA_MAX, s + STAMINA_REGEN));
    }, 1000);
    return () => clearInterval(id);
  }, [fightActive, paused]);

  // ── Heavy cooldown ticker ───────────────────────────────────
  useEffect(() => {
    if (heavyCd <= 0) return;
    const id = setInterval(() => {
      setHeavyCd(c => Math.max(0, c - 100));
    }, 100);
    return () => clearInterval(id);
  }, [heavyCd]);

  // ── Boss telegraph (random interval 6-14s) ──────────────────
  useEffect(() => {
    if (!fightActive || paused) return;

    let telegraphTimeout: ReturnType<typeof setTimeout>;
    let warningInterval: ReturnType<typeof setInterval>;

    const scheduleNext = () => {
      const delay = 6000 + Math.random() * 8000;
      telegraphTimeout = setTimeout(() => {
        // Start telegraph warning
        setTelegraphing(true);
        setTelegraphPct(100);

        const start = Date.now();
        warningInterval = setInterval(() => {
          const elapsed = Date.now() - start;
          const pct = Math.max(0, 100 - (elapsed / TELEGRAPH_WARN_MS) * 100);
          setTelegraphPct(pct);
          if (elapsed >= TELEGRAPH_WARN_MS) {
            clearInterval(warningInterval);
            setTelegraphing(false);
            // Boss attacks
            const dmg = blockingRef.current
              ? Math.floor(5 + Math.random() * 8)   // blocked: tiny damage
              : Math.floor(18 + Math.random() * 20); // unblocked: big hit
            setPlayerHp(hp => {
              const next = Math.max(0, hp - dmg);
              addFloat(`-${dmg}`, 50, 40, "#f87171");
              if (next === 0 && chatId) {
                forfeitBoss(chatId).catch(() => {});
              }
              return next;
            });
            scheduleNext();
          }
        }, 50);
      }, delay);
    };

    scheduleNext();
    return () => {
      clearTimeout(telegraphTimeout);
      clearInterval(warningInterval);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fightActive, paused]);

  // ── Weak spots (random interval 5-10s) ─────────────────────
  useEffect(() => {
    if (!fightActive || paused) return;
    const schedule = () => {
      const delay = 5000 + Math.random() * 5000;
      return setTimeout(() => {
        const id = nextWsId.current++;
        const ws: WeakSpot = {
          id,
          x: 10 + Math.random() * 80,  // % of boss area
          y: 10 + Math.random() * 80,
        };
        setWeakSpots(w => [...w, ws]);
        setTimeout(() => {
          setWeakSpots(w => w.filter(s => s.id !== id));
        }, WEAKSPOT_DURATION);
      }, delay);
    };
    let t = schedule();
    const repeat = setInterval(() => {
      clearTimeout(t);
      t = schedule();
    }, 8000);
    return () => { clearTimeout(t); clearInterval(repeat); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fightActive, paused]);
  const doStart = async () => {
    if (!chatId) return;
    setStarting(true);
    try {
      const r = await startBoss(chatId);
      if (!r.ok) { showToast("⚠️ " + (r.error ?? "Ошибка")); return; }
      setSession(r.session);
      setBossHp(r.session.boss_max_hp);
      setBossMaxHp(r.session.boss_max_hp);
      setPlayerHp(100);
      setStamina(STAMINA_MAX);
      setHeavyCd(0);
      setBlocking(false);
      setWeakSpots([]);
      setPaused(false);
      setFightTimeLeft(r.session.fight_time_left_seconds ?? r.session.fight_timeout_seconds ?? 120);
      loadPotions();
    } catch (e: unknown) {
      showToast("⚠️ " + (e instanceof Error ? e.message : "Ошибка"));
    } finally { setStarting(false); }
  };

  // ── Use potion during fight ──────────────────────────────────
  const doUsePotion = useCallback(async (item: InventoryItem) => {
    if (!chatId) return;
    setUsingPotion(item.id);
    try {
      const r = await consumePotion(chatId, item.id);
      if (r.success) {
        // Apply local HP heal for hp_potion
        if (item.key === "hp_potion" || item.key === "hp_potion_superior") {
          setPlayerHp(hp => Math.min(100, hp + 50));
          addFloat("+50 ❤️", 20, 60, "#22c55e");
        } else {
          addFloat("⚡ " + item.name, 20, 60, "#a78bfa");
        }
        showToast(r.message);
        loadPotions(); // refresh list (consumed one)
      } else {
        showToast("❌ " + r.message);
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally { setUsingPotion(null); }
  }, [chatId, addFloat, showToast, loadPotions]);

  // ── Attack backend ──────────────────────────────────────────
  const doAttackBackend = useCallback(async (isCrit?: boolean) => {
    if (!chatId || attacking) return;
    if (fightTimeLeft != null && fightTimeLeft <= 0) {
      showToast("⏳ Время боя вышло");
      loadStatus();
      return;
    }
    setAttacking(true);
    try {
      const r = await attackBoss(chatId);
      if (!r.ok) return;
      const dmg = isCrit ? Math.floor(r.damage_dealt * 1.5) : r.damage_dealt;
      setBossHp(r.boss_hp);
      if (typeof r.fight_time_left_seconds === "number") {
        setFightTimeLeft(r.fight_time_left_seconds);
      }
      addFloat(
        `${r.crit || isCrit ? "⚡ КРИТ! " : ""}−${fmt(dmg)}`,
        50 + (Math.random() - 0.5) * 30,
        30,
        r.crit || isCrit ? "#facc15" : "var(--accent)",
      );
      if (r.boss_defeated) {
        setSession(s => s ? { ...s, is_completed: 1 } : s);
        setFightTimeLeft(0);
        showToast(`🏆 Босс повержен! +${r.rewards?.mora ?? 0}🪙 +${r.rewards?.xp ?? 0}⚡`);
        await loadStatus();
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка атаки");
      loadStatus();
    }
    finally { setAttacking(false); }
  }, [chatId, attacking, addFloat, showToast, loadStatus, fightTimeLeft]);

  // ── Skill: Fast Attack ──────────────────────────────────────
  const doFast = async () => {
    if (!fightActive || stamina < SKILL_FAST_COST || attacking) return;
    setStamina(s => s - SKILL_FAST_COST);
    await doAttackBackend(false);
  };

  // ── Skill: Heavy Blow ───────────────────────────────────────
  const doHeavy = async () => {
    if (!fightActive || stamina < SKILL_HEAVY_COST || heavyCd > 0 || attacking) return;
    setStamina(s => s - SKILL_HEAVY_COST);
    setHeavyCd(SKILL_HEAVY_CD);
    await doAttackBackend(true);
    await doAttackBackend(true);  // Two hits
  };

  // ── Skill: Block ────────────────────────────────────────────
  const doBlock = () => {
    if (!fightActive || stamina < SKILL_BLOCK_COST || blocking) return;
    setStamina(s => s - SKILL_BLOCK_COST);
    setBlocking(true);
    setTimeout(() => setBlocking(false), BLOCK_DURATION);
  };

  // ── Weak spot click ─────────────────────────────────────────
  const doClickWeakspot = async (wsId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setWeakSpots(w => w.filter(s => s.id !== wsId));
    addFloat("⚠️ СЛАБОЕ МЕСТО!", 50, 25, "#f97316");
    await doAttackBackend(true);
  };

  // ── Render ──────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 size={32} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  const completed = session?.is_completed === 1 || playerHp <= 0;
  const canStart  = !session || completed;
  const dailyRemaining = Math.max(0, dailyLimit - dailyUsed);
  const fightTimeText = fightTimeLeft == null ? null : fmtSecs(fightTimeLeft);

  const SLOT_EMOJI: Record<string, string> = { weapon: "⚔️", armor: "🛡️", helmet: "🪖", boots: "👢", artifact: "💎" };

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "var(--bg-primary)" }}>
      {/* Header + Mode Tabs */}
      <div className="px-4 pt-safe pb-2 glass-heavy" style={{ borderBottom: "1px solid var(--border-accent)" }}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>⚔️ Босс</h1>
            {mode === "solo" && progress && (
              <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                Макс. уровень: {progress.max_level} • Попыток осталось: {dailyRemaining}/{dailyLimit}
              </p>
            )}
          </div>
          {mode === "solo" && (
            <div className="badge badge-accent text-xs px-3 py-1">
              Ур. {nextLevel}
            </div>
          )}
        </div>
        {/* Mode tabs */}
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => setMode("solo")}
            className="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all"
            style={{
              backgroundColor: mode === "solo" ? "var(--accent)" : "var(--bg-secondary)",
              color: mode === "solo" ? "#fff" : "var(--text-hint)",
            }}
          >
            🗡️ Соло
          </button>
          <button
            onClick={() => setMode("couple")}
            className="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all"
            style={{
              backgroundColor: mode === "couple" ? "#e84393" : "var(--bg-secondary)",
              color: mode === "couple" ? "#fff" : "var(--text-hint)",
            }}
          >
            💞 Парный
          </button>
        </div>
      </div>

      {/* Couple boss mode */}
      {mode === "couple" && (
        <CoupleBoss userId={_userId} chatId={chatId} />
      )}

      {/* Solo boss mode */}
      {mode === "solo" && <>

      <div className="mx-4 mt-3 glass-card p-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold" style={{ color: "var(--text-hint)" }}>Дневной лимит</p>
          <p className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>
            {dailyUsed}/{dailyLimit} боёв
          </p>
        </div>
        <div className="text-right">
          <p className="text-[11px] font-semibold" style={{ color: "var(--text-hint)" }}>Сброс</p>
          <p className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{resetText || "--"}</p>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className="mx-4 mt-2 px-4 py-2.5 glass-card animate-fadeIn text-center text-sm font-medium"
          style={{ color: "var(--text-primary)" }}>
          {toast}
        </div>
      )}

      {/* ── No session / completed ── */}
      {canStart && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-4">
          <div className="text-center space-y-3">
            <div className="text-8xl drop-shadow-lg animate-orb">{bossArt(nextLevel)}</div>
            <p className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>{bossName(nextLevel)}</p>
            <p className="text-sm" style={{ color: "var(--text-hint)" }}>
              HP: {fmt(7_500 + (nextLevel - 1) * 4_500)}
            </p>
            {session?.is_completed === 1 && (
              <p className="badge badge-success text-sm px-4 py-1">✅ Побеждён сегодня!</p>
            )}
            {playerHp <= 0 && !session?.is_completed && (
              <p className="badge badge-danger text-sm px-4 py-1">💀 Ты пал в бою</p>
            )}
          </div>
          {session?.is_completed !== 1 && (
            <button
              onClick={doStart}
              disabled={starting}
              className="px-8 py-3.5 rounded-2xl text-base font-bold flex items-center gap-2 disabled:opacity-50 btn-primary"
            >
              {starting ? <Loader2 size={18} className="animate-spin" /> : <Swords size={18} />}
              {starting ? "Вызов..." : "Начать битву"}
            </button>
          )}
          {session?.is_completed === 1 && (
            <button
              onClick={doStart}
              disabled={starting}
              className="px-8 py-3.5 rounded-2xl text-base font-bold flex items-center gap-2 disabled:opacity-50 btn-primary"
            >
              {starting ? <Loader2 size={18} className="animate-spin" /> : <Swords size={18} />}
              {starting ? "Вызов..." : "Следующий уровень →"}
            </button>
          )}
        </div>
      )}

      {/* ── Active fight ── */}
      {!canStart && fightActive && (
        <div className="flex-1 flex flex-col gap-2.5 px-4 pt-3 pb-4 relative">

          {/* Pause overlay */}
          {paused && (
            <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-5 rounded-2xl glass-heavy">
              <p className="text-2xl font-bold" style={{ color: "#fff" }}>⏸️ Пауза</p>
              <button
                onClick={() => setPaused(false)}
                className="flex items-center gap-2 px-6 py-3 btn-primary rounded-2xl text-sm"
              >
                <Play size={16} /> Продолжить
              </button>
              <button
                onClick={async () => {
                  setPaused(false);
                  if (chatId) {
                    try { await forfeitBoss(chatId); } catch {}
                  }
                  setPlayerHp(0);
                  showToast("🏳️ Ты сдался...");
                  loadStatus();
                }}
                className="flex items-center gap-2 px-6 py-3 rounded-2xl font-semibold text-sm btn-danger"
              >
                <Flag size={16} /> Сдаться
              </button>
            </div>
          )}

          {/* Boss info */}
          <div className={`glass-card p-4 ${telegraphing ? "animate-danger" : ""}`}>
            <div className="flex items-center gap-3">
              <div className="text-5xl relative shrink-0">
                {bossArt(session!.boss_level)}
                {/* Weak spots */}
                {weakSpots.map(ws => (
                  <button
                    key={ws.id}
                    onClick={e => doClickWeakspot(ws.id, e)}
                    className="absolute rounded-full border-2 border-yellow-400 animate-weakspot-ripple"
                    style={{
                      width: 28, height: 28,
                      left: `${ws.x}%`, top: `${ws.y}%`,
                      transform: "translate(-50%,-50%)",
                      backgroundColor: "#facc1540",
                    }}
                  />
                ))}
              </div>
              <div className="flex-1 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{bossName(session!.boss_level)}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs tabular-nums font-semibold" style={{ color: "var(--text-hint)" }}>
                      {fmt(bossHp)} / {fmt(bossMaxHp)}
                    </span>
                    <button
                      onClick={() => setPaused(true)}
                      className="p-1.5 rounded-lg glass-card-sm"
                      style={{ color: "var(--text-hint)" }}
                    >
                      <Pause size={14} />
                    </button>
                  </div>
                </div>
                <div className="progress-bar">
                  <div className="progress-bar-fill" style={{ width: `${Math.max(0, (bossHp / bossMaxHp) * 100)}%` }} />
                </div>
                <div className="flex items-center justify-between text-[11px]" style={{ color: "var(--text-hint)" }}>
                  <span>Попыток осталось: {dailyRemaining}/{dailyLimit}</span>
                  <span>⏳ {fightTimeText ?? "--"}</span>
                </div>
                {/* Telegraph bar */}
                {telegraphing && (
                  <div className="space-y-0.5">
                    <p className="text-[11px] font-bold text-red-400 animate-pulse">⚠️ АТАКА БОССА — БЛОК!</p>
                    <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "#ef444430" }}>
                      <div
                        className="h-full rounded-full transition-none"
                        style={{ width: `${telegraphPct}%`, backgroundColor: "#ef4444" }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Float damage texts */}
          <div className="relative h-8 pointer-events-none overflow-hidden">
            {floats.map(f => (
              <span
                key={f.id}
                className="absolute text-sm font-bold animate-reward-fly"
                style={{
                  left: `${f.x}%`,
                  top: `${f.y}%`,
                  color: f.color,
                  transform: "translate(-50%, -50%)",
                  textShadow: `0 0 8px ${f.color}`,
                } as React.CSSProperties}
              >
                {f.text}
              </span>
            ))}
          </div>

          {/* Player status — HP + Stamina */}
          <div className="glass-card p-3 space-y-2">
            <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-hint)" }}>
              <span>❤️ HP</span><span className="tabular-nums font-bold">{playerHp}/100</span>
            </div>
            <div className="progress-bar">
              <div className="h-full rounded-full transition-all duration-300"
                style={{ width: `${playerHp}%`, background: "linear-gradient(90deg, #22c55e, #4ade80)", boxShadow: "0 0 8px #22c55e55" }} />
            </div>

            <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-hint)" }}>
              <span className="animate-stamina">⚡ Выносливость</span>
              <span className="tabular-nums font-bold">{Math.round(stamina)} / {STAMINA_MAX}</span>
            </div>
            <div className="progress-bar">
              <div className="h-full rounded-full transition-all duration-500"
                style={{ width: `${(stamina / STAMINA_MAX) * 100}%`, background: "linear-gradient(90deg, #3b82f6, #60a5fa)", boxShadow: "0 0 8px #3b82f655" }} />
            </div>

            {blocking && (
              <p className="text-xs font-bold text-center animate-pulse" style={{ color: "#60a5fa" }}>
                🛡️ Блок активен…
              </p>
            )}
          </div>

          {/* ─ Equipment strip — always visible ─ */}
          {equipped.length > 0 && (
            <div className="flex gap-1.5 overflow-x-auto tab-scroll">
              {equipped.map(eq => (
                <div key={eq.id} className="glass-card-sm flex items-center gap-1.5 px-2.5 py-1.5 shrink-0"
                  style={{ fontSize: 11 }}>
                  <span>{SLOT_EMOJI[eq.slot ?? ""] ?? "📦"}</span>
                  <span className="font-semibold truncate max-w-[80px]" style={{
                    color: eq.rarity === "legendary" ? "#f59e0b" : eq.rarity === "rare" ? "#60a5fa" : "var(--text-secondary)",
                  }}>{eq.name}</span>
                  {eq.enhancement_level > 0 && <span style={{ color: "#22c55e" }}>+{eq.enhancement_level}</span>}
                </div>
              ))}
            </div>
          )}

          {/* Skills */}
          <div className="grid grid-cols-3 gap-2.5">
            {/* Fast attack */}
            <button
              onClick={doFast}
              disabled={stamina < SKILL_FAST_COST || attacking || paused}
              className="glass-card p-3 flex flex-col items-center gap-1.5 disabled:opacity-40 btn-press transition-transform active:scale-95"
            >
              <Sword size={24} style={{ color: "var(--accent)" }} />
              <span className="text-[11px] font-bold" style={{ color: "var(--text-primary)" }}>Быстро</span>
              <span className="text-[10px] font-semibold" style={{ color: "var(--text-hint)" }}>{SKILL_FAST_COST}⚡</span>
            </button>

            {/* Heavy blow */}
            <button
              onClick={doHeavy}
              disabled={stamina < SKILL_HEAVY_COST || heavyCd > 0 || attacking || paused}
              className="glass-card p-3 flex flex-col items-center gap-1.5 disabled:opacity-40 btn-press transition-transform active:scale-95"
            >
              <Swords size={24} style={{ color: heavyCd > 0 ? "var(--text-hint)" : "#f97316" }} />
              <span className="text-[11px] font-bold" style={{ color: "var(--text-primary)" }}>Удар</span>
              <span className="text-[10px] font-semibold" style={{ color: "var(--text-hint)" }}>
                {heavyCd > 0 ? `${(heavyCd / 1000).toFixed(1)}s` : `${SKILL_HEAVY_COST}⚡`}
              </span>
            </button>

            {/* Block */}
            <button
              onClick={doBlock}
              disabled={stamina < SKILL_BLOCK_COST || blocking || paused}
              className={`glass-card p-3 flex flex-col items-center gap-1.5 disabled:opacity-40 btn-press transition-transform active:scale-95 ${telegraphing ? "animate-accent-glow" : ""}`}
            >
              <Shield size={24} style={{ color: blocking ? "#60a5fa" : telegraphing ? "#facc15" : "var(--text-primary)" }} />
              <span className="text-[11px] font-bold" style={{ color: "var(--text-primary)" }}>Блок</span>
              <span className="text-[10px] font-semibold" style={{ color: "var(--text-hint)" }}>
                {blocking ? "✓ БЛОК" : `${SKILL_BLOCK_COST}⚡`}
              </span>
            </button>
          </div>

          {/* ─ Potion quick-bar — ALWAYS visible ─ */}
          <div className="glass-card p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="flex items-center gap-1.5 text-xs font-bold" style={{ color: "var(--text-primary)" }}>
                <FlaskConical size={14} style={{ color: "#a78bfa" }} /> Зелья
                <span className="badge badge-accent">{potions.length}</span>
              </span>
              <button onClick={() => setShowPotions(v => !v)} className="text-[11px] font-semibold" style={{ color: "var(--text-hint)" }}>
                {showPotions ? "Свернуть ▲" : "Развернуть ▼"}
              </button>
            </div>
            {/* Quick-use row (always visible: first 3 potions) */}
            {!showPotions && potions.length > 0 && (
              <div className="flex gap-2">
                {potions.slice(0, 3).map(p => (
                  <button
                    key={p.id}
                    disabled={usingPotion === p.id}
                    onClick={() => doUsePotion(p)}
                    className="flex-1 flex items-center justify-center gap-1 px-2 py-2 rounded-xl text-xs font-semibold disabled:opacity-50 btn-press"
                    style={{ background: "#a78bfa15", color: "#c4b5fd", border: "1px solid #a78bfa30" }}
                  >
                    {usingPotion === p.id ? <Loader2 size={12} className="animate-spin" /> : "🧪"}
                    <span className="truncate">{p.name}</span>
                    {p.stack_count > 1 && <span className="opacity-60">×{p.stack_count}</span>}
                  </button>
                ))}
              </div>
            )}
            {/* Expanded view */}
            {showPotions && (
              potions.length === 0
                ? <p className="text-xs text-center py-2" style={{ color: "var(--text-hint)" }}>Зельи не найдены</p>
                : <div className="flex flex-wrap gap-2">
                    {potions.map(p => (
                      <button
                        key={p.id}
                        disabled={usingPotion === p.id}
                        onClick={() => doUsePotion(p)}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold disabled:opacity-50 btn-press"
                        style={{ background: "#a78bfa15", color: "#c4b5fd", border: "1px solid #a78bfa30" }}
                      >
                        {usingPotion === p.id
                          ? <Loader2 size={11} className="animate-spin" />
                          : "🧪"}
                        {p.name}
                        {p.stack_count > 1 && <span style={{ color: "var(--text-hint)" }}>×{p.stack_count}</span>}
                      </button>
                    ))}
                  </div>
            )}
          </div>

          {/* Hits info */}
          <div className="flex gap-2 text-[11px] justify-end" style={{ color: "var(--text-hint)" }}>
            <span>Нанесено: {fmt(session!.boss_max_hp - bossHp)}</span>
            <span>·</span>
            <span>Урон/удар: ~50-150</span>
            {attacking && <Zap size={11} className="animate-spin" style={{ color: "var(--accent)" }} />}
          </div>
        </div>
      )}
      </>}
    </div>
  );
}
