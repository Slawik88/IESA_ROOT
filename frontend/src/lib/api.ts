/* ──────────────────────────────────────────────────────────────
   API-клиент — fetch-обёртка с авторизацией через initData.
   Бэкенд ożидает заголовок: X-Telegram-Init-Data: <initData>
   ────────────────────────────────────────────────────────────── */

import type {
  UserData,
  AchievementsResponse,
  BadgesResponse,
  SeasonDataResponse,
  CheckinStatus,
  CheckinResult,
  QuestData,
  QuestRerollResult,
  LeaderboardResponse,
  InventoryResponse,
  GachaRollResult,
  BankInfoResponse,
  BankDepositResult,
  BankWithdrawResult,
  ShopCatalog,
  ShopBuyResult,
  TransferResult,
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

/** Данные Season Pass (uid берётся бэкендом из initData-заголовка) */
export function fetchSeasonData(): Promise<SeasonDataResponse> {
  return request<SeasonDataResponse>("/api/season/data");
}

/** Статус чекина (GET) */
export function fetchCheckinStatus(chatId: number): Promise<CheckinStatus> {
  const qs = chatId ? `?chat_id=${chatId}` : "";
  return request<CheckinStatus>(`/api/checkin${qs}`);
}

/** Выполнить чекин (POST) */
export function doCheckin(chatId: number): Promise<CheckinResult> {
  return request<CheckinResult>("/api/checkin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

/** Текущее задание */
export function fetchQuest(chatId: number): Promise<QuestData> {
  const qs = chatId ? `?chat_id=${chatId}` : "";
  return request<QuestData>(`/api/quest${qs}`);
}

/** Перебросить задание */
export function rerollQuest(chatId: number, useCoupon = false): Promise<QuestRerollResult> {
  return request<QuestRerollResult>("/api/quest/reroll", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, use_coupon: useCoupon }),
  });
}

/** Лидерборд */
export function fetchLeaderboard(
  chatId: number,
  type: "xp" | "messages" | "boss" | "mora" = "xp",
): Promise<LeaderboardResponse> {
  return request<LeaderboardResponse>(`/api/leaderboard?chat_id=${chatId}&type=${type}`);
}

/** Забрать награду Season Pass */
export function claimSeasonReward(
  seasonId: number,
  level: number,
  isPremium: boolean,
): Promise<{ ok: boolean; error?: string }> {
  return request("/api/season/claim", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ season_id: seasonId, level, is_premium: isPremium }),
  });
}

/** Купить премиум Season Pass */
export function buySeasonPremium(seasonId: number): Promise<{ ok: boolean; error?: string }> {
  return request("/api/season/premium", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ season_id: seasonId }),
  });
}

// ── Gacha ─────────────────────────────────────────────────────

/** Крутка гачи */
export function rollGacha(
  chatId: number,
  count: 1 | 10 | 50,
  walletType: "personal" | "family" = "personal",
): Promise<GachaRollResult> {
  return request<GachaRollResult>("/api/gacha/roll", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, count, wallet_type: walletType }),
  });
}

// ── Inventory ─────────────────────────────────────────────────

/** Полный инвентарь с деталями */
export function fetchInventory(chatId: number): Promise<InventoryResponse> {
  return request<InventoryResponse>(`/api/inventory?chat_id=${chatId}`);
}

/** Экипировать предмет в слот */
export function equipItem(
  chatId: number,
  itemId: number,
  slot: string,
): Promise<{ ok: boolean; equipped: string; slot: string; error?: string }> {
  return request("/api/equip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, item_id: itemId, slot }),
  });
}

/** Переключить экипировку (снять) через POST /api/inventory */
export function toggleEquip(
  chatId: number,
  itemId: number,
): Promise<{ ok: boolean; equipped: boolean; error?: string }> {
  return request("/api/inventory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, item_id: itemId }),
  });
}

/** Продать весь хлам */
export function sellJunk(chatId: number): Promise<{ ok: boolean; sold: number; mora: number; balance: number }> {
  return request("/api/inventory/sell_junk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

/** Продать конкретные предметы */
export function batchSell(
  chatId: number,
  items: { id: number; qty: number }[],
): Promise<{ sold: number; mora: number; balance: number }> {
  return request("/api/batch_sell", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, items }),
  });
}

/** Улучшить предмет */
export function enhanceItem(
  chatId: number,
  itemId: number,
  useStone?: boolean,
): Promise<{ success: boolean; message: string; enhancement_level: number; balance: number }> {
  return request("/api/enhance_item", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, item_id: itemId, use_stone: useStone ?? null }),
  });
}

/** Использовать зелье/расходник */
export function consumePotion(
  chatId: number,
  itemId: number,
): Promise<{ success: boolean; message: string }> {
  return request("/api/consume_potion", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, item_id: itemId }),
  });
}

// ── Bank ──────────────────────────────────────────────────────

/** Информация о банке: баланс, вклады, планы */
export function fetchBankInfo(chatId: number): Promise<BankInfoResponse> {
  return request<BankInfoResponse>(`/api/bank?chat_id=${chatId}`);
}

/** Открыть вклад */
export function openDeposit(
  chatId: number,
  planKey: string,
  amount: number,
  wallet: "personal" | "family" = "personal",
): Promise<BankDepositResult> {
  return request<BankDepositResult>("/api/bank/deposit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, plan_key: planKey, amount, wallet }),
  });
}

/** Забрать/досрочно закрыть вклад */
export function withdrawDeposit(
  chatId: number,
  depositId: number,
): Promise<BankWithdrawResult> {
  return request<BankWithdrawResult>("/api/bank/withdraw", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, deposit_id: depositId }),
  });
}

// ── Shop ──────────────────────────────────────────────────────

/** Каталог магазина */
export function fetchShopCatalog(chatId: number): Promise<ShopCatalog> {
  return request<ShopCatalog>(`/api/shop/catalog?chat_id=${chatId}`);
}

/** Купить предмет в магазине */
export function buyShopItem(
  chatId: number,
  itemType: "frame" | "cosmetic" | "vip" | "potion" | "pet_color" | "profile_theme",
  itemKey: string,
  equip = true,
  walletType: "personal" | "family" = "personal",
): Promise<ShopBuyResult> {
  return request<ShopBuyResult>("/api/shop/buy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, item_type: itemType, item_key: itemKey, equip, wallet_type: walletType }),
  });
}

// ── Transfer ─────────────────────────────────────────────────

/** Перевести мору другому пользователю */
export function transferMora(
  chatId: number,
  targetId: number,
  amount: number,
  coverVat = true,
): Promise<TransferResult> {
  return request<TransferResult>("/api/transfer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, target_id: targetId, amount, cover_vat: coverVat }),
  });
}
