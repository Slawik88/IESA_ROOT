/* ──────────────────────────────────────────────────────────────
   Shards.tsx — Осколки & Крафт
   GET  /api/shards?chat_id=X  →  {stash, catalog}
   POST /api/shards/craft  {chat_id, shard_key}
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Gem, Loader2, RefreshCw, X } from "lucide-react";
import { fetchShards, craftShard, type ShardsResponse } from "../lib/api";

interface Props { userId: number; chatId: number; }

interface ModalState { key: string; info: import("../lib/api").ShardCatalogEntry; }

export default function Shards({ chatId }: Props) {
  const [data, setData]       = useState<ShardsResponse | null>(null);
  const [error, setError]     = useState("");
  const [busy, setBusy]       = useState<string | null>(null);
  const [toast, setToast]     = useState<{ msg: string; ok: boolean } | null>(null);
  const [modal, setModal]     = useState<ModalState | null>(null);

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

  const doCraftBulk = useCallback(async (shardKey: string) => {
    if (busy) return;
    if (!data) return;
    
    const shardInfo = data.catalog[shardKey];
    if (!shardInfo) return;
    
    const maxCrafts = Math.floor(shardInfo.owned / shardInfo.craft_amount);
    if (maxCrafts < 1) return;
    
    setBusy(`bulk_${shardKey}`);
    let successCount = 0;
    
    try {
      // Craft items one by one to avoid race conditions
      for (let i = 0; i < maxCrafts; i++) {
        try {
          const res = await craftShard(chatId, shardKey);
          if (res.ok) {
            successCount++;
          } else {
            break; // Stop if we can't craft anymore
          }
        } catch (e) {
          break; // Stop on error
        }
      }
      
      if (successCount > 0) {
        showToast(`✅ Создано предметов: ${successCount}`);
        load();
      } else {
        showToast("Не удалось создать предметы", false);
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка массового крафта", false);
    } finally { setBusy(null); }
  }, [busy, data, chatId, load, showToast]);

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
          
          // ✨ Use enhanced readable target if available
          const craftTarget = info.readable_target || 
            (info.craft_frame ? `🖼 Рамка «${info.craft_frame}»` : `предмет: ${info.craft_into ?? "?"}`);
          
          return (
            <div key={key} className="glass-card p-4 rounded-xl cursor-pointer active:scale-[0.98] transition-transform"
                 onClick={() => setModal({ key, info })}>
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
                <div className="flex-none flex gap-1.5" onClick={e => e.stopPropagation()}>
                  <button
                    onClick={() => doCraft(key)}
                    disabled={!canCraft || !!busy}
                    className="px-3 py-2 rounded-lg text-xs font-semibold disabled:opacity-40 transition-all"
                    style={{ backgroundColor: canCraft ? "var(--accent)" : "var(--bg-secondary)", color: canCraft ? "#fff" : "var(--text-hint)" }}
                  >
                    {busy === key ? <Loader2 size={12} className="animate-spin" /> : "×1"}
                  </button>
                  {owned >= info.craft_amount * 3 && (
                    <button
                      onClick={() => doCraftBulk(key)}
                      disabled={!canCraft || !!busy}
                      className="px-2 py-2 rounded-lg text-xs font-semibold disabled:opacity-40 transition-all"
                      style={{ 
                        backgroundColor: canCraft ? "#22c55e" : "var(--bg-secondary)", 
                        color: canCraft ? "#fff" : "var(--text-hint)" 
                      }}
                      title={`Создать максимально (${Math.floor(owned / info.craft_amount)}шт)`}
                    >
                      {busy === `bulk_${key}` ? <Loader2 size={12} className="animate-spin" /> : "MAX"}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Shard Detail Modal ── */}
      {modal && (() => {
        const { key, info } = modal;
        const owned    = info.owned;
        const canCraft = owned >= info.craft_amount;
        const pct      = Math.min(100, (owned / info.craft_amount) * 100);
        const maxCrafts = Math.floor(owned / info.craft_amount);
        const craftTarget = info.readable_target ||
          (info.craft_frame ? `🖼 Рамка «${info.craft_frame}»` : `предмет: ${info.craft_into ?? "?"}`);
        return (
          <>
            <div className="fixed inset-0 z-40 bg-black/60" onClick={() => setModal(null)} />
            <div className="fixed bottom-0 inset-x-0 z-50 rounded-t-2xl pb-8 animate-slideUp"
                 style={{ backgroundColor: "var(--bg-primary)", maxHeight: "80vh", overflowY: "auto" }}>
              <div className="flex justify-center pt-3 pb-1">
                <div className="w-10 h-1 rounded-full" style={{ backgroundColor: "var(--border)" }} />
              </div>

              {/* Header */}
              <div className="flex items-start justify-between px-4 pt-2 pb-3">
                <div className="flex items-center gap-3">
                  <span className="text-4xl">{info.emoji}</span>
                  <div>
                    <h2 className="font-bold text-base" style={{ color: "var(--text-primary)" }}>{info.name}</h2>
                    <p className="text-xs" style={{ color: "var(--text-hint)" }}>
                      {info.craft_frame ? "🖼 Осколок рамки" : info.craft_into?.includes("potion") ? "🧪 Осколок зелья" : "⚔️ Осколок снаряжения"}
                    </p>
                  </div>
                </div>
                <button onClick={() => setModal(null)} style={{ color: "var(--text-hint)" }}><X size={20} /></button>
              </div>

              {/* Description */}
              {info.desc && (
                <div className="mx-4 mb-3 px-3 py-2.5 rounded-xl text-sm" style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-secondary)" }}>
                  {info.desc}
                </div>
              )}

              {/* Craft target info */}
              <div className="mx-4 mb-3 px-3 py-2.5 rounded-xl text-sm flex items-center justify-between"
                   style={{ backgroundColor: "var(--accent-soft)" }}>
                <span style={{ color: "var(--text-hint)" }}>Результат крафта:</span>
                <span className="font-semibold" style={{ color: "var(--accent)" }}>{craftTarget}</span>
              </div>

              {/* Progress */}
              <div className="px-4 mb-4">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold" style={{ color: "var(--text-hint)" }}>Прогресс</span>
                  <span className="text-xs font-bold tabular-nums" style={{ color: canCraft ? "#22c55e" : "var(--text-primary)" }}>
                    {owned} / {info.craft_amount}
                    {maxCrafts > 1 && <span className="ml-1.5 text-xs font-normal" style={{ color: "var(--text-hint)" }}>({maxCrafts}× доступно)</span>}
                  </span>
                </div>
                <div className="h-3 rounded-full overflow-hidden" style={{ backgroundColor: "var(--bg-secondary)" }}>
                  <div className="h-full rounded-full transition-all duration-500"
                       style={{ width: `${pct}%`, backgroundColor: canCraft ? "#22c55e" : "var(--accent)" }} />
                </div>
              </div>

              {/* Actions */}
              <div className="px-4 space-y-2">
                <button
                  onClick={() => { doCraft(key); setModal(null); }}
                  disabled={!canCraft || !!busy}
                  className="w-full py-3 rounded-xl text-sm font-bold disabled:opacity-40 transition-all"
                  style={{ backgroundColor: canCraft ? "var(--accent)" : "var(--bg-secondary)", color: canCraft ? "#fff" : "var(--text-hint)" }}>
                  {busy === key ? <Loader2 size={14} className="animate-spin inline" /> : `⚒️ Создать ×1`}
                </button>
                {maxCrafts >= 3 && (
                  <button
                    onClick={() => { doCraftBulk(key); setModal(null); }}
                    disabled={!canCraft || !!busy}
                    className="w-full py-3 rounded-xl text-sm font-bold disabled:opacity-40 transition-all"
                    style={{ backgroundColor: canCraft ? "#22c55e" : "var(--bg-secondary)", color: canCraft ? "#fff" : "var(--text-hint)" }}>
                    {busy === `bulk_${key}` ? <Loader2 size={14} className="animate-spin inline" /> : `⚒️ Создать всё (×${maxCrafts})`}
                  </button>
                )}
              </div>
            </div>
          </>
        );
      })()}
    </div>
  );
}
