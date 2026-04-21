import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

export function Drawer({
  open,
  onClose,
  title,
  children,
  width = "max-w-xl",
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
    <div className="fixed inset-0 z-50 flex">
      <div
        className="flex-1 bg-ink/30 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <aside
        className={cn(
          "flex h-full w-full flex-col border-l border-line bg-bg-surface shadow-2xl",
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
        <div className="flex-1 overflow-y-auto scrollbar-thin p-5">{children}</div>
      </aside>
    </div>
  );
}
