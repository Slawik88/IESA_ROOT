/* ──────────────────────────────────────────────────────────────
   Shards.tsx — Осколки & Крафт
   GET  /api/shards?chat_id=X  →  {stash, catalog}
   POST /api/shards/craft  {chat_id, shard_key}
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Gem, Loader2, RefreshCw } from "lucide-react";
import { fetchShards, craftShard, type ShardsResponse } from "../lib/api";

interface Props { userId: number; chatId: number; }

export default function Shards({ chatId }: Props) {
  const [data, setData]   = useState<ShardsResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy]   = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  const showToast = useCallback((msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3500);
  }, []);

  const load = useCallback(() => {
    if (!chatId) return;
    fetchShards(chatId).then(setData).catch((e: Error) => setError(e.message));
  }, [chatId]);

  useEffect(() => { load(); }, [load]);

  const doCraft = useCallback(async (shardKey: string) => {
    if (busy) return;
    setBusy(shardKey);
    try {
      const res = await craftShard(chatId, shardKey);
      if (res.ok) {
        showToast(`✅ ${res.message ?? "Предмет создан!"}`);
        load();
      } else {
        showToast(res.error ?? "Недостаточно осколков", false);
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка", false);
    } finally { setBusy(null); }
  }, [busy, chatId, load, showToast]);

  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <p className="font-medium">Ошибка загрузки</p>
        <p className="text-sm mt-1 break-all">{error}</p>
        <button onClick={load} className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}>Обновить</button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 space-y-3 animate-pulse">
        {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-24 rounded-xl" />)}
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
      <div className="glass-hero p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl" style={{ backgroundColor: "var(--accent-soft)" }}>
            <Gem size={22} style={{ color: "var(--accent)" }} />
          </div>
          <div>
            <p className="font-bold text-base">Осколки & Крафт</p>
            <p className="text-xs" style={{ color: "var(--text-hint)" }}>Собирай осколки и создавай предметы</p>
          </div>
        </div>
        <button onClick={load} className="p-2 rounded-lg" style={{ color: "var(--text-hint)" }}>
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Quick stash overview */}
      {Object.keys(data.stash).length > 0 && (
        <div className="glass-card p-3 rounded-xl">
          <p className="text-xs font-semibold mb-2" style={{ color: "var(--text-hint)" }}>Ваш запас</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.stash).map(([k, v]) => {
              const cat = data.catalog[k];
              return (
                <div key={k} className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs"
                     style={{ backgroundColor: "var(--bg-secondary)" }}>
                  <span>{cat?.emoji ?? "🔹"}</span>
                  <span className="font-semibold">{v}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Catalog */}
      <div className="space-y-3">
        {Object.entries(data.catalog).map(([key, info]) => {
          const owned    = info.owned;
          const canCraft = owned >= info.craft_amount;
          const pct      = Math.min(100, (owned / info.craft_amount) * 100);
          const craftTarget = info.craft_frame
            ? `🖼 Рамка «${info.craft_frame}»`
            : `предмет: ${info.craft_into ?? "?"}`;
          return (
            <div key={key} className="glass-card p-4 rounded-xl">
              <div className="flex items-center gap-3">
                <span className="text-3xl flex-none">{info.emoji}</span>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm">{info.name}</p>
                  <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>
                    {info.craft_amount} шт. → {craftTarget}
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <div className="h-2 flex-1 rounded-full overflow-hidden" style={{ backgroundColor: "var(--bg-secondary)" }}>
                      <div className="h-full rounded-full transition-all"
                           style={{ width: `${pct}%`, backgroundColor: canCraft ? "#22c55e" : "var(--accent)" }} />
                    </div>
                    <span className="text-xs font-semibold tabular-nums"
                          style={{ color: canCraft ? "#22c55e" : "var(--text-hint)" }}>
                      {owned}/{info.craft_amount}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => doCraft(key)}
                  disabled={!canCraft || !!busy}
                  className="flex-none px-3 py-2 rounded-lg text-xs font-semibold disabled:opacity-40 transition-all"
                  style={{ backgroundColor: canCraft ? "var(--accent)" : "var(--bg-secondary)", color: canCraft ? "#fff" : "var(--text-hint)" }}
                >
                  {busy === key ? <Loader2 size={12} className="animate-spin" /> : "Создать"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
