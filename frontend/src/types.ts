/* ──────────────────────────────────────────────────────────────
   Типы данных API — точное соответствие Django miniapp_views.py
   ────────────────────────────────────────────────────────────── */

// ── /api/user_data ────────────────────────────────────────────

export interface BondInfo {
  name: string;
  amount: number;
  value: number;
}

export interface PetInfo {
  type: string;
  name: string;
  emoji: string;
  fatigue: number;
  on_walk: boolean;
  walk_mins_left: number;
  walk_end_at: string | null;
  color_name: string | null;
}

export interface RpgStats {
  hp: number;
  atk: number;
  def: number;
  crit: number;
}

export interface UserData {
  // Идентификаторы
  uid: number;
  chat_id: number;
  // Основное
  name: string;
  balance: number;
  crystals: number;
  xp: number;
  level: number;
  xp_max: number;
  vip: boolean;
  active_frame: string;
  active_theme: string;
  // Ранг / статус
  rank: string;
  is_dev: boolean;
  custom_title: string;
  bio: string;
  chat_role: string | null;
  // Активность
  message_count: number;
  streak: number;
  warns: number;
  first_active: string | null;
  last_active: string | null;
  newbie_shield_until: string | null;
  // Партнёр / семья
  has_partner: boolean;
  partner_name: string | null;
  partner_id: number | null;
  family_balance: number;
  my_family_balance: number;
  partner_family_balance: number;
  // Инвентарь / игровые данные
  bonds: BondInfo[];
  items: string[];
  pet: PetInfo | null;
  rpg: RpgStats;
  pity: number;
  // Кристальные предметы
  transfer_passes: number;
  enhancement_stones: number;
  guarantee_scrolls: number;
  avatar_unlocked: boolean;
  avatar_url?: string | null;
  crystal_cosmetics_owned: string[];
  has_rainbow_title: boolean;
}

// ── /api/achievements ─────────────────────────────────────────
export interface AchievementRank {
  rank: number;
  key: string;
  title: string;
  emoji: string;
  description: string;
  threshold: number;
  mora: number;
  xp: number;
  unlocked: boolean;
  obtained_at: string | null;
}

export interface AchievementCategory {
  type: string;
  label: string;
  emoji: string;
  order: number;
  current_value: number;
  current_rank: number;
  total_defined: number;
  next_threshold: number | null;
  next_title: string | null;
  progress_pct: number;
  is_bool: boolean;
  ranks: AchievementRank[];
}

export interface AchievementsResponse {
  categories: AchievementCategory[];
  total_unlocked: number;
  total_defined: number;
}

// ── /api/achievements?mode=global_leaderboard ─────────────────
export interface AchLeaderboardEntry {
  rank: number;
  user_id: number;
  full_name: string;
  badge_count: number;
}

export interface AchLeaderboardResponse {
  leaderboard: AchLeaderboardEntry[];
}

// ── /api/achievements/badges ──────────────────────────────────
export interface BadgesResponse {
  badges: string[];
}

// ── /api/season/data ──────────────────────────────────────────
export interface SeasonInfo {
  id: number;
  name: string;
  start_date: string | null;
  end_date: string | null;
  active: boolean;
}

export interface SeasonReward {
  level: number;
  free_reward: string | null;
  premium_reward: string | null;
  free_mora: number;
  premium_mora: number;
  free_xp: number;
  premium_xp: number;
}

export interface SeasonProgress {
  level: number;
  xp: number;
  has_premium: boolean;
  claimed_free: number[];
  claimed_premium: number[];
}

export interface SeasonDataResponse {
  season: SeasonInfo;
  progress: SeasonProgress;
  rewards: SeasonReward[];
}

// ── /api/checkin ──────────────────────────────────────────────
export interface CheckinStatus {
  streak: number;
  total_days: number;
  last_checkin: string | null;
  checkpoint: number;
  today_done: boolean;
}

export interface CheckinResult {
  ok: boolean;
  already_done: boolean;
  streak: number;
  total_days: number;
  mora?: number;
  is_checkpoint?: boolean;
  free_gacha?: boolean;
  vip_bonus?: boolean;
  error?: string;
}

