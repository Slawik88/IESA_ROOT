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
  /** BUG-054: human-readable error when chatId could not be determined */
  error: string | null;
}

/**
 * Инициализирует Telegram WebApp и возвращает данные пользователя.
 * Автоматически записывает initData в API-клиент (X-Telegram-Init-Data).
 *
 * chatId извлекается по приоритету:
 *  1. initDataUnsafe.chat.id  (group inline keyboard context)
 *  2. start_param — бот шлёт abs(chat.id) + "_section" суффикс
 *     Пример: "1003841515877_profile" → chatId = -1003841515877
 *  3. Разбор raw initData строки (резервный)
 */

/** Извлечь и нормализовать chat_id из startapp-параметра.
 *  Бот формирует: abs(chat.id)_section  → нам нужно вернуть chat.id (отрицательный).
 *  На выходе всегда отрицательное число (группы в Bot API всегда < 0) или 0 если нет данных.
 */
function parseStartParam(startParam: string): number {
  if (!startParam) return 0;
  // Берём часть до первого '_' (отбрасываем суффикс "_profile", "_gacha" и т.д.)
  const numStr = startParam.split("_")[0];
  const n = parseInt(numStr, 10);
  if (!n || isNaN(n)) return 0;
  // Бот отправляет abs(chat.id) — восстанавливаем знак
  return n > 0 ? -n : n;
}

export function useTelegram(): UseTelegramResult {
  const [state, setState] = useState<UseTelegramResult>({
    ready: false,
    isInsideTelegram: false,
    userId: 0,
    chatId: 0,
    user: null,
    initData: "",
    colorScheme: "dark",
    error: null,
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
    const unsafe = tg.initDataUnsafe as Record<string, unknown> | undefined;

    let chatId = 0;

    // Priority 1: initDataUnsafe.chat.id (menu button / inline keyboard в группе)
    const chatObj = unsafe?.chat as { id?: number } | undefined;
    if (chatObj?.id) {
      chatId = chatObj.id; // Bot API уже отрицательный для групп
    }

    // Priority 2: start_param — бот шлёт abs(chat.id)_section
    // Примеры: "1003841515877_profile", "1003841515877_gacha", "1003841515877"
    if (!chatId) {
      const startParam = (unsafe?.start_param as string) ?? "";
      if (startParam.startsWith("chat_")) {
        // Старый формат deep-link: "chat_-1003841515877"
        chatId = parseInt(startParam.slice(5), 10) || 0;
      } else if (startParam) {
        chatId = parseStartParam(startParam);
      }
    }

    // Priority 3: разбор raw initData строки (резервный)
    if (!chatId && tg.initData) {
      try {
        const params = new URLSearchParams(tg.initData);
        // Поле "chat" в подписанной строке
        const chatRaw = params.get("chat");
        if (chatRaw) {
          const parsed = JSON.parse(chatRaw) as { id?: number };
          chatId = parsed.id ?? 0;
        }
        // start_param из подписанной строки
        if (!chatId) {
          chatId = parseStartParam(params.get("start_param") ?? "");
        }
      } catch { /* ignore */ }
    }

    setState({
      ready: true,
      isInsideTelegram: true,
      userId: user?.id ?? 0,
      chatId,
      user: user ?? null,
      initData,
      colorScheme: tg.colorScheme ?? "dark",
      error: chatId === 0 ? "Не удалось определить чат. Откройте приложение из группы." : null,
    });
  }, []);

  return state;
}
