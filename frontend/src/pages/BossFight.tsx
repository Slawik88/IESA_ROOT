/* в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
   BossFight.tsx вЂ” Tactical Solo Boss Fight
   ATB Stamina + QTE (Telegraph + Weak Spots)
   в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ */
import { useState, useEffect, useRef, useCallback } from "react";
import {
  fetchBossStatus, startBoss, attackBoss, forfeitBoss, buyBossCoupon, fetchInventory, consumePotion,
  type BossSession, type BossProgress,
} from "../lib/api";
import type { InventoryItem } from "../types";
import { Loader2, Shield, Zap, Sword, Swords, Pause, Play, Flag, FlaskConical, Ticket, X } from "lucide-react";
import CoupleBoss from "./CoupleBoss";
import { useToast } from "../components/ToastContext";

// в”Ђв”Ђв”Ђ Constants в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
const STAMINA_MAX         = 100;
const STAMINA_REGEN       = 8;          // per second
const SKILL_FAST_COST     = 18;
const SKILL_HEAVY_COST    = 45;
const SKILL_BLOCK_COST    = 22;
const SKILL_HEAVY_CD      = 8000;       // ms
const BLOCK_DURATION      = 3000;       // ms
const WEAKSPOT_DURATION   = 1600;       // ms
const TELEGRAPH_WARN_MS   = 2200;       // boss warning before attack

const BOSS_NAMES: Record<number, string> = {
  1: "РЎС‚СЂР°Р¶ РўРµРЅРµР№",   2: "РџРѕР¶РёСЂР°С‚РµР»СЊ Р—РІС‘Р·Рґ", 3: "РџРѕРІРµР»РёС‚РµР»СЊ Р‘РµР·РґРЅС‹",
  4: "РћС‚СЂР°Р¶РµРЅРёРµ РҐР°РѕСЃР°", 5: "Р Р°Р·СЂСѓС€РёС‚РµР»СЊ РњРёСЂР°",
};
function bossName(level: number) {
  return BOSS_NAMES[level] ?? `РўС‘РјРЅС‹Р№ РЎС‚СЂР°Р¶ РЈСЂ. ${level}`;
}

const BOSS_ART: Record<number, string> = {
  1: "рџ‘№", 2: "рџђ‰", 3: "рџ’Ђ", 4: "рџ‘ѕ", 5: "рџЊ‘",
};
function bossArt(level: number) {
  return BOSS_ART[level] ?? "рџ‘ѕ";
}

// в”Ђв”Ђв”Ђ Types в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
interface WeakSpot { id: number; x: number; y: number; }
interface FloatText { id: number; text: string; x: number; y: number; color: string; }

interface Props {
  userId: number | null;
  chatId: number | null;
}

// в”Ђв”Ђв”Ђ Helpers в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
function fmt(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(0) + "K";
  return String(n);
}

// в”Ђв”Ђ Constants в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

