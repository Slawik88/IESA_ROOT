/* ──────────────────────────────────────────────────────────────
   API-клиент — fetch-обёртка с авторизацией через initData.
   Бэкенд ożидает заголовок: X-Telegram-Init-Data: <initData>
   ────────────────────────────────────────────────────────────── */

import type {
  UserData,
  AchievementsResponse,
  AchLeaderboardResponse,
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
  MembersResponse,
  BondsResponse,
  BondTradeResult,
  TreasuryResponse,
  TreasuryPayoutResult,
  ThemesResponse,
  ThemeActivateResult,
  DevUsersResponse,
  DevUpdateResult,
  PetWalkResult,
  PetFeedResult,
  DevChatsResponse,
  FeatureFlagsResponse,
  FamilyTransferResult,
  FamilyLogResponse,
  ExpeditionsResponse,
  ExpeditionStartResult,
  ExpeditionCollectResult,
  WalletHistoryResponse,
  CoinFlipResult,
  RouletteResult,
  LotteryStatusResult,
  LotteryBuyResult,
  PublicProfileResponse,
  StarsInvoiceResult,
} from "../types";

// ── Promo types (inline — no need for types.ts) ───────────────
export interface PromoActivateResult { ok: boolean; rewards?: string[]; payload?: Record<string, unknown>; error?: string; }
export interface PromoRecord { id: number; code: string; payload: Record<string, unknown>; max_uses: number | null; uses: number; expires_at: string | null; is_active: boolean; created_at: string; }
export interface PromoListResult  { ok: boolean; promos?: PromoRecord[]; error?: string; }
export interface PromoCreateResult { ok: boolean; promo?: PromoRecord; error?: string; }

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

/** Глобальный топ-100 по достижениям */
export function fetchGlobalLeaderboard(chatId: number): Promise<AchLeaderboardResponse> {
  return request<AchLeaderboardResponse>(
    `/api/achievements?mode=leaderboard&chat_id=${chatId}`,
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

/** Бесплатная крутка гачи (использует 1 free_gacha_roll) */
export function rollFreeGacha(chatId: number): Promise<GachaRollResult & { remaining_free_rolls: number }> {
  return request("/api/gacha/free_roll", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

/** Получить кол-во бесплатных кручений гачи */
export function getFreeGachaRolls(): Promise<{ ok: boolean; free_rolls: number }> {
  return request("/api/gacha/free_rolls");
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
  return request("/api/enhance", {
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

/** Переименовать питомца (с купоном или без) */
export function renamePet(
  chatId: number,
  name: string,
  couponItemId?: number,
): Promise<{ ok: boolean; error?: string }> {
  return request("/api/pets/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, name, use_coupon: couponItemId != null ? true : undefined, item_id: couponItemId }),
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

// ── Members ───────────────────────────────────────────────────

/** Список участников чата (для визуального выбора получателя) */
export function fetchMembers(chatId: number): Promise<MembersResponse> {
  return request<MembersResponse>(`/api/members?chat_id=${chatId}`);
}

// ── Bonds / Биржа ─────────────────────────────────────────────

/** Состояние биржи: цены облигаций + портфель текущего пользователя */
export function fetchBonds(chatId: number): Promise<BondsResponse> {
  return request<BondsResponse>(`/api/bonds?chat_id=${chatId}`);
}

/** Купить облигации */
export function buyBond(
  chatId: number,
  bondKey: string,
  amount: number,
  wallet: "personal" | "family" = "personal",
): Promise<BondTradeResult> {
  return request<BondTradeResult>("/api/bonds/buy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, bond_key: bondKey, amount, wallet }),
  });
}

/** Продать облигации */
export function sellBond(
  chatId: number,
  bondKey: string,
  amount: number,
): Promise<BondTradeResult> {
  return request<BondTradeResult>("/api/bonds/sell", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, bond_key: bondKey, amount }),
  });
}

// ── Treasury / Казна ──────────────────────────────────────────

/** Казна чата (только dev/owner) */
export function fetchTreasury(chatId: number): Promise<TreasuryResponse> {
  return request<TreasuryResponse>(`/api/treasury?chat_id=${chatId}`);
}

/** Выплата из казны (только dev) */
export function treasuryPayout(
  chatId: number,
  targetId: number,
  amount: number,
  reason: string,
): Promise<TreasuryPayoutResult> {
  return request<TreasuryPayoutResult>("/api/treasury/payout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, target_id: targetId, amount, reason }),
  });
}

// ── Themes / Темы профиля ─────────────────────────────────────

/** Список тем профиля с состоянием владения */
export function fetchThemes(chatId: number): Promise<ThemesResponse> {
  return request<ThemesResponse>(`/api/themes?chat_id=${chatId}`);
}

/** Активировать тему профиля */
export function activateTheme(chatId: number, themeKey: string): Promise<ThemeActivateResult> {
  return request<ThemeActivateResult>("/api/themes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, theme_key: themeKey }),
  });
}

// ── Admin (God Mode) ──────────────────────────────────────────

/** Поиск пользователей в чате (только dev) */
export function fetchDevUsers(chatId: number, q = ""): Promise<DevUsersResponse> {
  return request<DevUsersResponse>(
    `/api/dev/users?chat_id=${chatId}&q=${encodeURIComponent(q)}`,
  );
}

/** Обновить профиль пользователя: баланс, XP, ранг (только dev) */
export function devMemberUpdate(
  chatId: number,
  targetId: number,
  balance: number,
  xp: number,
  rank: string,
  reputation?: number,
): Promise<DevUpdateResult> {
  return request<DevUpdateResult>("/api/dev/member_update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, target_id: targetId, balance, xp, rank, reputation }),
  });
}

/** Начислить/списать мору (только dev) */
export function devAddMora(
  chatId: number,
  targetId: number,
  amount: number,
): Promise<DevUpdateResult> {
  return request<DevUpdateResult>("/api/dev/add_mora", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, target_id: targetId, amount }),
  });
}

