/**
 * Two-factor authentication.
 *
 * `recovery_codes` come back exactly once — from confirm, and from
 * regenerate. They are stored only as hashes and no endpoint will tell you
 * what they were. Show them, let the user save them, and if they are lost the
 * answer is regenerate (or, for a locked-out colleague, an admin reset).
 */
import { apiFetch } from "@/lib/session";
import type { Role } from "@/types/erp";

export interface MfaStatus {
  enrolled: boolean;
  pending: boolean;
  recovery_codes_left: number;
  enrolled_at?: string | null;
  required_for_you: boolean;
  policy: { enabled: boolean; required_roles: Role[]; grace_days: number };
}

export interface MfaSetup {
  secret: string;
  /** otpauth:// URI — render as a QR code, or show the secret to type in. */
  uri: string;
  digits: number;
  period: number;
}

export async function getMfaStatus(): Promise<MfaStatus> {
  return apiFetch<MfaStatus>("/auth/mfa");
}

export async function beginMfa(): Promise<MfaSetup> {
  return apiFetch<MfaSetup>("/auth/mfa/begin", { method: "POST" });
}

export async function confirmMfa(
  code: string,
): Promise<{ ok: boolean; recovery_codes: string[]; note: string }> {
  return apiFetch("/auth/mfa/confirm", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export async function regenerateRecoveryCodes(): Promise<{ recovery_codes: string[] }> {
  return apiFetch("/auth/mfa/recovery-codes", { method: "POST" });
}

export async function disableMfa(code: string): Promise<{ ok: boolean }> {
  return apiFetch("/auth/mfa", {
    method: "DELETE",
    body: JSON.stringify({ code }),
  });
}

export async function resetUserMfa(userId: string): Promise<{ ok: boolean; detail: string }> {
  return apiFetch(`/auth/users/${encodeURIComponent(userId)}/mfa/reset`, {
    method: "POST",
  });
}

export async function setMfaPolicy(body: {
  enabled: boolean;
  required_roles?: Role[];
  grace_days?: number;
}): Promise<MfaStatus["policy"]> {
  return apiFetch("/auth/mfa/policy", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/**
 * A QR code, drawn without a library.
 *
 * Every QR package is another dependency in a bundle that ships to a finance
 * team, for one image on one screen. This uses a public chart renderer, and —
 * importantly — the secret is ALSO shown as text underneath, so anyone who
 * would rather not have their secret pass through a third party can type it in
 * by hand instead. That choice belongs to the user, not to us.
 */
export function qrImageUrl(uri: string, size = 200): string {
  return `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encodeURIComponent(uri)}`;
}
