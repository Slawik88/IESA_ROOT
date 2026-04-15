/* ──────────────────────────────────────────────────────────────
   Auction.tsx — Аукцион предметов
   Вкладки: Лоты | Мои лоты | Новый лот
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Gavel, Plus, Package, RefreshCw } from "lucide-react";
import {
  fetchAuctions,
  placeBid,
  buyoutAuction,
  cancelAuction,
  createAuction,
  fetchInventory,
  type AuctionLot,
  type AuctionListResponse,
} from "../lib/api";
import type { InventoryItem } from "../types";

interface Props {
  userId: number;
  chatId: number;
}

type SubTab = "lots" | "mine" | "new";

const fmt = (n: number) => n.toLocaleString("ru-RU");

function timeLeft(endsAt?: string | null): string {
  if (!endsAt) return "";
  const diff = Math.max(0, new Date(endsAt).getTime() - Date.now());
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  if (diff === 0) return "Завершён";
  if (h > 0) return `${h}ч ${m}м`;
  return `${m}м`;
}

export default function Auction({ userId, chatId }: Props) {
  const [data, setData]       = useState<AuctionListResponse | null>(null);
  const [tab, setTab]         = useState<SubTab>("lots");
  const [loading, setLoading] = useState(false);
  const [toast, setToast]     = useState<string | null>(null);
  const [toastErr, setToastErr] = useState<string | null>(null);

  const showOk  = useCallback((msg: string) => { setToast(msg);    setTimeout(() => setToast(null), 3000); }, []);
  const showErr = useCallback((msg: string) => { setToastErr(msg); setTimeout(() => setToastErr(null), 4000); }, []);

  const reload = useCallback(() => {
    if (!chatId) return;
    setLoading(true);
    fetchAuctions(chatId)
      .then(setData)
      .catch((e: Error) => showErr(e.message))
      .finally(() => setLoading(false));
  }, [chatId, showErr]);

  useEffect(() => { reload(); }, [reload]);

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-2" style={{ minHeight: "100vh" }}>
      {/* ── Заголовок ──────────────────────────────────────────── */}
      <div className="glass-hero p-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "var(--accent-soft)" }}>
            <Gavel size={18} style={{ color: "var(--accent)" }} />
          </div>
          <span className="font-bold text-base">Аукцион</span>
        </div>
        <button onClick={reload} disabled={loading} style={{ color: "var(--text-hint)" }}>
          <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* ── Под-вкладки ────────────────────────────────────────── */}
      <div className="flex gap-1 rounded-xl p-1" style={{ backgroundColor: "var(--bg-secondary)" }}>
        {(["lots", "mine", "new"] as SubTab[]).map((t) => {
          const labels: Record<SubTab, string> = { lots: "Лоты", mine: "Мои", new: "Выставить" };
          const active = tab === t;
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="flex-1 py-1.5 rounded-lg text-sm font-medium transition-all"
              style={{
                backgroundColor: active ? "var(--accent)" : "transparent",
                color: active ? "#fff" : "var(--text-hint)",
              }}
            >
              {labels[t]}
            </button>
          );
        })}
      </div>

      {/* ── Контент ────────────────────────────────────────────── */}
      {tab === "lots" && (
        <LotsList lots={data?.lots ?? []} userId={userId} chatId={chatId}
          onBid={(id, amount) => {
            placeBid(chatId, id, amount)
              .then(() => { showOk("Ставка принята!"); reload(); })
              .catch((e: Error) => showErr(extractError(e.message)));
          }}
          onBuyout={(id) => {
            buyoutAuction(chatId, id)
              .then(() => { showOk("Выкуп выполнен!"); reload(); })
              .catch((e: Error) => showErr(extractError(e.message)));
          }}
        />
      )}

      {tab === "mine" && (
        <MyLots
          myLots={data?.my_lots ?? []}
          myBids={data?.my_bids ?? []}
          userId={userId}
          chatId={chatId}
          onCancel={(id) => {
            cancelAuction(chatId, id)
              .then(() => { showOk("Лот отменён"); reload(); })
              .catch((e: Error) => showErr(extractError(e.message)));
          }}
        />
      )}

      {tab === "new" && (
        <NewLotForm
          chatId={chatId}
          onCreated={() => { showOk("Лот выставлен!"); reload(); setTab("mine"); }}
          onError={showErr}
        />
      )}

      {/* ── Тосты ─────────────────────────────────────────────── */}
      {toast && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-xl text-sm font-medium shadow-lg"
          style={{ backgroundColor: "#22c55e", color: "#fff" }}>
          {toast}
        </div>
      )}
      {toastErr && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-xl text-sm font-medium shadow-lg"
          style={{ backgroundColor: "#ef4444", color: "#fff" }}>
          {toastErr}
        </div>
      )}
    </div>
  );
}

// ── Компонент: список всех лотов ──────────────────────────────

