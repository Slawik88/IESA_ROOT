/* ──────────────────────────────────────────────────────────────
   UserPicker — визуальный выбор пользователя из чата
   Загружает /api/members, показывает список с поиском.
   Используется в: Bank.tsx (Перевод), Admin.tsx
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Search, UserCheck, X as XIcon, Loader2 } from "lucide-react";
import { fetchMembers } from "../lib/api";
import type { ChatMember } from "../types";

interface UserPickerProps {
  chatId: number;
  /** Уже выбранный пользователь (или null) */
  selected: ChatMember | null;
  /** Вызывается при выборе — передаётся объект ChatMember */
  onSelect: (member: ChatMember | null) => void;
  /** Исключить этого userId из списка (например, самого себя) */
  excludeId?: number;
  placeholder?: string;
}

export default function UserPicker({
  chatId,
  selected,
  onSelect,
  excludeId,
  placeholder = "Поиск участника...",
}: UserPickerProps) {
  const [members, setMembers] = useState<ChatMember[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");
  const [query, setQuery]     = useState("");
  const [open, setOpen]       = useState(false);

  const load = useCallback(() => {
    if (!chatId || members.length > 0) return;
    setLoading(true);
    fetchMembers(chatId)
      .then((r) => setMembers(r.members))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [chatId, members.length]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const filtered = members
    .filter((m) => m.user_id !== excludeId)
    .filter((m) =>
      query === "" ||
      m.name.toLowerCase().includes(query.toLowerCase()) ||
      String(m.user_id).includes(query),
    );

  const initials = (name: string) =>
    name
      .split(" ")
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase() ?? "")
      .join("");

  /* Closed state — shows selected user OR a button to open */
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all"
        style={{
          backgroundColor: "var(--bg-primary)",
          border: `1px solid ${selected ? "var(--accent)" : "var(--border)"}`,
          color: selected ? "var(--text-primary)" : "var(--text-hint)",
        }}
      >
        {selected ? (
          <>
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
              style={{ backgroundColor: "var(--accent)22", color: "var(--accent)" }}
            >
              {initials(selected.name)}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{selected.name}</p>
              <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                ID: {selected.user_id}
              </p>
            </div>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onSelect(null); }}
              className="shrink-0 p-1 rounded-full"
              style={{ color: "var(--text-hint)" }}
            >
              <XIcon size={14} />
            </button>
          </>
        ) : (
          <>
            <Search size={15} />
            <span className="text-sm">{placeholder}</span>
          </>
        )}
      </button>
    );
  }

  /* Open state — overlay sheet */
  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50"
        onClick={() => setOpen(false)}
      />

      {/* List sheet */}
      <div
        className="fixed bottom-0 inset-x-0 z-50 rounded-t-2xl animate-slideUp flex flex-col"
        style={{
          backgroundColor: "var(--bg-primary)",
          maxHeight: "70vh",
        }}
      >
        {/* drag handle */}
        <div className="flex justify-center pt-3 pb-1 shrink-0">
          <div className="w-10 h-1 rounded-full" style={{ backgroundColor: "var(--border)" }} />
        </div>

        {/* Header + search */}
        <div className="px-4 pb-3 shrink-0">
          <div className="flex items-center justify-between mb-3">
            <span className="font-semibold text-sm">Выберите получателя</span>
            <button
              onClick={() => setOpen(false)}
              style={{ color: "var(--text-hint)" }}
            >
              <XIcon size={18} />
            </button>
          </div>
          <div
            className="flex items-center gap-2 rounded-xl px-3 py-2"
            style={{ backgroundColor: "var(--bg-secondary)" }}
          >
            <Search size={14} style={{ color: "var(--text-hint)" }} />
            <input
              autoFocus
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={placeholder}
              className="flex-1 text-sm bg-transparent outline-none"
              style={{ color: "var(--text-primary)" }}
            />
            {query && (
              <button onClick={() => setQuery("")} style={{ color: "var(--text-hint)" }}>
                <XIcon size={12} />
              </button>
            )}
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto px-4 pb-8 space-y-1.5">
          {loading && (
            <div className="flex justify-center py-6">
              <Loader2 size={22} className="animate-spin" style={{ color: "var(--accent)" }} />
            </div>
          )}
          {!loading && error && (
            <p className="text-center text-sm py-4" style={{ color: "#e74c3c" }}>
              {error}
            </p>
          )}
          {!loading && !error && filtered.length === 0 && (
            <p className="text-center text-sm py-4" style={{ color: "var(--text-hint)" }}>
              {query ? "Не найдено" : "Список пуст"}
            </p>
          )}
          {!loading &&
            filtered.map((m) => (
              <button
                key={m.user_id}
                type="button"
                onClick={() => { onSelect(m); setOpen(false); setQuery(""); }}
                className="w-full flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all active:scale-[0.98]"
                style={{
                  backgroundColor:
                    selected?.user_id === m.user_id
                      ? "var(--accent)22"
                      : "var(--bg-secondary)",
                  border:
                    selected?.user_id === m.user_id
                      ? "1px solid var(--accent)"
                      : "1px solid transparent",
                }}
              >
                <div
                  className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                  style={{ backgroundColor: "var(--accent)22", color: "var(--accent)" }}
                >
                  {initials(m.name)}
                </div>
                <div className="flex-1 min-w-0 text-left">
                  <p className="text-sm font-medium truncate">{m.name}</p>
                  <p className="text-[11px]" style={{ color: "var(--text-hint)" }}>
                    ID: {m.user_id}
                  </p>
                </div>
                {selected?.user_id === m.user_id && (
                  <UserCheck size={16} style={{ color: "var(--accent)" }} />
                )}
              </button>
            ))}
        </div>
      </div>
    </>
  );
}
