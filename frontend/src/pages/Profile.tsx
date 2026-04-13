/* ──────────────────────────────────────────────────────────────
   Profile.tsx — Полный профиль пользователя
   Показывает ВСЕ поля из /api/user_data Django-бэкенда
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import {
  Coins, Star, Heart, PawPrint, TrendingUp, Shield, Swords,
  MessageSquare, Gem, CalendarCheck, CheckCircle2, Flame,
  ArrowUpCircle, ArrowDownCircle, Compass, Loader2, ScrollText, History,
} from "lucide-react";
import {
  fetchUserData, fetchCheckinStatus, doCheckin, petWalk,
  familyDeposit, familyWithdraw, fetchFamilyLog,
  fetchExpeditions, startExpedition, collectExpedition,
  fetchWalletHistory,
} from "../lib/api";
import type {
  UserData, BondInfo, CheckinStatus,
  FamilyLogEntry, ExpeditionsResponse, WalletHistoryEntry,
} from "../types";
import { useAppContext } from "../AppContext";

interface Props {
  userId: number;
  chatId: number;
}

const RANK_COLOR: Record<string, string> = {
  developer:    "#ff4757",
  owner:        "#f59e0b",
  co_owner:     "#a855f7",
  admin_senior: "#e84393",
  admin_junior: "#3b82f6",
  admin:        "#ffa502",
  moderator:    "#2ed573",
  vip:          "#7bed9f",
  user:         "var(--text-hint)",
};
const RANK_LABEL: Record<string, string> = {
  developer:    "Разработчик",
  owner:        "Владелец",
  co_owner:     "Совладелец",
  admin_senior: "Стар. Администратор",
  admin_junior: "Мл. Администратор",
  admin:        "Администратор",
  moderator:    "Модератор",
  vip:          "VIP",
  user:         "Участник",
};

export default function Profile({ chatId }: Props) {
  const { userData: ctxUserData, refreshUserData } = useAppContext();
  const [data, setData]             = useState<UserData | null>(ctxUserData);
  const [error, setError]           = useState("");
  const [checkin, setCheckin]       = useState<CheckinStatus | null>(null);
  const [checkinLoading, setCiLoad] = useState(false);
  const [toast, setToast]           = useState<string | null>(null);
  const [petLoading, setPetLoading] = useState(false);

  // Family wallet
  const [familyAmount, setFamilyAmt]   = useState("");
  const [familyBusy, setFamilyBusy]    = useState(false);
  const [familyLog, setFamilyLog]      = useState<FamilyLogEntry[]>([]);
  const [familyLogOpen, setFLogOpen]   = useState(false);

  // Wallet history
  const [walletHist, setWalletHist]   = useState<WalletHistoryEntry[]>([]);
  const [walletHistOpen, setWHistOpen] = useState(false);
  const [walletHistLoading, setWHistLoad] = useState(false);

  // Expeditions
  const [expData, setExpData]     = useState<ExpeditionsResponse | null>(null);
  const [expBusy, setExpBusy]     = useState(false);
  const [expLoading, setExpLoad]  = useState(false);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }, []);

  useEffect(() => {
    fetchUserData(chatId)
      .then(setData)
      .catch((e: Error) => setError(e.message));
    if (chatId) {
      fetchCheckinStatus(chatId)
        .then(setCheckin)
        .catch(() => { /* не критично */ });
    }
  }, [chatId]);

  const handleCheckin = useCallback(async () => {
    if (checkinLoading || checkin?.today_done || !chatId) return;
    setCiLoad(true);
    try {
      const res = await doCheckin(chatId);
      if (res.already_done) {
        showToast("Вы уже получили ежедневную награду сегодня ✅");
        setCheckin(prev => prev ? { ...prev, today_done: true } : prev);
      } else if (res.ok) {
        let msg = `+${res.mora?.toLocaleString("ru-RU")} 🪙  Стрик: ${res.streak} дн. 🔥`;
        if (res.vip_bonus) msg += " (+VIP бонус)";
        if (res.is_checkpoint) msg += " ✨ Чекпоинт!";
        if (res.free_gacha) msg += " 🎁 Бесплатная гача!";
        showToast(msg);
        setCheckin(prev => prev ? { ...prev, today_done: true, streak: res.streak, total_days: res.total_days } : prev);
        // обновляем баланс в профиле
        setData(prev => prev && res.mora ? { ...prev, balance: prev.balance + res.mora } : prev);
        refreshUserData(); // синхронизируем глобальный контекст
      } else {
        showToast(res.error ?? "Ошибка чекина");
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setCiLoad(false);
    }
  }, [chatId, checkin, checkinLoading, showToast]);

  const handlePetWalk = useCallback(async () => {
    if (petLoading || !chatId || !data?.pet || data.pet.on_walk || data.pet.fatigue >= 100) return;
    setPetLoading(true);
    try {
      const res = await petWalk(chatId);
      if (res.ok) {
        showToast(`${res.pet_emoji} ${res.pet_name} отправлен на прогулку! (${res.walk_mins} мин)`);
        setData(prev => prev && prev.pet ? { ...prev, pet: { ...prev.pet, on_walk: true, walk_mins_left: res.walk_mins ?? 30 } } : prev);
      } else {
        showToast(res.error ?? "Ошибка");
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setPetLoading(false);
    }
  }, [chatId, data, petLoading, showToast]);

  // Load expeditions
  const loadExpeditions = useCallback(() => {
    if (!chatId) return;
    setExpLoad(true);
    fetchExpeditions(chatId)
      .then(setExpData)
      .catch(() => {})
      .finally(() => setExpLoad(false));
  }, [chatId]);

  useEffect(() => { loadExpeditions(); }, [loadExpeditions]);

  const handleStartExpedition = useCallback(async (optionKey: string) => {
    if (expBusy || !chatId) return;
    setExpBusy(true);
    try {
      const r = await startExpedition(chatId, optionKey);
      if (r.ok) {
        showToast(`🧭 Экспедиция начата! (${r.mins ?? "?"} мин)`);
        loadExpeditions();
      } else {
        showToast(r.error ?? "Ошибка");
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setExpBusy(false);
    }
  }, [chatId, expBusy, showToast, loadExpeditions]);

  const handleCollectExpedition = useCallback(async () => {
    if (expBusy || !chatId) return;
    setExpBusy(true);
    try {
      const r = await collectExpedition(chatId);
      if (r.ok) {
        let msg = "🎉 Экспедиция завершена!";
        if (r.mora) msg += ` +${r.mora} 🪙`;
        if (r.xp) msg += ` +${r.xp} XP`;
        if (r.items?.length) msg += ` 📦 ${r.items.join(", ")}`;
        showToast(msg);
        loadExpeditions();
        // Refresh profile
        fetchUserData(chatId).then(setData).catch(() => {});
      } else {
        showToast(r.error ?? "Ошибка");
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setExpBusy(false);
    }
  }, [chatId, expBusy, showToast, loadExpeditions]);

  // Family wallet handlers
  const handleFamilyDeposit = useCallback(async () => {
    if (familyBusy || !chatId || !familyAmount) return;
    setFamilyBusy(true);
    try {
      const r = await familyDeposit(chatId, Math.round(Number(familyAmount)));
      if (r.ok) {
        showToast(`✅ Внесено в семейный кошелёк! Личный: ${r.personal} · Семейный: ${r.family}`);
        setData(prev => prev ? { ...prev, balance: r.personal, family_balance: r.family } : prev);
        setFamilyAmt("");
      } else {
        showToast(r.error ?? "Ошибка");
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setFamilyBusy(false);
    }
  }, [chatId, familyAmount, familyBusy, showToast]);

  const handleFamilyWithdraw = useCallback(async () => {
    if (familyBusy || !chatId || !familyAmount) return;
    setFamilyBusy(true);
    try {
      const r = await familyWithdraw(chatId, Math.round(Number(familyAmount)));
      if (r.ok) {
        showToast(`✅ Снято из семейного кошелька! Личный: ${r.personal} · Семейный: ${r.family}`);
        setData(prev => prev ? { ...prev, balance: r.personal, family_balance: r.family } : prev);
        setFamilyAmt("");
      } else {
        showToast(r.error ?? "Ошибка");
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setFamilyBusy(false);
    }
  }, [chatId, familyAmount, familyBusy, showToast]);

  const handleLoadFamilyLog = useCallback(async () => {
    if (!chatId) return;
    setFLogOpen(!familyLogOpen);
    if (!familyLogOpen) {
      fetchFamilyLog(chatId)
        .then(r => setFamilyLog(r.entries ?? []))
        .catch(() => {});
    }
  }, [chatId, familyLogOpen]);

  const handleWalletHistory = useCallback(async () => {
    if (!chatId) return;
    const nextOpen = !walletHistOpen;
    setWHistOpen(nextOpen);
    if (nextOpen && walletHist.length === 0) {
      setWHistLoad(true);
      fetchWalletHistory(chatId)
        .then(r => setWalletHist(r.history ?? []))
        .catch(() => {})
        .finally(() => setWHistLoad(false));
    }
  }, [chatId, walletHistOpen, walletHist.length]);

  if (error) return <ErrorBox message={error} />;
  if (!data)  return <ProfileSkeleton />;

  const xpPct = data.xp_max > 0 ? Math.min(100, Math.round((data.xp / data.xp_max) * 100)) : 0;
  const rankColor = RANK_COLOR[data.rank] ?? RANK_COLOR.user;
  const rankLabel = RANK_LABEL[data.rank] ?? data.rank;

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-2">

      {/* ── Шапка — Hero Card ──────────────────────────────────── */}
      <header className="glass-hero rounded-2xl p-5 flex items-center gap-4">
        <div
          className="w-16 h-16 rounded-2xl flex items-center justify-center text-2xl font-bold shrink-0 overflow-hidden"
          style={{
            background: `linear-gradient(135deg, var(--accent-soft), color-mix(in srgb, var(--accent) 8%, var(--bg-primary)))`,
            border: "2px solid var(--border-accent)",
            color: "var(--accent)",
          }}
        >
          {data.avatar_url
            ? <img src={data.avatar_url} alt={data.name} className="w-full h-full object-cover" />
            : data.name.charAt(0).toUpperCase()
          }
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap">
            {data.crystal_cosmetics_owned?.includes("neon_prefix") && (
              <span className="neon-prefix text-sm shrink-0">◈</span>
            )}
            <h1 className={`text-lg font-bold truncate max-w-[160px] ${data.has_rainbow_title ? "rainbow-text" : ""}`}>{data.name}</h1>
            {data.vip && <VipBadge />}
            {data.is_dev && (
              <span className="badge badge-danger">DEV</span>
            )}
          </div>
          {data.custom_title && (
            <p className={`text-xs truncate mt-0.5 ${data.has_rainbow_title ? "rainbow-text" : ""}`}
               style={data.has_rainbow_title ? undefined : { color: "var(--accent)" }}>
              {data.custom_title}
            </p>
          )}
          {data.chat_role && (
            <p className="text-xs truncate" style={{ color: "#a29bfe" }}>{data.chat_role}</p>
          )}
          <div className="flex items-center gap-1.5 mt-1.5">
            <span className="badge" style={{ background: `${rankColor}20`, color: rankColor }}>{rankLabel}</span>
            <span className="text-[11px]" style={{ color: "var(--text-hint)" }}>Ур. {data.level}</span>
          </div>
        </div>
      </header>

      {/* ── Bio ────────────────────────────────────────────────── */}
      {data.bio && (
        <p className="text-sm px-1" style={{ color: "var(--text-hint)" }}>{data.bio}</p>
      )}

      {/* ── XP прогресс ────────────────────────────────────────── */}
      <Card>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 text-sm">
            <Star size={15} style={{ color: "var(--accent)" }} />
            <span className="font-medium">Опыт</span>
          </div>
          <span className="text-xs tabular-nums" style={{ color: "var(--text-hint)" }}>
            {fmt(data.xp)} / {fmt(data.xp_max)} XP
          </span>
        </div>
        <div className="progress-bar">
          <div className="progress-bar-fill" style={{ width: `${xpPct}%` }} />
        </div>
        <p className="text-[11px] mt-1.5" style={{ color: "var(--text-hint)" }}>
          {xpPct}% до уровня {data.level + 1}
        </p>
      </Card>

      {/* ── Основные валюты ────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard icon={<Coins size={18} />} label="Мора"       value={fmt(data.balance)}  color="#f59e0b" />
        <StatCard icon={<Gem   size={18} />} label="Кристаллы" value={fmt(data.crystals)} color="#a855f7" />
      </div>

      {/* ── Активность ─────────────────────────────────────────── */}
      <Card>
        <SectionTitle icon={<MessageSquare size={15} />} label="Активность" />
        <div className="grid grid-cols-3 gap-1 mt-2">
          <MiniStat label="Сообщений"  value={fmt(data.message_count)} />
          <MiniStat label="Стрик"      value={`${data.streak} дн.`} />
          <MiniStat label="Варны"      value={`${data.warns} / 4`} accent={data.warns > 0} />
        </div>
      </Card>

      {/* ── RPG боёвка (если не дефолт) ────────────────────────── */}
      {(data.rpg.hp !== 100 || data.rpg.atk !== 50) && (
        <Card>
          <SectionTitle icon={<Swords size={15} />} label="Боевые характеристики" />
          <div className="grid grid-cols-4 gap-1 mt-2">
            <MiniStat label="HP"   value={String(data.rpg.hp)} />
            <MiniStat label="ATK"  value={String(data.rpg.atk)} color="#ef4444" />
            <MiniStat label="DEF"  value={String(data.rpg.def)} color="#3b82f6" />
            <MiniStat label="Крит" value={`${Math.round(data.rpg.crit * 100)}%`} color="#f59e0b" />
          </div>
        </Card>
      )}

      {/* ── Питомец ────────────────────────────────────────────── */}
      {data.pet && (
        <Card>
          <SectionTitle icon={<PawPrint size={15} />} label="Питомец" />
          <div className="flex items-center justify-between mt-2">
            <div className="flex items-center gap-2">
              <span className="text-2xl">{data.pet.emoji}</span>
              <div>
                <p className="text-sm font-medium">{data.pet.name}</p>
                <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                  {data.pet.type}{data.pet.color_name ? ` · ${data.pet.color_name}` : ""}
                </p>
              </div>
            </div>
            <div className="text-right">
              {data.pet.on_walk
                ? <p className="text-[11px]" style={{ color: "#22c55e" }}>На прогулке · {data.pet.walk_mins_left} мин</p>
                : <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>Усталость: {data.pet.fatigue}%</p>
              }
            </div>
          </div>
          {/* Кнопки действий */}
          <div className="flex gap-2 mt-3">
            <button
              onClick={handlePetWalk}
              disabled={petLoading || data.pet.on_walk || data.pet.fatigue >= 100}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-40"
              style={{ backgroundColor: "var(--accent)", color: "#fff" }}
            >
              🐾 {data.pet.on_walk ? "На прогулке..." : petLoading ? "..." : "Прогулка"}
            </button>
          </div>
          {data.pet.fatigue >= 100 && !data.pet.on_walk && (
            <p className="text-[10px] mt-1.5 text-center" style={{ color: "#ef4444" }}>
              Питомец устал — покормите его в магазине 🍖
            </p>
          )}
        </Card>
      )}

      {/* ── Экспедиции ─────────────────────────────────────────── */}
      {data.pet && (
        <Card>
          <SectionTitle icon={<Compass size={15} />} label="Экспедиции" />
          {expLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 size={18} className="animate-spin" style={{ color: "var(--text-hint)" }} />
            </div>
          ) : expData?.active ? (
            <div className="mt-2 space-y-2">
              <div className="rounded-lg p-2.5" style={{ backgroundColor: "var(--bg-primary)" }}>
                <p className="text-sm font-medium">🧭 {expData.active.label}</p>
                <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                  {expData.active.finished
                    ? "✅ Завершена — можно собрать награду!"
                    : `⏳ Осталось: ${expData.active.mins_left} мин`}
                </p>
              </div>
              {expData.active.finished && (
                <button
                  onClick={handleCollectExpedition}
                  disabled={expBusy}
                  className="w-full py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-opacity disabled:opacity-40"
                  style={{ backgroundColor: "#22c55e", color: "#fff" }}
                >
                  {expBusy ? <Loader2 size={12} className="animate-spin" /> : "🎁 Забрать награду"}
                </button>
              )}
              {expData.partner_active && (
                <div className="rounded-lg p-2.5" style={{ backgroundColor: "var(--bg-primary)" }}>
                  <p className="text-sm font-medium">👫 {expData.partner_active.label}</p>
                  <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                    {expData.partner_active.finished
                      ? "✅ Завершена"
                      : `⏳ Осталось: ${expData.partner_active.mins_left} мин`}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="mt-2 space-y-1.5">
              {expData?.partner_active && (
                <div className="rounded-lg p-2.5 mb-2" style={{ backgroundColor: "var(--bg-primary)" }}>
                  <p className="text-sm font-medium">👫 {expData.partner_active.label}</p>
                  <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                    {expData.partner_active.finished
                      ? "✅ Завершена"
                      : `⏳ Осталось: ${expData.partner_active.mins_left} мин`}
                  </p>
                </div>
              )}
              {(expData?.options ?? []).length === 0 ? (
                <p className="text-[11px] text-center py-2" style={{ color: "var(--text-hint)" }}>
                  Нет доступных экспедиций
                </p>
              ) : (
                (expData?.options ?? []).map(opt => (
                  <div key={opt.key} className="flex items-center justify-between rounded-lg p-2"
                    style={{ backgroundColor: "var(--bg-primary)" }}>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{opt.label}</p>
                      <p className="text-[10px]" style={{ color: "var(--text-hint)" }}>
                        {opt.duration_min} мин · {opt.rewards_desc}
                      </p>
                    </div>
                    <button
                      onClick={() => handleStartExpedition(opt.key)}
                      disabled={expBusy}
                      className="shrink-0 ml-2 px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-opacity disabled:opacity-40"
                      style={{ backgroundColor: "var(--accent)", color: "#fff" }}
                    >
                      {expBusy ? "..." : opt.cost > 0 ? `${fmt(opt.cost)} 🪙` : "Бесплатно"}
                    </button>
                  </div>
                ))
              )}
            </div>
          )}
        </Card>
      )}

      {/* ── Партнёр + Семейный кошелёк ─────────────────────────── */}
      {data.has_partner && data.partner_name && (
        <Card>
          <SectionTitle icon={<Heart size={15} style={{ color: "#e84393" }} />} label="Партнёр" />
          <div className="flex items-center justify-between mt-2">
            <p className="text-sm font-medium">{data.partner_name}</p>
            <div className="text-right text-[11px]" style={{ color: "var(--text-hint)" }}>
              <p>Семейный счёт</p>
              <p className="font-semibold" style={{ color: "var(--accent)" }}>{fmt(data.family_balance)} 🪙</p>
            </div>
          </div>
          {/* Family wallet controls */}
          <div className="mt-3 space-y-2">
            <div className="flex gap-2">
              <input
                type="number"
                value={familyAmount}
                onChange={e => setFamilyAmt(e.target.value)}
                placeholder="Сумма"
                min="1"
                step="1"
                className="flex-1 rounded-lg px-2.5 py-1.5 text-sm bg-transparent outline-none"
                style={{ border: "1px solid var(--border)", color: "var(--text-primary)" }}
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleFamilyDeposit}
                disabled={familyBusy || !familyAmount}
                className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-40"
                style={{ backgroundColor: "#22c55e", color: "#fff" }}
              >
                {familyBusy ? <Loader2 size={11} className="animate-spin" /> : <><ArrowUpCircle size={12} /> Внести</>}
              </button>
              <button
                onClick={handleFamilyWithdraw}
                disabled={familyBusy || !familyAmount}
                className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-40"
                style={{ backgroundColor: "#ef4444", color: "#fff" }}
              >
                {familyBusy ? <Loader2 size={11} className="animate-spin" /> : <><ArrowDownCircle size={12} /> Снять</>}
              </button>
            </div>
            <button
              onClick={handleLoadFamilyLog}
              className="w-full flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs font-medium transition-opacity"
              style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-hint)" }}
            >
              <ScrollText size={12} /> {familyLogOpen ? "Скрыть историю" : "История операций"}
            </button>
            {familyLogOpen && familyLog.length > 0 && (
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {familyLog.map((e, i) => (
                  <div key={i} className="flex justify-between items-center text-[11px] py-1"
                    style={{ borderBottom: "1px solid var(--border)" }}>
                    <span className="truncate flex-1">{e.description}</span>
                    <span className="tabular-nums shrink-0 ml-2 font-medium"
                      style={{ color: e.amount > 0 ? "#22c55e" : "#ef4444" }}>
                      {e.amount > 0 ? "+" : ""}{fmt(e.amount)}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {familyLogOpen && familyLog.length === 0 && (
              <p className="text-[11px] text-center" style={{ color: "var(--text-hint)" }}>Нет операций</p>
            )}
          </div>
        </Card>
      )}

      {/* ── Кристальные предметы ───────────────────────────────── */}
      {(data.transfer_passes > 0 || data.enhancement_stones > 0 || data.guarantee_scrolls > 0) && (
        <Card>
          <SectionTitle icon={<Shield size={15} />} label="Кристальные предметы" />
          <div className="grid grid-cols-3 gap-1 mt-2">
            {data.transfer_passes  > 0 && <MiniStat label="🎫 Пропуска" value={String(data.transfer_passes)} />}
            {data.enhancement_stones > 0 && <MiniStat label="⚒️ Камни"   value={String(data.enhancement_stones)} />}
            {data.guarantee_scrolls > 0 && <MiniStat label="📜 Свитки"  value={String(data.guarantee_scrolls)} />}
          </div>
        </Card>
      )}

      {/* ── Облигации ──────────────────────────────────────────── */}
      {data.bonds.length > 0 && (
        <Card>
          <SectionTitle icon={<TrendingUp size={15} />} label="Облигации" />
          <div className="space-y-1.5 mt-2">
            {data.bonds.map((b: BondInfo) => (
              <div key={b.name} className="flex justify-between items-center text-sm">
                <span className="truncate">{b.name} ×{b.amount}</span>
                <span className="tabular-nums shrink-0 ml-2" style={{ color: "var(--text-hint)" }}>
                  {fmt(b.value)} 🪙
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {data.pity > 0 && (
        <p className="text-[11px] text-center" style={{ color: "var(--text-hint)" }}>
          Пити: {data.pity} роллов без legendary
        </p>
      )}

      {/* ── Чекин ─────────────────────────────────────────────── */}
      {chatId !== 0 && (() => {
        const streak = checkin?.streak ?? data.streak;
        const dayInWeek = streak % 7;            // 0..6
        const nextMilestone = 7 - dayInWeek;     // days until 7-day bonus
        const milestonePct = (dayInWeek / 7) * 100;
        const DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

        return (
          <div className="glass-hero p-4 space-y-3">
            {/* Title row */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${checkin?.today_done ? "" : "animate-claim-glow"}`}
                  style={{ background: checkin?.today_done ? "#22c55e22" : "linear-gradient(135deg, #f59e0b33, #ef444433)" }}>
                  <Flame size={18} style={{ color: checkin?.today_done ? "#22c55e" : "#f59e0b" }} />
                </div>
                <div>
                  <p className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>
                    Ежедневная награда
                  </p>
                  <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                    Стрик: <span className="font-bold" style={{ color: "#f59e0b" }}>{streak} дн.</span>
                    {streak >= 7 && " 🔥"}
                  </p>
                </div>
              </div>
              <button
                onClick={handleCheckin}
                disabled={checkinLoading || !!checkin?.today_done}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-bold transition-all disabled:opacity-40 ${checkin?.today_done ? "" : "btn-primary animate-streak-pop"}`}
                style={checkin?.today_done ? { background: "#22c55e22", color: "#22c55e" } : undefined}
              >
                {checkin?.today_done
                  ? <><CheckCircle2 size={14} /> Готово</>
                  : <><CalendarCheck size={14} /> {checkinLoading ? "..." : "Отметиться"}</>}
              </button>
            </div>

            {/* 7-day streak calendar */}
            <div className="grid grid-cols-7 gap-1.5">
              {DAYS.map((d, i) => {
                const done = i < dayInWeek;
                const isToday = i === dayInWeek;
                return (
                  <div key={d}
                    className={`flex flex-col items-center gap-0.5 py-1.5 rounded-lg transition-all ${done ? "animate-streak-pop" : ""}`}
                    style={{
                      background: done ? "#22c55e18" : isToday ? "var(--accent-soft)" : "var(--bg-elevated)",
                      border: isToday ? "1.5px solid var(--accent)" : "1px solid transparent",
                    }}>
                    <span className="text-[10px] font-semibold" style={{ color: done ? "#22c55e" : isToday ? "var(--accent)" : "var(--text-hint)" }}>
                      {d}
                    </span>
                    <span className="text-xs">
                      {done ? "✅" : isToday ? "🔥" : "·"}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Milestone progress */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px]" style={{ color: "var(--text-hint)" }}>
                <span>До бонуса × 7:</span>
                <span className="font-bold" style={{ color: milestonePct >= 85 ? "#f59e0b" : "var(--text-secondary)" }}>
                  {nextMilestone === 7 ? "✨ Сегодня!" : `${nextMilestone} дн.`}
                </span>
              </div>
              <div className="progress-bar">
                <div className="progress-bar-fill" style={{ width: `${milestonePct}%` }} />
              </div>
            </div>

            {/* Total days */}
            <p className="text-[10px] text-center" style={{ color: "var(--text-hint)" }}>
              Всего отмечено: {checkin?.total_days ?? 0} дн.
            </p>
          </div>
        );
      })()}

      {/* ── История транзакций ────────────────────────────────── */}
      {chatId !== 0 && (
        <Card>
          <button
            onClick={handleWalletHistory}
            className="w-full flex items-center justify-between"
          >
            <SectionTitle icon={<History size={15} />} label="История транзакций" />
            <span className="text-xs" style={{ color: "var(--text-hint)" }}>
              {walletHistOpen ? "Скрыть" : "Показать"}
            </span>
          </button>
          {walletHistOpen && (
            <div className="mt-2">
              {walletHistLoading ? (
                <div className="space-y-1 animate-pulse">
                  {Array.from({length: 4}).map((_, i) => (
                    <div key={i} className="skeleton h-8 rounded-lg" />
                  ))}
                </div>
              ) : walletHist.length === 0 ? (
                <p className="text-[11px] text-center py-2" style={{ color: "var(--text-hint)" }}>
                  Нет транзакций за последние 30 дней
                </p>
              ) : (
                <div className="space-y-0.5 max-h-52 overflow-y-auto">
                  {walletHist.map((entry, i) => (
                    <div key={i} className="flex justify-between items-center py-1.5 px-1 text-[11px]"
                      style={{ borderBottom: "1px solid var(--border)" }}>
                      <div className="flex-1 min-w-0">
                        <p className="truncate" style={{ color: "var(--text-primary)" }}>{entry.description}</p>
                        <p style={{ color: "var(--text-hint)" }}>{entry.ts}</p>
                      </div>
                      <span className="shrink-0 ml-2 font-semibold tabular-nums"
                        style={{ color: entry.amount >= 0 ? "#22c55e" : "#ef4444" }}>
                        {entry.amount >= 0 ? "+" : ""}{entry.amount.toLocaleString("ru-RU")} 🪙
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {/* ── Тост ──────────────────────────────────────────────── */}
      {toast && (
        <div
          className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-[90vw] px-4 py-2.5 rounded-xl text-sm font-medium shadow-lg pointer-events-none"
          style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--accent)" }}
        >
          {toast}
        </div>
      )}

    </div>
  );
}

/* ── Вспомогательные компоненты ───────────────────────────────── */

function VipBadge() {
  return (
    <span className="badge badge-gold">VIP</span>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="glass-card p-4">
      {children}
    </div>
  );
}

function SectionTitle({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm font-semibold">
      <span style={{ color: "var(--accent)" }}>{icon}</span>
      {label}
    </div>
  );
}

function StatCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string; color: string }) {
  return (
    <div className="glass-card p-4 flex flex-col gap-2">
      <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-hint)" }}>
        <span className="p-1.5 rounded-lg" style={{ backgroundColor: `${color}15`, color }}>{icon}</span>
        <span className="font-medium">{label}</span>
      </div>
      <span className="text-2xl font-extrabold tabular-nums stat-value">{value}</span>
    </div>
  );
}

function MiniStat({ label, value, color, accent }: { label: string; value: string; color?: string; accent?: boolean }) {
  return (
    <div className="rounded-lg p-2 text-center" style={{ backgroundColor: "var(--bg-primary)" }}>
      <p className="text-xs font-bold tabular-nums"
        style={{ color: accent ? "#ef4444" : (color ?? "var(--text-primary)") }}>
        {value}
      </p>
      <p className="text-[10px] mt-0.5 leading-tight" style={{ color: "var(--text-hint)" }}>{label}</p>
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
      <p className="font-medium">Ошибка загрузки профиля</p>
      <p className="text-sm mt-1 break-all">{message}</p>
    </div>
  );
}

function ProfileSkeleton() {
  return (
    <div className="p-4 space-y-3 animate-pulse">
      <div className="rounded-2xl p-4 flex items-center gap-3" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <div className="skeleton w-14 h-14 rounded-full" />
        <div className="space-y-2 flex-1">
          <div className="skeleton h-4 w-32 rounded" />
          <div className="skeleton h-3 w-20 rounded" />
        </div>
      </div>
      <div className="skeleton h-16 rounded-xl" />
      <div className="grid grid-cols-2 gap-2">
        <div className="skeleton h-20 rounded-xl" />
        <div className="skeleton h-20 rounded-xl" />
      </div>
      <div className="skeleton h-20 rounded-xl" />
    </div>
  );
}

function fmt(n: number): string {
  return (n ?? 0).toLocaleString("ru-RU");
}
