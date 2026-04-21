// MOCK AUTH — replace with real auth later. Static demo user.
import { createContext, useContext, type ReactNode } from "react";

export interface User {
  id: string;
  name: string;
  email: string;
  role: "reviewer" | "editor" | "admin";
  initials: string;
}

const DEMO_USER: User = {
  id: "u-demo",
  name: "Demo User",
  email: "demo@abg.local",
  role: "reviewer",
  initials: "DU",
};

const AuthContext = createContext<{ user: User }>({ user: DEMO_USER });

export function AuthProvider({ children }: { children: ReactNode }) {
  return <AuthContext.Provider value={{ user: DEMO_USER }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
