import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type BrandKey = "all" | "abg" | "avis" | "budget";

interface Ctx {
  brand: BrandKey;
  setBrand: (b: BrandKey) => void;
  /** Returns brand value for API query, or undefined when "all". */
  brandParam: () => string | undefined;
}

const BrandContext = createContext<Ctx>({
  brand: "all",
  setBrand: () => {},
  brandParam: () => undefined,
});

const STORAGE_KEY = "abg.brand";

export function BrandProvider({ children }: { children: ReactNode }) {
  const [brand, setBrandState] = useState<BrandKey>(() => {
    const v = localStorage.getItem(STORAGE_KEY) as BrandKey | null;
    return v ?? "all";
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, brand);
  }, [brand]);

  const setBrand = (b: BrandKey) => setBrandState(b);

  // API uses exact match against DB-stored brand values.
  // "abg" is the UI key for "Avis Budget Group" but the DB stores "avis_budget".
  const BRAND_TO_API: Record<BrandKey, string | undefined> = {
    all: undefined,
    abg: "avis_budget",
    avis: "avis",
    budget: "budget",
  };
  const brandParam = () => BRAND_TO_API[brand];

  return (
    <BrandContext.Provider value={{ brand, setBrand, brandParam }}>
      {children}
    </BrandContext.Provider>
  );
}

export const useBrand = () => useContext(BrandContext);
