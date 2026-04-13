/* ──────────────────────────────────────────────────────────────
   AppContext — глобальный стейт пользователя
   Кешируем UserData чтобы Profile не мигал при каждом переходе,
   а после покупок/транзакций можно вызвать refreshUserData().
   ────────────────────────────────────────────────────────────── */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { fetchUserData } from "./lib/api";
import type { UserData } from "./types";

interface AppContextValue {
  userData: UserData | null;
  userDataLoading: boolean;
  isDev: boolean;
  refreshUserData: () => Promise<void>;
}

const AppContext = createContext<AppContextValue>({
  userData: null,
  userDataLoading: true,
  isDev: false,
  refreshUserData: async () => {},
});

export function AppProvider({ children, chatId }: { children: ReactNode; chatId: number }) {
  const [userData, setUserData] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUserData = useCallback(async () => {
    if (!chatId) return;
    try {
      const d = await fetchUserData(chatId);
      setUserData(d);
      // Применяем тему на <html> синхронно
      const theme = d.active_theme ?? "default";
      if (theme && theme !== "default") {
        document.documentElement.setAttribute("data-theme", theme);
      } else {
        document.documentElement.removeAttribute("data-theme");
      }
    } catch {
      // игнорируем — не критично
    } finally {
      setLoading(false);
    }
  }, [chatId]);

  useEffect(() => {
    refreshUserData();
  }, [refreshUserData]);

  return (
    <AppContext.Provider
      value={{
        userData,
        userDataLoading: loading,
        isDev: !!userData?.is_dev,
        refreshUserData,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext(): AppContextValue {
  return useContext(AppContext);
}
