/* ──────────────────────────────────────────────────────────────
   Leaderboard.tsx — Таблица лидеров
   GET /api/leaderboard?chat_id=X&type=xp|messages|boss|mora
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Trophy, AlertCircle, X, Crown, Star } from "lucide-react";
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
  const [profileEntry, setProfileEntry] = useState<{ entry: LeaderboardEntry; tab: LBType } | null>(null);

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
                  onProfile={() => setProfileEntry({ entry, tab })}
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
                  onProfile={null}
                />
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Профиль пользователя ── */}
      {profileEntry && (
        <UserProfileSheet
          entry={profileEntry.entry}
          tab={profileEntry.tab}
          onClose={() => setProfileEntry(null)}
        />
      )}
    </div>
  );
}

/* ── Строка лидерборда ── */
function EntryRow({
  entry,
  isSelf,
  tab,
  onProfile,
}: {
  entry: LeaderboardEntry;
  isSelf: boolean;
  tab: LBType;
  onProfile: (() => void) | null;
}) {
  const medal = MEDAL[entry.rank];

  return (
    <div
      onClick={onProfile ?? undefined}
      className={`flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all ${onProfile ? "cursor-pointer active:scale-[0.98] hover:brightness-105" : ""}`}
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

/* ── Профиль пользователя (BottomSheet) ── */
const SCORE_LABEL: Record<LBType, string> = {
  xp: "XP", messages: "Сообщений", boss: "Босс-урон", mora: "Мора 🪙",
};

function UserProfileSheet({
  entry,
  tab,
  onClose,
}: {
  entry: LeaderboardEntry;
  tab: LBType;
  onClose: () => void;
}) {
  const medal = MEDAL[entry.rank];
  const initials = entry.name.slice(0, 2).toUpperCase();

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <div
        className="fixed bottom-0 inset-x-0 z-50 rounded-t-2xl pb-8 animate-slideUp"
        style={{ backgroundColor: "var(--bg-primary)", maxHeight: "75vh", overflowY: "auto" }}
      >
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full" style={{ backgroundColor: "var(--border)" }} />
        </div>

        <div className="flex items-start justify-between px-4 pb-2 pt-2">
          <h3 className="font-semibold text-base" style={{ color: "var(--text-primary)" }}>Профиль игрока</h3>
          <button onClick={onClose} style={{ color: "var(--text-hint)" }}><X size={20} /></button>
        </div>

        {/* Аватар + имя */}
        <div className="flex flex-col items-center gap-3 pt-2 pb-4">
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold"
            style={{ backgroundColor: "var(--accent)22", color: "var(--accent)" }}
          >
            {initials}
          </div>
          <div className="text-center">
            <p className="text-base font-bold flex items-center justify-center gap-1.5">
              {entry.name}
              {entry.vip && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{ backgroundColor: "#f59e0b22", color: "#f59e0b" }}>
                  VIP
                </span>
              )}
            </p>
            {entry.level !== undefined && (
              <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>Уровень {entry.level}</p>
            )}
          </div>
        </div>

        {/* Статы */}
        <div className="grid grid-cols-2 gap-3 px-4 pb-4">
          <div className="rounded-xl p-3 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
            <p className="text-lg font-bold">{medal ?? `#${entry.rank}`}</p>
            <p className="text-[11px] mt-0.5" style={{ color: "var(--text-hint)" }}>Место в рейтинге</p>
          </div>
          <div className="rounded-xl p-3 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
            <p className="text-lg font-bold tabular-nums">
              {entry.score != null ? entry.score.toLocaleString("ru-RU") : "—"}
            </p>
            <p className="text-[11px] mt-0.5" style={{ color: "var(--text-hint)" }}>{SCORE_LABEL[tab]}</p>
          </div>
        </div>

        {/* Категория */}
        <div className="px-4">
          <div className="flex items-center gap-2 p-3 rounded-xl" style={{ backgroundColor: "var(--bg-secondary)" }}>
            <Star size={16} style={{ color: "var(--accent)" }} />
            <div>
              <p className="text-xs font-medium">Категория</p>
              <p className="text-sm font-semibold" style={{ color: "var(--accent)" }}>
                {TABS.find(t => t.key === tab)?.label ?? tab}
              </p>
            </div>
            {entry.vip && (
              <div className="ml-auto flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-full"
                style={{ backgroundColor: "#f59e0b22", color: "#f59e0b" }}>
                <Crown size={12} /> VIP
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
