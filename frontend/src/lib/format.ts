export const fmtNum = (n: number | null | undefined) =>
  n == null ? "—" : new Intl.NumberFormat("en-US").format(n);

export const fmtPct = (n: number | null | undefined, digits = 1) =>
  n == null ? "—" : `${n.toFixed(digits)}%`;

export const fmtRelTime = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
};

export const fmtDate = (iso: string | null | undefined) =>
  !iso ? "—" : new Date(iso).toLocaleDateString();
