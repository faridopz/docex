"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  Copy,
  KeyRound,
  Loader2,
  ShieldOff,
  UserPlus,
  Users,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import { listDepartments, type DepartmentDef } from "@/lib/erpApi";
import { deptLabel, cacheDepartmentLabels } from "@/lib/erpFormat";
import {
  inviteUser,
  listUsers,
  resetUserPassword,
  setUserActive,
  updateUser,
  type InviteResult,
} from "@/lib/userApi";
import type { AuthUser, Department, Role } from "@/types/erp";

/**
 * /settings/users — the screen an organisation's administrator lives in on
 * day one, and visits about four times a year afterwards.
 *
 * The design follows what actually happens: someone sits down and creates
 * fifteen to twenty accounts in one sitting, reading each temporary password
 * out to a colleague or pasting it into a message. So the invite form stays
 * open and resets itself after each person, and the password appears in a
 * panel that must be dismissed deliberately — losing it costs a reset, and a
 * toast that fades after three seconds would cause that constantly.
 *
 * "Never signed in" is called out because the useful question a week later is
 * not who has an account, it is who never started.
 */

const ROLES: { value: Role; label: string; hint: string }[] = [
  { value: "viewer", label: "Viewer", hint: "Can see work, cannot act on it" },
  { value: "reviewer", label: "Reviewer", hint: "Moves work along; cannot release payment" },
  { value: "approver", label: "Approver", hint: "Can authorise payment" },
  { value: "admin", label: "Administrator", hint: "All of the above, plus accounts and settings" },
];

