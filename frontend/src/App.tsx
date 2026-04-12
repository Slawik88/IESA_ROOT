/* ──────────────────────────────────────────────────────────────
   App.tsx — корневой компонент Mini App
   Навигация: Профиль | Гача | Инвентарь | Банк | Магазин | Задания | Топ | Сезон | Ачивки | Биржа | [Адм.]
   ────────────────────────────────────────────────────────────── */
import { useState, useEffect } from "react";
import { User, Sparkles, Backpack, ScrollText, Trophy, Medal, Star, Landmark, ShoppingBag, TrendingUp, ShieldAlert } from "lucide-react";
import { useTelegram } from "./hooks/useTelegram";
import { fetchUserData } from "./lib/api";
import Profile from "./pages/Profile";
import Gacha from "./pages/Gacha";
import Inventory from "./pages/Inventory";
import Achievements from "./pages/Achievements";
import Quests from "./pages/Quests";
import Leaderboard from "./pages/Leaderboard";
import Season from "./pages/Season";
import Bank from "./pages/Bank";
import Shop from "./pages/Shop";
import Exchange from "./pages/Exchange";
import Admin from "./pages/Admin";
import NotInTelegram from "./pages/NotInTelegram";

type Tab = "profile" | "gacha" | "inventory" | "bank" | "shop" | "quests" | "leaderboard" | "season" | "achievements" | "exchange" | "admin";

const BASE_TABS: { key: Tab; label: string; Icon: typeof User }[] = [
  { key: "profile",      label: "Профиль",  Icon: User },
  { key: "gacha",        label: "Гача",     Icon: Sparkles },
  { key: "inventory",    label: "Сумка",    Icon: Backpack },
  { key: "bank",         label: "Банк",     Icon: Landmark },
  { key: "shop",         label: "Магазин",  Icon: ShoppingBag },
  { key: "exchange",     label: "Биржа",    Icon: TrendingUp },
  { key: "quests",       label: "Задания",  Icon: ScrollText },
  { key: "leaderboard",  label: "Топ",      Icon: Trophy },
  { key: "season",       label: "Сезон",    Icon: Star },
  { key: "achievements", label: "Ачивки",   Icon: Medal },
];

export default function App() {
  const { ready, isInsideTelegram, userId, chatId } = useTelegram();
  const [tab, setTab] = useState<Tab>("profile");
  const [isDev, setIsDev] = useState(false);

  useEffect(() => {
    if (!chatId) return;
    fetchUserData(chatId)
      .then((d) => {
        setIsDev(!!d.is_dev);
        // Динамическая тема: применяем active_theme к <html>
        const theme = d.active_theme ?? "default";
        if (theme && theme !== "default") {
          document.documentElement.setAttribute("data-theme", theme);
        } else {
          document.documentElement.removeAttribute("data-theme");
        }
      })
      .catch(() => { /* ignore */ });
  }, [chatId]);

  if (!ready) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="skeleton w-20 h-20 rounded-full" />
      </div>
    );
  }

  if (!isInsideTelegram) {
    return <NotInTelegram />;
  }

  const TABS = isDev
    ? [...BASE_TABS, { key: "admin" as Tab, label: "Адм.", Icon: ShieldAlert }]
    : BASE_TABS;

  return (
    <div className="flex flex-col min-h-screen pb-16">
      {/* ── Контент ──────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        {tab === "profile"      && <Profile      userId={userId} chatId={chatId} />}
        {tab === "gacha"        && <Gacha        userId={userId} chatId={chatId} />}
        {tab === "inventory"    && <Inventory    userId={userId} chatId={chatId} />}
        {tab === "bank"         && <Bank         userId={userId} chatId={chatId} />}
        {tab === "shop"         && <Shop         userId={userId} chatId={chatId} />}
        {tab === "exchange"     && <Exchange     userId={userId} chatId={chatId} isDev={isDev} />}
        {tab === "quests"       && <Quests       userId={userId} chatId={chatId} />}
        {tab === "leaderboard"  && <Leaderboard  chatId={chatId} />}
        {tab === "season"       && <Season />}
        {tab === "achievements" && <Achievements userId={userId} chatId={chatId} />}
        {tab === "admin"        && <Admin        userId={userId} chatId={chatId} isDev={isDev} />}
      </main>

      {/* ── Нижняя навигация (скролл при 9+ табах) ───── */}
      <nav
        className="fixed bottom-0 inset-x-0 flex overflow-x-auto border-t"
        style={{
          backgroundColor: "var(--bg-primary)",
          borderColor: "var(--border)",
          scrollbarWidth: "none",
        }}
      >
        {TABS.map(({ key, label, Icon }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className="flex-none flex flex-col items-center gap-0.5 py-2 px-3 min-w-[52px] transition-colors"
              style={{ color: active ? "var(--accent)" : "var(--text-hint)" }}
            >
              <Icon size={19} strokeWidth={active ? 2.5 : 1.8} />
              <span className="text-[10px] font-medium whitespace-nowrap">{label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
