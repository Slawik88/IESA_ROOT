/* ──────────────────────────────────────────────────────────────
   Bank.tsx — Банк и переводы
   Вкладки: Вклады | Новый вклад | Перевод
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Landmark, ArrowRightLeft, TrendingUp, Clock, CheckCircle2, CircleDollarSign } from "lucide-react";
import { fetchBankInfo, openDeposit, withdrawDeposit, transferMora, trackEvent } from "../lib/api";
import type { BankInfoResponse, BankDeposit, BankPlan, ChatMember } from "../types";
import { useToast } from "../components/ToastContext";
import UserPicker from "../components/UserPicker";
import Loans from "./Loans";

interface Props {
  userId: number;
  chatId: number;
}

type SubTab = "deposits" | "new" | "transfer" | "loans";

const fmt = (n: number) => n.toLocaleString("ru-RU");

export default function Bank({ userId, chatId }: Props) {
  const [data, setData]           = useState<BankInfoResponse | null>(null);
  const [error, setError]         = useState("");
  const [tab, setTab]             = useState<SubTab>("deposits");
  const [loading, setLoading]     = useState(false);
  const { toast } = useToast();
  const showOk  = useCallback((msg: string) => toast(msg, "success"), [toast]);
  const showErr = useCallback((msg: string) => toast(msg, "error"), [toast]);

  const reload = useCallback(() => {
    if (!chatId) return;
    fetchBankInfo(chatId).then(setData).catch((e: Error) => setError(e.message));
  }, [chatId]);

  useEffect(() => { reload(); }, [reload]);

  if (!chatId) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 p-6 text-center">
        <Landmark size={48} strokeWidth={1.2} style={{ color: "var(--text-hint)" }} />
        <div>
          <p className="font-semibold">Нет контекста чата</p>
          <p className="text-sm mt-1" style={{ color: "var(--text-hint)" }}>
            Откройте Mini App из чата группы.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center flex flex-col items-center gap-3">
        <p className="font-medium" style={{ color: "#e74c3c" }}>Ошибка загрузки банка</p>
        <p className="text-sm break-all" style={{ color: "var(--text-hint)" }}>{error}</p>
        <button
          onClick={() => { setError(""); reload(); }}
          className="px-4 py-2 rounded-xl text-sm font-semibold"
          style={{ backgroundColor: "var(--accent)", color: "#fff" }}
        >
          🔄 Повторить
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 space-y-3 animate-pulse">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton h-20 rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-2">

      {/* ── Заголовок ──────────────────────────────────────────── */}
      <div className="glass-hero p-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "var(--accent-soft)" }}>
            <Landmark size={18} style={{ color: "var(--accent)" }} />
          </div>
          <span className="font-bold text-base">Банк</span>
        </div>
        <div className="text-right">
          <p className="text-lg font-bold tabular-nums stat-value">{fmt(data.balance)} 🪙</p>
          {data.family_balance > 0 && (
            <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
              Семья: {fmt(data.family_balance)} 🪙
            </p>
          )}
        </div>
      </div>

      {/* ── Под-вкладки ────────────────────────────────────────── */}
      <div className="flex gap-1 rounded-xl p-1" style={{ backgroundColor: "var(--bg-secondary)" }}>
        {(["deposits", "new", "transfer", "loans"] as SubTab[]).map((t) => {
          const labels: Record<SubTab, string> = { deposits: "Вклады", new: "Вложить", transfer: "Перевод", loans: "Займы" };
          const active = tab === t;
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="flex-1 py-1.5 text-sm font-medium rounded-lg transition-colors"
              style={{
                backgroundColor: active ? "var(--accent)" : "transparent",
                color: active ? "#fff" : "var(--text-hint)",
              }}
            >
              {labels[t]}
            </button>
          );
        })}
      </div>

      {/* ── Вклады ────────────────────────────────────────────── */}
      {tab === "deposits" && (
        <DepositList
          deposits={data.deposits}
          earlyPenaltyPct={data.early_penalty_pct}
          chatId={chatId}
          loading={loading}
          setLoading={setLoading}
          showOk={showOk}
          showErr={showErr}
          reload={reload}
        />
      )}

      {/* ── Новый вклад ─────────────────────────────────────────── */}
      {tab === "new" && (
        <NewDeposit
          plans={data.plans}
          balance={data.balance}
          familyBalance={data.family_balance}
          chatId={chatId}
          loading={loading}
          setLoading={setLoading}
          showOk={showOk}
          showErr={showErr}
          reload={() => { reload(); setTab("deposits"); }}
        />
      )}

      {/* ── Займы ──────────────────────────────────────────────── */}
      {tab === "loans" && (
        <Loans userId={userId} chatId={chatId} />
      )}

      {/* ── Перевод ────────────────────────────────────────────── */}
      {tab === "transfer" && (
        <Transfer
          balance={data.balance}
          chatId={chatId}
          loading={loading}
          setLoading={setLoading}
          showOk={showOk}
          showErr={showErr}
          reload={reload}
        />
      )}


    </div>
  );
}

