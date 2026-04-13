/* ──────────────────────────────────────────────────────────────
   Shop.tsx — Магазин
   Вкладки: Рамки | Косметика | Питомцы | Еда | Зелья | Темы
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { ShoppingBag, CheckCircle2, Palette, Loader2, Lock, Gem } from "lucide-react";
import { fetchShopCatalog, buyShopItem, fetchThemes, activateTheme, buyCrystalItem, saveAvatar, fetchUserData } from "../lib/api";
import type {
  ShopCatalog,
  ShopFrame,
  ShopCosmetic,
  ShopPetColor,
  ShopFood,
  ShopPotion,
  ProfileTheme,
  ThemesResponse,
} from "../types";

interface Props {
  userId: number;
  chatId: number;
}

type ShopTab = "frames" | "cosmetics" | "pets" | "food" | "potions" | "themes" | "donate";

const fmt = (n: number) => n.toLocaleString("ru-RU");

export default function Shop({ chatId }: Props) {
  const [data, setData]           = useState<ShopCatalog | null>(null);
  const [error, setError]         = useState("");
  const [tab, setTab]             = useState<ShopTab>("frames");
  const [buying, setBuying]       = useState<string | null>(null);
  const [toast, setToast]         = useState<string | null>(null);
  const [toastError, setToastErr] = useState<string | null>(null);

  // Themes tab state
  const [themesData, setThemesData]     = useState<ThemesResponse | null>(null);
  const [activatingTheme, setActivating] = useState<string | null>(null);

  // Donate tab state
  const [crystalBalance, setCrystalBalance] = useState<number | null>(null);

  const showOk  = useCallback((msg: string) => { setToast(msg);    setTimeout(() => setToast(null), 3500); }, []);
  const showErr = useCallback((msg: string) => { setToastErr(msg); setTimeout(() => setToastErr(null), 4000); }, []);

  const reload = useCallback(() => {
    if (!chatId) return;
    fetchShopCatalog(chatId).then(setData).catch((e: Error) => setError(e.message));
  }, [chatId]);

  useEffect(() => { reload(); }, [reload]);

  const loadThemes = useCallback(() => {
    if (!chatId) return;
    fetchThemes(chatId).then(setThemesData).catch(() => { /* ignore */ });
  }, [chatId]);

  useEffect(() => {
    if (tab === "themes") loadThemes();
    if (tab === "donate") fetchUserData(chatId).then(d => setCrystalBalance(d.crystals ?? 0)).catch(() => {});
  }, [tab, loadThemes, chatId]);

  const buy = useCallback(async (
    itemType: "frame" | "cosmetic" | "pet_color" | "potion",
    key: string,
    label: string,
  ) => {
    if (buying) return;
    setBuying(key);
    try {
      const res = await buyShopItem(chatId, itemType, key);
      if (res.ok) {
        showOk(`${label} куплено! ${res.balance !== undefined ? `Баланс: ${fmt(res.balance)} 🪙` : ""}`);
        reload();
      } else {
        showErr(res.error ?? "Ошибка покупки");
      }
    } catch (e: unknown) {
      showErr(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBuying(null);
    }
  }, [buying, chatId, showOk, showErr, reload]);

  const doActivateTheme = useCallback(async (theme: ProfileTheme) => {
    if (activatingTheme) return;
    setActivating(theme.key);
    try {
      if (!theme.owned) {
        // Purchase via shop catalog
        const r = await buyShopItem(chatId, "profile_theme", theme.key, true);
        if (r.ok) { showOk(`Тема «${theme.name}» куплена и активирована!`); }
        else      { showErr(r.error ?? "Ошибка покупки"); setActivating(null); return; }
      } else {
        const r = await activateTheme(chatId, theme.key);
        if (r.ok) { showOk(`Тема «${theme.name}» активирована`); }
        else      { showErr(r.error ?? "Ошибка"); setActivating(null); return; }
      }
      // Instant apply: update data-theme on <html> without page reload
      if (theme.key && theme.key !== "default") {
        document.documentElement.setAttribute("data-theme", theme.key);
      } else {
        document.documentElement.removeAttribute("data-theme");
      }
      loadThemes();
    } catch (e: unknown) {
      showErr(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setActivating(null);
    }
  }, [activatingTheme, chatId, showOk, showErr, loadThemes]);

  if (!chatId) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 p-6 text-center">
        <ShoppingBag size={48} strokeWidth={1.2} style={{ color: "var(--text-hint)" }} />
        <div>
          <p className="font-semibold">Нет контекста чата</p>
          <p className="text-sm mt-1" style={{ color: "var(--text-hint)" }}>
            Откройте Mini App из чата группы.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <p className="font-medium">Ошибка загрузки магазина</p>
        <p className="text-sm mt-1 break-all">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 space-y-3 animate-pulse">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="skeleton h-16 rounded-xl" />
        ))}
      </div>
    );
  }

  const shopTabs: { key: ShopTab; label: string }[] = [
    { key: "frames",    label: "Рамки" },
    { key: "cosmetics", label: "Косметика" },
    { key: "pets",      label: "Питомцы" },
    { key: "food",      label: "Еда" },
    { key: "potions",   label: "Зелья" },
    { key: "themes",    label: "🎨 Темы" },
    { key: "donate",    label: "💎 Донат" },
  ];

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-2">

      {/* ── Заголовок с балансом ────────────────────────────────── */}
      <div
        className="rounded-2xl p-4 flex items-center justify-between"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        <div className="flex items-center gap-2">
          <ShoppingBag size={20} style={{ color: "var(--accent)" }} />
          <span className="font-bold text-base">Магазин</span>
          {data.has_vip && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded"
              style={{ backgroundColor: "#f59e0b", color: "#000" }}>VIP</span>
          )}
        </div>
        <p className="text-lg font-bold tabular-nums">{fmt(data.balance)} 🪙</p>
      </div>

      {/* ── Под-вкладки (горизонтальный скролл) ────────────────── */}
      <div
        className="flex gap-1 overflow-x-auto rounded-xl p-1"
        style={{ backgroundColor: "var(--bg-secondary)", scrollbarWidth: "none" }}
      >
        {shopTabs.map(({ key, label }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className="flex-none px-3 py-1.5 text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
              style={{
                backgroundColor: active ? "var(--accent)" : "transparent",
                color: active ? "#fff" : "var(--text-hint)",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* ── Контент вкладок ─────────────────────────────────────── */}
      {tab === "frames"    && <FrameList    frames={data.frames}           buying={buying} onBuy={buy} />}
      {tab === "cosmetics" && <CosmeticList cosmetics={data.cosmetics}     buying={buying} onBuy={buy} />}
      {tab === "pets"      && <PetColorList petColors={data.pet_colors}    buying={buying} onBuy={buy} />}
      {tab === "food"      && <FoodList     food={data.food}               buying={buying} onBuy={buy} />}
      {tab === "potions"   && <PotionList   potions={data.potions}         buying={buying} onBuy={buy} />}
      {tab === "themes"    && <ThemeList    themes={themesData} activating={activatingTheme} onActivate={doActivateTheme} />}
      {tab === "donate"    && <DonateTab    chatId={chatId} balance={crystalBalance} onRefresh={() => fetchUserData(chatId).then(d => setCrystalBalance(d.crystals ?? 0)).catch(() => {})} showOk={showOk} showErr={showErr} />}

      {/* ── Тосты ─────────────────────────────────────────────── */}
      {toast && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-[90vw] px-4 py-2.5 rounded-xl text-sm font-medium shadow-lg pointer-events-none"
          style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--accent)" }}>
          {toast}
        </div>
      )}
      {toastError && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-[90vw] px-4 py-2.5 rounded-xl text-sm font-medium shadow-lg pointer-events-none"
          style={{ backgroundColor: "#450a0a", color: "#fca5a5", border: "1px solid #ef4444" }}>
          {toastError}
        </div>
      )}
    </div>
  );
}

