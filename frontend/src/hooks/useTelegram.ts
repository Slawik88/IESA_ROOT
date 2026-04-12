/* ──────────────────────────────────────────────────────────────
   Хук useTelegram — инициализация Telegram WebApp SDK
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState } from "react";
import { setInitData } from "../lib/api";

interface TgUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
}

interface UseTelegramResult {
  ready: boolean;
  /** true если запущено внутри Telegram WebApp */
  isInsideTelegram: boolean;
  userId: number;
  chatId: number;
  user: TgUser | null;
  initData: string;
  colorScheme: "light" | "dark";
}

/**
 * Инициализирует Telegram WebApp и возвращает данные пользователя.
 * Автоматически записывает initData в API-клиент (X-Telegram-Init-Data).
 * chatId берётся из start_param (формат: "chat_<id>") или 0.
 */
export function useTelegram(): UseTelegramResult {
  const [state, setState] = useState<UseTelegramResult>({
    ready: false,
    isInsideTelegram: false,
    userId: 0,
    chatId: 0,
    user: null,
    initData: "",
    colorScheme: "dark",
  });

  useEffect(() => {
    const tg = window.Telegram?.WebApp;

    if (!tg || !tg.initData) {
      // Открыто вне Telegram — помечаем как не-Telegram среду
      setState((s) => ({ ...s, ready: true, isInsideTelegram: false }));
      return;
    }

    tg.ready();
    tg.expand();

    const initData = tg.initData;
    // Записываем в глобальный API-клиент — все запросы получат заголовок автоматически
    setInitData(initData);

    const user = tg.initDataUnsafe?.user as TgUser | undefined;
    const startParam = tg.initDataUnsafe?.start_param ?? "";
    const chatId = startParam.startsWith("chat_")
      ? parseInt(startParam.slice(5), 10) || 0
      : 0;

    setState({
      ready: true,
      isInsideTelegram: true,
      userId: user?.id ?? 0,
      chatId,
      user: user ?? null,
      initData,
      colorScheme: tg.colorScheme ?? "dark",
    });
  }, []);

  return state;
}