/* ── DepositList ──────────────────────────────────────────────── */

interface DepositListProps {
  deposits: BankDeposit[];
  earlyPenaltyPct: number;
  chatId: number;
  loading: boolean;
  setLoading: (v: boolean) => void;
  showOk: (m: string) => void;
  showErr: (m: string) => void;
  reload: () => void;
}

function DepositList({ deposits, earlyPenaltyPct, chatId, loading, setLoading, showOk, showErr, reload }: DepositListProps) {
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const doWithdraw = async (deposit: BankDeposit) => {
    setConfirmId(null);
    setLoading(true);
    try {
      const res = await withdrawDeposit(chatId, deposit.id);
      if (res.ok) {
        trackEvent("bank_withdraw");
        const earlyNote = res.early ? " (досрочно)" : "";
        showOk(`+${fmt(res.payout)} 🪙${earlyNote}  Новый баланс: ${fmt(res.new_balance)} 🪙`);
        reload();
      } else {
        showErr(res.error ?? "Ошибка вывода");
      }
    } catch (e: unknown) {
      showErr(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setLoading(false);
    }
  };

  const handleWithdraw = (deposit: BankDeposit) => {
    if (loading) return;
    if (!deposit.mature) {
      setConfirmId(deposit.id);
      return;
    }
    doWithdraw(deposit);
  };

  if (deposits.length === 0) {
    return (
      <div className="rounded-xl p-6 text-center" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <TrendingUp size={32} strokeWidth={1.2} className="mx-auto mb-2" style={{ color: "var(--text-hint)" }} />
        <p className="text-sm" style={{ color: "var(--text-hint)" }}>Нет активных вкладов</p>
        <p className="text-xs mt-1" style={{ color: "var(--text-hint)" }}>Перейдите во вкладку «Вложить»</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {deposits.map((d) => (
        <div
          key={d.id}
          className="rounded-xl p-3"
          style={{ backgroundColor: "var(--bg-secondary)" }}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                {d.mature
                  ? <CheckCircle2 size={14} style={{ color: "#22c55e" }} />
                  : <Clock size={14} style={{ color: "#f59e0b" }} />
                }
                <span className="text-sm font-medium">{fmt(d.amount)} 🪙 · {d.plan_days} дн.</span>
                <span className="text-xs px-1.5 py-0.5 rounded" style={{
                  backgroundColor: d.mature ? "#14532d" : "var(--bg-primary)",
                  color: d.mature ? "#86efac" : "var(--text-hint)",
                }}>
                  {d.rate_pct}%
                </span>
              </div>
              <p className="text-[11px] mt-1" style={{ color: "var(--text-hint)" }}>
                Доход: +{fmt(d.reward)} 🪙
                {!d.mature && ` · осталось ${d.time_left_h}ч ${d.time_left_m}м`}
                {d.mature && " · Готово!"}
              </p>
              {/* Прогресс-бар */}
              <div className="mt-2 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "var(--border)" }}>
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${d.progress_pct}%`,
                    backgroundColor: d.mature ? "#22c55e" : "var(--accent)",
                  }}
                />
              </div>
            </div>
            <button
              onClick={() => handleWithdraw(d)}
              disabled={loading}
              className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold transition-opacity disabled:opacity-40"
              style={{
                backgroundColor: d.mature ? "#22c55e" : "var(--border)",
                color: d.mature ? "#fff" : "var(--text-primary)",
              }}
            >
              {d.mature ? "Забрать" : "Досрочно"}
            </button>
          </div>
          {/* Inline confirmation for early withdrawal */}
          {confirmId === d.id && (
            <div className="mt-2 p-2.5 rounded-lg flex items-center justify-between gap-2" style={{ backgroundColor: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)" }}>
              <p className="text-xs" style={{ color: "#fca5a5" }}>
                ⚠️ Штраф {earlyPenaltyPct}% от процентов. Закрыть?
              </p>
              <div className="flex gap-1.5 shrink-0">
                <button
                  onClick={() => setConfirmId(null)}
                  className="px-2.5 py-1 rounded-lg text-xs font-medium"
                  style={{ backgroundColor: "var(--border)", color: "var(--text-primary)" }}
                >
                  Нет
                </button>
                <button
                  onClick={() => doWithdraw(d)}
                  disabled={loading}
                  className="px-2.5 py-1 rounded-lg text-xs font-semibold disabled:opacity-40"
                  style={{ backgroundColor: "#ef4444", color: "#fff" }}
                >
                  Да, закрыть
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ── NewDeposit ──────────────────────────────────────────────── */

interface NewDepositProps {
  plans: BankPlan[];
  balance: number;
  familyBalance: number;
  chatId: number;
  loading: boolean;
  setLoading: (v: boolean) => void;
  showOk: (m: string) => void;
  showErr: (m: string) => void;
  reload: () => void;
}

function NewDeposit({ plans, balance, familyBalance, chatId, loading, setLoading, showOk, showErr, reload }: NewDepositProps) {
  const [selectedPlan, setSelectedPlan] = useState<BankPlan | null>(plans[0] ?? null);
  const [amount, setAmount]             = useState<string>("");
  const [wallet, setWallet]             = useState<"personal" | "family">("personal");

  const maxBalance = wallet === "family" ? familyBalance : balance;
  const reward     = selectedPlan && Number(amount) > 0
    ? Math.floor(Number(amount) * selectedPlan.rate_pct / 100)
    : 0;

  const handleSubmit = async () => {
    const amt = parseInt(amount, 10);
    if (!selectedPlan || !amt || amt <= 0) return showErr("Укажите сумму");
    if (amt > maxBalance) return showErr("Недостаточно средств");

    setLoading(true);
    try {
      const res = await openDeposit(chatId, selectedPlan.key, amt, wallet);
      if (res.ok) {
        trackEvent("bank_deposit");
        showOk(`Вклад открыт: ${fmt(amt)} 🪙 на ${res.days} дн. Доход: +${fmt(res.reward)} 🪙`);
        setAmount("");
        reload();
      } else {
        showErr(res.error ?? "Ошибка открытия вклада");
      }
    } catch (e: unknown) {
      showErr(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      {/* Выбор плана */}
      <div className="rounded-xl p-3 space-y-2" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <p className="text-xs font-medium" style={{ color: "var(--text-hint)" }}>Срок вклада</p>
        <div className="grid grid-cols-3 gap-2">
          {plans.map((p) => {
            const active = selectedPlan?.key === p.key;
            return (
              <button
                key={p.key}
                onClick={() => setSelectedPlan(p)}
                className="rounded-lg p-2 text-center transition-colors"
                style={{
                  backgroundColor: active ? "var(--accent)" : "var(--bg-primary)",
                  color: active ? "#fff" : "var(--text-primary)",
                  border: active ? "none" : "1px solid var(--border)",
                }}
              >
                <p className="text-base font-bold">{p.days} дн.</p>
                <p className="text-xs font-semibold mt-0.5" style={{ color: active ? "rgba(255,255,255,0.8)" : "#22c55e" }}>
                  +{p.rate_pct}%
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Выбор кошелька */}
      {familyBalance > 0 && (
        <div className="flex gap-1 rounded-xl p-1" style={{ backgroundColor: "var(--bg-secondary)" }}>
          {(["personal", "family"] as const).map((w) => {
            const labels = { personal: "Личный", family: "Семейный" };
            const active = wallet === w;
            return (
              <button
                key={w}
                onClick={() => setWallet(w)}
                className="flex-1 py-1.5 text-sm font-medium rounded-lg transition-colors"
                style={{
                  backgroundColor: active ? "var(--accent)" : "transparent",
                  color: active ? "#fff" : "var(--text-hint)",
                }}
              >
                {labels[w]}
              </button>
            );
          })}
        </div>
      )}

      {/* Быстрые суммы */}
      {selectedPlan && (
        <div className="rounded-xl p-3 space-y-2" style={{ backgroundColor: "var(--bg-secondary)" }}>
          <p className="text-xs font-medium" style={{ color: "var(--text-hint)" }}>Сумма</p>
          <div className="flex flex-wrap gap-1.5">
            {selectedPlan.amounts.filter((a) => a <= maxBalance).map((a) => (
              <button
                key={a}
                onClick={() => setAmount(String(a))}
                className="px-2.5 py-1 rounded-lg text-xs font-medium transition-colors"
                style={{
                  backgroundColor: amount === String(a) ? "var(--accent)" : "var(--bg-primary)",
                  color: amount === String(a) ? "#fff" : "var(--text-primary)",
                }}
              >
                {fmt(a)}
              </button>
            ))}
          </div>
          <input
            type="number"
            inputMode="numeric"
            pattern="[0-9]*"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder={`Или введите сумму (макс ${fmt(maxBalance)})`}
            min={1}
            max={maxBalance}
            className="w-full rounded-lg px-3 py-2 text-sm bg-transparent border outline-none"
            style={{ borderColor: "var(--border)", color: "var(--text-primary)" }}
          />
          {reward > 0 && (
            <p className="text-xs" style={{ color: "#22c55e" }}>
              Доход через {selectedPlan.days} дн.: +{fmt(reward)} 🪙
            </p>
          )}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={loading || !amount || Number(amount) <= 0}
        className="w-full py-3 rounded-xl font-semibold text-sm transition-opacity disabled:opacity-40"
        style={{ backgroundColor: "var(--accent)", color: "#fff" }}
      >
        {loading ? "Открываю..." : "Открыть вклад"}
      </button>
    </div>
  );
}

/* ── Transfer ─────────────────────────────────────────────────── */

interface TransferProps {
  balance: number;
  chatId: number;
  loading: boolean;
  setLoading: (v: boolean) => void;
  showOk: (m: string) => void;
  showErr: (m: string) => void;
  reload: () => void;
}

const TRANSFER_MIN = 1;
const TRANSFER_MAX = 5000;

function Transfer({ balance, chatId, loading, setLoading, showOk, showErr, reload }: TransferProps) {
  const [selectedMember, setSelectedMember] = useState<ChatMember | null>(null);
  const [amount, setAmount]     = useState("");
  const [coverVat, setCoverVat] = useState(true);

  const handleTransfer = async () => {
    const tid = selectedMember?.user_id ?? 0;
    const amt = parseInt(amount, 10);

    if (!tid || tid <= 0) return showErr("Выберите получателя");
    if (!amt || amt < TRANSFER_MIN || amt > TRANSFER_MAX)
      return showErr(`Сумма от ${TRANSFER_MIN} до ${fmt(TRANSFER_MAX)} 🪙`);
    if (amt > balance) return showErr("Недостаточно средств");

    setLoading(true);
    try {
      const res = await transferMora(chatId, tid, amt, coverVat);
      if (res.ok) {
        trackEvent("bank_transfer");
        showOk(`Переведено ${fmt(res.amount ?? amt)} 🪙  Баланс: ${fmt(res.sender_balance ?? 0)} 🪙`);
        setSelectedMember(null);
        setAmount("");
        reload();
      } else {
        showErr(res.error ?? "Ошибка перевода");
      }
    } catch (e: unknown) {
      showErr(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="rounded-xl p-3 space-y-3" style={{ backgroundColor: "var(--bg-secondary)" }}>
        <div className="flex items-center gap-1.5 text-sm font-medium">
          <ArrowRightLeft size={15} style={{ color: "var(--accent)" }} />
          Перевод Моры
        </div>
        <div className="space-y-2">
          <UserPicker
            chatId={chatId}
            selected={selectedMember}
            onSelect={setSelectedMember}
          />
          <input
            type="number"
            inputMode="numeric"
            pattern="[0-9]*"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder={`Сумма (${TRANSFER_MIN}–${fmt(TRANSFER_MAX)}) · баланс: ${fmt(balance)}`}
            min={TRANSFER_MIN}
            max={Math.min(TRANSFER_MAX, balance)}
            className="w-full rounded-lg px-3 py-2 text-sm bg-transparent border outline-none"
            style={{ borderColor: "var(--border)", color: "var(--text-primary)" }}
          />
        </div>
        {/* VAT-опция */}
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <input
            type="checkbox"
            checked={coverVat}
            onChange={(e) => setCoverVat(e.target.checked)}
            className="rounded"
          />
          <span style={{ color: "var(--text-hint)" }}>Учесть НДС (вычтется из суммы)</span>
        </label>
        <div className="flex items-center gap-1.5 p-2 rounded-lg text-xs" style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-hint)" }}>
          <CircleDollarSign size={13} />
          Лимит: {TRANSFER_MIN}–{fmt(TRANSFER_MAX)} 🪙 за раз
        </div>
      </div>

      <button
        onClick={handleTransfer}
        disabled={loading || !selectedMember || !amount}
        className="w-full py-3 rounded-xl font-semibold text-sm transition-opacity disabled:opacity-40"
        style={{ backgroundColor: "var(--accent)", color: "#fff" }}
      >
        {loading ? "Перевожу..." : "Отправить"}
      </button>
    </div>
  );
}
