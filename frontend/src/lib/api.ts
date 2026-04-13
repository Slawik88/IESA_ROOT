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
export function fetchGlobalLeaderboard(): Promise<AchLeaderboardResponse> {
  return request<AchLeaderboardResponse>(
    `/api/achievements?mode=global_leaderboard`,
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
): Promise<{ ok: boolean; new_balance?: number; error?: string }> {
  return request<{ ok: boolean; new_balance?: number; error?: string }>("/api/crystals/spend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, item_key: itemKey, price }),
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