// в”Ђв”Ђв”Ђ Component в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
export default function BossFight({ userId: _userId, chatId }: Props) {
  // Boss mode tabs
  const [mode, setMode] = useState<"solo" | "couple">("solo");

  // Remote state
  const [session, setSession]   = useState<BossSession | null>(null);
  const [progress, setProgress] = useState<BossProgress | null>(null);
  const [nextLevel, setNextLevel] = useState(1);
  const [dailyLimit, setDailyLimit] = useState(2);
  const [dailyUsed, setDailyUsed] = useState(0);
  const [resetText, setResetText] = useState<string>("");
  const [loading, setLoading]   = useState(true);
  const [starting, setStarting] = useState(false);
  const [fightTimeLeft, setFightTimeLeft] = useState<number | null>(null);
  const [bossCoupons, setBossCoupons]     = useState(5);
  const [buyingCoupon, setBuyingCoupon]   = useState(false);
  const [showCouponModal, setShowCouponModal] = useState(false);
  const { toast } = useToast();

  // Local fight state
  const [bossHp, setBossHp]       = useState(0);
  const [bossMaxHp, setBossMaxHp] = useState(1);
  const [playerHp, setPlayerHp]   = useState(100);
  const [stamina, setStamina]      = useState(STAMINA_MAX);
  const [blocking, setBlocking]    = useState(false);
  const [heavyCd, setHeavyCd]      = useState(0);    // ms remaining
  const [attacking, setAttacking]  = useState(false);

  // Boss telegraph
  const [telegraphing, setTelegraphing] = useState(false);
  const [telegraphPct, setTelegraphPct] = useState(100);

  // Weak spots
  const [weakSpots, setWeakSpots] = useState<WeakSpot[]>([]);
  const nextWsId = useRef(0);

  // Float damage texts
  const [floats, setFloats] = useState<FloatText[]>([]);
  const nextFid = useRef(0);

  // Pause + potions + equipment
  const [paused, setPaused]     = useState(false);
  const [potions, setPotions]   = useState<InventoryItem[]>([]);
  const [equipped, setEquipped] = useState<InventoryItem[]>([]);
  const [usingPotion, setUsingPotion] = useState<number | null>(null);
  const [showPotions, setShowPotions] = useState(false);

  // Fight active flag
  const fightActive = session != null && !session.is_completed && playerHp > 0;

  // Refs for intervals (avoid stale closures)
  const staminaRef  = useRef(stamina);
  const blockingRef = useRef(blocking);
  const playerHpRef = useRef(playerHp);
  staminaRef.current   = stamina;
  blockingRef.current  = blocking;
  playerHpRef.current  = playerHp;

  const addFloat = useCallback((text: string, x: number, y: number, color: string) => {
    const id = nextFid.current++;
    setFloats(f => [...f, { id, text, x, y, color }]);
    setTimeout(() => setFloats(f => f.filter(t => t.id !== id)), 900);
  }, []);

  // в”Ђв”Ђ Load boss status в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  const loadStatus = useCallback(async () => {
    if (!chatId) return;
    try {
      const r = await fetchBossStatus(chatId);
      setSession(r.session);
      setProgress(r.progress);
      setNextLevel(r.next_level);
      setDailyLimit(r.daily_limit);
      setDailyUsed(r.daily_used);
      setResetText(r.reset_in_text);
      setBossCoupons(r.boss_coupons ?? 5);
      if (r.session && !r.session.is_completed) {
        setBossHp(r.session.boss_current_hp);
        setBossMaxHp(r.session.boss_max_hp);
        setPlayerHp(100);
        setStamina(STAMINA_MAX);
        setFightTimeLeft(null); // С‚Р°Р№РјРµСЂ РѕС‚РєР»СЋС‡С‘РЅ
      } else {
        setFightTimeLeft(null);
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [chatId]);

  const loadPotions = useCallback(async () => {
    if (!chatId) return;
    const COMBAT_SLOTS = ["weapon", "armor", "helmet", "boots", "artifact"];
    try {
      const inv = await fetchInventory(chatId);
      setPotions(inv.items.filter(i => i.slot === "potion"));
      setEquipped(inv.items.filter(i => i.equipped && COMBAT_SLOTS.includes(i.slot ?? "")));
    } catch { /* ignore */ }
  }, [chatId]);

  useEffect(() => { loadStatus(); }, [loadStatus]);
  useEffect(() => { loadPotions(); }, [loadPotions]);

  // в”Ђв”Ђ Stamina regen в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  useEffect(() => {
    if (!fightActive || paused) return;
    const id = setInterval(() => {
      setStamina(s => Math.min(STAMINA_MAX, s + STAMINA_REGEN));
    }, 1000);
    return () => clearInterval(id);
  }, [fightActive, paused]);

  // в”Ђв”Ђ Heavy cooldown ticker в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  useEffect(() => {
    if (heavyCd <= 0) return;
    const id = setInterval(() => {
      setHeavyCd(c => Math.max(0, c - 100));
    }, 100);
    return () => clearInterval(id);
  }, [heavyCd]);

  // в”Ђв”Ђ Boss telegraph (random interval 6-14s) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  useEffect(() => {
    if (!fightActive || paused) return;

    let telegraphTimeout: ReturnType<typeof setTimeout>;
    let warningInterval: ReturnType<typeof setInterval>;

    const scheduleNext = () => {
      const delay = 6000 + Math.random() * 8000;
      telegraphTimeout = setTimeout(() => {
        // Start telegraph warning
        setTelegraphing(true);
        setTelegraphPct(100);

        const start = Date.now();
        warningInterval = setInterval(() => {
          const elapsed = Date.now() - start;
          const pct = Math.max(0, 100 - (elapsed / TELEGRAPH_WARN_MS) * 100);
          setTelegraphPct(pct);
          if (elapsed >= TELEGRAPH_WARN_MS) {
            clearInterval(warningInterval);
            setTelegraphing(false);
            // Boss attacks
            const dmg = blockingRef.current
              ? Math.floor(5 + Math.random() * 8)   // blocked: tiny damage
              : Math.floor(18 + Math.random() * 20); // unblocked: big hit
            setPlayerHp(hp => {
              const next = Math.max(0, hp - dmg);
              addFloat(`-${dmg}`, 50, 40, "#f87171");
              if (next === 0 && chatId) {
                forfeitBoss(chatId).catch(() => {});
              }
              return next;
            });
            scheduleNext();
          }
        }, 50);
      }, delay);
    };

    scheduleNext();
    return () => {
      clearTimeout(telegraphTimeout);
      clearInterval(warningInterval);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fightActive, paused]);

  // в”Ђв”Ђ Weak spots (random interval 5-10s) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  useEffect(() => {
    if (!fightActive || paused) return;
    const schedule = () => {
      const delay = 5000 + Math.random() * 5000;
      return setTimeout(() => {
        const id = nextWsId.current++;
        const ws: WeakSpot = {
          id,
          x: 10 + Math.random() * 80,  // % of boss area
          y: 10 + Math.random() * 80,
        };
        setWeakSpots(w => [...w, ws]);
        setTimeout(() => {
          setWeakSpots(w => w.filter(s => s.id !== id));
        }, WEAKSPOT_DURATION);
      }, delay);
    };
    let t = schedule();
    const repeat = setInterval(() => {
      clearTimeout(t);
      t = schedule();
    }, 8000);
    return () => { clearTimeout(t); clearInterval(repeat); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fightActive, paused]);
  const doStart = async () => {
    if (!chatId) return;
    setStarting(true);
    try {
      const r = await startBoss(chatId);
      if (!r.ok) { toast("вљ пёЏ " + (r.error ?? "РћС€РёР±РєР°")); return; }
      setSession(r.session);
      setBossHp(r.session.boss_max_hp);
      setBossMaxHp(r.session.boss_max_hp);
      setPlayerHp(100);
      setStamina(STAMINA_MAX);
      setHeavyCd(0);
      setBlocking(false);
      setWeakSpots([]);
      setPaused(false);
      setFightTimeLeft(null); // С‚Р°Р№РјРµСЂ РѕС‚РєР»СЋС‡С‘РЅ
      loadPotions();
    } catch (e: unknown) {
      toast("вљ пёЏ " + (e instanceof Error ? e.message : "РћС€РёР±РєР°"));
    } finally { setStarting(false); }
  };

  // в”Ђв”Ђ Use potion during fight в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  const doUsePotion = useCallback(async (item: InventoryItem) => {
    if (!chatId) return;
    setUsingPotion(item.id);
    try {
      const r = await consumePotion(chatId, item.id);
      if (r.success) {
        // Apply local HP heal for hp_potion
        if (item.key === "hp_potion" || item.key === "hp_potion_superior") {
          setPlayerHp(hp => Math.min(100, hp + 50));
          addFloat("+50 вќ¤пёЏ", 20, 60, "#22c55e");
        } else {
          addFloat("вљЎ " + item.name, 20, 60, "#a78bfa");
        }
        toast(r.message);
        loadPotions(); // refresh list (consumed one)
      } else {
        toast("вќЊ " + r.message);
      }
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "РћС€РёР±РєР°");
    } finally { setUsingPotion(null); }
  }, [chatId, addFloat, toast, loadPotions]);

  // в”Ђв”Ђ Attack backend в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  const doAttackBackend = useCallback(async (isCrit?: boolean) => {
    if (!chatId || attacking) return;
    if (fightTimeLeft != null && fightTimeLeft <= 0) {
      toast("вЏі Р’СЂРµРјСЏ Р±РѕСЏ РІС‹С€Р»Рѕ");
      loadStatus();
      return;
    }
    setAttacking(true);
    try {
      const r = await attackBoss(chatId);
      if (!r.ok) return;
      const dmg = isCrit ? Math.floor(r.damage_dealt * 1.5) : r.damage_dealt;
      setBossHp(r.boss_hp);
      if (typeof r.fight_time_left_seconds === "number") {
        setFightTimeLeft(r.fight_time_left_seconds);
      }
      addFloat(
        `${r.crit || isCrit ? "вљЎ РљР РРў! " : ""}в€’${fmt(dmg)}`,
        50 + (Math.random() - 0.5) * 30,
        30,
        r.crit || isCrit ? "#facc15" : "var(--accent)",
      );
      if (r.boss_defeated) {
        setSession(s => s ? { ...s, is_completed: 1 } : s);
        setFightTimeLeft(0);
        toast(`рџЏ† Р‘РѕСЃСЃ РїРѕРІРµСЂР¶РµРЅ! +${r.rewards?.mora ?? 0}рџЄ™ +${r.rewards?.xp ?? 0}вљЎ`);
        await loadStatus();
      }
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "РћС€РёР±РєР° Р°С‚Р°РєРё");
      loadStatus();
    }
    finally { setAttacking(false); }
  }, [chatId, attacking, addFloat, toast, loadStatus, fightTimeLeft]);

  // в”Ђв”Ђ Skill: Fast Attack в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  const doFast = async () => {
    if (!fightActive || stamina < SKILL_FAST_COST || attacking) return;
    setStamina(s => s - SKILL_FAST_COST);
    await doAttackBackend(false);
  };

  // в”Ђв”Ђ Skill: Heavy Blow в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  const doHeavy = async () => {
    if (!fightActive || stamina < SKILL_HEAVY_COST || heavyCd > 0 || attacking) return;
    setStamina(s => s - SKILL_HEAVY_COST);
    setHeavyCd(SKILL_HEAVY_CD);
    await doAttackBackend(true);
    await doAttackBackend(true);  // Two hits
  };

  // в”Ђв”Ђ Skill: Block в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  const doBlock = () => {
    if (!fightActive || stamina < SKILL_BLOCK_COST || blocking) return;
    setStamina(s => s - SKILL_BLOCK_COST);
    setBlocking(true);
    setTimeout(() => setBlocking(false), BLOCK_DURATION);
  };

  // в”Ђв”Ђ Weak spot click в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  const doClickWeakspot = async (wsId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setWeakSpots(w => w.filter(s => s.id !== wsId));
    addFloat("вљ пёЏ РЎР›РђР‘РћР• РњР•РЎРўРћ!", 50, 25, "#f97316");
    await doAttackBackend(true);
  };

  // в”Ђв”Ђ Render в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 size={32} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  const completed = session?.is_completed === 1 || playerHp <= 0;
  const canStart  = !session || completed;
  const dailyRemaining = Math.max(0, dailyLimit - dailyUsed);
  const fightTimeText = null; // С‚Р°Р№РјРµСЂ Р±РѕСЏ РѕС‚РєР»СЋС‡С‘РЅ

  const SLOT_EMOJI: Record<string, string> = { weapon: "вљ”пёЏ", armor: "рџ›ЎпёЏ", helmet: "рџЄ–", boots: "рџ‘ў", artifact: "рџ’Ћ" };

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "var(--bg-primary)" }}>
      {/* Header + Mode Tabs */}
      <div className="px-4 pt-safe pb-2 glass-heavy" style={{ borderBottom: "1px solid var(--border-accent)" }}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>вљ”пёЏ Р‘РѕСЃСЃ</h1>
            {mode === "solo" && progress && (
              <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                РњР°РєСЃ. СѓСЂРѕРІРµРЅСЊ: {progress.max_level} вЂў РџРѕРїС‹С‚РѕРє РѕСЃС‚Р°Р»РѕСЃСЊ: {dailyRemaining}/{dailyLimit}
              </p>
            )}
          </div>
          {mode === "solo" && (
            <div className="badge badge-accent text-xs px-3 py-1">
              РЈСЂ. {nextLevel}
            </div>
          )}
        </div>
        {/* Mode tabs */}
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => setMode("solo")}
            className="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all"
            style={{
              backgroundColor: mode === "solo" ? "var(--accent)" : "var(--bg-secondary)",
              color: mode === "solo" ? "#fff" : "var(--text-hint)",
            }}
          >
            рџ—ЎпёЏ РЎРѕР»Рѕ
          </button>
          <button
            onClick={() => setMode("couple")}
            className="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all"
            style={{
              backgroundColor: mode === "couple" ? "#e84393" : "var(--bg-secondary)",
              color: mode === "couple" ? "#fff" : "var(--text-hint)",
            }}
          >
            рџ’ћ РџР°СЂРЅС‹Р№
          </button>
        </div>
      </div>

      {/* Couple boss mode */}
      {mode === "couple" && (
        <CoupleBoss userId={_userId} chatId={chatId} />
      )}

      {/* Solo boss mode */}
      {mode === "solo" && <>

      {/* ── Купоны боя — блок вверху ── */}
      <div className="mx-4 mt-3">
        <div
          className="glass-card p-3 flex items-center gap-3 cursor-pointer active:scale-[0.98] transition-transform"
          onClick={() => setShowCouponModal(true)}
        >
          <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: bossCoupons > 0 ? "rgba(245,158,11,0.18)" : "rgba(239,68,68,0.15)" }}>
            <Ticket size={18} style={{ color: bossCoupons > 0 ? "#f59e0b" : "#f87171" }} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-semibold" style={{ color: "var(--text-hint)" }}>Купоны боя</p>
            <div className="flex items-center gap-0.5 mt-0.5">
              {Array.from({ length: 5 }).map((_, i) => (
                <span key={i} className="text-sm transition-all" style={{ opacity: i < bossCoupons ? 1 : 0.2 }}>🎫</span>
              ))}
              <span className="ml-1.5 text-xs font-bold tabular-nums" style={{ color: "var(--text-hint)" }}>
                {bossCoupons}/5
              </span>
            </div>
          </div>
          <div className="text-right shrink-0">
            <p className="text-[11px] font-semibold" style={{ color: "var(--text-hint)" }}>Дневной лимит</p>
            <p className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>
              {dailyUsed}/{dailyLimit} боёв
            </p>
          </div>
        </div>
      </div>

      {/* ── Модалька купонов ── */}
      {showCouponModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ backgroundColor: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}
          onClick={() => setShowCouponModal(false)}
        >
          <div
            className="glass-card w-full max-w-sm p-5 space-y-4"
            onClick={e => e.stopPropagation()}
          >
            {/* Заголовок */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Ticket size={18} style={{ color: "#f59e0b" }} />
                <p className="font-bold text-base" style={{ color: "var(--text-primary)" }}>Купоны боя</p>
              </div>
              <button onClick={() => setShowCouponModal(false)}
                className="w-7 h-7 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: "var(--bg-secondary)" }}>
                <X size={14} style={{ color: "var(--text-hint)" }} />
              </button>
            </div>

            {/* Иконки купонов */}
            <div className="flex justify-center gap-2 py-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i}
                  className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl transition-all"
                  style={{
                    backgroundColor: i < bossCoupons ? "rgba(245,158,11,0.18)" : "var(--bg-secondary)",
                    border: `1px solid ${i < bossCoupons ? "rgba(245,158,11,0.4)" : "var(--border)"}`,
                    opacity: i < bossCoupons ? 1 : 0.3,
                  }}
                >🎫</div>
              ))}
            </div>

            {/* Описание */}
            <div className="rounded-xl p-3" style={{ backgroundColor: "var(--bg-secondary)" }}>
              <p className="text-xs" style={{ color: "var(--text-hint)" }}>
                Купоны позволяют выйти за дневной лимит боёв с боссом.
                Максимум 5 купонов. Один купон регенерирует каждые 3 часа.
              </p>
            </div>

            {/* Кнопка покупки */}
            <button
              className="w-full py-3 rounded-xl font-bold text-sm btn-primary disabled:opacity-40 flex items-center justify-center gap-2"
              disabled={buyingCoupon || bossCoupons >= 5}
              onClick={async () => {
                if (!chatId) return;
                setBuyingCoupon(true);
                try {
                  const r = await buyBossCoupon(chatId);
                  if (r.ok) {
                    setBossCoupons(r.coupons);
                    toast("🎫 Купон куплен!", "success");
                  } else {
                    toast("⚠️ " + (r.error ?? "Ошибка"), "warning");
                  }
                } finally { setBuyingCoupon(false); }
              }}
            >
              {buyingCoupon
                ? <Loader2 size={16} className="animate-spin" />
                : bossCoupons >= 5
                ? "Купоны заполнены"
                : <>Купить купон — 7 💎</>}
            </button>
          </div>
        </div>
      )}

      {/* в”Ђв”Ђ No session / completed в”Ђв”Ђ */}
      {canStart && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-4">
          <div className="text-center space-y-3">
            <div className="text-8xl drop-shadow-lg animate-orb">{bossArt(nextLevel)}</div>
            <p className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>{bossName(nextLevel)}</p>
            <p className="text-sm" style={{ color: "var(--text-hint)" }}>
              HP: {fmt(7_500 + (nextLevel - 1) * 4_500)}
            </p>
            {session?.is_completed === 1 && (
              <p className="badge badge-success text-sm px-4 py-1">вњ… РџРѕР±РµР¶РґС‘РЅ СЃРµРіРѕРґРЅСЏ!</p>
            )}
            {playerHp <= 0 && !session?.is_completed && (
              <p className="badge badge-danger text-sm px-4 py-1">рџ’Ђ РўС‹ РїР°Р» РІ Р±РѕСЋ</p>
            )}
          </div>
          {session?.is_completed !== 1 && (
            <button
              onClick={doStart}
              disabled={starting}
              className="px-8 py-3.5 rounded-2xl text-base font-bold flex items-center gap-2 disabled:opacity-50 btn-primary"
            >
              {starting ? <Loader2 size={18} className="animate-spin" /> : <Swords size={18} />}
              {starting ? "Р’С‹Р·РѕРІ..." : "РќР°С‡Р°С‚СЊ Р±РёС‚РІСѓ"}
            </button>
          )}
          {session?.is_completed === 1 && (
            <button
              onClick={doStart}
              disabled={starting}
              className="px-8 py-3.5 rounded-2xl text-base font-bold flex items-center gap-2 disabled:opacity-50 btn-primary"
            >
              {starting ? <Loader2 size={18} className="animate-spin" /> : <Swords size={18} />}
              {starting ? "Р’С‹Р·РѕРІ..." : "РЎР»РµРґСѓСЋС‰РёР№ СѓСЂРѕРІРµРЅСЊ в†’"}
            </button>
          )}
        </div>
      )}

      {/* в”Ђв”Ђ Active fight в”Ђв”Ђ */}
      {!canStart && fightActive && (
        <div className="flex-1 flex flex-col gap-2.5 px-4 pt-3 pb-4 relative">

          {/* Pause overlay */}
          {paused && (
            <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-5 rounded-2xl glass-heavy">
              <p className="text-2xl font-bold" style={{ color: "#fff" }}>вЏёпёЏ РџР°СѓР·Р°</p>
              <button
                onClick={() => setPaused(false)}
                className="flex items-center gap-2 px-6 py-3 btn-primary rounded-2xl text-sm"
              >
                <Play size={16} /> РџСЂРѕРґРѕР»Р¶РёС‚СЊ
              </button>
              <button
                onClick={async () => {
                  setPaused(false);
                  if (chatId) {
                    try { await forfeitBoss(chatId); } catch {}
                  }
                  setPlayerHp(0);
                  toast("рџЏіпёЏ РўС‹ СЃРґР°Р»СЃСЏ...");
                  loadStatus();
                }}
                className="flex items-center gap-2 px-6 py-3 rounded-2xl font-semibold text-sm btn-danger"
              >
                <Flag size={16} /> РЎРґР°С‚СЊСЃСЏ
              </button>
            </div>
          )}

          {/* Boss info */}
          <div className={`glass-card p-4 ${telegraphing ? "animate-danger" : ""}`}>
            <div className="flex items-center gap-3">
              <div className="text-5xl relative shrink-0">
                {bossArt(session!.boss_level)}
                {/* Weak spots */}
                {weakSpots.map(ws => (
                  <button
                    key={ws.id}
                    onClick={e => doClickWeakspot(ws.id, e)}
                    className="absolute rounded-full border-2 border-yellow-400 animate-weakspot-ripple"
                    style={{
                      width: 28, height: 28,
                      left: `${ws.x}%`, top: `${ws.y}%`,
                      transform: "translate(-50%,-50%)",
                      backgroundColor: "#facc1540",
                    }}
                  />
                ))}
              </div>
              <div className="flex-1 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{bossName(session!.boss_level)}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs tabular-nums font-semibold" style={{ color: "var(--text-hint)" }}>
                      {fmt(bossHp)} / {fmt(bossMaxHp)}
                    </span>
                    <button
                      onClick={() => setPaused(true)}
                      className="p-1.5 rounded-lg glass-card-sm"
                      style={{ color: "var(--text-hint)" }}
                    >
                      <Pause size={14} />
                    </button>
                  </div>
                </div>
                <div className="progress-bar">
                  <div className="progress-bar-fill" style={{ width: `${Math.max(0, (bossHp / bossMaxHp) * 100)}%` }} />
                </div>
                <div className="flex items-center justify-between text-[11px]" style={{ color: "var(--text-hint)" }}>
                  <span>РџРѕРїС‹С‚РѕРє РѕСЃС‚Р°Р»РѕСЃСЊ: {dailyRemaining}/{dailyLimit}</span>
                </div>
                {/* Telegraph bar */}
                {telegraphing && (
                  <div className="space-y-0.5">
                    <p className="text-[11px] font-bold text-red-400 animate-pulse">вљ пёЏ РђРўРђРљРђ Р‘РћРЎРЎРђ вЂ” Р‘Р›РћРљ!</p>
                    <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "#ef444430" }}>
                      <div
                        className="h-full rounded-full transition-none"
                        style={{ width: `${telegraphPct}%`, backgroundColor: "#ef4444" }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Float damage texts */}
          <div className="relative h-8 pointer-events-none overflow-hidden">
            {floats.map(f => (
              <span
                key={f.id}
                className="absolute text-sm font-bold animate-reward-fly"
                style={{
                  left: `${f.x}%`,
                  top: `${f.y}%`,
                  color: f.color,
                  transform: "translate(-50%, -50%)",
                  textShadow: `0 0 8px ${f.color}`,
                } as React.CSSProperties}
              >
                {f.text}
              </span>
            ))}
          </div>

          {/* Player status вЂ” HP + Stamina */}
          <div className="glass-card p-3 space-y-2">
            <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-hint)" }}>
              <span>вќ¤пёЏ HP</span><span className="tabular-nums font-bold">{playerHp}/100</span>
            </div>
            <div className="progress-bar">
              <div className="h-full rounded-full transition-all duration-300"
                style={{ width: `${playerHp}%`, background: "linear-gradient(90deg, #22c55e, #4ade80)", boxShadow: "0 0 8px #22c55e55" }} />
            </div>

            <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-hint)" }}>
              <span className="animate-stamina">вљЎ Р’С‹РЅРѕСЃР»РёРІРѕСЃС‚СЊ</span>
              <span className="tabular-nums font-bold">{Math.round(stamina)} / {STAMINA_MAX}</span>
            </div>
            <div className="progress-bar">
              <div className="h-full rounded-full transition-all duration-500"
                style={{ width: `${(stamina / STAMINA_MAX) * 100}%`, background: "linear-gradient(90deg, #3b82f6, #60a5fa)", boxShadow: "0 0 8px #3b82f655" }} />
            </div>

            {blocking && (
              <p className="text-xs font-bold text-center animate-pulse" style={{ color: "#60a5fa" }}>
                рџ›ЎпёЏ Р‘Р»РѕРє Р°РєС‚РёРІРµРЅвЂ¦
              </p>
            )}
          </div>

          {/* в”Ђ Equipment strip вЂ” always visible в”Ђ */}
          {equipped.length > 0 && (
            <div className="flex gap-1.5 overflow-x-auto tab-scroll">
              {equipped.map(eq => (
                <div key={eq.id} className="glass-card-sm flex items-center gap-1.5 px-2.5 py-1.5 shrink-0"
                  style={{ fontSize: 11 }}>
                  <span>{SLOT_EMOJI[eq.slot ?? ""] ?? "рџ“¦"}</span>
                  <span className="font-semibold truncate max-w-[80px]" style={{
                    color: eq.rarity === "legendary" ? "#f59e0b" : eq.rarity === "rare" ? "#60a5fa" : "var(--text-secondary)",
                  }}>{eq.name}</span>
                  {eq.enhancement_level > 0 && <span style={{ color: "#22c55e" }}>+{eq.enhancement_level}</span>}
                </div>
              ))}
            </div>
          )}

          {/* Skills */}
          <div className="grid grid-cols-3 gap-2.5">
            {/* Fast attack */}
            <button
              onClick={doFast}
              disabled={stamina < SKILL_FAST_COST || attacking || paused}
              className="glass-card p-3 flex flex-col items-center gap-1.5 disabled:opacity-40 btn-press transition-transform active:scale-95"
            >
              <Sword size={24} style={{ color: "var(--accent)" }} />
              <span className="text-[11px] font-bold" style={{ color: "var(--text-primary)" }}>Р‘С‹СЃС‚СЂРѕ</span>
              <span className="text-[10px] font-semibold" style={{ color: "var(--text-hint)" }}>{SKILL_FAST_COST}вљЎ</span>
            </button>

            {/* Heavy blow */}
            <button
              onClick={doHeavy}
              disabled={stamina < SKILL_HEAVY_COST || heavyCd > 0 || attacking || paused}
              className="glass-card p-3 flex flex-col items-center gap-1.5 disabled:opacity-40 btn-press transition-transform active:scale-95"
            >
              <Swords size={24} style={{ color: heavyCd > 0 ? "var(--text-hint)" : "#f97316" }} />
              <span className="text-[11px] font-bold" style={{ color: "var(--text-primary)" }}>РЈРґР°СЂ</span>
              <span className="text-[10px] font-semibold" style={{ color: "var(--text-hint)" }}>
                {heavyCd > 0 ? `${(heavyCd / 1000).toFixed(1)}s` : `${SKILL_HEAVY_COST}вљЎ`}
              </span>
            </button>

            {/* Block */}
            <button
              onClick={doBlock}
              disabled={stamina < SKILL_BLOCK_COST || blocking || paused}
              className={`glass-card p-3 flex flex-col items-center gap-1.5 disabled:opacity-40 btn-press transition-transform active:scale-95 ${telegraphing ? "animate-accent-glow" : ""}`}
            >
              <Shield size={24} style={{ color: blocking ? "#60a5fa" : telegraphing ? "#facc15" : "var(--text-primary)" }} />
              <span className="text-[11px] font-bold" style={{ color: "var(--text-primary)" }}>Р‘Р»РѕРє</span>
              <span className="text-[10px] font-semibold" style={{ color: "var(--text-hint)" }}>
                {blocking ? "вњ“ Р‘Р›РћРљ" : `${SKILL_BLOCK_COST}вљЎ`}
              </span>
            </button>
          </div>

          {/* в”Ђ Potion quick-bar вЂ” ALWAYS visible в”Ђ */}
          <div className="glass-card p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="flex items-center gap-1.5 text-xs font-bold" style={{ color: "var(--text-primary)" }}>
                <FlaskConical size={14} style={{ color: "#a78bfa" }} /> Р—РµР»СЊСЏ
                <span className="badge badge-accent">{potions.length}</span>
              </span>
              <button onClick={() => setShowPotions(v => !v)} className="text-[11px] font-semibold" style={{ color: "var(--text-hint)" }}>
                {showPotions ? "РЎРІРµСЂРЅСѓС‚СЊ в–І" : "Р Р°Р·РІРµСЂРЅСѓС‚СЊ в–ј"}
              </button>
            </div>
            {/* Quick-use row (always visible: first 3 potions) */}
            {!showPotions && potions.length > 0 && (
              <div className="flex gap-2">
                {potions.slice(0, 3).map(p => (
                  <button
                    key={p.id}
                    disabled={usingPotion === p.id}
                    onClick={() => doUsePotion(p)}
                    className="flex-1 flex items-center justify-center gap-1 px-2 py-2 rounded-xl text-xs font-semibold disabled:opacity-50 btn-press"
                    style={{ background: "#a78bfa15", color: "#c4b5fd", border: "1px solid #a78bfa30" }}
                  >
                    {usingPotion === p.id ? <Loader2 size={12} className="animate-spin" /> : "рџ§Є"}
                    <span className="truncate">{p.name}</span>
                    {p.stack_count > 1 && <span className="opacity-60">Г—{p.stack_count}</span>}
                  </button>
                ))}
              </div>
            )}
            {/* Expanded view */}
            {showPotions && (
              potions.length === 0
                ? <p className="text-xs text-center py-2" style={{ color: "var(--text-hint)" }}>Р—РµР»СЊРё РЅРµ РЅР°Р№РґРµРЅС‹</p>
                : <div className="flex flex-wrap gap-2">
                    {potions.map(p => (
                      <button
                        key={p.id}
                        disabled={usingPotion === p.id}
                        onClick={() => doUsePotion(p)}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold disabled:opacity-50 btn-press"
                        style={{ background: "#a78bfa15", color: "#c4b5fd", border: "1px solid #a78bfa30" }}
                      >
                        {usingPotion === p.id
                          ? <Loader2 size={11} className="animate-spin" />
                          : "рџ§Є"}
                        {p.name}
                        {p.stack_count > 1 && <span style={{ color: "var(--text-hint)" }}>Г—{p.stack_count}</span>}
                      </button>
                    ))}
                  </div>
            )}
          </div>

          {/* Hits info */}
          <div className="flex gap-2 text-[11px] justify-end" style={{ color: "var(--text-hint)" }}>
            <span>РќР°РЅРµСЃРµРЅРѕ: {fmt(session!.boss_max_hp - bossHp)}</span>
            <span>В·</span>
            <span>РЈСЂРѕРЅ/СѓРґР°СЂ: ~50-150</span>
            {attacking && <Zap size={11} className="animate-spin" style={{ color: "var(--accent)" }} />}
          </div>
        </div>
      )}
      </>}
    </div>
  );
}

