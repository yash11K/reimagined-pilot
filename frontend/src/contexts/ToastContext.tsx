import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/cn";

export type ToastTone = "success" | "error" | "info" | "warn";

interface Toast {
  id: string;
  tone: ToastTone;
  title: string;
  message?: string;
}

interface Ctx {
  push: (t: Omit<Toast, "id">) => void;
  success: (title: string, message?: string) => void;
  error: (title: string, message?: string) => void;
  info: (title: string, message?: string) => void;
  warn: (title: string, message?: string) => void;
}

const ToastContext = createContext<Ctx>({
  push: () => {},
  success: () => {},
  error: () => {},
  info: () => {},
  warn: () => {},
});

const toneStyles: Record<ToastTone, { bg: string; border: string; icon: ReactNode }> = {
  success: {
    bg: "bg-status-okSoft",
    border: "border-status-ok/30",
    icon: <CheckCircle2 className="h-4 w-4 text-status-ok" />,
  },
  error: {
    bg: "bg-status-errSoft",
    border: "border-status-err/30",
    icon: <XCircle className="h-4 w-4 text-status-err" />,
  },
  info: {
    bg: "bg-status-infoSoft",
    border: "border-status-info/30",
    icon: <Info className="h-4 w-4 text-status-info" />,
  },
  warn: {
    bg: "bg-status-warnSoft",
    border: "border-status-warn/30",
    icon: <AlertTriangle className="h-4 w-4 text-status-warn" />,
  },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { ...t, id }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, 4500);
  }, []);

  const api: Ctx = {
    push,
    success: (title, message) => push({ tone: "success", title, message }),
    error: (title, message) => push({ tone: "error", title, message }),
    info: (title, message) => push({ tone: "info", title, message }),
    warn: (title, message) => push({ tone: "warn", title, message }),
  };

  const dismiss = (id: string) => setToasts((prev) => prev.filter((x) => x.id !== id));

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed right-6 top-6 z-[60] flex w-80 flex-col gap-2">
        {toasts.map((t) => {
          const s = toneStyles[t.tone];
          return (
            <div
              key={t.id}
              className={cn(
                "pointer-events-auto flex items-start gap-2 rounded-xl border p-3 shadow-card",
                s.bg,
                s.border
              )}
            >
              <div className="mt-0.5 shrink-0">{s.icon}</div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-ink">{t.title}</p>
                {t.message && <p className="mt-0.5 text-xs text-ink-soft">{t.message}</p>}
              </div>
              <button
                onClick={() => dismiss(t.id)}
                className="shrink-0 rounded p-0.5 text-ink-muted hover:bg-bg-surface hover:text-ink"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