/** Добавить XP пользователю (только dev) */
export function devAddXp(
  chatId: number,
  targetId: number,
  amount: number,
): Promise<DevUpdateResult> {
  return request<DevUpdateResult>("/api/dev/add_xp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, target_id: targetId, amount }),
  });
}

/** Начислить кристаллы пользователю (только dev). Отрицательное amount — списать. */
export function devGiveCrystals(
  chatId: number,
  targetId: number,
  amount: number,
): Promise<DevUpdateResult> {
  return request<DevUpdateResult>("/api/dev/give_crystals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, target_id: targetId, amount }),
  });
}

/** Выдать предмет пользователю (только dev) */
export function devGiveItem(
  chatId: number,
  targetId: number,
  itemName: string,
  rarity: string,
): Promise<DevUpdateResult> {
  return request<DevUpdateResult>("/api/dev/give_item", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, target_id: targetId, item_name: itemName, rarity }),
  });
}

/** Переключить фичу (включить/выключить) для чата (только dev) */
export function devFeatureToggle(
  chatId: number,
  feature: string,
  enabled: boolean,
): Promise<DevUpdateResult> {
  return request<DevUpdateResult>("/api/dev/feature_toggle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, feature, enabled }),
  });
}

// ── Pet ───────────────────────────────────────────────────────

/** Отправить питомца на прогулку */
export function petWalk(chatId: number): Promise<PetWalkResult> {
  return request<PetWalkResult>("/api/pet/walk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

/** Покормить питомца */
export function petFeed(chatId: number, foodKey: string, walletType: "personal" | "family" = "personal"): Promise<PetFeedResult> {
  return request<PetFeedResult>("/api/pet/feed", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, food_key: foodKey, wallet_type: walletType }),
  });
}

