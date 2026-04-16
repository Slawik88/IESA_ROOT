/* ──────────────────────────────────────────────────────────────
   Talents.tsx — Дерево Талантов
   GET /api/talents  →  {talent_points, talents, tree}
   POST /api/talents/upgrade  {talent_id}
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Sparkles, Loader2 } from "lucide-react";
import { fetchTalents, upgradeTalent, type TalentsResponse } from "../lib/api";

interface Props { userId: number; chatId: number; }

const TIER_LABEL: Record<number, string> = {
  1: "Tier 1 — Базовые",
  2: "Tier 2 — Продвинутые (требует 5+ очков в T1)",
  3: "Tier 3 — Мастерские (требует 12+ очков в T1+T2)",
};

export default function Talents({ chatId }: Props) {
  // chatId is not used by /api/talents but kept for future filtering
  void chatId;
  const [data, setData]   = useState<TalentsResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy]   = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }, []);

  const load = useCallback(() => {
    fetchTalents().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  const doUpgrade = useCallback(async (talentId: string) => {
    if (busy) return;
    setBusy(talentId);
    try {
      const res = await upgradeTalent(talentId);
      if (res.ok) {
        showToast(`✅ Талант улучшен! Очков осталось: ${res.talent_points}`);
        setData(prev => prev ? {
          ...prev,
          talent_points: res.talent_points,
          talents: { ...prev.talents, [talentId]: (prev.talents[talentId] ?? 0) + 1 },
        } : prev);
      } else {
        showToast(res.error ?? "Ошибка");
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally { setBusy(null); }
  }, [busy, showToast]);

  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <p className="font-medium">Ошибка</p>
        <p className="text-sm mt-1">{error}</p>
        <button onClick={load} className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}>Обновить</button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 space-y-3 animate-pulse">
        {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-20 rounded-xl" />)}
      </div>
    );
  }

  const t1points  = Object.entries(data.talents).reduce((s, [id, lvl]) => data.tree[id]?.tier === 1 ? s + lvl : s, 0);
  const t12points = Object.entries(data.talents).reduce((s, [id, lvl]) => {
    const t = data.tree[id]?.tier;
    return (t === 1 || t === 2) ? s + lvl : s;
  }, 0);

  return (
    <div className="animate-fadeIn p-4 space-y-4 pb-24">
      {toast && (
        <div className="fixed top-4 left-4 right-4 z-50 px-4 py-3 rounded-xl text-sm font-medium text-white shadow-xl"
             style={{ backgroundColor: "var(--accent)" }}>
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="glass-hero p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl" style={{ backgroundColor: "var(--accent-soft)" }}>
            <Sparkles size={22} style={{ color: "var(--accent)" }} />
          </div>
          <span className="font-bold text-base">Таланты</span>
        </div>
        <div className="text-right">
          <p className="text-2xl font-extrabold tabular-nums stat-value">{data.talent_points}</p>
          <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>свободных очков</p>
        </div>
      </div>

      {([1, 2, 3] as const).map(tier => {
        const tierTalents = Object.entries(data.tree).filter(([, t]) => t.tier === tier);
        const locked = (tier === 2 && t1points < 5) || (tier === 3 && t12points < 12);
        return (
          <div key={tier}>
            <p className="text-xs font-semibold mb-2 px-1"
               style={{ color: locked ? "var(--text-hint)" : "var(--text-primary)" }}>
              {locked ? "🔒 " : ""}{TIER_LABEL[tier]}
            </p>
            <div className="space-y-2">
              {tierTalents.map(([id, info]) => {
                const level   = data.talents[id] ?? 0;
                const maxed   = level >= info.max_level;
                const canUp   = !locked && !maxed && data.talent_points > 0;
                return (
                  <div key={id} className="glass-card p-3 rounded-xl flex items-center gap-3">
                    <span className="text-2xl flex-none">{info.emoji}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold truncate">{info.name}</p>
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full flex-none"
                              style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-hint)" }}>
                          {level}/{info.max_level}
                        </span>
                      </div>
                      <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>{info.desc}</p>
                      <div className="flex gap-0.5 mt-1.5">
                        {Array.from({ length: info.max_level }).map((_, i) => (
                          <div key={i} className="h-1.5 flex-1 rounded-full"
                               style={{ backgroundColor: i < level ? "var(--accent)" : "var(--bg-secondary)" }} />
                        ))}
                      </div>
                    </div>
                    <button
                      onClick={() => doUpgrade(id)}
                      disabled={!canUp || busy === id}
                      className="flex-none px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-40 transition-all"
                      style={{ backgroundColor: canUp ? "var(--accent)" : "var(--bg-secondary)", color: canUp ? "#fff" : "var(--text-hint)" }}
                    >
                      {busy === id ? <Loader2 size={12} className="animate-spin" /> : maxed ? "✅" : "+1"}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
