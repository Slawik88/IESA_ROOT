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

export interface SeasonDataResponse {
  season: SeasonInfo;
  progress: Record<string, unknown>;
  rewards: Record<string, unknown>[];
}
