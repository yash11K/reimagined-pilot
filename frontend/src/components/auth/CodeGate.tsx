import { useState, type FormEvent } from "react";
import { Lock } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

export default function CodeGate({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, login } = useAuth();
  const [code, setCode] = useState("");
  const [error, setError] = useState(false);

  if (isAuthenticated) return <>{children}</>;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!login(code.trim())) {
      setError(true);
      setCode("");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <form
        onSubmit={handleSubmit}
        className="mx-4 flex w-full max-w-sm flex-col items-center gap-5 rounded-xl bg-bg-surface p-8 shadow-card"
      >
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-soft">
          <Lock className="h-7 w-7 text-brand" />
        </div>

        <h1 className="text-xl font-semibold text-ink">Enter Access Code</h1>

        <input
          type="password"
          value={code}
          onChange={(e) => {
            setCode(e.target.value);
            setError(false);
          }}
          placeholder="Access code"
          autoFocus
          className="w-full rounded-lg border border-line bg-bg-surface px-4 py-2.5 text-sm text-ink placeholder-ink-faint outline-none focus:border-brand focus:ring-1 focus:ring-brand/40"
        />

        {error && (
          <p className="text-sm text-status-err">Invalid code. Try again.</p>
        )}

        <button
          type="submit"
          className="w-full rounded-lg bg-brand py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:ring-offset-1"
        >
          Unlock
        </button>
      </form>
    </div>
  );
}
