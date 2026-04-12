/* ──────────────────────────────────────────────────────────────
   Quests.tsx — Задание дня
   GET /api/quest + POST /api/quest/reroll
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { ScrollText, RefreshCw, CheckCircle2, Loader2, AlertCircle } from "lucide-react";
import { fetchQuest, rerollQuest } from "../lib/api";
import type { QuestData, QuestInfo } from "../types";

interface Props {
  userId: number;
  chatId: number;
}

/* Иконки/цвета по типу задания */
const QUEST_TYPE_LABEL: Record<string, string> = {
  messages:     "💬 Написать сообщений",
  checkin:      "📅 Чекины подряд",
  gacha:        "🎲 Прокрутить гачу",
  boss:         "⚔️ Атаковать босса",
  expedition:   "🗺️ Экспедиций",
  transfer:     "💸 Переводов",
  casino:       "🎰 Игр в казино",
  bond:         "📈 Купить облигации",
  pet_walk:     "🐾 Прогулок питомца",
};

function questTypeLabel(type: string): string {
  return QUEST_TYPE_LABEL[type] ?? `📋 ${type}`;
}

export default function Quests({ chatId }: Props) {
  const [data, setData]           = useState<QuestData | null>(null);
  const [error, setError]         = useState("");
  const [rerolling, setRerolling] = useState(false);
  const [toast, setToast]         = useState<string | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }, []);

  const loadQuest = useCallback(() => {
    setError("");
    fetchQuest(chatId)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [chatId]);

  useEffect(() => { loadQuest(); }, [loadQuest]);

  const handleReroll = useCallback(async () => {
    if (rerolling || data?.quest == null) return;
    setRerolling(true);
    try {
      const res = await rerollQuest(chatId);
      setData(prev => prev ? { ...prev, quest: res.quest, progress: 0, completed: false, rewarded: false } : prev);
      const costMsg = res.used_coupon
        ? "Задание заменено (купон использован)!"
        : `Задание заменено. Списано: ${res.cost.toLocaleString("ru-RU")} 🪙`;
      showToast(costMsg);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Ошибка реролла");
    } finally {
      setRerolling(false);
    }
  }, [chatId, data, rerolling, showToast]);

  /* ── Спецслучай: chatId = 0 ── */
  if (!chatId) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3 p-6 text-center" style={{ color: "var(--text-hint)" }}>
        <AlertCircle size={40} strokeWidth={1.2} />
        <p className="text-sm">Откройте Mini App из чата группы, чтобы посмотреть задания.</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
        <AlertCircle size={32} className="mx-auto mb-2" />
        <p className="font-medium">Ошибка</p>
        <p className="text-sm mt-1 break-all">{error}</p>
        <button onClick={loadQuest} className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}>
          Попробовать снова
        </button>
      </div>
    );
  }

  if (!data) return <QuestSkeleton />;

  const quest = data.quest;
  const pct = quest.goal > 0 ? Math.min(100, Math.round((data.progress / quest.goal) * 100)) : 0;

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-2">

      <h2 className="text-lg font-bold flex items-center gap-2">
        <ScrollText size={20} style={{ color: "var(--accent)" }} />
        Задание дня
      </h2>

      {/* ── Основная карточка ── */}
      <div
        className="rounded-2xl p-4 space-y-3"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        {/* Статус */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
            style={{
              backgroundColor: data.completed ? "#22c55e22" : "var(--bg-primary)",
              color: data.completed ? "#22c55e" : "var(--text-hint)",
            }}>
            {data.completed ? "✅ Выполнено" : "В процессе"}
          </span>
          <span className="text-xs tabular-nums" style={{ color: "var(--text-hint)" }}>
            {data.today}
          </span>
        </div>

        {/* Тип + описание */}
        <div>
          <p className="text-xs font-medium mb-0.5" style={{ color: "var(--accent)" }}>
            {questTypeLabel(quest.type)}
          </p>
          <p className="text-base font-semibold leading-snug">{quest.desc}</p>
        </div>

        {/* Прогресс */}
        <div>
          <div className="flex justify-between text-xs mb-1" style={{ color: "var(--text-hint)" }}>
            <span>Прогресс</span>
            <span className="tabular-nums">{data.progress} / {quest.goal}</span>
          </div>
          <div className="h-2.5 rounded-full overflow-hidden" style={{ backgroundColor: "var(--border)" }}>
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{
                width: `${pct}%`,
                backgroundColor: data.completed ? "#22c55e" : "var(--accent)",
              }}
            />
          </div>
          <p className="text-[11px] mt-1 text-right tabular-nums" style={{ color: "var(--text-hint)" }}>
            {pct}%
          </p>
        </div>

        {/* Награды */}
        <RewardRow quest={quest} rewarded={data.rewarded} />
      </div>

      {/* ── Кнопка реролла ── */}
      {!data.completed && (
        <div
          className="rounded-xl p-3 flex items-center justify-between gap-3"
          style={{ backgroundColor: "var(--bg-secondary)" }}
        >
          <div>
            <p className="text-sm font-medium">Заменить задание</p>
            <p className="text-[11px] mt-0.5" style={{ color: "var(--text-hint)" }}>
              Стоимость: несколько Моры или купон из инвентаря
            </p>
          </div>
          <button
            onClick={handleReroll}
            disabled={rerolling}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-opacity disabled:opacity-50 shrink-0"
            style={{ backgroundColor: "var(--border)", color: "var(--text-primary)" }}
          >
            {rerolling
              ? <Loader2 size={14} className="animate-spin" />
              : <RefreshCw size={14} />}
            {rerolling ? "..." : "Заменить"}
          </button>
        </div>
      )}

      {/* ── Тост ── */}
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

/* ── Секция наград ── */
function RewardRow({ quest, rewarded }: { quest: QuestInfo; rewarded: boolean }) {
  return (
    <div className="flex items-center gap-3 pt-1 border-t" style={{ borderColor: "var(--border)" }}>
      <span className="text-[11px]" style={{ color: "var(--text-hint)" }}>Награда:</span>
      <div className="flex gap-2">
        {quest.mora > 0 && (
          <span className="text-xs font-semibold tabular-nums">+{quest.mora.toLocaleString("ru-RU")} 🪙</span>
        )}
        {quest.xp > 0 && (
          <span className="text-xs font-semibold tabular-nums" style={{ color: "var(--accent)" }}>+{quest.xp} XP</span>
        )}
      </div>
      {rewarded && (
        <CheckCircle2 size={14} className="ml-auto shrink-0" style={{ color: "#22c55e" }} />
      )}
    </div>
  );
}

/* ── Скелетон ── */
function QuestSkeleton() {
  return (
    <div className="p-4 space-y-3 animate-pulse">
      <div className="skeleton h-6 w-40 rounded" />
      <div className="skeleton h-48 rounded-2xl" />
      <div className="skeleton h-16 rounded-xl" />
    </div>
  );
}
