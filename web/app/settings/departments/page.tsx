"use client";

import { useEffect, useState } from "react";
import { Building2, Loader2, Plus, Trash2, UserPlus, Users } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import {
  createDepartment,
  deleteDepartment,
  listDepartments,
  listUsers,
  registerUser,
  setStateOwner,
  type DepartmentDef,
} from "@/lib/erpApi";
import { cacheDepartmentLabels, deptLabel, STATE_LABEL } from "@/lib/erpFormat";
import { getToken } from "@/lib/session";
import type { AuthUser, Role } from "@/types/erp";

/**
 * /settings/departments — the admin screen.
 *
 * Two jobs: define this organisation's departments (every org's org-chart
 * differs), and put people in them. Also routes each workflow stage to the
 * department that owns it, so approvals land in the right queue.
 * Admin-only; other roles see a clear message rather than a broken page.
 */

const ROUTABLE_STATES = [
  "submitted",
  "intake",
  "compliance_review",
  "finance_review",
  "approval",
  "paid",
];

const ROLES: Role[] = ["viewer", "reviewer", "approver", "admin"];

export default function DepartmentSettingsPage() {
  const { user, ready } = useAuth();
  const [depts, setDepts] = useState<DepartmentDef[]>([]);
  const [owners, setOwners] = useState<Record<string, string>>({});
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [newDept, setNewDept] = useState("");
  const [newUser, setNewUser] = useState({
    name: "", email: "", password: "", department: "", role: "reviewer" as Role,
  });

  const isAdmin = user?.role === "admin";

  async function refresh() {
    const d = await listDepartments();
    setDepts(d.departments);
    setOwners(d.state_owners);
    cacheDepartmentLabels(d.departments);
    if (isAdmin) {
      try {
        setUsers(await listUsers());
      } catch {
        /* non-fatal */
      }
    }
  }

  useEffect(() => {
    if (!ready || !user) return;
    (async () => {
      setLoading(true);
      try {
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load settings.");
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, user]);

  async function act<T>(fn: () => Promise<T>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't work.");
    } finally {
      setBusy(false);
    }
  }

  if (ready && user && !isAdmin) {
    return (
      <AppShell>
        <div className="mx-auto max-w-2xl px-6 py-16 text-center">
          <Building2 className="mx-auto h-8 w-8 text-gray-300" />
          <h1 className="mt-3 text-lg font-semibold text-gray-900">Admin only</h1>
          <p className="mt-1 text-sm text-gray-500">
            Departments and team members are managed by an administrator.
          </p>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-6 py-8">
        <header className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-600">Settings</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-gray-900">
            Departments &amp; team
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Set up your organisation&apos;s departments, decide which one owns each stage of the
            workflow, and add the people who work in them.
          </p>
        </header>

        {error && (
          <p className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</p>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-400">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : (
          <div className="space-y-6">
            {/* Departments */}
            <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 px-5 py-3">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900">
                  <Building2 className="h-4 w-4 text-gray-400" /> Departments
                </h2>
              </div>
              <ul className="divide-y divide-gray-50">
                {depts.map((d) => (
                  <li key={d.key} className="flex items-center gap-3 px-5 py-3">
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-gray-900">
                        {d.name}
                        {d.is_final_authority && (
                          <span className="ml-2 rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-semibold text-violet-700">
                            FINAL AUTHORITY
                          </span>
                        )}
                      </span>
                      <span className="block font-mono text-[11px] text-gray-400">{d.key}</span>
                    </span>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => act(() => deleteDepartment(d.key))}
                      className="text-gray-300 transition hover:text-red-500 disabled:opacity-40"
                      title="Delete department"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
              <div className="flex items-center gap-2 border-t border-gray-100 px-5 py-3">
                <input
                  value={newDept}
                  onChange={(e) => setNewDept(e.target.value)}
                  placeholder="New department, e.g. Executive Director"
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                />
                <button
                  type="button"
                  disabled={busy || !newDept.trim()}
                  onClick={() =>
                    act(async () => {
                      await createDepartment({ name: newDept.trim() });
                      setNewDept("");
                    })
                  }
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
                >
                  <Plus className="h-4 w-4" /> Add
                </button>
              </div>
            </section>

            {/* Workflow routing */}
            <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 px-5 py-3">
                <h2 className="text-sm font-semibold text-gray-900">Who owns each stage</h2>
                <p className="text-xs text-gray-400">
                  When an item reaches a stage, it lands in this department&apos;s queue and they get notified.
                </p>
              </div>
              <ul className="divide-y divide-gray-50">
                {ROUTABLE_STATES.map((s) => (
                  <li key={s} className="flex items-center gap-3 px-5 py-2.5">
                    <span className="flex-1 text-sm text-gray-900">
                      {STATE_LABEL[s as keyof typeof STATE_LABEL] ?? s}
                    </span>
                    <select
                      value={owners[s] ?? ""}
                      disabled={busy}
                      onChange={(e) => act(() => setStateOwner(s, e.target.value || null))}
                      className="rounded-lg border border-gray-300 px-2.5 py-1.5 text-sm outline-none transition focus:border-brand-400"
                    >
                      <option value="">— unassigned —</option>
                      {depts.map((d) => (
                        <option key={d.key} value={d.key}>{d.name}</option>
                      ))}
                    </select>
                  </li>
                ))}
              </ul>
            </section>

            {/* People */}
            <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 px-5 py-3">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900">
                  <Users className="h-4 w-4 text-gray-400" /> Team members
                </h2>
              </div>
              <ul className="divide-y divide-gray-50">
                {users.map((u) => (
                  <li key={u.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                    <span className="min-w-0 flex-1">
                      <span className="block font-medium text-gray-900">{u.name}</span>
                      <span className="block text-xs text-gray-400">{u.email}</span>
                    </span>
                    <span className="rounded-full bg-gray-50 px-2.5 py-0.5 text-xs text-gray-600 ring-1 ring-inset ring-gray-100">
                      {deptLabel(u.department)}
                    </span>
                    <span className="w-20 text-right text-xs font-medium capitalize text-gray-500">
                      {u.role}
                    </span>
                  </li>
                ))}
                {users.length === 0 && (
                  <li className="px-5 py-6 text-center text-xs text-gray-400">
                    No team members yet — add the first one below.
                  </li>
                )}
              </ul>

              <div className="grid grid-cols-1 gap-2 border-t border-gray-100 px-5 py-3 sm:grid-cols-5">
                <input
                  value={newUser.name}
                  onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
                  placeholder="Name"
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-brand-400"
                />
                <input
                  value={newUser.email}
                  onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                  placeholder="Email"
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-brand-400"
                />
                <input
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                  placeholder="Password"
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-brand-400"
                />
                <select
                  value={newUser.department}
                  onChange={(e) => setNewUser({ ...newUser, department: e.target.value })}
                  className="rounded-lg border border-gray-300 px-2 py-2 text-sm outline-none focus:border-brand-400"
                >
                  <option value="">Department…</option>
                  {depts.map((d) => (
                    <option key={d.key} value={d.key}>{d.name}</option>
                  ))}
                </select>
                <select
                  value={newUser.role}
                  onChange={(e) => setNewUser({ ...newUser, role: e.target.value as Role })}
                  className="rounded-lg border border-gray-300 px-2 py-2 text-sm outline-none focus:border-brand-400"
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
              <div className="px-5 pb-4">
                <button
                  type="button"
                  disabled={
                    busy || !newUser.name.trim() || !newUser.email.trim() ||
                    !newUser.password || !newUser.department
                  }
                  onClick={() =>
                    act(async () => {
                      await registerUser(
                        {
                          email: newUser.email.trim(),
                          name: newUser.name.trim(),
                          password: newUser.password,
                          department: newUser.department,
                          role: newUser.role,
                        },
                        getToken() ?? undefined,
                      );
                      setNewUser({ name: "", email: "", password: "", department: "", role: "reviewer" });
                    })
                  }
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
                >
                  <UserPlus className="h-4 w-4" /> Add team member
                </button>
                <p className="mt-2 text-[11px] text-gray-400">
                  Roles: <strong>viewer</strong> reads only · <strong>reviewer</strong> can move work
                  forward · <strong>approver</strong> can authorise payment · <strong>admin</strong> manages
                  the org.
                </p>
              </div>
            </section>
          </div>
        )}
      </div>
    </AppShell>
  );
}
