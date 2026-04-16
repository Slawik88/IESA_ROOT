/* ──────────────────────────────────────────────────────────────
   App.tsx — корневой компонент Mini App
   Навигация: Профиль | Гача | Инвентарь | Банк | Магазин | Задания | Топ | Сезон | Ачивки | Биржа | [Адм.]
   ────────────────────────────────────────────────────────────── */
import { useState, useEffect, Component, type ReactNode, type ErrorInfo } from "react";
import { User, Sparkles, Backpack, ScrollText, Trophy, Medal, Star, Landmark, ShoppingBag, TrendingUp, ShieldAlert, Dices, Gem, Swords, Ticket, Gavel, Banknote, Zap, Settings } from "lucide-react";

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) {
    fetch("/api/frontend_error_log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ error: error.message, stack: info.componentStack?.slice(0, 2000) }),
    }).catch(() => {});
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-6 text-center" style={{ color: "var(--text-primary)" }}>
          <p className="text-lg font-semibold mb-2">Что-то пошло не так 😓</p>
          <p className="text-sm mb-4" style={{ color: "var(--text-hint)" }}>{this.state.error.message}</p>
          <button
            onClick={() => this.setState({ error: null })}
            className="px-4 py-2 rounded-xl text-sm font-semibold"
            style={{ backgroundColor: "var(--accent)", color: "#fff" }}
          >
            Попробовать снова
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
import { useTelegram } from "./hooks/useTelegram";
import { useTelemetry } from "./hooks/useTelemetry";
import { AppProvider, useAppContext } from "./AppContext";
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
import Casino from "./pages/Casino";
import Stars from "./pages/Stars";
import Admin from "./pages/Admin";
import Promo from "./pages/Promo";
import BossFight from "./pages/BossFight";
import Auction from "./pages/Auction";
import Loans from "./pages/Loans";
import NotInTelegram from "./pages/NotInTelegram";
import Talents from "./pages/Talents";
import Shards from "./pages/Shards";
import AppSettings from "./pages/Settings";
import { triggerNewbieQuest } from "./lib/api";

type Tab = "profile" | "gacha" | "inventory" | "bank" | "shop" | "quests" | "leaderboard" | "season" | "achievements" | "exchange" | "casino" | "stars" | "promo" | "boss" | "auction" | "loans" | "talents" | "shards" | "settings" | "admin";

const BASE_TABS: { key: Tab; label: string; Icon: typeof User }[] = [
  { key: "profile",      label: "Профиль",  Icon: User },
  { key: "gacha",        label: "Гача",     Icon: Sparkles },
  { key: "inventory",    label: "Сумка",    Icon: Backpack },
  { key: "bank",         label: "Банк",     Icon: Landmark },
  { key: "shop",         label: "Магазин",  Icon: ShoppingBag },
  { key: "exchange",     label: "Биржа",    Icon: TrendingUp },
  { key: "casino",       label: "Казино",   Icon: Dices },
  { key: "auction",      label: "Аукцион",  Icon: Gavel },
  { key: "loans",        label: "Займы",    Icon: Banknote },  { key: "talents",      label: "Таланты",  Icon: Zap },
  { key: "shards",       label: "Осколки",  Icon: Gem },
  { key: "settings",     label: "Настройки",Icon: Settings },  { key: "stars",        label: "Stars",    Icon: Gem },
  { key: "promo",        label: "Промо",    Icon: Ticket },
  { key: "boss",         label: "Босс",     Icon: Swords },
  { key: "quests",       label: "Задания",  Icon: ScrollText },
  { key: "leaderboard",  label: "Топ",      Icon: Trophy },
  { key: "season",       label: "Сезон",    Icon: Star },
  { key: "achievements", label: "Ачивки",   Icon: Medal },
];

export default function App() {
  const { ready, isInsideTelegram, userId, chatId } = useTelegram();

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
    <AppProvider chatId={chatId}>
      <AppContent userId={userId} chatId={chatId} />
    </AppProvider>
  );
}

