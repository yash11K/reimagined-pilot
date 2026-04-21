import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Search,
  Compass,
  Library,
  ShieldCheck,
  PenSquare,
  ChevronsLeft,
  Server,
} from "lucide-react";
import { cn } from "@/lib/cn";

const NAV = [
  { to: "/", label: "Executive Dashboard", icon: LayoutDashboard, end: true },
  { to: "/search-operations", label: "Search Operations", icon: Search },
  { to: "/discovery-tools", label: "Discovery Tools", icon: Compass },
  { to: "/knowledge-library", label: "Knowledge Library", icon: Library },
  { to: "/review-governance", label: "Review & Governance", icon: ShieldCheck },
  { to: "/authoring-mode", label: "Authoring Mode", icon: PenSquare },
  { to: "/operations", label: "Operations", icon: Server },
];

export function Sidebar() {
  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r border-sidebar-active bg-sidebar text-sidebar-text">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand text-sm font-bold text-white">
          ABG
        </div>
        <div className="leading-tight">
          <div className="text-xs font-semibold uppercase tracking-wide text-white">
            Avis Budget Group
          </div>
          <div className="text-[11px] text-sidebar-textMuted">Knowledge System</div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3 py-2">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-active text-white"
                  : "text-sidebar-text hover:bg-sidebar-hover hover:text-white"
              )
            }
          >
            <Icon className="h-4 w-4" />
            <span className="truncate">{label}</span>
          </NavLink>
        ))}
      </nav>

      <button className="mx-3 mb-4 flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-sidebar-textMuted hover:bg-sidebar-hover hover:text-white">
        <ChevronsLeft className="h-4 w-4" />
        Collapse
      </button>
    </aside>
  );
}
