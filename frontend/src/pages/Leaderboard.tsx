/* ──────────────────────────────────────────────────────────────
   Leaderboard.tsx — Таблица лидеров
   GET /api/leaderboard?chat_id=X&type=xp|messages|boss|mora
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Trophy, AlertCircle, X, Swords, Shield, Heart, PawPrint } from "lucide-react";
import { fetchLeaderboard, fetchPublicProfile } from "../lib/api";
import type { LeaderboardResponse, LeaderboardEntry, PublicProfileResponse } from "../types";
import ProfileAvatar from "../components/ProfileAvatar";

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
    // chat_id=0 → backend returns global leaderboard (all chats)
    fetchLeaderboard(0, type)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(tab); }, [tab, load]);

  return (
    <div className="animate-fadeIn flex flex-col min-h-screen pb-24">

      {/* ── Заголовок ── */}
      <div className="glass-hero px-4 pt-4 pb-2 mb-2">
        <h1 className="text-xl font-bold flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "var(--accent-soft)" }}>
            <Trophy size={18} style={{ color: "var(--accent)" }} />
          </div>
          Глобальная таблица лидеров
        </h1>
      </div>

      {/* ── Табы ── */}
      <div className="flex gap-2 px-4 pb-3 overflow-x-auto tab-scroll">
        {TABS.map(t => {
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className="px-3 py-1.5 rounded-xl text-sm font-semibold whitespace-nowrap transition-all"
              style={{
                backgroundColor: active ? "var(--accent)" : "transparent",
                color: active ? "#fff" : "var(--text-secondary)",
                border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
                boxShadow: active ? "0 0 12px var(--accent-glow)" : "none",
              }}
            >
              {t.label}
            </button>
          );
        })}
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
          chatId={chatId}
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
      className={`flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all glass-card ${isSelf ? "" : ""} ${onProfile ? "cursor-pointer active:scale-[0.98] glass-card-hover" : ""}`}
      style={{
        border: isSelf ? "1px solid var(--accent)" : undefined,
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

const RANK_LABEL: Record<string, string> = {
  developer: "Разработчик", owner: "Владелец", co_owner: "Совладелец",
  admin_senior: "Ст. Администратор", admin_junior: "Мл. Администратор",
  admin: "Администратор", moderator: "Модератор", vip: "VIP", user: "Участник",
};
const RANK_COLOR: Record<string, string> = {
  developer: "#ff4757", owner: "#f59e0b", co_owner: "#a855f7",
  admin_senior: "#e84393", admin_junior: "#3b82f6", admin: "#ffa502",
  moderator: "#2ed573", vip: "#7bed9f", user: "var(--text-hint)",
};

function UserProfileSheet({
  entry,
  tab,
  chatId,
  onClose,
}: {
  entry: LeaderboardEntry;
  tab: LBType;
  chatId: number;
  onClose: () => void;
}) {
  const medal = MEDAL[entry.rank];
  const initials = entry.name.slice(0, 2).toUpperCase();
  const [profile, setProfile] = useState<PublicProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [profileError, setProfileError] = useState("");

  useEffect(() => {
    if (!entry.user_id || !chatId) { setLoading(false); return; }
    setLoading(true);
    setProfileError("");
    fetchPublicProfile(entry.user_id, chatId)
      .then(setProfile)
      .catch((e: Error) => setProfileError(e.message))
      .finally(() => setLoading(false));
  }, [entry.user_id, chatId]);

  const xpPct = profile && profile.xp_max > 0
    ? Math.min(100, Math.round((profile.xp / profile.xp_max) * 100))
    : 0;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <div
        className="fixed bottom-0 inset-x-0 z-50 rounded-t-2xl pb-8 animate-slideUp"
        style={{
          maxHeight: "82vh",
          overflowY: "auto",
          backgroundColor: "var(--bg-primary)",
          borderTop: "1px solid var(--border)",
          boxShadow: "0 -4px 32px -4px rgba(0,0,0,0.4)",
        }}
      >
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full" style={{ backgroundColor: "var(--border)" }} />
        </div>

        <div className="flex items-start justify-between px-4 pb-2 pt-2">
          <h3 className="font-semibold text-base" style={{ color: "var(--text-primary)" }}>Профиль игрока</h3>
          <button onClick={onClose} style={{ color: "var(--text-hint)" }}><X size={20} /></button>
        </div>

        {loading ? (
          <div className="px-4 space-y-3 pb-4 animate-pulse">
            <div className="flex flex-col items-center gap-3 pt-2">
              <div className="w-16 h-16 rounded-full skeleton" />
              <div className="skeleton h-5 w-32 rounded" />
            </div>
            <div className="skeleton h-16 rounded-xl" />
            <div className="grid grid-cols-2 gap-3"><div className="skeleton h-20 rounded-xl" /><div className="skeleton h-20 rounded-xl" /></div>
          </div>
        ) : profileError ? (
          <div className="px-4 py-6 text-center" style={{ color: "#e74c3c" }}>
            <p className="text-sm font-medium">Ошибка загрузки профиля</p>
            <p className="text-xs mt-1 break-all">{profileError}</p>
            <button
              onClick={() => { setLoading(true); setProfileError(""); fetchPublicProfile(entry.user_id, chatId).then(setProfile).catch((e: Error) => setProfileError(e.message)).finally(() => setLoading(false)); }}
              className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}
            >Повторить</button>
          </div>
        ) : (
          <>
            {/* Аватар + имя */}
            <div className="flex flex-col items-center gap-2 pt-2 pb-3">
              <ProfileAvatar
                src={profile?.avatar_url}
                frame={profile?.active_frame && profile.active_frame !== "default" ? profile.active_frame : null}
                size={64}
                alt={profile?.name ?? entry.name}
              />
              <div className="text-center">
                <p className="text-base font-bold flex items-center justify-center gap-1.5">
                  {profile?.crystal_cosmetics_owned?.includes("neon_prefix") && (
                    <span className="neon-prefix text-sm shrink-0">◈</span>
                  )}
                  <span className={profile?.has_rainbow_title ? "rainbow-text" : ""}>
                    {profile?.name ?? entry.name}
                  </span>
                  {(profile?.vip ?? entry.vip) && (
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{ backgroundColor: "#f59e0b22", color: "#f59e0b" }}>VIP</span>
                  )}
                  {profile?.online_status === "online" && (
                    <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: "#22c55e" }} />
                  )}
                </p>
                {profile?.custom_title && (
                  <p className={`text-xs mt-0.5 font-medium ${profile.has_rainbow_title ? "rainbow-text" : ""}`}
                    style={profile.has_rainbow_title ? undefined : { color: "var(--accent)" }}>
                    {profile.custom_title}
                  </p>
                )}
                <p className="text-xs mt-0.5" style={{ color: RANK_COLOR[profile?.rank ?? "user"] ?? "var(--text-hint)" }}>
                  {RANK_LABEL[profile?.rank ?? "user"] ?? profile?.rank}
                </p>
              </div>
            </div>

            {/* Bio */}
            {profile?.bio && (
              <div className="mx-4 mb-3 p-2.5 rounded-xl text-xs" style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)" }}>
                {profile.bio}
              </div>
            )}

            {/* Уровень + XP */}
            {profile && (
              <div className="mx-4 mb-3 rounded-xl p-3" style={{ backgroundColor: "var(--bg-secondary)" }}>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="font-semibold">Уровень {profile.level}</span>
                  <span style={{ color: "var(--text-hint)" }}>{profile.xp.toLocaleString("ru-RU")} / {profile.xp_max.toLocaleString("ru-RU")} XP</span>
                </div>
                <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "var(--border)" }}>
                  <div className="h-full rounded-full transition-all" style={{ width: `${xpPct}%`, backgroundColor: "var(--accent)" }} />
                </div>
              </div>
            )}

            {/* Статы рейтинга */}
            <div className="grid grid-cols-2 gap-3 px-4 mb-3">
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

            {/* RPG статы */}
            {profile?.rpg && (
              <div className="mx-4 mb-3 grid grid-cols-4 gap-2">
                {[
                  { icon: <Swords size={12} />, label: "АТК", val: profile.rpg.atk, color: "#ef4444" },
                  { icon: <Shield size={12} />, label: "ЗЩТ", val: profile.rpg.def, color: "#3b82f6" },
                  { icon: "❤️", label: "HP", val: profile.rpg.hp, color: "#22c55e" },
                  { icon: "⚡", label: "КРИТ", val: `${(profile.rpg.crit * 100).toFixed(0)}%`, color: "#f59e0b" },
                ].map(s => (
                  <div key={s.label} className="rounded-xl p-2 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
                    <p className="text-base font-bold tabular-nums" style={{ color: s.color }}>{s.val}</p>
                    <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>{s.label}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Партнёр + питомец */}
            {(profile?.partner_name || profile?.pet) && (
              <div className="grid grid-cols-2 gap-3 px-4 mb-3">
                {profile.partner_name && (
                  <div className="rounded-xl p-3 flex items-center gap-2" style={{ backgroundColor: "var(--bg-secondary)" }}>
                    <Heart size={14} style={{ color: "#e84393" }} />
                    <div className="min-w-0">
                      <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>Партнёр</p>
                      <p className="text-xs font-semibold truncate">{profile.partner_name}</p>
                    </div>
                  </div>
                )}
                {profile.pet && (
                  <div className="rounded-xl p-3 flex items-center gap-2" style={{ backgroundColor: "var(--bg-secondary)" }}>
                    <PawPrint size={14} style={{ color: "#a855f7" }} />
                    <div className="min-w-0">
                      <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>Питомец</p>
                      <p className="text-xs font-semibold truncate">{profile.pet.emoji} {profile.pet.name}</p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Сообщения */}
            {(profile?.message_count ?? 0) > 0 && (
              <div className="mx-4 mb-3 p-3 rounded-xl flex justify-between" style={{ backgroundColor: "var(--bg-secondary)" }}>
                <span className="text-xs" style={{ color: "var(--text-hint)" }}>Сообщений</span>
                <span className="text-xs font-bold">{profile!.message_count!.toLocaleString("ru-RU")}</span>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
