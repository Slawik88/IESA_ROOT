/* ──────────────────────────────────────────────────────────────
   ToastContext — глобальная система уведомлений (Toast/Snackbar).
   Использование:
     const { toast } = useToast();
     toast("✅ Куплено!");
     toast("❌ Недостаточно средств", "error");
     toast("⚠️ Внимание", "warning");
   Оберни AppContent в <ToastProvider>.
   ────────────────────────────────────────────────────────────── */
import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from "react";

export type ToastType = "success" | "error" | "warning" | "info";

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
  exiting: boolean;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });
let _nextId = 0;

const TYPE_STYLES: Record<ToastType, { border: string; icon: string }> = {
  success: { border: "#22c55e", icon: "✅" },
  error:   { border: "#ef4444", icon: "❌" },
  warning: { border: "#f59e0b", icon: "⚠️" },
  info:    { border: "var(--accent)", icon: "ℹ️" },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timerIds = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    return () => {
      timerIds.current.forEach(clearTimeout);
    };
  }, []);

  const toast = useCallback((message: string, type: ToastType = "info") => {
    const id = ++_nextId;
    setItems(prev => [...prev.slice(-4), { id, message, type, exiting: false }]);

    // Start exit animation just before removal
    const t1 = setTimeout(() => {
      setItems(prev => prev.map(t => t.id === id ? { ...t, exiting: true } : t));
    }, 2800);
    const t2 = setTimeout(() => {
      setItems(prev => prev.filter(t => t.id !== id));
    }, 3100);
    timerIds.current.push(t1, t2);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}

      {/* Toast container — top-center, fixed, above everything */}
      {items.length > 0 && (
        <div
          style={{
            position: "fixed",
            top: 12,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 9999,
            display: "flex",
            flexDirection: "column",
            gap: 8,
            alignItems: "center",
            width: "min(90vw, 360px)",
            pointerEvents: "none",
          }}
        >
          {items.map(item => {
            const s = TYPE_STYLES[item.type];
            return (
              <div
                key={item.id}
                className={item.exiting ? "toast-exit" : "toast-enter"}
                style={{
                  width: "100%",
                  padding: "10px 16px",
                  borderRadius: 14,
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 10,
                  fontSize: 13,
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  backdropFilter: "blur(24px) saturate(2)",
                  WebkitBackdropFilter: "blur(24px) saturate(2)",
                  background: "linear-gradient(135deg, rgba(0,0,0,0.75), rgba(0,0,0,0.6))",
                  border: `1px solid ${s.border}55`,
                  boxShadow: `0 4px 24px -4px ${s.border}44, 0 2px 8px rgba(0,0,0,0.5)`,
                  lineHeight: 1.4,
                }}
              >
                <span style={{ fontSize: 16, lineHeight: 1.2, flexShrink: 0 }}>{s.icon}</span>
                <span style={{ flex: 1, wordBreak: "break-word" }}>{item.message}</span>
              </div>
            );
          })}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  return useContext(ToastContext);
}
