"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Loader2, Lock, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { getAuthStatus } from "@/lib/erpApi";

/**
 * /login — the real sign-in screen. Authenticates against POST /auth/login,
 * stores the session token, and routes to /dashboard. If a user is already
 * signed in, bounce them straight there.
 */
export default function LoginPage() {
  const router = useRouter();
  const { signIn, user, ready } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Second step. Only shown once the server has confirmed the password was
  // right and this account has a second factor — asking for a code first would
  // tell an attacker which accounts exist and which of them approve payments.
  const [mfaCode, setMfaCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  // Whether this instance has been set up. Starts null (unknown) so the
  // "set up a workspace" link never flashes before we know it is wrong.
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);

  useEffect(() => {
    if (!ready || !user) return;
    // Somebody still on the one-time password an administrator gave them: the
    // API will refuse the dashboard anyway, so send them somewhere that works.
    router.replace(user.must_change_password ? "/change-password" : "/dashboard");
  }, [ready, user, router]);

  // A brand-new instance has no accounts yet — send the first person to setup
  // rather than a sign-in form they could never pass.
  useEffect(() => {
    (async () => {
      try {
        const s = await getAuthStatus();
        setNeedsSetup(s.needs_setup);
        if (s.needs_setup) router.replace("/setup");
      } catch {
        /* offline/unreachable API — leave the form up */
      }
    })();
  }, [router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const res = await signIn(email, password, needsCode ? mfaCode : undefined);
    if (!res.ok) {
      if (res.mfaRequired) {
        setNeedsCode(true);
        // A fresh attempt is a fresh code — leaving the old one in the box is
        // how somebody resubmits a code that has already been spent.
        setMfaCode("");
        setError(needsCode ? (res.error ?? "That code was not accepted.") : null);
      } else {
        setNeedsCode(false);
        setError(res.error ?? "Sign in failed.");
      }
      setBusy(false);
      return;
    }
    if (res.mustChangePassword) router.push("/change-password");
    else if (res.mfaSetupRequired) router.push("/settings/security?setup=1");
    else router.push("/dashboard");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#fafaf7] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="text-2xl font-bold tracking-tight text-brand-600">
            DOCex
          </span>
          <p className="mt-1 text-[11px] font-medium uppercase tracking-wide text-gray-400">
            Audit-grade compliance
          </p>
        </div>

        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="mb-5 flex items-center gap-2">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
              <Lock className="h-4 w-4" />
            </span>
            <div>
              <h1 className="text-base font-semibold text-gray-900">Sign in</h1>
              <p className="text-xs text-gray-500">Access your department workspace</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Email
              </label>
              <input
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@org.com"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Password
              </label>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                required
              />
            </div>

            {needsCode && (
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  6-digit code
                </label>
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  autoFocus
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  placeholder="123456"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-center text-lg tracking-[0.4em] text-gray-900 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                  required
                />
                <p className="mt-1.5 text-[11px] text-gray-500">
                  From your authenticator app. Lost your phone? Use one of your
                  recovery codes instead.
                </p>
              </div>
            )}

            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              Sign in
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-[11px] text-gray-400">
          Signed in per user · your department decides what you see
          {/* Only on a brand-new instance. On a client's live system twenty
              people see this screen, and an invitation to "set up a workspace"
              reads as "create your own account" — which they cannot do, and
              should not try. Their administrator issues accounts. */}
          {needsSetup === true && (
            <>
              <br />
              Setting up a new workspace?{" "}
              <Link href="/setup" className="text-brand-600">Start here</Link>
            </>
          )}
          {needsSetup === false && (
            <>
              <br />
              No account yet? Your organisation&apos;s administrator creates it.
            </>
          )}
        </p>
      </div>
    </div>
  );
}
