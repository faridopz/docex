/**
 * Administering an organisation's people.
 *
 * Everything here is admin-only on the server; the screen hides the controls
 * as a courtesy, not as the control. The one thing worth knowing as a caller:
 * `temporary_password` comes back exactly once, from invite and reset. It is
 * never stored in readable form and there is no endpoint that will tell you
 * what it was. Show it, let the administrator copy it, and if it is lost,
 * reset again.
 */
import { apiFetch } from "@/lib/session";
import type { AuthUser, Department, Role } from "@/types/erp";

export interface InviteResult {
  user: AuthUser;
  temporary_password: string;
  note: string;
}

export async function listUsers(): Promise<AuthUser[]> {
  const r = await apiFetch<{ users: AuthUser[] }>("/auth/users");
  return r.users ?? [];
}

export async function inviteUser(body: {
  email: string;
  name: string;
  department: Department;
  role: Role;
}): Promise<InviteResult> {
  return apiFetch<InviteResult>("/auth/users/invite", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function resetUserPassword(userId: string): Promise<InviteResult> {
  return apiFetch<InviteResult>(
    `/auth/users/${encodeURIComponent(userId)}/reset-password`,
    { method: "POST" },
  );
}

export async function setUserActive(userId: string, active: boolean): Promise<AuthUser> {
  return apiFetch<AuthUser>(
    `/auth/users/${encodeURIComponent(userId)}/${active ? "activate" : "deactivate"}`,
    { method: "POST" },
  );
}

export async function updateUser(
  userId: string,
  changes: { name?: string; department?: Department; role?: Role },
): Promise<AuthUser> {
  return apiFetch<AuthUser>(`/auth/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

/** Set your own password. Returns a fresh token, because the server has just
 *  revoked every session including the one that made this call. */
export async function changeOwnPassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ ok: boolean; token: string; detail: string }> {
  return apiFetch("/auth/password", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}

/** Mirrors auth.check_password_strength on the server, so the user sees the
 *  rule while typing rather than after a round trip. The server still decides
 *  — this is help, not enforcement. */
export function passwordProblem(pw: string): string | null {
  if (pw.length < 10) return "At least 10 characters.";
  const kinds = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length;
  if (kinds < 2) return "Mix letters with numbers or punctuation.";
  return null;
}
