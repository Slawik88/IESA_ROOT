/* ──────────────────────────────────────────────────────────────
   Loans.tsx — Займы между участниками чата
   Вкладки: Займы | Входящие | Выдать
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Banknote, ArrowDownLeft, ArrowUpRight, RefreshCw, Users } from "lucide-react";
import { useToast } from "../components/ToastContext";
import {
  fetchLoans,
  createLoan,
  repayLoan,
  respondLoan,
  cancelLoan,
  fetchMembers,
  type LoansResponse,
  type LoanRecord,
} from "../lib/api";
import type { ChatMember } from "../types";

interface Props {
  userId: number;
  chatId: number;
}

type SubTab = "active" | "incoming" | "new";

const fmt = (n: number) => n.toLocaleString("ru-RU");

function formatDate(iso?: string | null): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }); }
  catch { return iso; }
}

export default function Loans({ userId, chatId }: Props) {
  const [data, setData]         = useState<LoansResponse | null>(null);
  const [tab, setTab]           = useState<SubTab>("active");
  const [loading, setLoading]   = useState(false);
  const { toast: globalToast } = useToast();

  const showOk  = useCallback((msg: string) => globalToast(msg, "success"), [globalToast]);
  const showErr = useCallback((msg: string) => globalToast(msg, "error"), [globalToast]);

  const reload = useCallback(() => {
    if (!chatId) return;
    setLoading(true);
    fetchLoans(chatId)
      .then(setData)
      .catch((e: Error) => showErr(e.message))
      .finally(() => setLoading(false));
  }, [chatId, showErr]);

  useEffect(() => { reload(); }, [reload]);

  const incomingCount = data?.pending_incoming?.length ?? 0;

  return (
    <div className="animate-fadeIn p-4 space-y-3 pb-2" style={{ minHeight: "100vh" }}>
      {/* ── Заголовок ──────────────────────────────────────────── */}
      <div className="glass-hero p-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "var(--accent-soft)" }}>
            <Banknote size={18} style={{ color: "var(--accent)" }} />
          </div>
          <span className="font-bold text-base">Займы</span>
        </div>
        <button onClick={reload} disabled={loading} style={{ color: "var(--text-hint)" }}>
          <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* ── Под-вкладки ────────────────────────────────────────── */}
      <div className="flex gap-1 rounded-xl p-1" style={{ backgroundColor: "var(--bg-secondary)" }}>
        {(["active", "incoming", "new"] as SubTab[]).map((t) => {
          const labels: Record<SubTab, string> = { active: "Мои займы", incoming: `Входящие${incomingCount > 0 ? ` (${incomingCount})` : ""}`, new: "Выдать заём" };
          const active = tab === t;
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="flex-1 py-1.5 rounded-lg text-sm font-medium transition-all"
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

      {/* ── Контент ───────────────────────────────────────────── */}
      {tab === "active" && (
        <ActiveLoans
          asLender={data?.as_lender ?? []}
          asBorrower={data?.as_borrower ?? []}
          userId={userId}
          onRepay={(id) =>
            repayLoan(chatId, id)
              .then(() => { showOk("Заём погашен!"); reload(); })
              .catch((e: Error) => showErr(extractError(e.message)))
          }
          onCancel={(id) =>
            cancelLoan(chatId, id)
              .then(() => { showOk("Заём отменён"); reload(); })
              .catch((e: Error) => showErr(extractError(e.message)))
          }
        />
      )}

      {tab === "incoming" && (
        <IncomingLoans
          loans={data?.pending_incoming ?? []}
          onAccept={(id) =>
            respondLoan(chatId, id, "accept")
              .then(() => { showOk("Заём принят!"); reload(); })
              .catch((e: Error) => showErr(extractError(e.message)))
          }
          onReject={(id) =>
            respondLoan(chatId, id, "reject")
              .then(() => { showOk("Заём отклонён"); reload(); })
              .catch((e: Error) => showErr(extractError(e.message)))
          }
        />
      )}

      {tab === "new" && (
        <NewLoanForm
          chatId={chatId}
          userId={userId}
          onCreated={() => { showOk("Запрос займа отправлен!"); reload(); setTab("active"); }}
          onError={showErr}
        />
      )}
    </div>
  );
}

// ── Активные займы ────────────────────────────────────────────

function ActiveLoans({
  asLender, asBorrower, userId: _userId, onRepay, onCancel,
}: {
  asLender: LoanRecord[];
  asBorrower: LoanRecord[];
  userId: number;
  onRepay: (id: number) => void;
  onCancel: (id: number) => void;
}) {
  return (
    <div className="space-y-4">
      {/* Займы, которые я выдал */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <ArrowUpRight size={14} style={{ color: "#22c55e" }} />
          <p className="text-xs font-semibold uppercase" style={{ color: "var(--text-hint)" }}>
            Выданные займы ({asLender.length})
          </p>
        </div>
        {asLender.length === 0 ? (
          <p className="text-sm py-2 text-center" style={{ color: "var(--text-hint)" }}>Нет выданных займов</p>
        ) : (
          <div className="space-y-2">
            {asLender.map((loan) => (
              <LoanCard
                key={loan.id}
                loan={loan}
                role="lender"
                onAction={loan.status === "pending" ? () => onCancel(loan.id) : undefined}
                actionLabel="Отменить"
              />
            ))}
          </div>
        )}
      </div>

      {/* Займы, которые я получил */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <ArrowDownLeft size={14} style={{ color: "#f59e0b" }} />
          <p className="text-xs font-semibold uppercase" style={{ color: "var(--text-hint)" }}>
            Полученные займы ({asBorrower.length})
          </p>
        </div>
        {asBorrower.length === 0 ? (
          <p className="text-sm py-2 text-center" style={{ color: "var(--text-hint)" }}>Нет активных займов</p>
        ) : (
          <div className="space-y-2">
            {asBorrower.map((loan) => (
              <LoanCard
                key={loan.id}
                loan={loan}
                role="borrower"
                onAction={loan.status === "accepted" ? () => onRepay(loan.id) : undefined}
                actionLabel="Погасить"
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LoanCard({
  loan, role, onAction, actionLabel,
}: {
  loan: LoanRecord;
  role: "lender" | "borrower";
  onAction?: () => void;
  actionLabel?: string;
}) {
  const statusColor: Record<string, string> = {
    pending:   "#f59e0b",
    accepted:  "var(--accent)",
    repaid:    "#22c55e",
    cancelled: "#9ca3af",
  };
  const statusLabel: Record<string, string> = {
    pending:   "Ожидает",
    accepted:  "Активен",
    repaid:    "Погашен",
    cancelled: "Отменён",
  };

  return (
    <div
      className="rounded-xl p-3 flex items-center justify-between gap-3"
      style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
    >
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold tabular-nums">{fmt(loan.amount)} 🪙</p>
        <p className="text-xs mt-0.5 truncate" style={{ color: "var(--text-hint)" }}>
          {role === "lender"
            ? `→ ${loan.borrower_name ?? `#${loan.borrower_id}`}`
            : `← ${loan.lender_name ?? `#${loan.lender_id}`}`}
          {loan.loaned_at && ` · ${formatDate(loan.loaned_at)}`}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span
          className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
          style={{ backgroundColor: (statusColor[loan.status] ?? "#9ca3af") + "22", color: statusColor[loan.status] ?? "#9ca3af" }}
        >
          {statusLabel[loan.status] ?? loan.status}
        </span>
        {onAction && (
          <button
            onClick={onAction}
            className="text-xs px-2.5 py-1 rounded-lg font-medium"
            style={{ backgroundColor: "var(--accent)", color: "#fff" }}
          >
            {actionLabel}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Входящие запросы займа ─────────────────────────────────────

function IncomingLoans({
  loans, onAccept, onReject,
}: {
  loans: LoanRecord[];
  onAccept: (id: number) => void;
  onReject: (id: number) => void;
}) {
  if (loans.length === 0) {
    return (
      <div className="text-center py-12" style={{ color: "var(--text-hint)" }}>
        <Banknote size={40} strokeWidth={1.2} className="mx-auto mb-2" />
        <p className="text-sm">Нет входящих запросов</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {loans.map((loan) => (
        <div key={loan.id} className="rounded-xl p-4 space-y-3"
          style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
          <div>
            <p className="font-semibold text-sm">
              {loan.lender_name ?? `#${loan.lender_id}`} предлагает {fmt(loan.amount)} 🪙
            </p>
            {loan.loaned_at && (
              <p className="text-xs mt-0.5" style={{ color: "var(--text-hint)" }}>
                {formatDate(loan.loaned_at)}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => onAccept(loan.id)}
              className="flex-1 py-2 rounded-xl text-sm font-semibold"
              style={{ backgroundColor: "var(--accent)", color: "#fff" }}
            >
              Принять
            </button>
            <button
              onClick={() => onReject(loan.id)}
              className="flex-1 py-2 rounded-xl text-sm font-semibold"
              style={{ backgroundColor: "#ef444422", color: "#ef4444" }}
            >
              Отклонить
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Форма нового займа ─────────────────────────────────────────

function NewLoanForm({
  chatId, userId, onCreated, onError,
}: {
  chatId: number;
  userId: number;
  onCreated: () => void;
  onError: (msg: string) => void;
}) {
  const [members, setMembers]     = useState<ChatMember[]>([]);
  const [selected, setSelected]   = useState<ChatMember | null>(null);
  const [amount, setAmount]       = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchMembers(chatId)
      .then((r) => setMembers((r.members ?? []).filter((m) => m.user_id !== userId)))
      .catch(() => setMembers([]));
  }, [chatId, userId]);

  const handleSubmit = () => {
    if (!selected) { onError("Выберите получателя"); return; }
    const amt = parseInt(amount);
    if (isNaN(amt) || amt <= 0) { onError("Введите сумму займа"); return; }

    setSubmitting(true);
    createLoan(chatId, selected.user_id, amt)
      .then(() => onCreated())
      .catch((e: Error) => onError(extractError(e.message)))
      .finally(() => setSubmitting(false));
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl p-3 text-xs" style={{ backgroundColor: "#3b82f622", color: "#3b82f6" }}>
        <p>💡 Заём будет создан в статусе «Ожидает». Получатель должен принять его.</p>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase" style={{ color: "var(--text-hint)" }}>
          <Users size={12} className="inline mr-1" />Получатель
        </p>
        <div className="max-h-40 overflow-y-auto space-y-1.5">
          {members.map((m) => (
            <button
              key={m.user_id}
              onClick={() => setSelected(m)}
              className="w-full rounded-xl px-3 py-2 text-sm flex items-center gap-2 text-left"
              style={{
                backgroundColor: selected?.user_id === m.user_id ? "var(--accent-soft)" : "var(--bg-secondary)",
                border: `1.5px solid ${selected?.user_id === m.user_id ? "var(--accent)" : "var(--border)"}`,
              }}
            >
              <span className="font-medium">{m.name ?? `#${m.user_id}`}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium" style={{ color: "var(--text-hint)" }}>
          Сумма займа (🪙) *
        </label>
        <input
          type="number"
          min={1}
          placeholder="Например: 500"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="w-full rounded-xl px-3 py-2.5 text-sm border"
          style={{
            backgroundColor: "var(--bg-secondary)",
            borderColor: "var(--border)",
            color: "var(--text-primary)",
          }}
        />
      </div>

      <button
        onClick={handleSubmit}
        disabled={submitting || !selected}
        className="w-full py-3 rounded-xl font-semibold text-sm"
        style={{
          backgroundColor: selected ? "var(--accent)" : "var(--bg-secondary)",
          color: selected ? "#fff" : "var(--text-hint)",
        }}
      >
        {submitting ? "Отправляю..." : "Отправить предложение займа"}
      </button>
    </div>
  );
}

function extractError(msg: string): string {
  try { return JSON.parse(msg.split("API 400: ")[1]).error ?? msg; } catch { return msg; }
}
