/* ──────────────────────────────────────────────────────────────
   Analytics.tsx — Аналитический дашборд (Dev only)
   Данные из /api/dev/analytics?period=day|week|month
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState } from "react";
import { BarChart2, Clock, MousePointerClick, Users, Loader2, AlertTriangle } from "lucide-react";
import { fetchAnalytics, type AnalyticsResponse } from "../lib/api";

type Period = "day" | "week" | "month";

const PERIOD_LABELS: Record<Period, string> = { day: "День", week: "Неделя", month: "Месяц" };

function fmtSecs(s: number): string {
  if (s < 60) return `${s}с`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r > 0 ? `${m}м ${r}с` : `${m}м`;
}

interface Props {
  userId: number;
}

export default function Analytics({ userId: _userId }: Props) {
  const [period, setPeriod] = useState<Period>("week");
  const [data, setData]     = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchAnalytics(period)
      .then(setData)
      .catch(e => setError(e?.message ?? "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [period]);

  const maxTabSecs   = data ? Math.max(...data.top_tabs.map(t => t.seconds),   1) : 1;
  const maxClicksCnt = data ? Math.max(...data.top_clicks.map(c => c.count),   1) : 1;
  const maxDaily     = data ? Math.max(...data.daily_sessions.map(d => d.count), 1) : 1;

  return (
    <div className="space-y-4 animate-fadeIn">
      {/* Period selector */}
      <div className="glass-hero p-3 flex gap-2">
        {(["day", "week", "month"] as Period[]).map(p => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className="flex-1 py-1.5 rounded-lg text-sm font-semibold transition-all"
            style={{
              background: period === p ? "var(--accent)" : "transparent",
              color:      period === p ? "#fff" : "var(--text-hint)",
              border:     period === p ? "none" : "1px solid var(--text-hint)33",
            }}
          >
            {PERIOD_LABELS[p]}
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <Loader2 size={28} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      )}

      {error && !loading && (
        <div className="glass-hero p-4 flex items-center gap-3" style={{ borderColor: "#ef444444" }}>
          <AlertTriangle size={20} style={{ color: "#ef4444" }} />
          <span className="text-sm" style={{ color: "#ef4444" }}>{error}</span>
        </div>
      )}

      {!loading && data && (
        <>
          {/* Summary row */}
          <div className="grid grid-cols-2 gap-3">
            <div className="glass-hero p-3 space-y-0.5">
              <div className="flex items-center gap-1.5 mb-1">
                <Users size={14} style={{ color: "var(--accent)" }} />
                <span className="text-xs font-semibold" style={{ color: "var(--text-hint)" }}>
                  Сессий за период
                </span>
              </div>
              <p className="text-2xl font-bold">{data.total_sessions.toLocaleString()}</p>
              <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                {data.date_from} — {data.date_to}
              </p>
            </div>
            <div className="glass-hero p-3 space-y-0.5">
              <div className="flex items-center gap-1.5 mb-1">
                <Clock size={14} style={{ color: "var(--accent)" }} />
                <span className="text-xs font-semibold" style={{ color: "var(--text-hint)" }}>
                  Средняя сессия
                </span>
              </div>
              <p className="text-2xl font-bold">{fmtSecs(data.avg_session_sec)}</p>
              <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>на пользователя</p>
            </div>
          </div>

          {/* Top tabs */}
          {data.top_tabs.length > 0 && (
            <div className="glass-hero p-4 space-y-3">
              <div className="flex items-center gap-2">
                <BarChart2 size={16} style={{ color: "var(--accent)" }} />
                <p className="font-semibold text-sm">Топ вкладок по времени</p>
              </div>
              <div className="space-y-2.5">
                {data.top_tabs.slice(0, 8).map((t, i) => (
                  <div key={t.key} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium">
                        {i + 1}. {t.label || t.key}
                      </span>
                      <span style={{ color: "var(--text-hint)" }}>
                        {fmtSecs(t.seconds)} · {t.sessions} сесс.
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full" style={{ background: "var(--card-bg)" }}>
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${(t.seconds / maxTabSecs) * 100}%`,
                          background: i === 0
                            ? "var(--accent)"
                            : i === 1
                            ? "#a855f7"
                            : "var(--text-hint)",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {data.user_breakdown.length > 0 && (
            <div className="glass-hero p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Clock size={16} style={{ color: "var(--accent)" }} />
                <p className="font-semibold text-sm">Время по вкладкам на пользователя</p>
              </div>
              <div className="space-y-3">
                {data.user_breakdown.map((user, index) => {
                  const maxUserTab = Math.max(...user.tabs.map(tab => tab.seconds), 1);
                  return (
                    <div
                      key={user.user_id}
                      className="rounded-2xl p-3 space-y-2"
                      style={{ background: "var(--card-bg)", border: "1px solid var(--border)" }}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold">
                            {index + 1}. {user.name}
                          </p>
                          <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                            ID: {user.user_id}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-bold">{fmtSecs(user.seconds)}</p>
                          <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                            всего за период
                          </p>
                        </div>
                      </div>

                      {user.tabs.length > 0 ? (
                        <div className="space-y-2">
                          {user.tabs.map((tab) => (
                            <div key={`${user.user_id}_${tab.key}`} className="space-y-1">
                              <div className="flex items-center justify-between text-[11px] gap-2">
                                <span className="truncate">{tab.label || tab.key}</span>
                                <span style={{ color: "var(--text-hint)" }}>{fmtSecs(tab.seconds)}</span>
                              </div>
                              <div className="h-1.5 rounded-full" style={{ background: "var(--bg-primary)" }}>
                                <div
                                  className="h-full rounded-full"
                                  style={{
                                    width: `${(tab.seconds / maxUserTab) * 100}%`,
                                    background: "var(--accent)",
                                  }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                          Нет данных по вкладкам.
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Top clicks */}
          {data.top_clicks.length > 0 && (
            <div className="glass-hero p-4 space-y-3">
              <div className="flex items-center gap-2">
                <MousePointerClick size={16} style={{ color: "var(--accent)" }} />
                <p className="font-semibold text-sm">Топ кнопок / действий</p>
              </div>
              <div className="space-y-2">
                {data.top_clicks.slice(0, 10).map((c, i) => (
                  <div key={c.key} className="flex items-center gap-2">
                    <span className="text-xs w-4 text-right" style={{ color: "var(--text-hint)" }}>
                      {i + 1}
                    </span>
                    <div className="flex-1 h-5 rounded relative overflow-hidden"
                         style={{ background: "var(--card-bg)" }}>
                      <div
                        className="h-full rounded transition-all"
                        style={{
                          width: `${(c.count / maxClicksCnt) * 100}%`,
                          background: "var(--accent)44",
                        }}
                      />
                      <span className="absolute inset-0 flex items-center px-2 text-[11px] font-medium">
                        {c.key}
                      </span>
                    </div>
                    <span className="text-xs font-bold w-10 text-right">
                      {c.count.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Daily sessions bar chart */}
          {data.daily_sessions.length > 0 && (
            <div className="glass-hero p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Users size={16} style={{ color: "var(--accent)" }} />
                <p className="font-semibold text-sm">Сессии по дням</p>
              </div>
              <div className="flex items-end gap-1 h-24">
                {data.daily_sessions.map(d => (
                  <div key={d.date} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                    <div
                      className="w-full rounded-t"
                      style={{
                        height: `${Math.max((d.count / maxDaily) * 80, 2)}px`,
                        background: "var(--accent)88",
                      }}
                    />
                    <span className="text-[9px] truncate w-full text-center"
                          style={{ color: "var(--text-hint)" }}>
                      {d.date.slice(5)} {/* MM-DD */}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
