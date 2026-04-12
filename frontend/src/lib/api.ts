/* ──────────────────────────────────────────────────────────────
   API-клиент — простая обёртка над fetch (без axios)
   Все запросы идут на тот же хост (относительные пути)
   ────────────────────────────────────────────────────────────── */

import type {
  UserData,
  AchievementsResponse,
  BadgesResponse,
  SeasonDataResponse,
} from "../types";

const BASE = "";  // пустой = относительные пути (единый хост)

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

/** Профиль пользователя */
export function fetchUserData(userId: number): Promise<UserData> {
  return request<UserData>(`/api/user_data?user_id=${userId}`);
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
