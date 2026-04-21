import { useState } from "react";
import { Plus, Rocket, Bell } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useBrand, type BrandKey } from "@/contexts/BrandContext";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { NavTreePicker } from "@/components/ingest/NavTreePicker";
import { GlobalSearch } from "./GlobalSearch";

const BRANDS: { key: BrandKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "abg", label: "ABG" },
  { key: "avis", label: "Avis" },
  { key: "budget", label: "Budget" },
];

export function TopBar() {
  const { brand, setBrand } = useBrand();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [launchOpen, setLaunchOpen] = useState(false);

  return (
    <>
      <header className="flex h-16 shrink-0 items-center gap-4 border-b border-line bg-bg-surface px-6">
        {/* Left: brand switcher */}
        <div className="flex items-center gap-1 rounded-lg border border-line bg-bg-muted p-1">
          {BRANDS.map((b) => (
            <button
              key={b.key}
              onClick={() => setBrand(b.key)}
              className={cn(
                "rounded-md px-3 py-1 text-xs font-semibold transition-colors",
                brand === b.key
                  ? "bg-bg-surface text-ink shadow-sm"
                  : "text-ink-muted hover:text-ink"
              )}
            >
              {b.label}
            </button>
          ))}
        </div>

        {/* Center: global search */}
        <div className="flex flex-1 justify-center">
          <GlobalSearch />
        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-2">
          <Button variant="outline" size="md" onClick={() => setLaunchOpen(true)}>
            <Rocket className="h-4 w-4" />
            Launch Ingestion
          </Button>

          <Button variant="primary" size="md" onClick={() => navigate("/authoring-mode")}>
            <Plus className="h-4 w-4" />
            Create Article
          </Button>

          <button className="grid h-9 w-9 place-items-center rounded-full text-ink-muted hover:bg-bg-muted hover:text-ink">
            <Bell className="h-4 w-4" />
          </button>

          <div className="grid h-9 w-9 place-items-center rounded-full bg-sidebar text-xs font-semibold text-white">
            {user.initials}
          </div>
        </div>
      </header>
      <NavTreePicker open={launchOpen} onClose={() => setLaunchOpen(false)} />
    </>
  );
}