// ── /api/quest ────────────────────────────────────────────────
export interface QuestInfo {
  type: string;
  goal: number;
  desc: string;
  xp: number;
  mora: number;
}

export interface QuestData {
  ok: boolean;
  quest: QuestInfo;
  progress: number;
  completed: boolean;
  rewarded: boolean;
  today: string;
}

export interface QuestRerollResult {
  ok: boolean;
  quest: QuestInfo;
  cost: number;
  new_balance: number;
  used_coupon: boolean;
}

// ── /api/leaderboard ─────────────────────────────────────────
export interface LeaderboardEntry {
  rank: number;
  user_id: number;
  name: string;
  score: number | null;
  color_name?: string;
  vip?: boolean;
  active_theme?: string;
  level?: number;
}

export interface LeaderboardResponse {
  type: string;
  entries: LeaderboardEntry[];
  uid: number | null;
  user_rank?: { rank: number; score: number };
}

// ── /api/inventory ────────────────────────────────────────────
export interface InventoryItem {
  id: number;
  key: string;
  name: string;
  rarity: string;
  equipped: boolean;
  atk: number;
  def_val: number;
  hp: number;
  crit_rate: number;
  slot: string | null;
  enhancement_level: number;
  stack_count: number;
  is_cosmetic: boolean;
  desc: string;
  sell_price: number;
  can_auction: boolean;
  days_until_auctionable: number | null;
  hours_until_auctionable: number | null;
}

export interface InventoryRpg {
  hp: number;
  atk: number;
  def: number;
  crit: number;
}

export interface InventoryResponse {
  items: InventoryItem[];
  rpg: InventoryRpg;
  pity: number;
}

// ── /api/gacha/roll ───────────────────────────────────────────
export interface GachaItem {
  id?: number;
  key: string;
  name: string;
  rarity: string;
  desc: string;
  atk?: number;
  def_val?: number;
  hp?: number;
  crit_rate?: number;
  slot?: string;
  enhancement_level?: number;
  is_new?: boolean;
}

export interface GachaRollResult {
  ok: boolean;
  items: GachaItem[];
  balance: number;
  family_balance?: number;
  pity: number;
  spent: number;
  quest_done: boolean;
  quest_xp?: number;
  quest_mora?: number;
  error?: string;
}

// ── /api/bank ─────────────────────────────────────────────────
export interface BankDeposit {
  id: number;
  amount: number;
  rate: number;
  rate_pct: number;
  reward: number;
  mature: boolean;
  time_left_h: number;
  time_left_m: number;
  progress_pct: number;
  plan_days: number;
  matures_at_iso: string;
}

export interface BankPlan {
  key: string;
  days: number;
  rate_pct: number;
  label: string;
  amounts: number[];
}

export interface BankInfoResponse {
  balance: number;
  family_balance: number;
  deposits: BankDeposit[];
  plans: BankPlan[];
  min_deposit: number;
  max_deposit: number;
  early_penalty_pct: number;
  singles_bonus: boolean;
}

export interface BankDepositResult {
  ok: boolean;
  deposit_id: number;
  amount: number;
  rate_pct: number;
  reward: number;
  days: number;
  new_balance: number;
  wallet: string;
  singles_bonus: boolean;
  error?: string;
}

export interface BankWithdrawResult {
  ok: boolean;
  deposit_id: number;
  payout: number;
  early: boolean;
  interest_tax: number;
  new_balance: number;
  error?: string;
}

// ── /api/shop/catalog ─────────────────────────────────────────
export interface ShopFrame {
  key: string;
  emoji: string;
  name: string;
  price: number;
  owned: boolean;
  active: boolean;
}

export interface ShopCosmetic {
  key: string;
  emoji: string;
  name: string;
  price: number;
  desc: string;
  owned: boolean;
}

export interface ShopPetColor {
  key: string;
  label: string;
  price: number;
  owned: boolean;
  active: boolean;
}

export interface ShopFood {
  key: string;
  name: string;
  emoji: string;
  price: number;
  fatigue: number;
}

