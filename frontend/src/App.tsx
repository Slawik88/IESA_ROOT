/* ──────────────────────────────────────────────────────────────
   App.tsx — корневой компонент Mini App
   Навигация: Профиль | Инвентарь | Ачивки
   ────────────────────────────────────────────────────────────── */
import { useState } from "react";
import { User, Backpack, Trophy } from "lucide-react";
import { useTelegram } from "./hooks/useTelegram";
import Profile from "./pages/Profile";
import Inventory from "./pages/Inventory";
import Achievements from "./pages/Achievements";

type Tab = "profile" | "inventory" | "achievements";

const TABS: { key: Tab; label: string; Icon: typeof User }[] = [
  { key: "profile",      label: "Профиль",  Icon: User },
  { key: "inventory",    label: "Инвентарь", Icon: Backpack },
  { key: "achievements", label: "Ачивки",    Icon: Trophy },
];

export default function App() {
  const { ready, userId, chatId } = useTelegram();
  const [tab, setTab] = useState<Tab>("profile");

  if (!ready) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="skeleton w-20 h-20 rounded-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen pb-16">
      {/* ── Контент ──────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        {tab === "profile"      && <Profile userId={userId} />}
        {tab === "inventory"    && <Inventory userId={userId} />}
        {tab === "achievements" && <Achievements userId={userId} chatId={chatId} />}
      </main>

      {/* ── Нижняя навигация ─────────────────────── */}
      <nav
        className="fixed bottom-0 inset-x-0 flex border-t"
        style={{
          backgroundColor: "var(--bg-primary)",
          borderColor: "var(--border)",
        }}
      >
        {TABS.map(({ key, label, Icon }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className="flex-1 flex flex-col items-center gap-0.5 py-2 transition-colors"
              style={{ color: active ? "var(--accent)" : "var(--text-hint)" }}
            >
              <Icon size={20} strokeWidth={active ? 2.5 : 1.8} />
              <span className="text-[11px] font-medium">{label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
