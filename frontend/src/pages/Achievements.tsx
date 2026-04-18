/* ──────────────────────────────────────────────────────────────
   Achievements.tsx — Достижения пользователя
   Категории · Прогресс · Ранги · Глобальный топ-100 · Синхронизация
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Trophy, Lock, ChevronDown, ChevronUp, MessagesSquare, RefreshCw, Crown, Globe } from "lucide-react";
import { fetchAchievements, fetchGlobalLeaderboard, fetchGlobalTop50 } from "../lib/api";
import type { AchievementsResponse, AchievementCategory, AchievementRank, AchLeaderboardEntry } from "../types";

interface Props {
  userId: number;
  chatId: number;
}

export default function Achievements({ userId, chatId }: Props) {
  const [tab, setTab] = useState<"my" | "top" | "global-top">("my");
  const [data, setData] = useState<AchievementsResponse | null>(null);
  const [leaderboard, setLeaderboard] = useState<AchLeaderboardEntry[] | null>(null);
  const [globalTop, setGlobalTop] = useState<AchLeaderboardEntry[] | null>(null);
  const [leaderboardError, setLeaderboardError] = useState("");
  const [globalTopError, setGlobalTopError] = useState("");
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState<Date | null>(null);

  const load = useCallback(() => {
    if (!userId || !chatId) {
      setError(chatId === 0 ? "__no_chat__" : "__no_user__");
      return;
    }
    fetchAchievements(userId, chatId)
      .then((d) => { setData(d); setLastSync(new Date()); })
      .catch((e: Error) => setError(e.message));
  }, [userId, chatId]);

  const loadLeaderboard = useCallback(() => {
    setLeaderboardError("");
    // If no chat context, fall back to global leaderboard
    const fetchFn = chatId
      ? () => fetchGlobalLeaderboard(chatId)
      : () => fetchGlobalTop50();
    fetchFn()
      .then((d) => setLeaderboard(d.leaderboard))
      .catch((e: Error) => setLeaderboardError(e.message));
  }, [chatId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === "top" && !leaderboard && !leaderboardError) loadLeaderboard(); }, [tab, leaderboard, leaderboardError, loadLeaderboard]);
  useEffect(() => {
    if (tab === "global-top" && !globalTop && !globalTopError) {
      setGlobalTopError("");
      fetchGlobalTop50()
        .then(d => setGlobalTop(d.leaderboard))
        .catch((e: Error) => setGlobalTopError(e.message));
    }
  }, [tab, globalTop, globalTopError]);

  const doSync = () => {
    setSyncing(true);
    fetchAchievements(userId, chatId)
      .then((d) => { setData(d); setLastSync(new Date()); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSyncing(false));
  };

  // chatId=0: показываем понятное сообщение вместо вечного спиннера
  if (error === "__no_chat__") {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 p-6 text-center">
        <MessagesSquare size={48} strokeWidth={1.2} style={{ color: "var(--text-hint)" }} />
        <div>
          <p className="font-semibold">Нет контекста чата</p>
          <p className="text-sm mt-1" style={{ color: "var(--text-hint)" }}>
            Откройте Mini App из чата группы, чтобы посмотреть достижения.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <p className="font-medium">Ошибка загрузки достижений</p>
        <p className="text-sm mt-1 break-all">{error}</p>
        <button onClick={() => { setError(""); load(); }} className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}>Попробовать снова</button>
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

  // Считаем суммарные награды за все разблокированные ранги
  const totalMora = data.categories
    .flatMap(c => c.ranks)
    .filter(r => r.unlocked)
    .reduce((acc, r) => acc + (r.mora ?? 0), 0);
  const totalXp = data.categories
    .flatMap(c => c.ranks)
    .filter(r => r.unlocked)
    .reduce((acc, r) => acc + (r.xp ?? 0), 0);
  const overallPct = data.total_defined > 0
    ? Math.round((data.total_unlocked / data.total_defined) * 100)
    : 0;

  return (
    <div className="animate-fadeIn p-4">
      {/* ── Заголовок с общим прогрессом ─────── */}
      <div className="flex items-center justify-between mb-4">
      <h2 className="text-lg font-bold flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: "var(--accent-soft)" }}>
          <Trophy size={18} style={{ color: "var(--accent)" }} />
        </div>
        Достижения
      </h2>
      <div className="flex items-center gap-2">
        {tab === "my" && (
          <button
            onClick={doSync}
            disabled={syncing}
            className="p-1.5 rounded-lg glass-card-sm transition-opacity disabled:opacity-50"
          >
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} style={{ color: "var(--text-hint)" }} />
          </button>
        )}
        {tab === "my" && (
          <span className="badge badge-accent text-sm font-bold">
            {data.total_unlocked}/{data.total_defined}
          </span>
        )}
      </div>
    </div>

    {/* ── Табы ─────── */}
    <div className="flex gap-2 mb-4 glass-card tab-scroll p-1 rounded-xl">
      {(["my", "top", "global-top"] as const).map((t) => (
        <button
          key={t}
          onClick={() => setTab(t)}
          className="flex-1 py-2 rounded-xl text-sm font-semibold transition-all"
          style={{
            backgroundColor: tab === t ? "var(--accent)" : "transparent",
            color: tab === t ? "#fff" : "var(--text-secondary)",
            boxShadow: tab === t ? "0 0 12px var(--accent-glow)" : "none",
          }}
        >
          {t === "my" ? "📋 Мои" : t === "top" ? "🏆 Топ-100" : "🌐 Глобальный"}
        </button>
      ))}
    </div>

      {tab === "top" ? (
        leaderboardError ? (
          <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
            <p className="font-medium text-sm">Ошибка загрузки</p>
            <p className="text-xs mt-1 break-all">{leaderboardError}</p>
            <button onClick={loadLeaderboard} className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}>
              Попробовать снова
            </button>
          </div>
        ) : (
          <LeaderboardTab entries={leaderboard} userId={userId} onRefresh={loadLeaderboard} />
        )
      ) : tab === "global-top" ? (
        globalTopError ? (
          <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
            <p className="font-medium text-sm">Ошибка загрузки</p>
            <p className="text-xs mt-1 break-all">{globalTopError}</p>
            <button
              onClick={() => { setGlobalTopError(""); fetchGlobalTop50().then(d => setGlobalTop(d.leaderboard)).catch((e: Error) => setGlobalTopError(e.message)); }}
              className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}>
              Попробовать снова
            </button>
          </div>
        ) : (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Globe size={14} style={{ color: "var(--accent)" }} />
              <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Топ-50 игроков мира</p>
            </div>
            <LeaderboardTab entries={globalTop} userId={userId} onRefresh={() => { setGlobalTop(null); setGlobalTopError(""); }} />
          </div>
        )
      ) : (
        <>
          {lastSync && (
            <p className="text-[10px] mb-3" style={{ color: "var(--text-hint)" }}>
              Синхронизировано: {lastSync.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
            </p>
          )}

      {/* ── Карточка общего прогресса ─────── */}
      <div className="glass-hero p-4 mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold">Общий прогресс</span>
          <span className="text-sm font-bold tabular-nums stat-value">{overallPct}%</span>
        </div>
        <div className="progress-bar mb-3">
          <div
            className="progress-bar-fill transition-all duration-700"
            style={{ width: `${overallPct}%`, background: overallPct === 100 ? "#22c55e" : undefined }}
          />
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl p-2" style={{ backgroundColor: "var(--bg-primary)" }}>
            <p className="text-sm font-bold tabular-nums">{data.total_unlocked}</p>
            <p className="text-[10px] mt-0.5" style={{ color: "var(--text-hint)" }}>Разблокировано</p>
          </div>
          <div className="rounded-xl p-2" style={{ backgroundColor: "var(--bg-primary)" }}>
            <p className="text-sm font-bold tabular-nums">{totalMora.toLocaleString("ru")}</p>
            <p className="text-[10px] mt-0.5" style={{ color: "var(--text-hint)" }}>Мора 🪙</p>
          </div>
          <div className="rounded-xl p-2" style={{ backgroundColor: "var(--bg-primary)" }}>
            <p className="text-sm font-bold tabular-nums">{totalXp.toLocaleString("ru")}</p>
            <p className="text-[10px] mt-0.5" style={{ color: "var(--text-hint)" }}>Опыт XP</p>
          </div>
        </div>
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
        </>
      )}
    </div>
  );
}

