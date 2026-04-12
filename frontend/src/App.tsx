/* ──────────────────────────────────────────────────────────────
   App.tsx — корневой компонент Mini App
   Навигация: Профиль | Гача | Инвентарь | Задания | Топ | Сезон | Ачивки
   ────────────────────────────────────────────────────────────── */
import { useState } from "react";
import { User, Sparkles, Backpack, ScrollText, Trophy, Medal, Star } from "lucide-react";
import { useTelegram } from "./hooks/useTelegram";
import Profile from "./pages/Profile";
import Gacha from "./pages/Gacha";
import Inventory from "./pages/Inventory";
import Achievements from "./pages/Achievements";
import Quests from "./pages/Quests";
import Leaderboard from "./pages/Leaderboard";
import Season from "./pages/Season";
import NotInTelegram from "./pages/NotInTelegram";

type Tab = "profile" | "gacha" | "inventory" | "quests" | "leaderboard" | "season" | "achievements";

const TABS: { key: Tab; label: string; Icon: typeof User }[] = [
  { key: "profile",      label: "Профиль",  Icon: User },
  { key: "gacha",        label: "Гача",     Icon: Sparkles },
  { key: "inventory",    label: "Сумка",    Icon: Backpack },
  { key: "quests",       label: "Задания",  Icon: ScrollText },
  { key: "leaderboard",  label: "Топ",      Icon: Trophy },
  { key: "season",       label: "Сезон",    Icon: Star },
  { key: "achievements", label: "Ачивки",   Icon: Medal },
];

export default function App() {
  const { ready, isInsideTelegram, userId, chatId } = useTelegram();
  const [tab, setTab] = useState<Tab>("profile");

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

  return (
    <div className="flex flex-col min-h-screen pb-16">
      {/* ── Контент ──────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        {tab === "profile"      && <Profile      userId={userId} chatId={chatId} />}
        {tab === "gacha"        && <Gacha        userId={userId} chatId={chatId} />}
        {tab === "inventory"    && <Inventory    userId={userId} chatId={chatId} />}
        {tab === "quests"       && <Quests       userId={userId} chatId={chatId} />}
        {tab === "leaderboard"  && <Leaderboard  userId={userId} />}
        {tab === "season"       && <Season       userId={userId} />}
        {tab === "achievements" && <Achievements userId={userId} chatId={chatId} />}
      </main>

      {/* ── Нижняя навигация (скролл при 7 табах) ───── */}
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
