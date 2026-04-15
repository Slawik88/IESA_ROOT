/* ──────────────────────────────────────────────────────────────
   CoupleBoss.tsx — Couple Boss Fight (marriage co-op)
   ────────────────────────────────────────────────────────────── */
import { useState, useEffect, useCallback, useRef } from "react";
import {
  fetchCoupleBossStatus, startCoupleBoss, attackCoupleBoss,
  type CoupleBossStatusResult, type CoupleBossAttackResult,
} from "../lib/api";
import { Loader2, Swords, Heart, Zap } from "lucide-react";

interface Props {
  userId: number | null;
  chatId: number | null;
}

const BOSS_NAMES: Record<number, string> = {
  1: "Теневой Дуэт", 2: "Звёздный Левиафан", 3: "Хранитель Пустоты",
  4: "Око Бездны", 5: "Архидемон Раздора",
};
function bossName(level: number) {
  return BOSS_NAMES[level] ?? `Парный Страж Ур. ${level}`;
}
const BOSS_ART: Record<number, string> = { 1: "🐲", 2: "🌌", 3: "👁️", 4: "🔮", 5: "😈" };
function bossArt(level: number) { return BOSS_ART[level] ?? "🐲"; }

function fmt(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(0) + "K";
  return String(n);
}

export default function CoupleBoss({ userId: _userId, chatId }: Props) {
  const [status, setStatus]       = useState<CoupleBossStatusResult | null>(null);
  const [loading, setLoading]     = useState(true);
  const [starting, setStarting]   = useState(false);
  const [attacking, setAttacking] = useState(false);
  const [toast, setToast]         = useState<string | null>(null);
  const [bossHp, setBossHp]       = useState(0);
  const [bossMaxHp, setBossMaxHp] = useState(1);
  const [lastHit, setLastHit]     = useState<{ dmg: number; crit: boolean } | null>(null);
  const hitTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }, []);

  const loadStatus = useCallback(async () => {
    if (!chatId) return;
    try {
      const r = await fetchCoupleBossStatus(chatId);
      setStatus(r);
      if (r.session && !r.session.is_completed) {
        setBossHp(r.session.boss_current_hp);
        setBossMaxHp(r.session.boss_max_hp);
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [chatId]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const doStart = useCallback(async () => {
    if (!chatId || starting || !status) return;
    const nextLevel = (status.max_level_completed ?? 0) + 1;
    setStarting(true);
    try {
      const r = await startCoupleBoss(chatId, nextLevel);
      if (r.ok) {
        setBossHp(r.boss_max_hp);
        setBossMaxHp(r.boss_max_hp);
        await loadStatus();
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally { setStarting(false); }
  }, [chatId, starting, status, loadStatus, showToast]);

  const doAttack = useCallback(async () => {
    if (!chatId || attacking) return;
    setAttacking(true);
    try {
      const r: CoupleBossAttackResult = await attackCoupleBoss(chatId);
      if (r.ok) {
        setBossHp(r.boss_hp);
        setLastHit({ dmg: r.damage_dealt, crit: r.crit });
        clearTimeout(hitTimer.current);
        hitTimer.current = setTimeout(() => setLastHit(null), 800);

        if (r.aggro) {
          showToast(`⚠️ Босс контратаковал! −${r.aggro_damage} HP`);
        }
        if (r.boss_defeated) {
          showToast(`🎉 Победа! Награда: ${r.rewards?.mora ?? 0} 🪙 + ${r.rewards?.xp ?? 0} XP`);
          await loadStatus();
        }
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally { setAttacking(false); }
  }, [chatId, attacking, loadStatus, showToast]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={28} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  // Not married
  if (status && !status.married) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6 py-20">
        <Heart size={48} style={{ color: "#e8439366" }} />
        <p className="text-center text-sm" style={{ color: "var(--text-hint)" }}>
          Парный босс доступен только для пар. Вступи в брак, чтобы сражаться вместе!
        </p>
      </div>
    );
  }

  const sess = status?.session;
  const active = sess && !sess.is_completed;
  const nextLevel = (status?.max_level_completed ?? 0) + 1;
  const hpPct = bossMaxHp > 0 ? Math.max(0, (bossHp / bossMaxHp) * 100) : 0;

  return (
    <div className="flex-1 flex flex-col gap-3 px-4 pt-3 pb-4">
      {/* Partner info */}
      <div className="glass-card p-3 flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold" style={{ color: "var(--text-hint)" }}>Партнёр</p>
          <p className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{status?.partner_name ?? "?"}</p>
        </div>
        <div className="badge badge-accent text-xs px-3 py-1">
          Макс. ур. {status?.max_level_completed ?? 0}
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className="px-4 py-2.5 glass-card animate-fadeIn text-center text-sm font-medium"
          style={{ color: "var(--text-primary)" }}>
          {toast}
        </div>
      )}

      {/* No active session */}
      {!active && (
        <div className="flex-1 flex flex-col items-center justify-center gap-5">
          <div className="text-center space-y-2">
            <div className="text-7xl drop-shadow-lg animate-orb">{bossArt(nextLevel)}</div>
            <p className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>{bossName(nextLevel)}</p>
            <p className="text-xs" style={{ color: "var(--text-hint)" }}>
              HP: {fmt(5_000 + (nextLevel - 1) * 3_000)} • Парный бой
            </p>
            {sess?.is_completed === 1 && (
              <p className="badge badge-success text-sm px-4 py-1">✅ Побеждён!</p>
            )}
          </div>
          <button
            onClick={doStart}
            disabled={starting}
            className="px-8 py-3 rounded-2xl text-base font-bold flex items-center gap-2 disabled:opacity-50 btn-primary"
          >
            {starting ? <Loader2 size={18} className="animate-spin" /> : <Swords size={18} />}
            {starting ? "Вызов..." : sess?.is_completed === 1 ? "Следующий уровень →" : "Начать парный бой"}
          </button>
        </div>
      )}

      {/* Active fight */}
      {active && (
        <div className="flex-1 flex flex-col gap-3">
          {/* Boss card */}
          <div className="glass-card p-4">
            <div className="flex items-center gap-3">
              <div className="text-5xl shrink-0">{bossArt(sess!.boss_level)}</div>
              <div className="flex-1 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{bossName(sess!.boss_level)}</span>
                  <span className="text-xs tabular-nums font-semibold" style={{ color: "var(--text-hint)" }}>
                    {fmt(bossHp)} / {fmt(bossMaxHp)}
                  </span>
                </div>
                <div className="progress-bar">
                  <div className="progress-bar-fill" style={{ width: `${hpPct}%` }} />
                </div>
              </div>
            </div>
          </div>

          {/* Hit feedback */}
          {lastHit && (
            <div className="text-center animate-fadeIn">
              <span className="text-lg font-bold" style={{ color: lastHit.crit ? "#f59e0b" : "#ef4444" }}>
                {lastHit.crit ? "💥 КРИТ! " : "⚔️ "}{fmt(lastHit.dmg)}
              </span>
            </div>
          )}

          {/* Damage summary */}
          <div className="glass-card p-3 grid grid-cols-2 gap-3">
            <div className="text-center">
              <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>Мой урон</p>
              <p className="text-sm font-bold" style={{ color: "var(--accent)" }}>{fmt(sess!.user_a_damage)}</p>
            </div>
            <div className="text-center">
              <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>Урон партнёра</p>
              <p className="text-sm font-bold" style={{ color: "#e84393" }}>{fmt(sess!.user_b_damage)}</p>
            </div>
          </div>

          {/* Attack button */}
          <button
            onClick={doAttack}
            disabled={attacking}
            className="w-full py-4 rounded-2xl text-lg font-bold flex items-center justify-center gap-2 disabled:opacity-50 btn-primary transition-transform active:scale-95"
          >
            {attacking ? <Loader2 size={20} className="animate-spin" /> : <Zap size={20} />}
            {attacking ? "Атака..." : "⚔️ Атаковать"}
          </button>
        </div>
      )}
    </div>
  );
}
