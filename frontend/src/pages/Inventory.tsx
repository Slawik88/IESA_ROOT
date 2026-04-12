/* ──────────────────────────────────────────────────────────────
   Inventory.tsx — Инвентарь (гача-предметы пользователя)
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState } from "react";
import { Backpack, Sparkles } from "lucide-react";
import { fetchUserData } from "../lib/api";

interface Props {
  userId: number;
}

const RARITY_COLORS: Record<string, string> = {
  common:    "#9ca3af",
  uncommon:  "#22c55e",
  rare:      "#3b82f6",
  epic:      "#a855f7",
  legendary: "#f59e0b",
};

/** Парсит строку вида "★Кинжал (rare)" */
function parseItem(raw: string): { name: string; rarity: string; equipped: boolean } {
  const equipped = raw.startsWith("★");
  const clean = equipped ? raw.slice(1) : raw;
  const match = clean.match(/^(.+?)\s*\((\w+)\)$/);
  if (match) {
    return { name: match[1].trim(), rarity: match[2].toLowerCase(), equipped };
  }
  return { name: clean, rarity: "common", equipped };
}

export default function Inventory({ userId }: Props) {
  const [items, setItems] = useState<string[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!userId) return;
    fetchUserData(userId)
      .then((d) => setItems(d.items))
      .catch((e: Error) => setError(e.message));
  }, [userId]);

  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <p className="font-medium">Ошибка</p>
        <p className="text-sm mt-1">{error}</p>
      </div>
    );
  }

  if (!items) {
    return (
      <div className="p-4 space-y-3 animate-pulse">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton h-14 rounded-xl" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3" style={{ color: "var(--text-hint)" }}>
        <Backpack size={48} strokeWidth={1.2} />
        <p className="text-sm">Инвентарь пуст</p>
      </div>
    );
  }

  const parsed = items.map(parseItem);

  return (
    <div className="animate-fadeIn p-4">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <Backpack size={20} />
        Инвентарь
        <span className="text-sm font-normal" style={{ color: "var(--text-hint)" }}>
          ({parsed.length})
        </span>
      </h2>

      <div className="space-y-2">
        {parsed.map((item, i) => (
          <div
            key={i}
            className="rounded-xl p-3 flex items-center gap-3"
            style={{ backgroundColor: "var(--bg-secondary)" }}
          >
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
              style={{ backgroundColor: RARITY_COLORS[item.rarity] + "22", color: RARITY_COLORS[item.rarity] }}
            >
              <Sparkles size={16} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium truncate">
                {item.equipped && <span className="text-amber-400 mr-1">★</span>}
                {item.name}
              </p>
              <p className="text-[11px] capitalize" style={{ color: RARITY_COLORS[item.rarity] }}>
                {item.rarity}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