// ── Dev: chats & feature flags ────────────────────────────────

/** Список чатов бота (только dev) */
export function fetchDevChats(): Promise<DevChatsResponse> {
  return request<DevChatsResponse>("/api/dev/chats");
}

/** Текущие флаги функций для чата (только dev) */
export function fetchFeatureFlags(chatId: number): Promise<FeatureFlagsResponse> {
  return request<FeatureFlagsResponse>(`/api/dev/feature_toggle?chat_id=${chatId}`);
}

// ── Family wallet ─────────────────────────────────────────────

/** Пополнить семейный кошелёк */
export function familyDeposit(chatId: number, amount: number): Promise<FamilyTransferResult> {
  return request<FamilyTransferResult>("/api/family/deposit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, amount }),
  });
}

/** Снять из семейного кошелька */
export function familyWithdraw(chatId: number, amount: number): Promise<FamilyTransferResult> {
  return request<FamilyTransferResult>("/api/family/withdraw", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, amount }),
  });
}

/** Лог семейного кошелька */
export function fetchFamilyLog(chatId: number): Promise<FamilyLogResponse> {
  return request<FamilyLogResponse>(`/api/family/log?chat_id=${chatId}`);
}

// ── Expeditions ───────────────────────────────────────────────

/** Текущая экспедиция + опции */
export function fetchExpeditions(chatId: number): Promise<ExpeditionsResponse> {
  return request<ExpeditionsResponse>(`/api/expeditions?chat_id=${chatId}`);
}

/** Начать экспедицию */
export function startExpedition(chatId: number, optionKey: string, walletType: "personal" | "family" = "personal"): Promise<ExpeditionStartResult> {
  return request<ExpeditionStartResult>("/api/expeditions/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, option_key: optionKey, wallet_type: walletType }),
  });
}

/** Забрать награду экспедиции */
export function collectExpedition(chatId: number): Promise<ExpeditionCollectResult> {
  return request<ExpeditionCollectResult>("/api/expeditions/collect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

/** Ускорить экспедицию купоном */
export function boostExpedition(chatId: number, itemId: number): Promise<{ ok: boolean; mins_left?: number; error?: string }> {
  return request<{ ok: boolean; mins_left?: number; error?: string }>("/api/expeditions/boost", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, item_id: itemId }),
  });
}

// ── Gifts (marriage) ──────────────────────────────────────────

export interface GiftCatalogItem { key: string; name: string; price: number; buff: { pct: string; hours: number } | null; }
export interface GiftsCatalogResponse {
  ok: boolean; married: boolean; partner_id?: number;
  catalog: GiftCatalogItem[]; summary?: { count: number; total: number };
  received?: number; balance?: number;
}
export interface GiftSendResult {
  ok: boolean; gift_name?: string; price?: number;
  new_balance?: number; buff?: { pct: string; hours: number }; error?: string;
}

/** Каталог подарков для партнёра */
export function fetchGiftsCatalog(chatId: number): Promise<GiftsCatalogResponse> {
  return request<GiftsCatalogResponse>(`/api/gifts/catalog?chat_id=${chatId}`);
}

/** Отправить подарок партнёру */
export function sendGift(chatId: number, giftKey: string, wallet: "personal" | "family" = "personal"): Promise<GiftSendResult> {
  return request<GiftSendResult>("/api/gifts/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, gift_key: giftKey, wallet }),
  });
}

