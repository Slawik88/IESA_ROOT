/* ──────────────────────────────────────────────────────────────
   Хук useTelegram — инициализация Telegram WebApp SDK
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState } from "react";

interface TgUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
}

interface UseTelegramResult {
  ready: boolean;
  userId: number;
  chatId: number;
  user: TgUser | null;
  initData: string;
  colorScheme: "light" | "dark";
}

/**
 * Инициализирует Telegram WebApp и возвращает данные пользователя.
 * chatId берётся из start_param (формат: "chat_<id>") или 0.
 */
export function useTelegram(): UseTelegramResult {
  const [state, setState] = useState<UseTelegramResult>({
    ready: false,
    userId: 0,
    chatId: 0,
    user: null,
    initData: "",
    colorScheme: "dark",
  });

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg) {
      // Фоллбэк для разработки вне Telegram
      setState((s) => ({ ...s, ready: true, userId: 1, chatId: 1 }));
      return;
    }
    tg.ready();
    tg.expand();

    const user = tg.initDataUnsafe?.user as TgUser | undefined;
    const startParam = tg.initDataUnsafe?.start_param ?? "";
    const chatId = startParam.startsWith("chat_")
      ? parseInt(startParam.slice(5), 10) || 0
      : 0;

    setState({
      ready: true,
      userId: user?.id ?? 0,
      chatId,
      user: user ?? null,
      initData: tg.initData ?? "",
      colorScheme: tg.colorScheme ?? "dark",
    });
  }, []);

  return state;
}