export default function UsersSettingsPage() {
  const { user, ready } = useAuth();
  const isAdmin = user?.role === "admin";

  const [users, setUsers] = useState<AuthUser[]>([]);
  const [depts, setDepts] = useState<DepartmentDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: "",
    email: "",
    department: "",
    role: "reviewer" as Role,
  });
  const [inviting, setInviting] = useState(false);
  const [issued, setIssued] = useState<InviteResult | null>(null);
  const [copied, setCopied] = useState(false);

  async function refresh() {
    const [u, d] = await Promise.all([listUsers(), listDepartments()]);
    setUsers(u);
    setDepts(d.departments);
    cacheDepartmentLabels(d.departments);
    setForm((f) => ({ ...f, department: f.department || d.departments[0]?.key || "" }));
  }

  useEffect(() => {
    if (!ready) return;
    if (!isAdmin) {
      setLoading(false);
      return;
    }
    refresh()
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load users."))
      .finally(() => setLoading(false));
  }, [ready, isAdmin]);

  const { active, inactive, neverSignedIn } = useMemo(() => {
    const a = users.filter((u) => u.active !== false);
    return {
      active: a,
      inactive: users.filter((u) => u.active === false),
      neverSignedIn: a.filter((u) => !u.last_login_at).length,
    };
  }, [users]);

  async function submitInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!form.email.trim() || !form.department) return;
    setInviting(true);
    setError(null);
    try {
      const res = await inviteUser({
        email: form.email.trim(),
        name: form.name.trim(),
        department: form.department as Department,
        role: form.role,
      });
      setIssued(res);
      setCopied(false);
      // Keep the department and role — the next three people are usually in
      // the same team, and retyping it fifteen times is how mistakes happen.
      setForm((f) => ({ ...f, name: "", email: "" }));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the account.");
    } finally {
      setInviting(false);
    }
  }

  async function doReset(u: AuthUser) {
    if (!confirm(`Issue a new one-time password for ${u.email}? Their current password stops working immediately.`)) return;
    setBusyId(u.id);
    setError(null);
    try {
      setIssued(await resetUserPassword(u.id));
      setCopied(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset the password.");
    } finally {
      setBusyId(null);
    }
  }

  async function toggleActive(u: AuthUser) {
    const disabling = u.active !== false;
    if (
      disabling &&
      !confirm(
        `End ${u.email}'s access now? Their record and approval history are kept — only sign-in stops.`,
      )
    )
      return;
    setBusyId(u.id);
    setError(null);
    try {
      await setUserActive(u.id, !disabling);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the account.");
    } finally {
      setBusyId(null);
    }
  }

  async function changeField(u: AuthUser, changes: { department?: Department; role?: Role }) {
    setBusyId(u.id);
    setError(null);
    try {
      await updateUser(u.id, changes);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the account.");
    } finally {
      setBusyId(null);
    }
  }

  if (ready && !isAdmin) {
    return (
      <AppShell>
        <div className="mx-auto max-w-2xl px-6 py-16 text-center">
          <Users className="mx-auto h-8 w-8 text-gray-300" />
          <h1 className="mt-4 text-lg font-semibold text-gray-900">Accounts</h1>
          <p className="mt-2 text-sm text-gray-500">
            Only an administrator can manage accounts. Ask whoever set up DOCex
            for your organisation.
          </p>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-6 py-8">
        <header className="mb-6">
          <h1 className="text-xl font-semibold text-gray-900">People</h1>
          <p className="mt-1 text-sm text-gray-500">
            {active.length} active
            {inactive.length > 0 && ` · ${inactive.length} deactivated`}
            {neverSignedIn > 0 && (
              <span className="text-amber-700">
                {" "}
                · {neverSignedIn} never signed in
              </span>
            )}
          </p>
        </header>

        {error && (
          <div className="mb-6 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {issued && <PasswordPanel issued={issued} copied={copied} setCopied={setCopied} onClose={() => setIssued(null)} />}

        {/* ── invite ── */}
        <section className="mb-8 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-900">
            <UserPlus className="h-4 w-4 text-blue-600" />
            Add someone
          </h2>
          <form onSubmit={submitInvite} className="grid gap-3 sm:grid-cols-5">
            <input
              placeholder="Full name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
            <input
              placeholder="name@organisation.org"
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
            <select
              value={form.department}
              onChange={(e) => setForm({ ...form, department: e.target.value })}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
            >
              {depts.map((d) => (
                <option key={d.key} value={d.key}>
                  {d.name}
                </option>
              ))}
            </select>
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={inviting}
              className="flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:bg-gray-300"
            >
              {inviting && <Loader2 className="h-4 w-4 animate-spin" />}
              Create
            </button>
          </form>
          <p className="mt-3 text-xs text-gray-500">
            {ROLES.find((r) => r.value === form.role)?.hint}. DOCex generates a
            one-time password and shows it once — you pass it on, they replace
            it the first time they sign in.
          </p>
        </section>

        {/* ── the list ── */}
        {loading ? (
          <div className="flex items-center gap-2 py-12 text-sm text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading accounts…
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Person</th>
                  <th className="px-4 py-3 font-medium">Department</th>
                  <th className="px-4 py-3 font-medium">Role</th>
                  <th className="px-4 py-3 font-medium">Last signed in</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {[...active, ...inactive].map((u) => {
                  const disabled = u.active === false;
                  const busy = busyId === u.id;
                  return (
                    <tr key={u.id} className={disabled ? "bg-gray-50/60 text-gray-400" : ""}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900">
                          {u.name}
                          {u.id === user?.id && (
                            <span className="ml-2 text-xs font-normal text-gray-400">you</span>
                          )}
                        </div>
                        <div className="text-xs text-gray-500">{u.email}</div>
                        {u.must_change_password && !disabled && (
                          <span className="mt-1 inline-block rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-700">
                            has not set their own password
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={u.department}
                          disabled={busy || disabled}
                          onChange={(e) =>
                            changeField(u, { department: e.target.value as Department })
                          }
                          className="rounded border border-transparent bg-transparent px-1 py-0.5 text-sm hover:border-gray-300 focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed"
                        >
                          {depts.map((d) => (
                            <option key={d.key} value={d.key}>
                              {d.name}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={u.role}
                          disabled={busy || disabled}
                          onChange={(e) => changeField(u, { role: e.target.value as Role })}
                          className="rounded border border-transparent bg-transparent px-1 py-0.5 text-sm hover:border-gray-300 focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed"
                        >
                          {ROLES.map((r) => (
                            <option key={r.value} value={r.value}>
                              {r.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {disabled ? (
                          <span className="text-gray-400">
                            deactivated{u.deactivated_at ? ` ${u.deactivated_at.slice(0, 10)}` : ""}
                          </span>
                        ) : u.last_login_at ? (
                          <span className="text-gray-600">{u.last_login_at.slice(0, 10)}</span>
                        ) : (
                          <span className="text-amber-700">never</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin text-gray-400" />}
                          {!disabled && (
                            <button
                              onClick={() => doReset(u)}
                              disabled={busy}
                              title="Issue a new one-time password"
                              className="rounded p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700"
                            >
                              <KeyRound className="h-4 w-4" />
                            </button>
                          )}
                          {u.id !== user?.id && (
                            <button
                              onClick={() => toggleActive(u)}
                              disabled={busy}
                              title={disabled ? "Restore access" : "End access"}
                              className={`rounded p-1.5 transition hover:bg-gray-100 ${
                                disabled
                                  ? "text-emerald-600 hover:text-emerald-700"
                                  : "text-gray-400 hover:text-red-600"
                              }`}
                            >
                              {disabled ? <Check className="h-4 w-4" /> : <ShieldOff className="h-4 w-4" />}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-4 text-xs text-gray-400">
          Accounts are never deleted. Ending access keeps the person&apos;s
          approval history intact, so DOCex can still say who authorised a
          payment after they have left.
        </p>
      </div>
    </AppShell>
  );
}

/**
 * The one-time password. Shown until dismissed, never fetched again.
 */
function PasswordPanel({
  issued,
  copied,
  setCopied,
  onClose,
}: {
  issued: InviteResult;
  copied: boolean;
  setCopied: (v: boolean) => void;
  onClose: () => void;
}) {
  return (
    <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-blue-900">
            One-time password for {issued.user.email}
          </h3>
          <p className="mt-1 text-xs text-blue-800">{issued.note}</p>
          <div className="mt-3 flex items-center gap-2">
            <code className="select-all rounded-lg border border-blue-200 bg-white px-3 py-2 font-mono text-base tracking-wide text-gray-900">
              {issued.temporary_password}
            </code>
            <button
              onClick={() => {
                navigator.clipboard?.writeText(issued.temporary_password);
                setCopied(true);
              }}
              className="flex items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-700 transition hover:bg-blue-100"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium text-blue-700 transition hover:bg-blue-100"
        >
          Done
        </button>
      </div>
    </div>
  );
}
