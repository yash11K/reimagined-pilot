import { NavLink, Outlet } from "react-router-dom";
import { PageHeader } from "@/components/ui/PageHeader";
import { cn } from "@/lib/cn";

const TABS = [
  { to: "analytics", label: "Analytics" },
  { to: "playground", label: "KB Playground" },
] as const;

export default function SearchOperations() {
  return (
    <>
      <PageHeader
        title="Search Operations"
        subtitle="Query analytics and a live KB retrieval/chat playground."
      />

      <div className="mb-5 flex items-center gap-1 rounded-lg border border-line bg-bg-muted p-1 w-fit">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            className={({ isActive }) =>
              cn(
                "rounded-md px-4 py-1.5 text-xs font-semibold transition-colors",
                isActive
                  ? "bg-bg-surface text-ink shadow-sm"
                  : "text-ink-muted hover:text-ink",
              )
            }
          >
            {t.label}
          </NavLink>
        ))}
      </div>

      <Outlet />
    </>
  );
}
