// TEMPORARY code-gate auth — replace with real auth later.
import { createContext, useContext, useState, type ReactNode } from "react";

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

interface AuthContextValue {
  user: User;
  isAuthenticated: boolean;
  login: (code: string) => boolean;
  logout: () => void;
}

const AUTH_KEY = "kb_auth";
const ACCESS_CODE = "amidreaming";

const AuthContext = createContext<AuthContextValue>({
  user: DEMO_USER,
  isAuthenticated: false,
  login: () => false,
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(
    () => sessionStorage.getItem(AUTH_KEY) === "1",
  );

  const login = (code: string): boolean => {
    if (code === ACCESS_CODE) {
      sessionStorage.setItem(AUTH_KEY, "1");
      setIsAuthenticated(true);
      return true;
    }
    return false;
  };

  const logout = () => {
    sessionStorage.removeItem(AUTH_KEY);
    setIsAuthenticated(false);
  };

  return (
    <AuthContext.Provider value={{ user: DEMO_USER, isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