function LotsList({
  lots, userId, chatId: _chatId, onBid, onBuyout,
}: {
  lots: AuctionLot[];
  userId: number;
  chatId: number;
  onBid: (id: number, amount: number) => void;
  onBuyout: (id: number) => void;
}) {
  const [bidInputs, setBidInputs] = useState<Record<number, string>>({});

  if (lots.length === 0) {
    return (
      <div className="text-center py-12" style={{ color: "var(--text-hint)" }}>
        <Package size={40} strokeWidth={1.2} className="mx-auto mb-2" />
        <p className="text-sm">Нет активных лотов</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {lots.map((lot) => {
        const isMine = lot.seller_id === userId;
        const minBid = (lot.current_bid ?? lot.start_price) + 1;
        return (
          <div
            key={lot.id}
            className="rounded-2xl p-4 space-y-2"
            style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
                  {lot.item_name}
                </p>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>
                  Продавец: {lot.seller_name ?? lot.seller_id}
                </p>
              </div>
              {lot.ends_at && (
                <span className="text-xs px-2 py-0.5 rounded-full shrink-0"
                  style={{ backgroundColor: "var(--accent-soft)", color: "var(--accent)" }}>
                  ⏱ {timeLeft(lot.ends_at)}
                </span>
              )}
            </div>

            <div className="flex gap-4 text-sm">
              <div>
                <span className="text-xs" style={{ color: "var(--text-hint)" }}>Ставка</span>
                <p className="font-bold tabular-nums">{fmt(lot.current_bid ?? lot.start_price)} 🪙</p>
              </div>
              {lot.buyout_price && (
                <div>
                  <span className="text-xs" style={{ color: "var(--text-hint)" }}>Выкуп</span>
                  <p className="font-bold tabular-nums" style={{ color: "#f59e0b" }}>{fmt(lot.buyout_price)} 🪙</p>
                </div>
              )}
              {lot.bidder_name && (
                <div>
                  <span className="text-xs" style={{ color: "var(--text-hint)" }}>Лидер</span>
                  <p className="text-xs font-medium">{lot.bidder_name}</p>
                </div>
              )}
            </div>

            {!isMine && (
              <div className="flex gap-2 pt-1">
                <input
                  type="number"
                  min={minBid}
                  placeholder={`от ${fmt(minBid)}`}
                  value={bidInputs[lot.id] ?? ""}
                  onChange={(e) => setBidInputs(prev => ({ ...prev, [lot.id]: e.target.value }))}
                  className="flex-1 rounded-lg px-3 py-1.5 text-sm border"
                  style={{
                    backgroundColor: "var(--bg-primary)",
                    borderColor: "var(--border)",
                    color: "var(--text-primary)",
                  }}
                />
                <button
                  onClick={() => {
                    const amt = parseInt(bidInputs[lot.id] ?? "");
                    if (!isNaN(amt) && amt >= minBid) {
                      onBid(lot.id, amt);
                      setBidInputs(prev => ({ ...prev, [lot.id]: "" }));
                    }
                  }}
                  className="px-3 py-1.5 rounded-lg text-sm font-medium"
                  style={{ backgroundColor: "var(--accent)", color: "#fff" }}
                >
                  Ставка
                </button>
                {lot.buyout_price && (
                  <button
                    onClick={() => onBuyout(lot.id)}
                    className="px-3 py-1.5 rounded-lg text-sm font-medium"
                    style={{ backgroundColor: "#f59e0b22", color: "#f59e0b", border: "1px solid #f59e0b44" }}
                  >
                    Выкуп
                  </button>
                )}
              </div>
            )}
            {isMine && (
              <p className="text-xs text-center py-1" style={{ color: "var(--text-hint)" }}>Ваш лот</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Компонент: мои лоты и ставки ──────────────────────────────

function MyLots({
  myLots, myBids, userId: _userId, chatId: _chatId, onCancel,
}: {
  myLots: AuctionLot[];
  myBids: AuctionLot[];
  userId: number;
  chatId: number;
  onCancel: (id: number) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase mb-2" style={{ color: "var(--text-hint)" }}>
          Мои лоты ({myLots.length})
        </p>
        {myLots.length === 0 ? (
          <p className="text-sm py-3 text-center" style={{ color: "var(--text-hint)" }}>Нет активных лотов</p>
        ) : (
          <div className="space-y-2">
            {myLots.map((lot) => (
              <div key={lot.id} className="rounded-xl p-3 flex items-center justify-between gap-2"
                style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                <div>
                  <p className="text-sm font-semibold">{lot.item_name}</p>
                  <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>
                    Ставка: {fmt(lot.current_bid ?? lot.start_price)} 🪙
                    {lot.bidder_name && ` · ${lot.bidder_name}`}
                  </p>
                </div>
                <button
                  onClick={() => onCancel(lot.id)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium shrink-0"
                  style={{ backgroundColor: "#ef444422", color: "#ef4444" }}
                >
                  Отменить
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <p className="text-xs font-semibold uppercase mb-2" style={{ color: "var(--text-hint)" }}>
          Мои ставки ({myBids.length})
        </p>
        {myBids.length === 0 ? (
          <p className="text-sm py-3 text-center" style={{ color: "var(--text-hint)" }}>Нет активных ставок</p>
        ) : (
          <div className="space-y-2">
            {myBids.map((lot) => (
              <div key={lot.id} className="rounded-xl p-3 flex items-center justify-between"
                style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                <div>
                  <p className="text-sm font-semibold">{lot.item_name}</p>
                  <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>
                    Моя ставка: {fmt(lot.current_bid ?? 0)} 🪙 · {timeLeft(lot.ends_at)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Компонент: форма нового лота ──────────────────────────────

function NewLotForm({
  chatId,
  onCreated,
  onError,
}: {
  chatId: number;
  onCreated: () => void;
  onError: (msg: string) => void;
}) {
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [invLoading, setInvLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState<InventoryItem | null>(null);
  const [startPrice, setStartPrice] = useState("");
  const [buyoutPrice, setBuyoutPrice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchInventory(chatId)
      .then((r) => {
        setInventory(r.items.filter((i) => i.rarity !== "junk"));
      })
      .catch(() => setInventory([]))
      .finally(() => setInvLoading(false));
  }, [chatId]);

  const handleSubmit = () => {
    if (!selectedItem) { onError("Выберите предмет"); return; }
    const sp = parseInt(startPrice);
    if (isNaN(sp) || sp <= 0) { onError("Стартовая цена должна быть > 0"); return; }
    const bp = buyoutPrice ? parseInt(buyoutPrice) : undefined;
    if (bp !== undefined && bp <= sp) { onError("Цена выкупа должна быть > стартовой"); return; }

    setSubmitting(true);
    createAuction(chatId, {
      item_id: selectedItem.id,
      item_source: "gacha",
      start_price: sp,
      buyout_price: bp,
    })
      .then(() => onCreated())
      .catch((e: Error) => onError(extractError(e.message)))
      .finally(() => setSubmitting(false));
  };

  return (
    <div className="space-y-4">
      <p className="text-sm font-medium" style={{ color: "var(--text-hint)" }}>
        Выставьте предмет из инвентаря на аукцион
      </p>

      {invLoading ? (
        <div className="space-y-2 animate-pulse">
          {[1, 2, 3].map((i) => <div key={i} className="skeleton h-14 rounded-xl" />)}
        </div>
      ) : inventory.length === 0 ? (
        <p className="text-sm text-center py-6" style={{ color: "var(--text-hint)" }}>
          Нет предметов для выставления
        </p>
      ) : (
        <div className="space-y-2 max-h-[40vh] overflow-y-auto">
          {inventory.map((item) => (
            <button
              key={item.id}
              onClick={() => setSelectedItem(item)}
              className="w-full rounded-xl p-3 flex items-center justify-between text-left"
              style={{
                backgroundColor: selectedItem?.id === item.id ? "var(--accent-soft)" : "var(--bg-secondary)",
                border: `1.5px solid ${selectedItem?.id === item.id ? "var(--accent)" : "var(--border)"}`,
              }}
            >
              <span className="text-sm font-medium">{item.name}</span>
              <span className="text-xs px-2 py-0.5 rounded-full font-medium capitalize"
                style={{ backgroundColor: "#3b82f622", color: "#3b82f6" }}>
                {item.rarity}
              </span>
            </button>
          ))}
        </div>
      )}

      <div className="space-y-2">
        <label className="text-xs font-medium" style={{ color: "var(--text-hint)" }}>
          Стартовая цена (🪙) *
        </label>
        <input
          type="number"
          min={1}
          placeholder="Например: 100"
          value={startPrice}
          onChange={(e) => setStartPrice(e.target.value)}
          className="w-full rounded-xl px-3 py-2.5 text-sm border"
          style={{
            backgroundColor: "var(--bg-secondary)",
            borderColor: "var(--border)",
            color: "var(--text-primary)",
          }}
        />
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium" style={{ color: "var(--text-hint)" }}>
          Цена мгновенного выкупа (🪙, необязательно)
        </label>
        <input
          type="number"
          min={1}
          placeholder="Оставьте пустым для аукциона"
          value={buyoutPrice}
          onChange={(e) => setBuyoutPrice(e.target.value)}
          className="w-full rounded-xl px-3 py-2.5 text-sm border"
          style={{
            backgroundColor: "var(--bg-secondary)",
            borderColor: "var(--border)",
            color: "var(--text-primary)",
          }}
        />
      </div>

      <button
        onClick={handleSubmit}
        disabled={submitting || !selectedItem}
        className="w-full py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2"
        style={{
          backgroundColor: selectedItem ? "var(--accent)" : "var(--bg-secondary)",
          color: selectedItem ? "#fff" : "var(--text-hint)",
        }}
      >
        <Plus size={16} />
        {submitting ? "Выставляю..." : "Выставить на аукцион"}
      </button>
    </div>
  );
}

function extractError(msg: string): string {
  try { return JSON.parse(msg.split("API 400: ")[1]).error ?? msg; } catch { return msg; }
}
