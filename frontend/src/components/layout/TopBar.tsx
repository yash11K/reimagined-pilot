import { useState } from "react";
import { Search, Plus, Rocket, Bell } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useBrand, type BrandKey } from "@/contexts/BrandContext";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { NavTreePicker } from "@/components/ingest/NavTreePicker";

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
  const [q, setQ] = useState("");
  const [launchOpen, setLaunchOpen] = useState(false);

  const onSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // FAQ static search per spec
    if (q.trim().toLowerCase() === "faq") {
      navigate("/knowledge-library?search=FAQ");
    } else if (q.trim()) {
      navigate(`/knowledge-library?search=${encodeURIComponent(q)}`);
    }
  };

  return (
    <>
      <header className="flex h-16 shrink-0 items-center gap-4 border-b border-line bg-bg-surface px-6">
        <form onSubmit={onSearchSubmit} className="flex-1 max-w-xl">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder='Search policies, sources, owners, regions… (try "FAQ")'
              className="h-10 w-full rounded-lg border border-line bg-bg-muted pl-10 pr-3 text-sm text-ink placeholder:text-ink-faint focus:border-ink-soft focus:bg-bg-surface focus:outline-none focus:ring-2 focus:ring-ink/10"
            />
          </div>
        </form>

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
      </header>
      <NavTreePicker open={launchOpen} onClose={() => setLaunchOpen(false)} />
    </>
  );
}