function AppContent({ userId, chatId }: { userId: number; chatId: number }) {
  const { isDev, userDataError, userDataLoading, refreshUserData } = useAppContext();
  const [tab, setTab] = useState<Tab>("profile");
  useTelemetry(tab, userId);

  // HIGH-013: trigger newbie quest initialisation on first load
  useEffect(() => {
    if (userId && chatId) triggerNewbieQuest(chatId).catch(() => {});
  }, [userId, chatId]);

  // Show error screen if initial data load failed and no data yet
  if (userDataError && !userDataLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4 p-6 text-center">
        <p className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
          Не удалось загрузить данные 😓
        </p>
        <p className="text-sm" style={{ color: "var(--text-hint)" }}>{userDataError}</p>
        <button
          onClick={() => { void refreshUserData(); }}
          className="px-5 py-2.5 rounded-xl text-sm font-semibold"
          style={{ backgroundColor: "var(--accent)", color: "#fff" }}
        >
          Попробовать снова
        </button>
      </div>
    );
  }

  const TABS = isDev
    ? [...BASE_TABS, { key: "admin" as Tab, label: "Адм.", Icon: ShieldAlert }]
    : BASE_TABS;

  return (
    <div className="flex flex-col min-h-screen pb-16">
      {/* ── Контент ──────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        <ErrorBoundary>
          {tab === "profile"      && <Profile      userId={userId} chatId={chatId} />}
          {tab === "gacha"        && <Gacha        userId={userId} chatId={chatId} />}
          {tab === "inventory"    && <Inventory    userId={userId} chatId={chatId} />}
          {tab === "bank"         && <Bank         userId={userId} chatId={chatId} />}
          {tab === "shop"         && <Shop         userId={userId} chatId={chatId} />}
          {tab === "exchange"     && <Exchange     userId={userId} chatId={chatId} isDev={isDev} />}
          {tab === "casino"       && <Casino        userId={userId} chatId={chatId} />}
          {tab === "auction"      && <Auction       userId={userId} chatId={chatId} />}
          {tab === "loans"        && <Loans         userId={userId} chatId={chatId} />}
          {tab === "talents"      && <Talents       userId={userId} chatId={chatId} />}
          {tab === "shards"       && <Shards        userId={userId} chatId={chatId} />}
          {tab === "settings"     && <AppSettings   userId={userId} chatId={chatId} isDev={isDev} />}
          {tab === "stars"        && <Stars         userId={userId} chatId={chatId} />}
          {tab === "quests"       && <Quests       userId={userId} chatId={chatId} />}
          {tab === "leaderboard"  && <Leaderboard  chatId={chatId} />}
          {tab === "season"       && <Season />}
          {tab === "achievements" && <Achievements userId={userId} chatId={chatId} />}
          {tab === "promo"        && <Promo        userId={userId} chatId={chatId} />}
          {tab === "boss"         && <BossFight    userId={userId} chatId={chatId} />}
          {tab === "admin"        && <Admin        userId={userId} chatId={chatId} isDev={isDev} />}
        </ErrorBoundary>
      </main>

      {/* ── Нижняя навигация ───── */}
      <nav
        className="fixed bottom-0 inset-x-0 flex overflow-x-auto glass-heavy tab-scroll"
        style={{
          borderTop: "1px solid var(--border-accent)",
          paddingBottom: "env(safe-area-inset-bottom, 0px)",
          backgroundColor: "var(--bg-primary)",
        }}
      >
        {TABS.map(({ key, label, Icon }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className="flex-none flex flex-col items-center gap-0.5 py-2 px-3 min-w-[52px] transition-all relative"
              style={{ color: active ? "var(--accent)" : "var(--text-hint)" }}
            >
              {active && (
                <span className="absolute top-0 left-1/2 -translate-x-1/2 w-6 h-0.5 rounded-full" style={{ backgroundColor: "var(--accent)" }} />
              )}
              <Icon size={19} strokeWidth={active ? 2.5 : 1.8} />
              <span className="text-[10px] font-medium whitespace-nowrap">{label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