/** Развестись с партнёром */
export function divorcePartner(chatId: number): Promise<{ ok: boolean; partner_id?: number; error?: string }> {
  return request<{ ok: boolean; partner_id?: number; error?: string }>("/api/marriage/divorce", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

// ── Wallet history ────────────────────────────────────────────

/** История кошелька */
export function fetchWalletHistory(chatId: number): Promise<WalletHistoryResponse> {
  return request<WalletHistoryResponse>(`/api/wallet/history?chat_id=${chatId}`);
}

// ── Public profile ────────────────────────────────────────────

/** Публичный профиль другого игрока */
export function fetchPublicProfile(targetUserId: number, chatId: number): Promise<PublicProfileResponse> {
  return request<PublicProfileResponse>(`/api/public_profile?user_id=${targetUserId}&chat_id=${chatId}`);
}

// ── Profile bio ───────────────────────────────────────────────

/** Обновить (или удалить) текст «О себе» */
export function setBio(chatId: number, bio: string): Promise<{ ok: boolean; bio?: string; error?: string }> {
  return request<{ ok: boolean; bio?: string; error?: string }>("/api/profile/bio", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, bio }),
  });
}

// ── Stars shop ────────────────────────────────────────────────

/** Создать Telegram Stars инвойс для покупки кристаллов */
export function createStarsInvoice(packKey: string, chatId: number): Promise<StarsInvoiceResult> {
  return request<StarsInvoiceResult>("/api/stars/invoice", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pack_key: packKey, chat_id: chatId }),
  });
}

/** Потратить кристаллы на предмет из донат-магазина */
export function buyCrystalItem(
  chatId: number,
  itemKey: string,
  price: number,
  extra?: { role_text?: string; megaphone_text?: string },
): Promise<{ ok: boolean; crystals_balance?: number; error?: string }> {
  return request<{ ok: boolean; crystals_balance?: number; error?: string }>("/api/crystals/spend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, item_key: itemKey, price, ...extra }),
  });
}

/** Каталог кристальных товаров с состоянием «куплено» */
export interface CrystalCatalogItem {
  key: string;
  emoji: string;
  name: string;
  price: number;
  desc: string;
  category: "aesthetic" | "gameplay" | "social" | "pets";
  oneTime: boolean;
  owned: boolean;
}
export interface CrystalCatalogResponse {
  ok: boolean;
  balance: number;
  first_deposit_available: boolean;
  items: CrystalCatalogItem[];
}
export function fetchCrystalCatalog(chatId: number): Promise<CrystalCatalogResponse> {
  return request<CrystalCatalogResponse>(`/api/crystals/catalog?chat_id=${chatId}`);
}

/** Список рупоров для модерации (dev only) */
export interface MegaphoneMessage {
  id: number;
  user_id: number;
  message: string;
  status: string;
  created_at: string;
  user_name: string;
}
export function fetchMegaphones(status?: string): Promise<{ ok: boolean; messages: MegaphoneMessage[] }> {
  return request<{ ok: boolean; messages: MegaphoneMessage[] }>(`/api/dev/megaphone/list?status=${status ?? "pending"}`);
}

/** Одобрить/отклонить рупор (dev only) */
export function reviewMegaphone(id: number, action: "approve" | "reject"): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/dev/megaphone/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, action }),
  });
}

/** Сохранить URL аватара из Telegram в профиле */
export function saveAvatar(photoUrl: string): Promise<{ ok: boolean; error?: string }> {
  return request<{ ok: boolean; error?: string }>("/api/save_avatar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ photo_url: photoUrl }),
  });
}

// ── Casino ────────────────────────────────────────────────────

/** Орёл или решка */
export function casinoCoinFlip(chatId: number, amount: number): Promise<CoinFlipResult> {
  return request<CoinFlipResult>("/api/casino/coin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, amount }),
  });
}

/** Рулетка */
export function casinoRoulette(chatId: number, betType: string, amount: number): Promise<RouletteResult> {
  return request<RouletteResult>("/api/casino/roulette", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, bet_type: betType, amount }),
  });
}

/** Статус лотереи */
export function fetchLotteryStatus(chatId: number): Promise<LotteryStatusResult> {
  return request<LotteryStatusResult>(`/api/casino/lottery?chat_id=${chatId}`);
}

