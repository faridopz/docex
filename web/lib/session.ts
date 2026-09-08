/**
 * Session + authenticated fetch for the ERP workflow API.
 *
 * The backend (auth.py) issues an HMAC-signed bearer token on login. We keep
 * it (and the current user) in localStorage and attach it to every workflow
 * request. On a 401 we clear the session so the app bounces to /login.
 */
import { friendlyError } from "@/lib/errors";
import type { AuthUser } from "@/types/erp";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "docex.session.token";
const USER_KEY = "docex.session.user";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: AuthUser): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    /* storage unavailable — session lasts for this tab only */
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

/**
 * fetch() wrapper that injects the bearer token and maps errors to friendly
 * messages. `auth: false` skips the token (login/register bootstrap).
 */
export async function apiFetch<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, headers, ...rest } = init;
  const h = new Headers(headers);
  // FormData must set its own Content-Type: the browser appends the multipart
  // boundary, and overriding it here would make the body unparseable.
  const isFormData = typeof FormData !== "undefined" && rest.body instanceof FormData;
  if (!h.has("Content-Type") && rest.body && !isFormData) {
    h.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = getToken();
    if (token) h.set("Authorization", `Bearer ${token}`);
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...rest, headers: h });
  } catch (e) {
    const fe = friendlyError(0, String(e));
    throw Object.assign(new Error(fe.message), { cause: e, reason: fe.reason });
  }

  if (res.status === 401) {
    clearSession();
  }
  // A one-time password is still a valid session — it just cannot reach
  // anything except the change-password screen. Signing the user out here
  // would throw away the credential they are in the middle of replacing, so
  // this redirects instead of clearing.
  if (res.status === 403) {
    const raw = await res.clone().text().catch(() => "");
    if (raw.includes("must_change_password")) {
      try {
        if (
          typeof window !== "undefined" &&
          window.location.pathname !== "/change-password"
        ) {
          window.location.href = "/change-password";
        }
      } catch {
        /* non-browser context — fall through to the thrown error */
      }
    }
  }
  if (!res.ok) {
    const raw = await res.text().catch(() => "");
    const fe = friendlyError(res.status, raw);
    throw Object.assign(new Error(fe.message), { cause: raw, reason: fe.reason, status: res.status });
  }
  // 204 / empty bodies
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
