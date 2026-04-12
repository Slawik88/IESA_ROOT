/* ──────────────────────────────────────────────────────────────
   Achievements.tsx — Достижения пользователя
   Категории · Прогресс · Ранги · Разблокированные / заблокированные
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState } from "react";
import { Trophy, Lock, ChevronDown, ChevronUp } from "lucide-react";
import { fetchAchievements } from "../lib/api";
import type { AchievementsResponse, AchievementCategory, AchievementRank } from "../types";

interface Props {
  userId: number;
  chatId: number;
}

export default function Achievements({ userId, chatId }: Props) {
  const [data, setData] = useState<AchievementsResponse | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (!userId || !chatId) return;
    fetchAchievements(userId, chatId)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [userId, chatId]);

  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <p className="font-medium">Ошибка</p>
        <p className="text-sm mt-1">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 space-y-3 animate-pulse">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="skeleton h-20 rounded-xl" />
        ))}
      </div>
    );
  }

  const toggle = (type: string) =>
    setExpanded((prev) => (prev === type ? null : type));

  return (
    <div className="animate-fadeIn p-4">
      {/* ── Заголовок с общим прогрессом ─────── */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Trophy size={20} />
          Достижения
        </h2>
        <span className="text-sm font-medium" style={{ color: "var(--accent)" }}>
          {data.total_unlocked}/{data.total_defined}
        </span>
      </div>

      {/* ── Список категорий ─────────────────── */}
      <div className="space-y-2">
        {data.categories.map((cat) => (
          <CategoryCard
            key={cat.type}
            cat={cat}
            isOpen={expanded === cat.type}
            onToggle={() => toggle(cat.type)}
          />
        ))}
      </div>
    </div>
  );
}

/* ── Карточка категории ────────────────────────────────────────── */

function CategoryCard({
  cat,
  isOpen,
  onToggle,
}: {
  cat: AchievementCategory;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const allDone = cat.current_rank === cat.total_defined;
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ backgroundColor: "var(--bg-secondary)" }}
    >
      {/* Заголовок-кнопка */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 p-3 text-left"
      >
        <span className="text-2xl shrink-0">{cat.emoji}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium truncate">{cat.label}</span>
            <span
              className="text-xs tabular-nums shrink-0 ml-2"
              style={{ color: allDone ? "var(--accent)" : "var(--text-hint)" }}
            >
              {cat.current_rank}/{cat.total_defined}
            </span>
          </div>
          {/* Прогресс-бар */}
          <div
            className="mt-1.5 h-1.5 rounded-full overflow-hidden"
            style={{ backgroundColor: "var(--border)" }}
          >
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${cat.progress_pct}%`,
                backgroundColor: allDone ? "#22c55e" : "var(--accent)",
              }}
            />
          </div>
          {/* Подсказка до следующего ранга */}
          {!allDone && cat.next_threshold != null && !cat.is_bool && (
            <p className="text-[11px] mt-1" style={{ color: "var(--text-hint)" }}>
              {cat.current_value.toLocaleString("ru")}/{cat.next_threshold.toLocaleString("ru")} → {cat.next_title}
            </p>
          )}
        </div>
        {isOpen ? (
          <ChevronUp size={16} style={{ color: "var(--text-hint)" }} />
        ) : (
          <ChevronDown size={16} style={{ color: "var(--text-hint)" }} />
        )}
      </button>

      {/* Раскрытый список рангов */}
      {isOpen && (
        <div className="px-3 pb-3 space-y-1.5">
          {cat.ranks.map((r) => (
            <RankRow key={r.key} rank={r} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Строка ранга ──────────────────────────────────────────────── */

function RankRow({ rank }: { rank: AchievementRank }) {
  const unlocked = rank.unlocked;
  return (
    <div
      className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm"
      style={{
        backgroundColor: "var(--bg-primary)",
        opacity: unlocked ? 1 : 0.45,
      }}
    >
      <span className="text-lg shrink-0">
        {unlocked ? rank.emoji : <Lock size={16} style={{ color: "var(--text-hint)" }} />}
      </span>
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate">{rank.title}</p>
        <p className="text-[11px] truncate" style={{ color: "var(--text-hint)" }}>
          {rank.description}
        </p>
      </div>
      <div className="text-right shrink-0">
        <p className="text-[11px] tabular-nums" style={{ color: "var(--accent)" }}>
          +{rank.mora} 🪙
        </p>
        {rank.xp > 0 && (
          <p className="text-[10px] tabular-nums" style={{ color: "var(--text-hint)" }}>
            +{rank.xp} XP
          </p>
        )}
      </div>
    </div>
  );
}
