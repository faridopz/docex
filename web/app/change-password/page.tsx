"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { changeOwnPassword, passwordProblem } from "@/lib/userApi";
import { getToken, getStoredUser, setSession } from "@/lib/session";

/**
 * /change-password — the first screen most NEEM users will ever see.
 *
 * An administrator created their account with a one-time password, so until it
 * is replaced the API refuses every other route. That makes this page the
 * whole product for about forty seconds, which is a good reason to make it
 * calm and obvious rather than a security lecture.
 *
 * Deliberately NOT inside AppShell: the navigation would offer links to pages
 * the server is about to refuse, and a user's first impression of a finance
 * system should not be four things that do not work.
 */
export default function ChangePasswordPage() {
  const router = useRouter();
  const { user, ready } = useAuth();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const forced = user?.must_change_password === true;

  useEffect(() => {
    if (ready && !getToken()) router.replace("/login");
  }, [ready, router]);

  const problem = next ? passwordProblem(next) : null;
  const mismatch = confirm.length > 0 && next !== confirm;
  const canSubmit =
    !busy && current.length > 0 && next.length > 0 && !problem && !mismatch;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const res = await changeOwnPassword(current, next);
      // The server revoked every session, including ours, and handed back a
      // replacement. Store it before navigating or the next request 401s.
      const stored = getStoredUser();
      if (res.token && stored) {
        setSession(res.token, { ...stored, must_change_password: false });
      }
      setDone(true);
      setTimeout(() => {
        window.location.href = "/dashboard";
      }, 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the password.");
    } finally {
      setBusy(false);
    }
  }

  if (!ready) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50">
        <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
          <div className="mb-6 flex items-start gap-3">
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50">
              <KeyRound className="h-4 w-4 text-blue-600" />
            </span>
            <div>
              <h1 className="text-lg font-semibold text-gray-900">
                {forced ? "Set your password" : "Change your password"}
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                {forced ? (
                  <>
                    The password you were given works once. Choose your own and
                    nobody else — including whoever set up your account — will
                    know it.
                  </>
                ) : (
                  <>
                    You will be signed out on every other device. That is
                    deliberate: if someone else had your password, this ends it.
                  </>
                )}
              </p>
            </div>
          </div>

          {done ? (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              <ShieldCheck className="h-4 w-4 shrink-0" />
              Password set. Taking you to your dashboard…
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <Field
                label={forced ? "The password you were given" : "Current password"}
                value={current}
                onChange={setCurrent}
                autoFocus
                autoComplete="current-password"
              />
              <div>
                <Field
                  label="New password"
                  value={next}
                  onChange={setNext}
                  autoComplete="new-password"
                />
                <p
                  className={`mt-1.5 text-xs ${
                    problem ? "text-amber-700" : "text-gray-500"
                  }`}
                >
                  {problem ??
                    "At least 10 characters, mixing letters with numbers or punctuation."}
                </p>
              </div>
              <div>
                <Field
                  label="Confirm new password"
                  value={confirm}
                  onChange={setConfirm}
                  autoComplete="new-password"
                />
                {mismatch && (
                  <p className="mt-1.5 text-xs text-amber-700">
                    These do not match.
                  </p>
                )}
              </div>

              {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={!canSubmit}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
              >
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                Set password
              </button>
            </form>
          )}
        </div>

        {forced && (
          <p className="mt-4 text-center text-xs text-gray-400">
            Signed in as {user?.email}
          </p>
        )}
      </div>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
  autoFocus,
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  autoFocus?: boolean;
  autoComplete?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-gray-700">{label}</span>
      <input
        type="password"
        value={value}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
      />
    </label>
  );
}