/** Купить лотерейный билет */
export function buyLotteryTicket(chatId: number): Promise<LotteryBuyResult> {
  return request<LotteryBuyResult>("/api/casino/lottery", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

// ── Promoccodes ───────────────────────────────────────────────

/** Активировать промокод */
export function activatePromocode(chatId: number, code: string): Promise<PromoActivateResult> {
  return request<PromoActivateResult>("/api/promo/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, code }),
  });
}

/** [DEV] Список промокодов */
export function fetchPromocodes(): Promise<PromoListResult> {
  return request<PromoListResult>("/api/dev/promo/list");
}

/** [DEV] Создать промокод */
export function createPromocode(data: {
  code: string;
  payload: Record<string, unknown>;
  max_uses: number | null;
  expires_at: string | null;
}): Promise<PromoCreateResult> {
  return request<PromoCreateResult>("/api/dev/promo/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/** [DEV] Деактивировать промокод */
export function deactivatePromocode(code: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/dev/promo/deactivate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
}

// ── Solo Boss ─────────────────────────────────────────────────

export interface BossSession {
  id: number;
  boss_level: number;
  boss_max_hp: number;
  boss_current_hp: number;
  user_damage: number;
  user_hits: number;
  is_completed: 0 | 1;
  is_repeat: 0 | 1;
}
export interface BossProgress { max_level: number; last_completed: string | null; }
export interface BossStatusResult { session: BossSession | null; progress: BossProgress | null; next_level: number; }
export interface BossAttackResult { ok: boolean; damage_dealt: number; crit: boolean; boss_hp: number; boss_defeated: boolean; rewards?: { mora: number; xp: number }; new_balance?: number; }

export function fetchBossStatus(chatId: number): Promise<BossStatusResult> {
  return request<BossStatusResult>(`/api/solo_boss/status?chat_id=${chatId}`);
}

export function startBoss(chatId: number): Promise<{ ok: boolean; session: BossSession; error?: string }> {
  return request<{ ok: boolean; session: BossSession; error?: string }>("/api/solo_boss/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

export function attackBoss(chatId: number): Promise<BossAttackResult> {
  return request<BossAttackResult>("/api/solo_boss/attack", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

export function forfeitBoss(chatId: number): Promise<{ ok: boolean; forfeited: boolean }> {
  return request<{ ok: boolean; forfeited: boolean }>("/api/solo_boss/forfeit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

// ── Couple Boss ───────────────────────────────────────────────

export interface CoupleBossSession {
  id: number;
  boss_level: number;
  boss_max_hp: number;
  boss_current_hp: number;
  user_a_damage: number;
  user_b_damage: number;
  is_completed: 0 | 1;
  is_repeat: 0 | 1;
}

export interface CoupleBossStatusResult {
  married: boolean;
  partner_id?: number;
  partner_name?: string;
  session?: CoupleBossSession | null;
  max_level_completed?: number;
  available_levels?: number[];
}

export interface CoupleBossAttackResult {
  ok: boolean;
  damage_dealt: number;
  crit: boolean;
  boss_hp: number;
  boss_defeated: boolean;
  aggro?: boolean;
  aggro_damage?: number;
  rewards?: { mora: number; xp: number };
}

export function fetchCoupleBossStatus(chatId: number): Promise<CoupleBossStatusResult> {
  return request<CoupleBossStatusResult>(`/api/couple_boss/status?chat_id=${chatId}`);
}

export function startCoupleBoss(chatId: number, bossLevel: number): Promise<{ ok: boolean; session_id: number; boss_level: number; boss_max_hp: number; is_repeat: number }> {
  return request(`/api/couple_boss/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, boss_level: bossLevel }),
  });
}

export function attackCoupleBoss(chatId: number): Promise<CoupleBossAttackResult> {
  return request<CoupleBossAttackResult>("/api/couple_boss/attack", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

// ── Error Logs (DEV) ─────────────────────────────────────────

/** [DEV] Получить логи ошибок */
export function fetchErrorLogs(): Promise<{ logs: import("../types").ErrorLogEntry[] }> {
  return request<{ logs: import("../types").ErrorLogEntry[] }>("/api/dev/error_logs");
}

/** [DEV] Очистить все логи ошибок */
export function clearErrorLogs(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/dev/error_logs", { method: "DELETE" });
}

// ── Telemetry ─────────────────────────────────────────────────────────────────

export interface TelemetryEvent {
  event_type: "tab_time" | "click" | "session";
  event_key: string;
  count: number;
  seconds: number;
}

export interface AnalyticsResponse {
  period: string;
  date_from: string;
  date_to: string;
  top_tabs: { key: string; label: string; seconds: number; sessions: number }[];
  top_clicks: { key: string; count: number }[];
  total_sessions: number;
  avg_session_sec: number;
  daily_sessions: { date: string; count: number }[];
}

/** Отправить батч событий телеметрии */
export function submitTelemetry(events: TelemetryEvent[]): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/telemetry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ events }),
  });
}

/** [DEV] Получить аналитику за период (day / week / month) */
export function fetchAnalytics(period: string = "week"): Promise<AnalyticsResponse> {
  return request<AnalyticsResponse>(`/api/dev/analytics?period=${period}`);
}

// ── Auction / Аукцион ─────────────────────────────────────────

export interface AuctionLot {
  id: number;
  seller_id: number;
  seller_name?: string;
  item_key?: string;
  item_name: string;
  item_source: string;
  start_price: number;
  buyout_price?: number | null;
  current_bid: number;
  bidder_id?: number | null;
  bidder_name?: string | null;
  ends_at?: string | null;
  created_at?: string;
  chat_id?: number;
}

export interface AuctionListResponse {
  lots: AuctionLot[];
  my_lots: AuctionLot[];
  my_bids: AuctionLot[];
}

export function fetchAuctions(chatId: number): Promise<AuctionListResponse> {
  return request<AuctionListResponse>(`/api/auction/list?chat_id=${chatId}`);
}

export function createAuction(chatId: number, data: {
  item_id?: number;
  item_key?: string;
  item_name?: string;
  item_source: "gacha" | "shop";
  start_price: number;
  buyout_price?: number;
}): Promise<{ ok: boolean; lot_id?: number; error?: string }> {
  return request<{ ok: boolean; lot_id?: number; error?: string }>("/api/auction/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, ...data }),
  });
}

export function placeBid(chatId: number, auctionId: number, amount: number): Promise<{ ok: boolean; error?: string }> {
  return request<{ ok: boolean; error?: string }>("/api/auction/bid", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, auction_id: auctionId, amount }),
  });
}

export function buyoutAuction(chatId: number, auctionId: number): Promise<{ ok: boolean; error?: string }> {
  return request<{ ok: boolean; error?: string }>("/api/auction/buyout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, auction_id: auctionId }),
  });
}

export function cancelAuction(chatId: number, auctionId: number): Promise<{ ok: boolean; error?: string }> {
  return request<{ ok: boolean; error?: string }>("/api/auction/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, auction_id: auctionId }),
  });
}

// ── Loans / Займы ─────────────────────────────────────────────

export interface LoanRecord {
  id: number;
  lender_id: number;
  borrower_id: number;
  lender_name?: string;
  borrower_name?: string;
  chat_id: number;
  amount: number;
  loaned_at?: string;
  due_at?: string | null;
  repaid_at?: string | null;
  status: "pending" | "accepted" | "repaid" | "cancelled";
}

export interface LoansResponse {
  as_lender: LoanRecord[];
  as_borrower: LoanRecord[];
  pending_incoming: LoanRecord[];
}

export function fetchLoans(chatId: number): Promise<LoansResponse> {
  return request<LoansResponse>(`/api/loans?chat_id=${chatId}`);
}

export function createLoan(chatId: number, targetId: number, amount: number): Promise<{ ok: boolean; loan_id?: number; error?: string }> {
  return request<{ ok: boolean; loan_id?: number; error?: string }>("/api/loans/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, target_id: targetId, amount }),
  });
}

export function repayLoan(chatId: number, loanId: number): Promise<{ ok: boolean; error?: string }> {
  return request<{ ok: boolean; error?: string }>("/api/loans/repay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, loan_id: loanId }),
  });
}

export function respondLoan(chatId: number, loanId: number, action: "accept" | "reject"): Promise<{ ok: boolean; error?: string }> {
  return request<{ ok: boolean; error?: string }>("/api/loans/respond", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, loan_id: loanId, action }),
  });
}

export function cancelLoan(chatId: number, loanId: number): Promise<{ ok: boolean; error?: string }> {
  return request<{ ok: boolean; error?: string }>("/api/loans/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, loan_id: loanId }),
  });
}

// ── Talents ───────────────────────────────────────────────────

export interface TalentInfo { name: string; emoji: string; tier: number; max_level: number; desc: string; effect_key: string; effect_per_level: number; }
export interface TalentsResponse { talent_points: number; talents: Record<string, number>; tree: Record<string, TalentInfo>; }

export function fetchTalents(): Promise<TalentsResponse> {
  return request<TalentsResponse>("/api/talents");
}

export function upgradeTalent(talentId: string): Promise<{ ok: boolean; talent_points: number; error?: string }> {
  return request<{ ok: boolean; talent_points: number; error?: string }>("/api/talents/upgrade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ talent_id: talentId }),
  });
}

// ── Shards ────────────────────────────────────────────────────

export interface ShardCatalogEntry { name: string; emoji: string; craft_into: string | null; craft_frame: string | null; craft_amount: number; owned: number; }
export interface ShardsResponse { stash: Record<string, number>; catalog: Record<string, ShardCatalogEntry>; }

export function fetchShards(chatId: number): Promise<ShardsResponse> {
  return request<ShardsResponse>(`/api/shards?chat_id=${chatId}`);
}

export function craftShard(chatId: number, shardKey: string): Promise<{ ok: boolean; message?: string; error?: string }> {
  return request<{ ok: boolean; message?: string; error?: string }>("/api/shards/craft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, shard_key: shardKey }),
  });
}

// ── Settings ──────────────────────────────────────────────────

export interface SettingsRankEntry { min_rank: string; min_rank_level: number; min_rank_name: string; }
export interface SettingsLocalResponse { ok: boolean; settings: Record<string, unknown>; user_rank: string; user_rank_level: number; rank_map: Record<string, SettingsRankEntry>; }
export interface SettingsGlobalResponse { ok: boolean; settings: Record<string, unknown>; is_dev: boolean; }

export function fetchSettingsLocal(chatId: number): Promise<SettingsLocalResponse> {
  return request<SettingsLocalResponse>(`/api/settings/local?chat_id=${chatId}`);
}

export function updateSettingLocal(chatId: number, key: string, value: unknown): Promise<{ ok: boolean; key: string; value: unknown; error?: string }> {
  return request<{ ok: boolean; key: string; value: unknown; error?: string }>("/api/settings/local", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, key, value }),
  });
}

export function fetchSettingsGlobal(): Promise<SettingsGlobalResponse> {
  return request<SettingsGlobalResponse>("/api/settings/global");
}

export function updateSettingGlobal(key: string, value: string): Promise<{ ok: boolean; key: string; value: string; error?: string }> {
  return request<{ ok: boolean; key: string; value: string; error?: string }>("/api/settings/global", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
}

// ── Newbie Quest ──────────────────────────────────────────────

export function triggerNewbieQuest(chatId: number): Promise<{ active: boolean }> {
  return request<{ active: boolean }>(`/api/newbie_quest?chat_id=${chatId}`);
}
