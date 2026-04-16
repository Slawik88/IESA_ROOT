/* ──────────────────────────────────────────────────────────────
   Settings.tsx — Настройки чата и глобальные настройки
   GET/POST /api/settings/local   (rank-gated per-chat settings)
   GET/POST /api/settings/global  (developer only)
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Settings2, Loader2, Lock } from "lucide-react";
import {
  fetchSettingsLocal,
  updateSettingLocal,
  fetchSettingsGlobal,
  updateSettingGlobal,
  type SettingsLocalResponse,
  type SettingsGlobalResponse,
} from "../lib/api";

interface Props { userId: number; chatId: number; isDev?: boolean; }

type SettingsTab = "local" | "global";

const SETTING_META: Record<string, { label: string; type: "toggle" | "select" | "number"; options?: string[]; desc?: string }> = {
  antiflood_enabled:       { label: "Антифлуд включён",           type: "toggle",  desc: "Ограничивать частоту сообщений" },
  antiflood_limit:         { label: "Лимит антифлуда",            type: "number" },
  antiflood_window:        { label: "Окно антифлуда (сек)",       type: "number" },
  antiflood_action:        { label: "Действие антифлуда",         type: "select",  options: ["warn", "mute", "kick", "ban"] },
  antiflood_mode:          { label: "Режим антифлуда",            type: "select",  options: ["soft", "hard"] },
  blacklist_enabled:       { label: "Чёрный список",              type: "toggle" },
  welcome_call:            { label: "Приветствие",                type: "toggle" },
  feat_website:            { label: "Фича: Сайт",                 type: "toggle" },
  feat_antispam:           { label: "Фича: Антиспам",             type: "toggle" },
  feat_marriages:          { label: "Фича: Браки",                type: "toggle" },
  feat_pets:               { label: "Фича: Питомцы",              type: "toggle" },
  feat_casino:             { label: "Фича: Казино",               type: "toggle" },
  feat_random_events:      { label: "Фича: Случайные события",    type: "toggle" },
  bot_disabled:            { label: "Бот отключён",               type: "toggle" },
  feat_roulette:           { label: "Фича: Рулетка",              type: "toggle" },
  feat_chest:              { label: "Фича: Сундуки",              type: "toggle" },
  feat_coin_flip:          { label: "Фича: Монетка",              type: "toggle" },
  feat_xp_gain:            { label: "Фича: Получение XP",         type: "toggle" },
  feat_auto_welcome:       { label: "Фича: Авто-приветствие",     type: "toggle" },
  cleanup_threshold:       { label: "Порог очистки (дни неакт.)", type: "number" },
  cleanup_message_norm:    { label: "Норма сообщений для очистки", type: "number" },
  cleanup_warn_hours:      { label: "Предупреждение за (часов)",   type: "number" },
  inactivity_warn_enabled: { label: "Предупреждение о неактивности", type: "toggle" },
  inactivity_warn_days:    { label: "Дней неактивности",           type: "number" },
};

const GLOBAL_META: Record<string, { label: string; type: "toggle" | "number" }> = {
  maintenance_mode:    { label: "Режим обслуживания",    type: "toggle" },
  bond_limit_per_user: { label: "Лимит облигаций (штук)", type: "number" },
  shop_enabled:        { label: "Магазин включён",        type: "toggle" },
  gacha_enabled:       { label: "Гача включена",          type: "toggle" },
  auction_enabled:     { label: "Аукцион включён",        type: "toggle" },
};

export default function Settings({ chatId, isDev }: Props) {
  const [tab, setTab]             = useState<SettingsTab>("local");
  const [localData, setLocalData] = useState<SettingsLocalResponse | null>(null);
  const [globalData, setGlobalData] = useState<SettingsGlobalResponse | null>(null);
  const [error, setError]         = useState("");
  const [busy, setBusy]           = useState<string | null>(null);
  const [toast, setToast]         = useState<{ msg: string; ok: boolean } | null>(null);

  const showToast = useCallback((msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3500);
  }, []);

  const loadLocal = useCallback(() => {
    if (!chatId) return;
    fetchSettingsLocal(chatId).then(setLocalData).catch((e: Error) => setError(e.message));
  }, [chatId]);

  const loadGlobal = useCallback(() => {
    fetchSettingsGlobal().then(setGlobalData).catch(() => {});
  }, []);

  useEffect(() => { loadLocal(); }, [loadLocal]);
  useEffect(() => { if (tab === "global") loadGlobal(); }, [tab, loadGlobal]);

  const doUpdateLocal = useCallback(async (key: string, value: unknown) => {
    if (busy) return;
    setBusy(key);
    try {
      const res = await updateSettingLocal(chatId, key, value);
      if (res.ok) {
        showToast("Сохранено");
        setLocalData(prev => prev ? { ...prev, settings: { ...prev.settings, [key]: value } } : prev);
      } else {
        showToast(res.error ?? "Ошибка", false);
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка", false);
    } finally { setBusy(null); }
  }, [busy, chatId, showToast]);

  const doUpdateGlobal = useCallback(async (key: string, value: string) => {
    if (busy) return;
    setBusy(key);
    try {
      const res = await updateSettingGlobal(key, value);
      if (res.ok) {
        showToast("Глобально сохранено");
        setGlobalData(prev => prev ? { ...prev, settings: { ...prev.settings, [key]: value } } : prev);
      } else {
        showToast(res.error ?? "Ошибка", false);
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка", false);
    } finally { setBusy(null); }
  }, [busy, showToast]);

  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <p className="font-medium">Ошибка</p>
        <p className="text-sm mt-1">{error}</p>
        <button onClick={loadLocal} className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}>Обновить</button>
      </div>
    );
  }

  return (
    <div className="animate-fadeIn p-4 space-y-4 pb-24">
      {toast && (
        <div className="fixed top-4 left-4 right-4 z-50 px-4 py-3 rounded-xl text-sm font-medium text-white shadow-xl"
             style={{ backgroundColor: toast.ok ? "var(--accent)" : "#e74c3c" }}>
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="glass-hero p-4 flex items-center gap-3">
        <div className="p-2 rounded-xl" style={{ backgroundColor: "var(--accent-soft)" }}>
          <Settings2 size={22} style={{ color: "var(--accent)" }} />
        </div>
        <div>
          <p className="font-bold text-base">Настройки</p>
          {localData && (
            <p className="text-xs" style={{ color: "var(--text-hint)" }}>
              Ранг: <span style={{ color: "var(--accent)" }}>{localData.user_rank}</span>
            </p>
          )}
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-2 rounded-2xl p-1.5 glass-card">
        {(["local", isDev ? "global" : null] as (SettingsTab | null)[]).filter(Boolean).map(t => (
          <button
            key={t as SettingsTab}
            onClick={() => setTab(t as SettingsTab)}
            className="flex-1 py-2 text-sm font-semibold rounded-xl transition-all"
            style={{
              backgroundColor: tab === t ? "var(--accent)" : "transparent",
              color: tab === t ? "#fff" : "var(--text-hint)",
            }}
          >
            {t === "local" ? "🏠 Чат" : "🌐 Глобальные"}
          </button>
        ))}
      </div>

      {/* LOCAL settings */}
      {tab === "local" && (
        !localData
          ? <div className="space-y-3 animate-pulse">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="skeleton h-14 rounded-xl" />)}</div>
          : (
            <div className="space-y-2">
              {Object.entries(SETTING_META).map(([key, meta]) => {
                const rawVal   = localData.settings[key];
                const rankReq  = localData.rank_map[key];
                const canEdit  = !rankReq || localData.user_rank_level >= rankReq.min_rank_level;
                return (
                  <div key={key} className="glass-card p-3 rounded-xl flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <p className="text-sm font-medium">{meta.label}</p>
                        {!canEdit && rankReq && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full"
                                style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-hint)" }}>
                            🔒 {rankReq.min_rank_name}
                          </span>
                        )}
                      </div>
                      {meta.desc && <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>{meta.desc}</p>}
                    </div>
                    <div className="flex-none">
                      {busy === key ? (
                        <Loader2 size={14} className="animate-spin" style={{ color: "var(--accent)" }} />
                      ) : meta.type === "toggle" ? (
                        <button
                          disabled={!canEdit}
                          onClick={() => doUpdateLocal(key, rawVal ? 0 : 1)}
                          className="w-10 h-6 rounded-full transition-all relative disabled:opacity-40"
                          style={{ backgroundColor: rawVal ? "var(--accent)" : "var(--bg-secondary)" }}
                        >
                          <span className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all"
                                style={{ left: rawVal ? "calc(100% - 1.25rem)" : "0.25rem" }} />
                        </button>
                      ) : meta.type === "select" ? (
                        <select
                          disabled={!canEdit}
                          value={String(rawVal ?? "")}
                          onChange={e => doUpdateLocal(key, e.target.value)}
                          className="text-xs rounded-lg px-2 py-1 border-0 disabled:opacity-40"
                          style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)" }}
                        >
                          {(meta.options ?? []).map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <input
                          type="number"
                          disabled={!canEdit}
                          defaultValue={Number(rawVal ?? 0)}
                          onBlur={e => doUpdateLocal(key, Number(e.target.value))}
                          className="w-16 text-xs rounded-lg px-2 py-1 border-0 text-center disabled:opacity-40"
                          style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)" }}
                        />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )
      )}

      {/* GLOBAL settings — dev only */}
      {tab === "global" && isDev && (
        !globalData
          ? <div className="space-y-3 animate-pulse">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-14 rounded-xl" />)}</div>
          : !globalData.is_dev
            ? (
              <div className="p-6 text-center" style={{ color: "var(--text-hint)" }}>
                <Lock size={32} className="mx-auto mb-2" strokeWidth={1.2} />
                <p className="text-sm">Только для разработчика</p>
              </div>
            )
            : (
              <div className="space-y-2">
                {Object.entries(GLOBAL_META).map(([key, meta]) => {
                  const rawVal = globalData.settings[key];
                  const isOn   = rawVal && rawVal !== "0" && rawVal !== 0;
                  return (
                    <div key={key} className="glass-card p-3 rounded-xl flex items-center gap-3">
                      <p className="text-sm font-medium flex-1">{meta.label}</p>
                      <div className="flex-none">
                        {busy === key ? (
                          <Loader2 size={14} className="animate-spin" style={{ color: "var(--accent)" }} />
                        ) : meta.type === "toggle" ? (
                          <button
                            onClick={() => doUpdateGlobal(key, isOn ? "0" : "1")}
                            className="w-10 h-6 rounded-full transition-all relative"
                            style={{ backgroundColor: isOn ? "var(--accent)" : "var(--bg-secondary)" }}
                          >
                            <span className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all"
                                  style={{ left: isOn ? "calc(100% - 1.25rem)" : "0.25rem" }} />
                          </button>
                        ) : (
                          <input
                            type="number"
                            defaultValue={Number(rawVal ?? 0)}
                            onBlur={e => doUpdateGlobal(key, e.target.value)}
                            className="w-16 text-xs rounded-lg px-2 py-1 border-0 text-center"
                            style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)" }}
                          />
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )
      )}
    </div>
  );
}
