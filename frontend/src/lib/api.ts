/* ──────────────────────────────────────────────────────────────
   API-клиент — fetch-обёртка с авторизацией через initData.
   Бэкенд ożидает заголовок: X-Telegram-Init-Data: <initData>
   ────────────────────────────────────────────────────────────── */

import type {
  UserData,
  AchievementsResponse,
  BadgesResponse,
  SeasonDataResponse,
} from "../types";

// Глобальное хранилище initData — заполняется в useTelegram при старте.
// Все запросы автоматически получают этот заголовок.
let _initData = "";

/** Вызывается из useTelegram сразу после tg.ready(). */
export function setInitData(initData: string): void {
  _initData = initData;
}

/** Возвращает текущий initData (для отладки). */
export function getInitData(): string {
  return _initData;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };

  // Добавляем initData в каждый запрос — бэкенд требует X-Telegram-Init-Data
  if (_initData) {
    headers["X-Telegram-Init-Data"] = _initData;
  }

  const res = await fetch(path, { ...options, headers });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

/** Профиль пользователя.
 *  uid берётся из initData на сервере — здесь нужен только chat_id для скопирования данных по чату.
 */
export function fetchUserData(chatId: number): Promise<UserData> {
  const qs = chatId ? `?chat_id=${chatId}` : "";
  return request<UserData>(`/api/user_data${qs}`);
}

/** Достижения пользователя */
export function fetchAchievements(
  userId: number,
  chatId: number,
): Promise<AchievementsResponse> {
  return request<AchievementsResponse>(
    `/api/achievements?user_id=${userId}&chat_id=${chatId}`,
  );
}

/** Бейджи пользователя */
export function fetchBadges(
  userId: number,
  chatId: number,
): Promise<BadgesResponse> {
  return request<BadgesResponse>(
    `/api/achievements/badges?user_id=${userId}&chat_id=${chatId}`,
  );
}

/** Данные Season Pass */
export function fetchSeasonData(userId: number): Promise<SeasonDataResponse> {
  return request<SeasonDataResponse>(`/api/season/data?user_id=${userId}`);
}
