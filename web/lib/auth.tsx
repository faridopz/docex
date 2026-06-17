"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

/**
 * Lightweight DEMO authentication — a front door, NOT real auth.
 *
 * This gates the in-product UI behind a sign-in screen so the app looks
 * access-controlled during a demo. It is purely client-side: credentials are
 * checked against the hardcoded list below and a session flag is kept in
 * localStorage. There is NO backend, NO database, and NO per-user data
 * isolation — everyone who signs in sees the same single instance.
 *
 * Real authentication (Supabase auth + org_id isolation) is the Phase 2
 * "Trust" build and will replace this file. Do not mistake this for security.
 *
 * To add or change accounts, edit DEMO_ACCOUNTS and redeploy.
 */

export type DemoUser = { email: string; name: string };

type Account = { email: string; password: string; name: string };

const DEMO_ACCOUNTS: Account[] = [
  { email: "demo@docex.app", password: "docex-demo", name: "Demo User" },
];

const STORAGE_KEY = "docex.demo.session";

type AuthState = {
  ready: boolean; // true once we've read localStorage (prevents redirect flash)
  user: DemoUser | null;
  signIn: (email: string, password: string) => { ok: boolean; error?: string };
  signOut: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<DemoUser | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as DemoUser;
        if (parsed?.email) setUser(parsed);
      }
    } catch {
      /* corrupt/unavailable storage — treat as signed out */
    }
    setReady(true);
  }, []);

  function signIn(email: string, password: string) {
    const e = email.trim().toLowerCase();
    const match = DEMO_ACCOUNTS.find(
      (a) => a.email.toLowerCase() === e && a.password === password,
    );
    if (!match) return { ok: false, error: "Incorrect email or password." };
    const u: DemoUser = { email: match.email, name: match.name };
    setUser(u);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(u));
    } catch {
      /* storage unavailable — session lasts for this tab only */
    }
    return { ok: true };
  }

  function signOut() {
    setUser(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }

  return (
    <AuthContext.Provider value={{ ready, user, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

/** First demo account — used by the login screen's "Use demo account" helper. */
export const DEMO_LOGIN_HINT = { email: DEMO_ACCOUNTS[0].email, password: DEMO_ACCOUNTS[0].password };
