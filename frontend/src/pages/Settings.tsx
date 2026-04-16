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
  antiflood_enabled:       { label: "Антифлуд",                    type: "toggle", desc: "Ограничивает слишком частую отправку сообщений" },
  antiflood_limit:         { label: "Лимит сообщений",             type: "number", desc: "Сколько сообщений можно отправить за окно антифлуда" },
  antiflood_window:        { label: "Окно проверки, сек",          type: "number", desc: "Период, в котором считается спам" },
  antiflood_action:        { label: "Наказание за спам",           type: "select", options: ["warn", "mute", "kick", "ban"], desc: "Что делать с нарушителем" },
  antiflood_mode:          { label: "Жёсткость защиты",            type: "select", options: ["soft", "hard"], desc: "Мягкий или строгий режим срабатывания" },
  blacklist_enabled:       { label: "Чёрный список",               type: "toggle", desc: "Блокировать слова и шаблоны из чёрного списка" },
  welcome_call:            { label: "Приветствие новичков",        type: "toggle", desc: "Показывать приветственное сообщение при входе" },
  feat_website:            { label: "Сайт",                        type: "toggle", desc: "Доступ к сайту и связанным функциям" },
  feat_antispam:           { label: "Антиспам",                    type: "toggle", desc: "Дополнительные антиспам-функции чата" },
  feat_marriages:          { label: "Браки",                       type: "toggle", desc: "Разрешить браки и парные механики" },
  feat_pets:               { label: "Питомцы",                     type: "toggle", desc: "Включить систему питомцев" },
  feat_casino:             { label: "Казино",                      type: "toggle", desc: "Открыть казино в мини-приложении" },
  feat_random_events:      { label: "Случайные события",           type: "toggle", desc: "Запускать неожиданные активности в чате" },
  bot_disabled:            { label: "Отключить бота",              type: "toggle", desc: "Полностью выключить активность бота в этом чате" },
  feat_roulette:           { label: "Рулетка",                     type: "toggle", desc: "Разрешить рулетку в казино" },
  feat_chest:              { label: "Сундуки",                     type: "toggle", desc: "Включить сундуки и награды" },
  feat_coin_flip:          { label: "Монетка",                     type: "toggle", desc: "Разрешить игру в монетку" },
  feat_xp_gain:            { label: "Получение XP",                type: "toggle", desc: "Игроки получают опыт за активность" },
  feat_auto_welcome:       { label: "Авто-приветствие",            type: "toggle", desc: "Бот сам приветствует новых участников" },
  cleanup_threshold:       { label: "Удаление после дней тишины",  type: "number", desc: "Через сколько дней неактивных пользователей считать на очистку" },
  cleanup_message_norm:    { label: "Минимум сообщений для защиты", type: "number", desc: "Пользователи с меньшей активностью попадут под очистку быстрее" },
  cleanup_warn_hours:      { label: "Предупредить заранее, часов", type: "number", desc: "За сколько часов бот предупреждает перед очисткой" },
  inactivity_warn_enabled: { label: "Предупреждать о неактивности", type: "toggle", desc: "Напоминать перед автоматической чисткой" },
  inactivity_warn_days:    { label: "Неактивность, дней",          type: "number", desc: "Через сколько дней начинать предупреждать" },
};

const LOCAL_SECTIONS: { title: string; desc: string; keys: string[] }[] = [
  {
    title: "Защита чата",
    desc: "Контроль спама, флуда и нежелательных сообщений.",
    keys: ["antiflood_enabled", "antiflood_limit", "antiflood_window", "antiflood_action", "antiflood_mode", "blacklist_enabled"],
  },
  {
    title: "Сценарии и функции",
    desc: "Что именно доступно участникам в этом чате.",
    keys: ["welcome_call", "feat_auto_welcome", "feat_website", "feat_antispam", "feat_marriages", "feat_pets", "feat_casino", "feat_roulette", "feat_coin_flip", "feat_chest", "feat_random_events", "feat_xp_gain", "bot_disabled"],
  },
  {
    title: "Чистка и неактив",
    desc: "Автоматическая очистка и предупреждения для неактивных участников.",
    keys: ["cleanup_threshold", "cleanup_message_norm", "cleanup_warn_hours", "inactivity_warn_enabled", "inactivity_warn_days"],
  },
];

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
              Ранг: <span style={{ color: "var(--accent)" }}>{localData.user_rank}</span> • Изменяй только то, что реально влияет на чат
            </p>
          )}
        </div>
      </div>

      {tab === "local" && localData && (
        <div className="glass-card p-4 grid grid-cols-2 gap-3">
          <div>
            <p className="text-[11px] font-semibold" style={{ color: "var(--text-hint)" }}>Доступ</p>
            <p className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{localData.user_rank}</p>
          </div>
          <div className="text-right">
            <p className="text-[11px] font-semibold" style={{ color: "var(--text-hint)" }}>Разделов</p>
            <p className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{LOCAL_SECTIONS.length}</p>
          </div>
        </div>
      )}

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
            <div className="space-y-4">
              {LOCAL_SECTIONS.map((section) => (
                <div key={section.title} className="glass-card p-4 space-y-3">
                  <div>
                    <p className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{section.title}</p>
                    <p className="text-xs mt-1" style={{ color: "var(--text-hint)" }}>{section.desc}</p>
                  </div>

                  <div className="space-y-2">
                    {section.keys.map((key) => {
                      const meta = SETTING_META[key];
                      const rawVal = localData.settings[key];
                      const rankReq = localData.rank_map[key];
                      const canEdit = !rankReq || localData.user_rank_level >= rankReq.min_rank_level;
                      return (
                        <div key={key} className="rounded-2xl p-3 flex items-center gap-3" style={{ backgroundColor: "var(--bg-secondary)" }}>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <p className="text-sm font-medium">{meta.label}</p>
                              {!canEdit && rankReq && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded-full"
                                      style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-hint)" }}>
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
                                style={{ backgroundColor: rawVal ? "var(--accent)" : "var(--bg-primary)" }}
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
                                style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                              >
                                {(meta.options ?? []).map(o => <option key={o} value={o}>{o}</option>)}
                              </select>
                            ) : (
                              <input
                                type="number"
                                disabled={!canEdit}
                                defaultValue={Number(rawVal ?? 0)}
                                onBlur={e => doUpdateLocal(key, Number(e.target.value))}
                                className="w-20 text-xs rounded-lg px-2 py-1 border-0 text-center disabled:opacity-40"
                                style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                              />
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
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