/* ── Глобальный топ-100 ─────────────────────────────────────── */

function LeaderboardTab({
  entries,
  userId,
  onRefresh,
}: {
  entries: AchLeaderboardEntry[] | null;
  userId: number;
  onRefresh: () => void;
}) {
  if (!entries) {
    return (
      <div className="space-y-2 animate-pulse">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="skeleton h-14 rounded-xl" />
        ))}
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="text-center py-10" style={{ color: "var(--text-hint)" }}>
        <Crown size={36} className="mx-auto mb-2" />
        <p className="text-sm">Пока нет данных</p>
      </div>
    );
  }

  const medalEmoji = (rank: number) =>
    rank === 1 ? "🥇" : rank === 2 ? "🥈" : rank === 3 ? "🥉" : null;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs" style={{ color: "var(--text-hint)" }}>
          Глобальный рейтинг по уникальным достижениям
        </p>
        <button
          onClick={onRefresh}
          className="p-1.5 rounded-lg"
          style={{ backgroundColor: "var(--bg-secondary)" }}
        >
          <RefreshCw size={14} style={{ color: "var(--text-hint)" }} />
        </button>
      </div>
      <div className="space-y-1.5">
        {entries.map((e) => {
          const isMe = e.user_id === userId;
          const medal = medalEmoji(e.rank);
          return (
            <div
              key={e.user_id}
              className="flex items-center gap-3 rounded-xl px-3 py-2.5"
              style={{
                backgroundColor: isMe ? "color-mix(in srgb, var(--accent) 12%, var(--bg-secondary))" : "var(--bg-secondary)",
                border: isMe ? "1px solid var(--accent)" : "1px solid transparent",
              }}
            >
              <span
                className="w-8 text-center text-sm font-bold tabular-nums shrink-0"
                style={{ color: medal ? undefined : "var(--text-hint)" }}
              >
                {medal ?? (e.rank != null ? `#${e.rank}` : "—")}
              </span>
              <span className="flex-1 text-sm font-medium truncate">
                {e.full_name}
                {isMe && <span style={{ color: "var(--accent)" }}> (вы)</span>}
              </span>
              <span
                className="text-sm font-bold tabular-nums shrink-0"
                style={{ color: "var(--accent)" }}
              >
                {e.badge_count} 🏆
              </span>
            </div>
          );
        })}
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