export interface ShopPotion {
  key: string;
  name: string;
  emoji: string;
  price: number;
  buff_type: string;
  buff_amount: number;
  duration: number;
  desc: string;
}

export interface ShopTheme {
  key: string;
  name: string;
  tier: string;
  price: number;
  owned: boolean;
  active: boolean;
}

export interface ShopCatalog {
  balance: number;
  frames: ShopFrame[];
  cosmetics: ShopCosmetic[];
  pet_colors: ShopPetColor[];
  current_color: string | null;
  food: ShopFood[];
  potions: ShopPotion[];
  has_vip: boolean;
  active_frame: string;
  gacha_p1: number;
  gacha_p10: number;
  themes: ShopTheme[];
}

export interface ShopBuyResult {
  ok: boolean;
  balance?: number;
  error?: string;
}

// ── /api/transfer ─────────────────────────────────────────────
export interface TransferResult {
  ok: boolean;
  sender_balance?: number;
  receiver_balance?: number;
  amount?: number;
  vat?: number;
  error?: string;
}

// ── /api/members ──────────────────────────────────────────────
export interface ChatMember {
  user_id: number;
  name: string;
}
export interface MembersResponse {
  members: ChatMember[];
}

// ── /api/bonds ────────────────────────────────────────────────
export interface BondPrice {
  key: string;
  name: string;
  description?: string;
  current_price: number;
  price: number;
  prev_price?: number;
  price_history?: number[];
  history?: { price: number; ts: string }[];
  amount: number;
  invested: number;
  avg_price: number;
  pnl_mora: number;
  pnl_pct: number;
  value: number;
}
export interface UserBond {
  bond_key: string;
  amount: number;
  current_price: number;
  total_value: number;
  invested?: number;
  avg_price?: number;
  pnl_mora?: number;
  pnl_pct?: number;
}
export interface BondsResponse {
  bonds: BondPrice[];
  holdings: UserBond[];
  balance: number;
  family_balance?: number;
  market_trend?: string;
  market_ticks?: number;
  prices_updated_at?: string;
}
export interface BondTradeResult {
  ok: boolean;
  new_balance?: number;
  amount_traded?: number;
  error?: string;
}

// ── /api/treasury ─────────────────────────────────────────────
export interface TreasuryEntry {
  description: string;
  amount: number;
  ts: string;
}
export interface TreasuryResponse {
  ok?: boolean;
  balance: number;
  total_collected?: number;
  recent?: TreasuryEntry[];
  error?: string;
}
export interface TreasuryPayoutResult {
  ok: boolean;
  new_balance?: number;
  error?: string;
}

// ── /api/themes ───────────────────────────────────────────────
export interface ProfileTheme {
  key: string;
  name: string;
  tier: string;
  source: string;
  price: number;
  header: string;
  separator: string;
  footer: string;
  owned: boolean;
  active: boolean;
}
export interface ThemesResponse {
  themes: ProfileTheme[];
  crystals?: number;
}
export interface ThemeActivateResult {
  ok: boolean;
  error?: string;
}

// ── /api/dev/users ────────────────────────────────────────────
export interface DevUserEntry {
  user_id: number;
  name: string;
  balance: number;
  xp: number;
  rank: string;
  level?: number;
  message_count?: number;
  reputation?: number;
  crystals?: number;
}
export interface DevUsersResponse {
  users: DevUserEntry[];
}
export interface DevUpdateResult {
  ok: boolean;
  message?: string;
  new_balance?: number;
  error?: string;
}

// ── /api/pet ──────────────────────────────────────────────────
export interface PetWalkResult {
  ok: boolean;
  fatigue?: number;
  reduced?: number;
  pet_emoji?: string;
  pet_name?: string;
  walk_mins?: number;
  reward?: number;
  error?: string;
}
export interface PetFeedResult {
  ok: boolean;
  pet_emoji?: string;
  pet_name?: string;
  food_name?: string;
  reduced?: number;
  error?: string;
}