/* ── FrameList ────────────────────────────────────────────────── */

function FrameList({ frames, buying, onBuy }: {
  frames: ShopFrame[];
  buying: string | null;
  onBuy: (type: "frame", key: string, label: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {frames.map((f) => (
        <ShopCard
          key={f.key}
          emoji={f.emoji}
          name={f.name}
          price={f.price}
          owned={f.owned}
          active={f.active}
          buying={buying === f.key}
          onBuy={() => onBuy("frame", f.key, f.name)}
          badge={f.active ? "Активна" : f.owned ? "Куплена" : undefined}
        />
      ))}
    </div>
  );
}

/* ── CosmeticList ─────────────────────────────────────────────── */

function CosmeticList({ cosmetics, buying, onBuy }: {
  cosmetics: ShopCosmetic[];
  buying: string | null;
  onBuy: (type: "cosmetic", key: string, label: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {cosmetics.map((c) => (
        <ShopCard
          key={c.key}
          emoji={c.emoji}
          name={c.name}
          price={c.price}
          owned={c.owned}
          buying={buying === c.key}
          onBuy={() => onBuy("cosmetic", c.key, c.name)}
          badge={c.owned ? "Куплено" : undefined}
          desc={c.desc}
        />
      ))}
    </div>
  );
}

/* ── PetColorList ─────────────────────────────────────────────── */

function PetColorList({ petColors, buying, onBuy }: {
  petColors: ShopPetColor[];
  buying: string | null;
  onBuy: (type: "pet_color", key: string, label: string) => void;
}) {
  if (petColors.length === 0) {
    return (
      <div className="rounded-xl p-6 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <p className="text-sm" style={{ color: "var(--text-hint)" }}>Нет питомца или цветов нет в наличии</p>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-2">
      {petColors.map((pc) => (
        <ShopCard
          key={pc.key}
          emoji="🎨"
          name={pc.label}
          price={pc.price}
          owned={pc.owned}
          active={pc.active}
          buying={buying === pc.key}
          onBuy={() => onBuy("pet_color", pc.key, pc.label)}
          badge={pc.active ? "Активен" : pc.owned ? "Куплен" : undefined}
        />
      ))}
    </div>
  );
}

/* ── FoodList ─────────────────────────────────────────────────── */

function FoodList({ food, buying, onBuy }: {
  food: ShopFood[];
  buying: string | null;
  onBuy: (type: "potion", key: string, label: string) => void;
}) {
  return (
    <div className="space-y-2">
      {food.map((f) => (
        <div
          key={f.key}
          className="rounded-xl p-3 flex items-center justify-between gap-3"
          style={{ backgroundColor: "var(--bg-secondary)" }}
        >
          <div className="flex items-center gap-2">
            <span className="text-2xl">{f.emoji}</span>
            <div>
              <p className="text-sm font-medium">{f.name}</p>
              <p className="text-[11px]" style={{ color: "#22c55e" }}>−{f.fatigue}% усталость</p>
            </div>
          </div>
          <button
            onClick={() => onBuy("potion", f.key, f.name)}
            disabled={!!buying}
            className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-40"
            style={{ backgroundColor: "var(--accent)", color: "#fff" }}
          >
            {buying === f.key ? "..." : `${fmt(f.price)} 🪙`}
          </button>
        </div>
      ))}
    </div>
  );
}

/* ── PotionList ───────────────────────────────────────────────── */

function PotionList({ potions, buying, onBuy }: {
  potions: ShopPotion[];
  buying: string | null;
  onBuy: (type: "potion", key: string, label: string) => void;
}) {
  return (
    <div className="space-y-2">
      {potions.map((p) => (
        <div
          key={p.key}
          className="rounded-xl p-3 flex items-center justify-between gap-3"
          style={{ backgroundColor: "var(--bg-secondary)" }}
        >
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="text-2xl">{p.emoji}</span>
            <div className="min-w-0">
              <p className="text-sm font-medium">{p.name}</p>
              <p className="text-[11px] truncate" style={{ color: "var(--text-hint)" }}>{p.desc}</p>
            </div>
          </div>
          <button
            onClick={() => onBuy("potion", p.key, p.name)}
            disabled={!!buying}
            className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-40"
            style={{ backgroundColor: "var(--accent)", color: "#fff" }}
          >
            {buying === p.key ? "..." : `${fmt(p.price)} 🪙`}
          </button>
        </div>
      ))}
    </div>
  );
}

/* ── ShopCard (общий компонент карточки) ──────────────────────── */

interface ShopCardProps {
  emoji: string;
  name: string;
  price: number;
  owned: boolean;
  active?: boolean;
  buying: boolean;
  onBuy: () => void;
  badge?: string;
  desc?: string;
}

function ShopCard({ emoji, name, price, owned, active, buying, onBuy, badge, desc }: ShopCardProps) {
  return (
    <div
      className="rounded-xl p-3 flex flex-col gap-2"
      style={{
        backgroundColor: "var(--bg-secondary)",
        border: active ? "1px solid var(--accent)" : "1px solid transparent",
      }}
    >
      <div className="flex items-start justify-between gap-1">
        <span className="text-2xl leading-none">{emoji}</span>
        {badge && (
          <span className="flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: active ? "var(--accent)" : "var(--bg-primary)",
              color: active ? "#fff" : "var(--text-hint)",
            }}>
            {active && <CheckCircle2 size={10} />}
            {badge}
          </span>
        )}
      </div>
      <div className="flex-1">
        <p className="text-sm font-medium leading-snug">{name}</p>
        {desc && (
          <p className="text-[11px] mt-0.5 line-clamp-2" style={{ color: "var(--text-hint)" }}>{desc}</p>
        )}
      </div>
      {/* Always show price tag */}
      <p className="text-[11px] font-semibold tabular-nums" style={{ color: "var(--text-hint)" }}>
        {price === 0 ? "Бесплатно" : `${fmt(price)} 🪙`}
      </p>
      {owned ? (
        <div className="flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs font-medium"
          style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-hint)" }}>
          <CheckCircle2 size={13} />
          {active ? "Активна" : "Куплено"}
        </div>
      ) : (
        <button
          onClick={onBuy}
          disabled={buying}
          className="py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-40"
          style={{ backgroundColor: "var(--accent)", color: "#fff" }}
        >
          {buying ? "..." : price === 0 ? "Применить" : `${fmt(price)} 🪙`}
        </button>
      )}
    </div>
  );
}

