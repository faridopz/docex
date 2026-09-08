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
  signIn: (
    email: string,
    password: string,
    mfaCode?: string,
  ) => Promise<{
    ok: boolean;
    error?: string;
    mustChangePassword?: boolean;
    /** The server accepted the password and now wants the 6-digit code. */
    mfaRequired?: boolean;
    /** Signed in, but this role must enrol a second factor. */
    mfaSetupRequired?: boolean;
  }>;
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

  async function signIn(email: string, password: string, mfaCode?: string) {
    try {
      const res = await apiLogin(email.trim(), password, mfaCode);
      const { token, user: u } = res;
      setSession(token, u);
      setUser(u);
      // Flagged at the top level as well as on the user, because the caller
      // has to route on it immediately and should not have to know that the
      // answer is nested.
      return {
        ok: true,
        mustChangePassword: res.must_change_password ?? u.must_change_password ?? false,
        mfaSetupRequired: res.mfa_setup_required ?? false,
      };
    } catch (e) {
      // A 401 carrying the MFA flag is not a failed sign-in — it is the second
      // step. Passed through so the screen shows the code box rather than
      // "wrong password", which would be both wrong and alarming.
      const mfaRequired =
        typeof e === "object" && e !== null && "mfaRequired" in e
          ? Boolean((e as { mfaRequired?: boolean }).mfaRequired)
          : false;
      return {
        ok: false,
        mfaRequired,
        error: e instanceof Error ? e.message : "Sign in failed.",
      };
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
