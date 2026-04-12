/* ──────────────────────────────────────────────────────────────
   Типы данных API — соответствуют ответам FastAPI-бэкенда
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
}

export interface PartnerInfo {
  partner_id: number;
  partner_name: string;
  married_at: string;
}

export interface UserData {
  name: string;
  balance: number;
  xp: number;
  vip: boolean;
  active_frame: string;
  bonds: BondInfo[];
  items: string[];
  pet: PetInfo | null;
  partner: PartnerInfo | null;
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
