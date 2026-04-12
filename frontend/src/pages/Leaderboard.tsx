/* ──────────────────────────────────────────────────────────────
   Leaderboard.tsx — Таблица лидеров
   GET /api/leaderboard?chat_id=X&type=xp|messages|boss|mora
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Trophy, AlertCircle } from "lucide-react";
import { fetchLeaderboard } from "../lib/api";
import type { LeaderboardResponse, LeaderboardEntry } from "../types";

type LBType = "xp" | "messages" | "boss" | "mora";

const TABS: { key: LBType; label: string }[] = [
  { key: "xp",       label: "XP"        },
  { key: "messages", label: "Сообщения" },
  { key: "boss",     label: "Босс"      },
  { key: "mora",     label: "Мора"      },
];

const MEDAL: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

interface Props {
  chatId: number;
}

export default function Leaderboard({ chatId }: Props) {
  const [tab, setTab]     = useState<LBType>("xp");
  const [data, setData]   = useState<LeaderboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback((type: LBType) => {
    setLoading(true);
    setError("");
    fetchLeaderboard(chatId, type)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [chatId]);

  useEffect(() => { load(tab); }, [tab, load]);

  if (chatId === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3 p-6 text-center"
        style={{ color: "var(--text-hint)" }}>
        <AlertCircle size={36} strokeWidth={1.2} />
        <p className="font-medium">Войдите через Telegram</p>
        <p className="text-sm">Для просмотра лидерборда необходим Telegram аккаунт.</p>
      </div>
    );
  }

  return (
    <div className="animate-fadeIn flex flex-col min-h-screen pb-24">

      {/* ── Заголовок ── */}
      <div className="p-4 pb-0">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <Trophy size={20} style={{ color: "var(--accent)" }} />
          Таблица лидеров
        </h1>
      </div>

      {/* ── Табы ── */}
      <div className="flex gap-2 p-4 overflow-x-auto">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className="px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-all"
            style={{
              backgroundColor: tab === t.key ? "var(--accent)" : "var(--bg-secondary)",
              color:            tab === t.key ? "#fff"          : "var(--text-secondary)",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Контент ── */}
      <div className="flex-1 px-4">
        {loading && <LBSkeleton />}

        {!loading && error && (
          <div className="text-center mt-8" style={{ color: "#e74c3c" }}>
            <AlertCircle size={28} className="mx-auto mb-2" />
            <p>{error}</p>
            <button
              onClick={() => load(tab)}
              className="mt-3 text-sm underline"
              style={{ color: "var(--accent)" }}
            >
              Повторить
            </button>
          </div>
        )}

        {!loading && !error && data && (
          <>
            {data.entries.length === 0 && (
              <p className="text-center mt-8 text-sm" style={{ color: "var(--text-hint)" }}>
                Записей пока нет
              </p>
            )}

            <div className="space-y-2">
              {data.entries.map(entry => (
                <EntryRow
                  key={entry.user_id}
                  entry={entry}
                  isSelf={entry.user_id === data.uid}
                  tab={tab}
                />
              ))}
            </div>

            {/* Блок: позиция текущего пользователя если не в топе */}
            {data.user_rank && !data.entries.some(e => e.user_id === data.uid) && (
              <div className="mt-4">
                <div
                  className="h-px my-2"
                  style={{ backgroundColor: "var(--border)" }}
                />
                <EntryRow
                  entry={{
                    rank:    data.user_rank.rank,
                    user_id: data.uid ?? 0,
                    name:    "Вы",
                    score:   data.user_rank.score,
                  }}
                  isSelf
                  tab={tab}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* ── Строка лидерборда ── */
function EntryRow({
  entry,
  isSelf,
  tab,
}: {
  entry: LeaderboardEntry;
  isSelf: boolean;
  tab: LBType;
}) {
  const medal = MEDAL[entry.rank];

  return (
    <div
      className="flex items-center gap-3 rounded-xl px-3 py-2.5"
      style={{
        backgroundColor: isSelf ? "var(--accent)22" : "var(--bg-secondary)",
        border:          isSelf ? "1px solid var(--accent)" : "1px solid transparent",
      }}
    >
      {/* Место */}
      <div className="w-8 text-center text-sm font-bold shrink-0" style={{ color: "var(--text-hint)" }}>
        {medal ?? `#${entry.rank}`}
      </div>

      {/* Имя */}
      <p
        className="flex-1 text-sm font-medium truncate"
        style={{ color: isSelf ? "var(--accent)" : "var(--text-primary)" }}
      >
        {entry.name}
        {entry.vip && (
          <span className="ml-1 text-[10px] font-bold px-1 py-0.5 rounded" style={{ backgroundColor: "#f59e0b22", color: "#f59e0b" }}>
            VIP
          </span>
        )}
        {entry.level !== undefined && (
          <span className="ml-1 text-xs" style={{ color: "var(--text-hint)" }}>
            Ур. {entry.level}
          </span>
        )}
      </p>

      {/* Очки */}
      <div className="shrink-0 text-sm tabular-nums font-semibold" style={{ color: "var(--text-primary)" }}>
        {entry.score !== null && entry.score !== undefined
          ? tab === "mora"
            ? `${entry.score.toLocaleString("ru-RU")} 🪙`
            : tab === "xp"
            ? `${entry.score.toLocaleString("ru-RU")} XP`
            : entry.score.toLocaleString("ru-RU")
          : "—"}
      </div>
    </div>
  );
}

/* ── Скелетон ── */
function LBSkeleton() {
  return (
    <div className="space-y-2 animate-pulse mt-2">
      {Array.from({ length: 7 }).map((_, i) => (
        <div key={i} className="skeleton h-12 rounded-xl" />
      ))}
    </div>
  );
}
