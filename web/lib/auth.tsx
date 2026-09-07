"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { login as apiLogin } from "@/lib/erpApi";
import {
  apiFetch,
  clearSession,
  getStoredUser,
  getToken,
  setSession,
} from "@/lib/session";
import type { AuthUser } from "@/types/erp";

/**
 * DOCex authentication — real, backend-backed.
 *
 * Sign-in calls POST /auth/login (auth.py), which returns an HMAC-signed
 * bearer token + the user (with department + role). We keep both in
 * localStorage (see lib/session.ts) and attach the token to every workflow
 * request. On mount we restore the stored session and revalidate it against
 * /auth/me, clearing it if the token has expired or the user is gone.
 *
 * The exported shape (ready / user / signIn / signOut) is unchanged from the
 * previous demo provider, so existing pages (AppShell, login) keep working —
 * `user` now additionally carries `department` and `role`.
 */

type AuthState = {
  ready: boolean;
  user: AuthUser | null;
  signIn: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    // Restore optimistically from storage to avoid a redirect flash, then
    // revalidate against the server.
    const stored = getStoredUser();
    if (stored && getToken()) setUser(stored);

    (async () => {
      if (getToken()) {
        try {
          const me = await apiFetch<AuthUser>("/auth/me");
          setUser(me);
        } catch {
          // Token invalid/expired → session already cleared by apiFetch on 401.
          clearSession();
          setUser(null);
        }
      }
      setReady(true);
    })();
  }, []);

  async function signIn(email: string, password: string) {
    try {
      const { token, user: u } = await apiLogin(email.trim(), password);
      setSession(token, u);
      setUser(u);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : "Sign in failed." };
    }
  }

  async function signOut() {
    // Tell the server FIRST. Clearing localStorage only hides the token from
    // this browser — a token that was captured keeps working until it expires.
    // /auth/logout records a cutoff that kills every session this account
    // holds, so signing out actually means something.
    //
    // The local clear happens either way: if the network call fails, the user
    // still expects to be signed out here, and a session they cannot reach is
    // better than a confusing half-state.
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      /* offline, or already expired — clearing locally is still correct */
    }
    clearSession();
    setUser(null);
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
