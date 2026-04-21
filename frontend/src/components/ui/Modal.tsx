import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

export function Modal({
  open,
  onClose,
  title,
  children,
  width = "max-w-2xl",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  width?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <div
        className={cn(
          "relative w-full overflow-hidden rounded-xl border border-line bg-bg-surface shadow-2xl",
          width
        )}
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="text-sm font-semibold text-ink">{title}</div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-ink-muted hover:bg-bg-muted hover:text-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto scrollbar-thin p-5">{children}</div>
      </div>
    </div>
  );
}
