"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Loader2, Rocket, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { getAuthStatus, listDepartments, registerUser, type DepartmentDef } from "@/lib/erpApi";

/**
 * /setup — first-run setup for a brand-new instance.
 *
 * Creates the organisation's FIRST account, which the API automatically makes
 * an admin (see auth_routes.register). From there the admin creates departments
 * and invites the rest of the team at /settings/departments.
 *
 * If the instance already has users, this page steps aside and points at /login
 * — it can't be used to mint extra admins.
 */
export default function SetupPage() {
  const router = useRouter();
  const { signIn } = useAuth();

  const [checking, setChecking] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [depts, setDepts] = useState<DepartmentDef[]>([]);
  const [form, setForm] = useState({ name: "", email: "", password: "", department: "finance" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const s = await getAuthStatus();
        setNeedsSetup(s.needs_setup);
        if (s.needs_setup) {
          // Departments are readable pre-auth only after setup; fall back to the
          // known defaults so the picker is never empty on a fresh install.
          try {
            const d = await listDepartments();
            setDepts(d.departments);
          } catch {
            setDepts([
              { key: "program", name: "Program / M&E", description: "", order: 10, is_final_authority: false },
              { key: "compliance", name: "Compliance", description: "", order: 20, is_final_authority: false },
              { key: "finance", name: "Finance", description: "", order: 30, is_final_authority: false },
              { key: "management", name: "Management", description: "", order: 40, is_final_authority: true },
            ]);
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not reach the server.");
      } finally {
        setChecking(false);
      }
    })();
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await registerUser({
        email: form.email.trim(),
        name: form.name.trim(),
        password: form.password,
        department: form.department,
      });
      // Sign straight in so the first run lands on the dashboard, not a login wall.
      const res = await signIn(form.email.trim(), form.password);
      router.push(res.ok ? "/dashboard" : "/login");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the account.");
      setBusy(false);
    }
  }

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#fafaf7] text-sm text-gray-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Checking setup…
      </div>
    );
  }

  if (!needsSetup) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#fafaf7] px-4">
        <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-6 text-center shadow-sm">
          <ShieldCheck className="mx-auto h-8 w-8 text-emerald-500" />
          <h1 className="mt-3 text-base font-semibold text-gray-900">Already set up</h1>
          <p className="mt-1 text-sm text-gray-500">
            This workspace already has an administrator.
          </p>
          <Link
            href="/login"
            className="mt-4 inline-flex w-full items-center justify-center rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700"
          >
            Go to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#fafaf7] px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <span className="text-2xl font-bold tracking-tight text-brand-600">DOCex</span>
          <p className="mt-1 text-[11px] font-medium uppercase tracking-wide text-gray-400">
            First-run setup
          </p>
        </div>

        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="mb-5 flex items-center gap-2">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
              <Rocket className="h-4 w-4" />
            </span>
            <div>
              <h1 className="text-base font-semibold text-gray-900">Create your admin account</h1>
              <p className="text-xs text-gray-500">
                The first account runs the workspace — you&apos;ll add departments and your team next.
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <Field label="Your name">
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Bola Adeyemi"
                className={inputCls}
                required
              />
            </Field>
            <Field label="Work email">
              <input
                type="email"
                autoComplete="username"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="you@org.org"
                className={inputCls}
                required
              />
            </Field>
            <Field label="Password">
              <input
                type="password"
                autoComplete="new-password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder="At least 6 characters"
                minLength={6}
                className={inputCls}
                required
              />
            </Field>
            <Field label="Your department">
              <select
                value={form.department}
                onChange={(e) => setForm({ ...form, department: e.target.value })}
                className={inputCls}
              >
                {depts.map((d) => (
                  <option key={d.key} value={d.key}>{d.name}</option>
                ))}
              </select>
            </Field>

            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-60"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              Create workspace
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-[11px] text-gray-400">
          Already have an account? <Link href="/login" className="text-brand-600">Sign in</Link>
        </p>
      </div>
    </div>
  );
}

const inputCls =
  "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-gray-700">{label}</label>
      {children}
    </div>
  );
}