/* ── ThemeList ────────────────────────────────────────────────── */

/** Strip HTML tags from theme header string (e.g. "👑✨ <b>КОРОЛЕВСКИЙ</b>" → "👑✨ КОРОЛЕВСКИЙ") */
function stripHtml(s: string): string {
  return s.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
}

const TIER_LABEL: Record<string, string> = {
  common: "Обычная",
  rare: "Редкая",
  epic: "Эпическая",
  legendary: "Легендарная",
};

const SOURCE_LABEL: Record<string, string> = {
  shop:    "🛒 Магазин",
  gacha:   "🎰 Только гача",
  default: "По умолчанию",
};

const TIER_COLOR: Record<string, string> = {
  common:    "#9ca3af",
  rare:      "#60a5fa",
  epic:      "#c084fc",
  legendary: "#f59e0b",
};

function ThemeList({
  themes, activating, onActivate,
}: {
  themes: ThemesResponse | null;
  activating: string | null;
  onActivate: (theme: ProfileTheme) => void;
}) {
  if (!themes) {
    return (
      <div className="space-y-2 animate-pulse">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="skeleton h-20 rounded-xl" />
        ))}
      </div>
    );
  }

  if (themes.themes.length === 0) {
    return (
      <div className="rounded-xl p-6 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <Palette size={28} strokeWidth={1.2} className="mx-auto mb-2" style={{ color: "var(--text-hint)" }} />
        <p className="text-sm" style={{ color: "var(--text-hint)" }}>Темы не найдены</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {(themes.crystals ?? 0) > 0 && (
        <div
          className="rounded-xl p-3 flex items-center justify-between"
          style={{ backgroundColor: "var(--bg-secondary)" }}
        >
          <span className="text-sm" style={{ color: "var(--text-hint)" }}>Кристаллы</span>
          <span className="text-base font-bold">{themes.crystals} 💎</span>
        </div>
      )}
      {themes.themes.map((t) => {
        const isGachaOnly = t.source === "gacha" && !t.owned;
        const tierColor = TIER_COLOR[t.tier] ?? "var(--text-hint)";
        return (
          <div
            key={t.key}
            className="rounded-xl p-3 flex items-center gap-3"
            style={{
              backgroundColor: "var(--bg-secondary)",
              border: t.active ? `1px solid ${tierColor}` : "1px solid transparent",
            }}
          >
            {/* Emoji preview — strip HTML from header */}
            <div
              className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0"
              style={{ backgroundColor: `${tierColor}22`, border: `1px solid ${tierColor}44` }}
            >
              {stripHtml(t.header ?? "").match(/(\p{Emoji})/u)?.[0] ?? "🎨"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate">{t.name}</p>
              <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                <span className="text-[10px] font-bold px-1 py-0.5 rounded" style={{ backgroundColor: `${tierColor}22`, color: tierColor }}>
                  {TIER_LABEL[t.tier] ?? t.tier}
                </span>
                <span className="text-[10px]" style={{ color: "var(--text-hint)" }}>
                  {SOURCE_LABEL[t.source] ?? t.source}
                </span>
                {/* Always show price */}
                {t.price > 0 && (
                  <span className="text-[10px] font-semibold" style={{ color: "#a78bfa" }}>
                    {t.price} 🪙
                  </span>
                )}
              </div>
            </div>
            {t.active ? (
              <div
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold shrink-0"
                style={{ backgroundColor: tierColor, color: "#000" }}
              >
                <CheckCircle2 size={11} /> Активна
              </div>
            ) : t.owned ? (
              <button
                onClick={() => onActivate(t)}
                disabled={!!activating}
                className="px-2.5 py-1 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-50 flex items-center gap-1 shrink-0"
                style={{ border: `1px solid ${tierColor}`, color: tierColor }}
              >
                {activating === t.key ? <Loader2 size={11} className="animate-spin" /> : "Применить"}
              </button>
            ) : isGachaOnly ? (
              // Gacha-only — not purchasable in shop
              <div
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold shrink-0"
                style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-hint)" }}
              >
                <Lock size={11} /> Гача
              </div>
            ) : (
              <button
                onClick={() => onActivate(t)}
                disabled={!!activating}
                className="px-2.5 py-1 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-50 flex items-center gap-1 shrink-0"
                style={{ backgroundColor: tierColor, color: "#000" }}
              >
                {activating === t.key
                  ? <Loader2 size={11} className="animate-spin" />
                  : `${t.price} 🪙`}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── DonateTab ────────────────────────────────────────────────── */

interface CrystalItem {
  key: string;
  emoji: string;
  name: string;
  price: number;
  desc: string;
  oneTime?: boolean;
}

const CRYSTAL_CATALOG: CrystalItem[] = [
  { key: "telegram_avatar",      emoji: "🖼️", name: "Telegram Аватар",     price: 150, desc: "Показывает фото из Telegram в профиле", oneTime: true },
  { key: "enhancement_stones_5", emoji: "⚒️", name: "5 камней заточки",     price: 150, desc: "5 гарантированных заточек без Моры" },
  { key: "enhancement_stones_1", emoji: "🔩", name: "1 камень заточки",      price: 50,  desc: "1 гарантированная заточка без Моры" },
];

function DonateTab({ chatId, balance, onRefresh, showOk, showErr }: {
  chatId: number;
  balance: number | null;
  onRefresh: () => void;
  showOk: (m: string) => void;
  showErr: (m: string) => void;
}) {
  const [buying, setBuying] = useState<string | null>(null);

  const handleBuy = useCallback(async (item: CrystalItem) => {
    if (buying) return;
    setBuying(item.key);
    try {
      const res = await buyCrystalItem(chatId, item.key, item.price);
      if (!res.ok) { showErr(res.error ?? "Ошибка покупки"); return; }

      // For telegram_avatar: also save the avatar URL
      if (item.key === "telegram_avatar") {
        const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user as { photo_url?: string } | undefined;
        const photoUrl = tgUser?.photo_url;
        if (photoUrl) {
          const sv = await saveAvatar(photoUrl);
          if (!sv.ok) showErr("Аватар куплен, но фото не сохранилось: " + (sv.error ?? ""));
        }
      }

      showOk(`${item.emoji} ${item.name} куплено!`);
      onRefresh();
    } catch (e: unknown) {
      showErr(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBuying(null);
    }
  }, [buying, chatId, showOk, showErr, onRefresh]);

  return (
    <div className="space-y-3">
      {/* Balance */}
      <div
        className="rounded-xl p-3 flex items-center justify-between"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        <div className="flex items-center gap-2">
          <Gem size={16} style={{ color: "#a78bfa" }} />
          <span className="text-sm font-medium">Кристаллы</span>
        </div>
        <span className="font-bold tabular-nums">
          {balance === null ? "..." : `${fmt(balance)} 💎`}
        </span>
      </div>

      {/* Catalog */}
      <div className="space-y-2">
        {CRYSTAL_CATALOG.map((item) => (
          <div
            key={item.key}
            className="rounded-xl p-3 flex items-center gap-3"
            style={{ backgroundColor: "var(--bg-secondary)" }}
          >
            <span className="text-2xl shrink-0">{item.emoji}</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">{item.name}</p>
              <p className="text-[11px] mt-0.5" style={{ color: "var(--text-hint)" }}>{item.desc}</p>
              {item.oneTime && (
                <span className="text-[10px] font-bold px-1 rounded" style={{ backgroundColor: "#a78bfa22", color: "#a78bfa" }}>
                  Разовая покупка
                </span>
              )}
            </div>
            <button
              onClick={() => handleBuy(item)}
              disabled={!!buying}
              className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-40 flex items-center gap-1"
              style={{ backgroundColor: "#7c3aed", color: "#fff" }}
            >
              {buying === item.key
                ? <Loader2 size={12} className="animate-spin" />
                : <>{item.price} 💎</>}
            </button>
          </div>
        ))}
      </div>

      <p className="text-[11px] text-center" style={{ color: "var(--text-hint)" }}>
        Пополнить кристаллы можно через раздел «⭐ Stars»
      </p>
    </div>
  );
}