// ── /api/dev/chats ────────────────────────────────────────────
export interface DevChat {
  chat_id: number;
  title: string;
  chat_type: string;
  members: number;
  ecosystem_id: number | null;
  ecosystem_label: string | null;
  ecosystem_role: string | null;
}
export interface DevChatsResponse {
  groups: DevChat[];
  admin_chats: DevChat[];
}

// ── /api/dev/feature_toggle GET ───────────────────────────────
export interface FeatureFlagsResponse {
  ok: boolean;
  flags: Record<string, boolean>;
}

// ── /api/family ───────────────────────────────────────────────
export interface FamilyTransferResult {
  ok: boolean;
  personal: number;
  family: number;
  error?: string;
}

export interface FamilyLogEntry {
  description: string;
  amount: number;
  ts: string;
}
export interface FamilyLogResponse {
  entries: FamilyLogEntry[];
}

// ── /api/expeditions ──────────────────────────────────────────
export interface ExpeditionOption {
  key: string;
  label: string;
  duration_min: number;
  cost: number;
  rewards_desc: string;
}
export interface ActiveExpedition {
  option_key: string;
  label: string;
  started_at: string;
  ends_at: string;
  mins_left: number;
  finished: boolean;
}
export interface ExpeditionsResponse {
  ok: boolean;
  active: ActiveExpedition | null;
  partner_active: { label: string; mins_left: number; finished: boolean } | null;
  options: ExpeditionOption[];
  has_pet: boolean;
  error?: string;
}
export interface ExpeditionStartResult {
  ok: boolean;
  ends_at?: string;
  mins?: number;
  error?: string;
}
export interface ExpeditionCollectResult {
  ok: boolean;
  rewards?: string;
  mora?: number;
  xp?: number;
  items?: string[];
  error?: string;
}

// ── /api/wallet/history ───────────────────────────────────────
export interface WalletHistoryEntry {
  description: string;
  amount: number;
  ts: string;
}
export interface WalletHistoryResponse {
  history: WalletHistoryEntry[];
}

// ── /api/public_profile ───────────────────────────────────────
export interface PublicProfileResponse {
  uid: number;
  name: string;
  level: number;
  xp: number;
  xp_max: number;
  rank: string;
  vip: boolean;
  custom_title?: string;
  bio?: string;
  active_frame?: string;
  active_theme?: string;
  theme_name?: string;
  rpg?: { hp: number; atk: number; def: number; crit: number };
  equipped_items?: { name: string; rarity: string; slot: string }[];
  partner_name?: string | null;
  pet?: { type: string; name: string; emoji: string; fatigue: number; on_walk: boolean } | null;
  is_own?: boolean;
  message_count?: number;
  warns?: number;
  online_status?: string;
  avatar_url?: string | null;
  error?: string;
  crystal_cosmetics_owned?: string[];
  has_rainbow_title?: boolean;
}

// ── /api/stars/invoice ────────────────────────────────────────
export interface StarsInvoiceResult {
  ok: boolean;
  link: string;
  pack: {
    stars: number;
    crystals: number;
    label: string;
    bonus_pct: number;
  };
  error?: string;
}

// ── /api/casino ───────────────────────────────────────────────
export interface CoinFlipResult {
  ok: boolean;
  win: boolean;
  bet: number;
  prize: number;
  win_tax: number;
  new_balance: number;
  quest_done: boolean;
}

export interface RouletteItemPrize {
  item_key: string;
  item_name: string;
  item_type: string;
  effect: string;
}

export interface RouletteResult {
  ok: boolean;
  number: number;
  color: "red" | "black" | "green";
  win: boolean;
  gross_profit: number;
  win_tax: number;
  net_prize: number;
  new_balance: number;
  item_prize: RouletteItemPrize | null;
}

export interface LotteryStatusResult {
  ok: boolean;
  tickets: number;
  week: string;
  ticket_price: number;
}

export interface LotteryBuyResult {
  ok: boolean;
  tickets: number;
  ticket_price: number;
  new_balance: number;
}

// ── Error Logs ────────────────────────────────────────────────
export interface ErrorLogEntry {
  id: number;
  source: string;
  context: string;
  error_msg: string;
  traceback: string;
  user_id: number | null;
  chat_id: number | null;
  created_at: string;
}
