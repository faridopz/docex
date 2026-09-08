"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertCircle,
  Check,
  Copy,
  Loader2,
  ShieldCheck,
  ShieldOff,
  Smartphone,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import {
  beginMfa,
  confirmMfa,
  disableMfa,
  getMfaStatus,
  qrImageUrl,
  regenerateRecoveryCodes,
  setMfaPolicy,
  type MfaSetup,
  type MfaStatus,
} from "@/lib/mfaApi";

/**
 * /settings/security — where a person turns on two-factor authentication, and
 * where an administrator decides who has to.
 *
 * The screen is built around the two moments that go wrong. Enrolment is two
 * steps, because a secret that went live the instant it was created would lock
 * out anyone whose app failed to scan it — and the people required to use this
 * are the ones who approve payments. And the recovery codes are shown in a
 * panel that must be dismissed deliberately, never a toast, because they are
 * shown exactly once and losing them means an admin reset.
 */
export default function SecurityPage() {
  const { user, ready } = useAuth();
  const params = useSearchParams();
  const isAdmin = user?.role === "admin";

  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [copied, setCopied] = useState(false);
  const [disabling, setDisabling] = useState(false);

  async function refresh() {
    setStatus(await getMfaStatus());
  }

  useEffect(() => {
    if (!ready) return;
    refresh()
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load."))
      .finally(() => setLoading(false));
  }, [ready]);

  // Arrived from sign-in because this role must enrol — start immediately
  // rather than making them find the button.
  useEffect(() => {
    if (params.get("setup") === "1" && status && !status.enrolled && !setup) {
      void start();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      setSetup(await beginMfa());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start setup.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await confirmMfa(code);
      setCodes(res.recovery_codes);
      setSetup(null);
      setCode("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That code was not accepted.");
    } finally {
      setBusy(false);
    }
  }

  async function turnOff(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await disableMfa(code);
      setCode("");
      setDisabling(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That code was not accepted.");
    } finally {
      setBusy(false);
    }
  }

  async function newCodes() {
    if (!confirm2("Issue ten new recovery codes? Every existing code stops working.")) return;
    setBusy(true);
    try {
      setCodes((await regenerateRecoveryCodes()).recovery_codes);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not regenerate.");
    } finally {
      setBusy(false);
    }
  }

  async function togglePolicy(enabled: boolean) {
    setBusy(true);
    try {
      await setMfaPolicy({ enabled });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change the policy.");
    } finally {
      setBusy(false);
    }
  }

  if (loading || !status) {
    return (
      <AppShell>
        <div className="flex items-center gap-2 px-6 py-16 text-sm text-gray-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-2xl px-6 py-8">
        <header className="mb-6">
          <h1 className="text-xl font-semibold text-gray-900">Security</h1>
          <p className="mt-1 text-sm text-gray-500">
            Two-factor authentication is the only control that still protects
            you after a password has leaked.
          </p>
        </header>

        {error && (
          <div className="mb-6 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {codes && (
          <RecoveryCodes
            codes={codes}
            copied={copied}
            onCopy={() => {
              navigator.clipboard?.writeText(codes.join("\n"));
              setCopied(true);
            }}
            onClose={() => {
              setCodes(null);
              setCopied(false);
            }}
          />
        )}

        {/* ── enrolled ── */}
        {status.enrolled && !codes && (
          <section className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 p-5">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
              <div className="flex-1">
                <h2 className="text-sm font-semibold text-emerald-900">
                  Two-factor authentication is on
                </h2>
                <p className="mt-1 text-xs text-emerald-800">
                  {status.enrolled_at && `Since ${status.enrolled_at.slice(0, 10)}. `}
                  {status.recovery_codes_left} recovery code
                  {status.recovery_codes_left === 1 ? "" : "s"} left.
                  {status.recovery_codes_left <= 2 && (
                    <span className="font-medium"> Worth generating more.</span>
                  )}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    onClick={newCodes}
                    disabled={busy}
                    className="rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-xs font-medium text-emerald-800 transition hover:bg-emerald-100"
                  >
                    New recovery codes
                  </button>
                  {!status.required_for_you && (
                    <button
                      onClick={() => setDisabling(true)}
                      disabled={busy}
                      className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-50"
                    >
                      Turn off
                    </button>
                  )}
                </div>
                {status.required_for_you && (
                  <p className="mt-2 text-[11px] text-emerald-700">
                    Required for your role — it cannot be turned off here. An
                    administrator can reset it if you lose your phone.
                  </p>
                )}
              </div>
            </div>

            {disabling && (
              <form onSubmit={turnOff} className="mt-4 flex items-end gap-2 border-t border-emerald-200 pt-4">
                <label className="flex-1">
                  <span className="mb-1 block text-xs font-medium text-emerald-900">
                    Enter a current code to confirm
                  </span>
                  <input
                    inputMode="numeric"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="123456"
                    className="w-full rounded-lg border border-emerald-300 px-3 py-2 text-sm outline-none focus:border-emerald-500"
                    required
                  />
                </label>
                <button
                  type="submit"
                  disabled={busy}
                  className="rounded-lg bg-red-600 px-3 py-2 text-xs font-medium text-white hover:bg-red-700 disabled:bg-gray-300"
                >
                  <ShieldOff className="mr-1 inline h-3.5 w-3.5" />
                  Turn off
                </button>
              </form>
            )}
          </section>
        )}

        {/* ── not enrolled ── */}
        {!status.enrolled && !codes && (
          <section className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3">
              <Smartphone className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" />
              <div className="flex-1">
                <h2 className="text-sm font-semibold text-gray-900">
                  Set up two-factor authentication
                </h2>
                <p className="mt-1 text-xs text-gray-500">
                  {status.required_for_you ? (
                    <span className="text-amber-700">
                      Required for your role — you can approve payments.
                    </span>
                  ) : (
                    "Recommended. A stolen password is not enough to sign in as you."
                  )}
                </p>

                {!setup ? (
                  <button
                    onClick={start}
                    disabled={busy}
                    className="mt-3 flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:bg-gray-300"
                  >
                    {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                    Get started
                  </button>
                ) : (
                  <div className="mt-4">
                    <ol className="space-y-4 text-sm text-gray-700">
                      <li>
                        <span className="font-medium">1.</span> Install an
                        authenticator app — Google Authenticator, Microsoft
                        Authenticator or 1Password all work.
                      </li>
                      <li>
                        <span className="font-medium">2.</span> Scan this:
                        <div className="mt-2 flex flex-wrap items-start gap-4">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={qrImageUrl(setup.uri)}
                            alt="QR code for your authenticator app"
                            width={180}
                            height={180}
                            className="rounded-lg border border-gray-200"
                          />
                          <div className="text-xs text-gray-500">
                            <p className="mb-1">Or type this in by hand:</p>
                            <code className="select-all break-all rounded border border-gray-200 bg-gray-50 px-2 py-1 font-mono text-[11px] text-gray-800">
                              {setup.secret}
                            </code>
                            <p className="mt-2 text-[11px]">
                              Prefer not to use the QR image? Typing the code
                              above does exactly the same thing.
                            </p>
                          </div>
                        </div>
                      </li>
                      <li>
                        <span className="font-medium">3.</span> Enter the
                        6-digit code it shows:
                        <form onSubmit={confirm} className="mt-2 flex items-center gap-2">
                          <input
                            inputMode="numeric"
                            autoComplete="one-time-code"
                            value={code}
                            onChange={(e) => setCode(e.target.value)}
                            placeholder="123456"
                            className="w-36 rounded-lg border border-gray-300 px-3 py-2 text-center text-lg tracking-[0.3em] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                            required
                          />
                          <button
                            type="submit"
                            disabled={busy}
                            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:bg-gray-300"
                          >
                            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                            Confirm
                          </button>
                        </form>
                      </li>
                    </ol>
                    <p className="mt-4 text-[11px] text-gray-400">
                      Nothing changes until you confirm — if the scan did not
                      work, you are not locked out.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </section>
        )}

        {/* ── admin policy ── */}
        {isAdmin && (
          <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-900">
              Organisation policy
            </h2>
            <p className="mt-1 text-xs text-gray-500">
              Currently{" "}
              <span className="font-medium">
                {status.policy.enabled ? "required" : "optional"}
              </span>
              {status.policy.enabled &&
                ` for ${status.policy.required_roles.join(" and ")}`}
              .
            </p>
            <button
              onClick={() => togglePolicy(!status.policy.enabled)}
              disabled={busy}
              className="mt-3 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50"
            >
              {status.policy.enabled ? "Make it optional" : "Require it for approvers and admins"}
            </button>
            <p className="mt-3 text-[11px] text-gray-400">
              Applies to people who can authorise payment. Viewers and reviewers
              are not asked — a control that feels gratuitous is one people work
              around. Anyone locked out can be reset from People &amp; access.
            </p>
          </section>
        )}
      </div>
    </AppShell>
  );
}

function confirm2(message: string): boolean {
  return typeof window === "undefined" ? true : window.confirm(message);
}

function RecoveryCodes({
  codes,
  copied,
  onCopy,
  onClose,
}: {
  codes: string[];
  copied: boolean;
  onCopy: () => void;
  onClose: () => void;
}) {
  return (
    <div className="mb-6 rounded-xl border border-amber-300 bg-amber-50 p-5">
      <h3 className="text-sm font-semibold text-amber-900">
        Save these recovery codes now
      </h3>
      <p className="mt-1 text-xs text-amber-800">
        Each one works once, and they are the only way back in if you lose your
        phone. Keep them somewhere other than that phone. They are shown now and
        never again.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-5">
        {codes.map((c) => (
          <code
            key={c}
            className="select-all rounded border border-amber-200 bg-white px-2 py-1.5 text-center font-mono text-xs text-gray-900"
          >
            {c}
          </code>
        ))}
      </div>
      <div className="mt-4 flex gap-2">
        <button
          onClick={onCopy}
          className="flex items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 transition hover:bg-amber-100"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy all"}
        </button>
        <button
          onClick={onClose}
          className="rounded-lg px-3 py-1.5 text-xs font-medium text-amber-800 transition hover:bg-amber-100"
        >
          I have saved them
        </button>
      </div>
    </div>
  );
}
