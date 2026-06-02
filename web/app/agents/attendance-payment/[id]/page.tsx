"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Building2,
  CalendarDays,
  CheckCircle2,
  CircleDollarSign,
  Download,
  ExternalLink,
  FileSpreadsheet,
  Landmark,
  Link2,
  Loader2,
  ShieldAlert,
  Sparkles,
  Tag,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import {
  deleteAttendanceRun,
  exportAttendanceSchedule,
  getAttendanceRun,
  verifyAttendanceRun,
} from "@/lib/api";
import { AssistantBrief } from "@/components/AssistantBrief";
import { GuidanceCard } from "@/components/GuidanceCard";
import type {
  AttendancePaymentRun,
  AttendeeStatus,
  MatchedAttendee,
} from "@/types";

/**
 * /agents/attendance-payment/[id] — the review page.
 *
 * The composite agent's payoff screen. Three buckets:
 *   - Paid (green) — these will go on the schedule
 *   - No attendance (red) — registered but didn't show; blocked from payment
 *   - No bank info (amber) — attended but missing payment info; chase them
 *
 * Bottom of the page has two actions:
 *   - Download schedule.xlsx — the clean payment schedule
 *   - Verify accounts → routes through Bank Verify with one click
 *
 * The verify action is the most important moment in the agent — it's where
 * one product (Attendance Payment Co-Pilot) hands off to another (Bank Verify)
 * with no re-upload, no copy-paste. That's the agent thesis in motion.
 */

export default function AttendanceRunDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [run, setRun] = useState<AttendancePaymentRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bucket, setBucket] = useState<AttendeeStatus | "all">("paid");
  const [downloading, setDownloading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  // Accuracy gate: the user has to tick "I've reviewed the flags" before
  // the Verify button unlocks. This is the team's existing eyeball-check
  // ritual made explicit in the product — no surprise payments.
  const [flagsAcknowledged, setFlagsAcknowledged] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getAttendanceRun(id);
        if (!cancelled) setRun(data);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load this attendance run.",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleDownload() {
    if (!run) return;
    setDownloading(true);
    try {
      await exportAttendanceSchedule(id);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not download the schedule.",
      );
    } finally {
      setDownloading(false);
    }
  }

  async function handleVerify() {
    if (!run) return;
    setVerifying(true);
    setError(null);
    try {
      const batch = await verifyAttendanceRun(id);
      if (batch.batch_id) {
        router.push(`/verify/${batch.batch_id}`);
      } else {
        setError("Verification ran but no batch id was returned.");
        setVerifying(false);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not hand off to Bank Verify.",
      );
      setVerifying(false);
    }
  }

  async function handleDelete() {
    if (!run) return;
    const ok = window.confirm(
      "Delete this attendance run? The audit record will be removed.",
    );
    if (!ok) return;
    try {
      await deleteAttendanceRun(id);
      router.push("/agents/attendance-payment");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not delete the run.",
      );
    }
  }

  const filteredRows: MatchedAttendee[] = run
    ? bucket === "paid"
      ? run.matched
      : bucket === "no_attendance"
        ? run.no_attendance
        : bucket === "no_payment_info"
          ? run.no_payment_info
          : [...run.matched, ...run.no_attendance, ...run.no_payment_info]
    : [];

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-6 px-6">
          <Link
            href="/agents/attendance-payment"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <Sparkles className="h-4 w-4 text-brand-600" />
            Attendance run
          </span>
          <button
            type="button"
            onClick={handleDelete}
            className="text-xs font-medium text-gray-400 hover:text-rose-600"
            title="Delete this run"
          >
            Delete
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-12">
        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {!run && !error && (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading run…
          </div>
        )}

        {run && (
          <div className="space-y-8">
            {/* DOCex Assistant briefing — narrates what the agent did,
                recommends next actions. */}
            <AssistantBrief
              contextKind="attendance_run"
              contextId={id}
              payload={run}
              onAction={(label) => {
                const l = label.toLowerCase();
                if (l.includes("verify")) void handleVerify();
                else if (l.includes("download")) void handleDownload();
              }}
            />

            {/* Hero summary */}
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <h1 className="text-2xl font-bold tracking-tight text-gray-900">
                    {run.event_name}
                  </h1>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
                    <span className="inline-flex items-center gap-1">
                      <CalendarDays className="h-3 w-3 shrink-0" />
                      {run.days_in_event}{" "}
                      {run.days_in_event === 1 ? "day" : "days"}
                    </span>
                    {run.rate_card_name ? (
                      <span className="inline-flex items-center gap-1">
                        <Tag className="h-3 w-3 shrink-0" />
                        {run.rate_card_name}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <CircleDollarSign className="h-3 w-3 shrink-0" />
                        ₦{run.rate_per_day.toLocaleString()}/day (flat)
                      </span>
                    )}
                    {/* Source-of-input badges — small chips that tell the
                        auditor whether the data came from a file upload or
                        from a Google Sheet (≈ Google Forms responses). */}
                    <SourceBadge source={run.attendance_source} label="attendance" />
                    <SourceBadge
                      source={run.payment_info_source}
                      label="payment info"
                    />
                    {run.created_at && (
                      <span className="text-gray-400">
                        · {new Date(run.created_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                    Total to pay
                  </p>
                  <p className="text-3xl font-bold tabular-nums text-gray-900">
                    ₦{run.total_to_pay.toLocaleString()}
                  </p>
                </div>
              </div>

              {/* Bucket filter chips */}
              <div className="mt-6 grid gap-3 sm:grid-cols-3">
                <BucketCard
                  active={bucket === "paid"}
                  onClick={() => setBucket("paid")}
                  tone="emerald"
                  icon={<CheckCircle2 className="h-4 w-4" />}
                  label="Paid"
                  count={run.paid_count}
                  hint={`₦${run.total_to_pay.toLocaleString()} across ${run.paid_count} ${run.paid_count === 1 ? "payee" : "payees"}`}
                />
                <BucketCard
                  active={bucket === "no_attendance"}
                  onClick={() => setBucket("no_attendance")}
                  tone="rose"
                  icon={<XCircle className="h-4 w-4" />}
                  label="No attendance"
                  count={run.no_attendance_count}
                  hint="Registered but never showed — blocked from payment"
                />
                <BucketCard
                  active={bucket === "no_payment_info"}
                  onClick={() => setBucket("no_payment_info")}
                  tone="amber"
                  icon={<TriangleAlert className="h-4 w-4" />}
                  label="No bank info"
                  count={run.no_payment_info_count}
                  hint="Attended but missing payment info — needs chasing"
                />
              </div>
            </div>

            {/* Accuracy gate — the most important UI on this page. Surfaces
                EVERY flag the engine raised, requires explicit user ack
                before the Verify button activates. Bank Verify is still the
                final hard gate at payment time; this is the earlier soft
                gate where the team's eyeball-check ritual lives. */}
            {run.accuracy_flags && run.accuracy_flags.length > 0 && (
              <div className="rounded-xl border-2 border-amber-200 bg-amber-50/60 p-5 shadow-sm">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700">
                    <ShieldAlert className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-semibold text-amber-900">
                      Review before paying ({run.accuracy_flags.length}{" "}
                      {run.accuracy_flags.length === 1 ? "flag" : "flags"})
                    </h3>
                    <p className="mt-1 text-xs text-amber-800">
                      DOCex caught a few things worth eyeballing before money
                      moves. None of these are blockers — but Bank Verify
                      won't run until you've reviewed and ticked the box.
                    </p>
                    <ul className="mt-3 space-y-1.5 text-xs text-amber-900">
                      {run.accuracy_flags.map((f, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="text-amber-500">⚠</span>
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                    {!run.bank_verify_batch_id && (
                      <label className="mt-4 flex cursor-pointer items-center gap-2 text-xs font-medium text-amber-900">
                        <input
                          type="checkbox"
                          checked={flagsAcknowledged}
                          onChange={(e) =>
                            setFlagsAcknowledged(e.target.checked)
                          }
                          className="h-4 w-4 rounded border-amber-300 text-amber-600 focus:ring-amber-500"
                        />
                        I've reviewed these flags — unlock Bank Verify
                      </label>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Guidance — what to do with each bucket */}
            {bucket === "no_attendance" && run.no_attendance_count > 0 && (
              <GuidanceCard title="What to do with no-attendance rows">
                These people registered but the attendance log shows they
                never showed up. Don't pay them. If you think the attendance
                log is wrong (someone got missed), update the attendance file
                and re-run. Otherwise, leave them blocked and move on.
              </GuidanceCard>
            )}
            {bucket === "no_payment_info" && run.no_payment_info_count > 0 && (
              <GuidanceCard title="What to do with no-bank-info rows">
                These people attended but aren't on the payment info form.
                Common cause: walk-in attendees or someone who didn't return
                their registration form. Chase them for bank details, add
                them to the payment info file, and re-run.
              </GuidanceCard>
            )}

            {/* Results table */}
            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-100">
                  <thead className="bg-gray-50/60">
                    <tr>
                      <Th>Name</Th>
                      <Th>Org · Role</Th>
                      <Th className="text-right">Days</Th>
                      <Th>Account</Th>
                      <Th>Bank</Th>
                      <Th className="text-right">Match</Th>
                      <Th className="text-right">Rate</Th>
                      <Th className="text-right">Amount</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {filteredRows.length === 0 ? (
                      <tr>
                        <td
                          colSpan={8}
                          className="px-4 py-12 text-center text-sm text-gray-500"
                        >
                          No rows in this bucket.
                        </td>
                      </tr>
                    ) : (
                      filteredRows.map((m, i) => <Row key={i} row={m} />)
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Action band — the agent's payoff moment */}
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">
                    {run.bank_verify_batch_id
                      ? "Schedule already verified ✓"
                      : "Ready to verify?"}
                  </h3>
                  <p className="mt-1 max-w-md text-xs text-gray-500">
                    {run.bank_verify_batch_id
                      ? "This run was handed off to Bank Verify. Click to jump straight to the verification result."
                      : "DOCex will call the bank on every paid row, match the name on the account, and surface anything that doesn't line up before the money leaves."}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={handleDownload}
                    disabled={downloading}
                    className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
                  >
                    {downloading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                    Download schedule
                  </button>
                  {run.bank_verify_batch_id ? (
                    <Link
                      href={`/verify/${run.bank_verify_batch_id}`}
                      className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700"
                    >
                      <ExternalLink className="h-4 w-4" />
                      Open verification
                    </Link>
                  ) : (
                    <button
                      type="button"
                      onClick={handleVerify}
                      disabled={
                        verifying ||
                        run.paid_count === 0 ||
                        (run.accuracy_flags &&
                          run.accuracy_flags.length > 0 &&
                          !flagsAcknowledged)
                      }
                      className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
                      title={
                        run.accuracy_flags &&
                        run.accuracy_flags.length > 0 &&
                        !flagsAcknowledged
                          ? "Tick the review-acknowledgement above to enable"
                          : ""
                      }
                    >
                      {verifying ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Verifying…
                        </>
                      ) : (
                        <>
                          <Landmark className="h-4 w-4" />
                          Verify accounts
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

/* ─── Building blocks ───────────────────────────────────────────────────── */

function Th({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500 ${className ?? ""}`}
    >
      {children}
    </th>
  );
}

function Row({ row }: { row: MatchedAttendee }) {
  const displayName =
    row.payment_info_name ?? row.attendance_name ?? "Unknown";
  return (
    <tr className="hover:bg-gray-50/60">
      <td className="px-4 py-3 text-sm font-medium text-gray-900">
        {displayName}
        {row.attendance_name &&
          row.payment_info_name &&
          row.attendance_name !== row.payment_info_name && (
            <p className="mt-0.5 text-[11px] text-gray-400">
              attendance log: {row.attendance_name}
            </p>
          )}
      </td>
      <td className="px-4 py-3 text-sm text-gray-700">
        <div className="space-y-0.5">
          {row.organisation ? (
            <p className="inline-flex items-center gap-1">
              <Building2 className="h-3 w-3 text-gray-400" />
              {row.organisation}
            </p>
          ) : (
            <p className="text-gray-300">—</p>
          )}
          {row.role && (
            <p className="text-[11px] text-gray-500">{row.role}</p>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-right text-sm tabular-nums text-gray-700">
        {row.days_attended > 0 ? (
          <span title={row.day_labels.join(", ")}>{row.days_attended}</span>
        ) : (
          <span className="text-gray-300">0</span>
        )}
      </td>
      <td className="px-4 py-3 font-mono text-xs text-gray-700">
        {row.account_number ?? <span className="text-gray-300">—</span>}
      </td>
      <td className="px-4 py-3 text-sm text-gray-700">
        {row.bank_name ?? row.bank_code ?? (
          <span className="text-gray-300">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-right text-sm tabular-nums text-gray-700">
        {row.match_score != null ? (
          <span
            className={`font-medium ${row.match_score < 85 ? "text-amber-700" : ""}`}
          >
            {row.match_score}
          </span>
        ) : (
          <span className="text-gray-300">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-right text-sm tabular-nums text-gray-500">
        {row.applied_rate_per_day > 0 ? (
          `₦${row.applied_rate_per_day.toLocaleString()}`
        ) : (
          <span className="text-gray-300">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-right text-sm font-semibold tabular-nums text-gray-900">
        {row.amount > 0 ? (
          `₦${row.amount.toLocaleString()}`
        ) : (
          <span className="font-normal text-gray-300">—</span>
        )}
      </td>
    </tr>
  );
}

function SourceBadge({
  source,
  label,
}: {
  source: "xlsx" | "google_sheets";
  label: string;
}) {
  const isSheets = source === "google_sheets";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
        isSheets
          ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
          : "bg-gray-50 text-gray-600 ring-1 ring-gray-200"
      }`}
      title={
        isSheets
          ? `${label}: pulled live from a Google Sheet`
          : `${label}: uploaded as an .xlsx file`
      }
    >
      {isSheets ? <Link2 className="h-2.5 w-2.5" /> : <FileSpreadsheet className="h-2.5 w-2.5" />}
      {label}
    </span>
  );
}

function BucketCard({
  active,
  onClick,
  tone,
  icon,
  label,
  count,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  tone: "emerald" | "rose" | "amber";
  icon: React.ReactNode;
  label: string;
  count: number;
  hint: string;
}) {
  const styles: Record<
    typeof tone,
    { border: string; activeBorder: string; bg: string; activeBg: string; text: string }
  > = {
    emerald: {
      border: "border-emerald-200",
      activeBorder: "border-emerald-500 ring-2 ring-emerald-100",
      bg: "bg-emerald-50/40",
      activeBg: "bg-emerald-50",
      text: "text-emerald-700",
    },
    rose: {
      border: "border-rose-200",
      activeBorder: "border-rose-500 ring-2 ring-rose-100",
      bg: "bg-rose-50/40",
      activeBg: "bg-rose-50",
      text: "text-rose-700",
    },
    amber: {
      border: "border-amber-200",
      activeBorder: "border-amber-500 ring-2 ring-amber-100",
      bg: "bg-amber-50/40",
      activeBg: "bg-amber-50",
      text: "text-amber-700",
    },
  };
  const s = styles[tone];
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-left rounded-xl border p-4 transition ${
        active
          ? `${s.activeBorder} ${s.activeBg}`
          : `${s.border} ${s.bg} hover:opacity-80`
      }`}
    >
      <div
        className={`flex items-center gap-2 text-xs font-medium uppercase tracking-wide ${s.text}`}
      >
        {icon}
        {label}
      </div>
      <p className="mt-2 text-3xl font-bold tabular-nums text-gray-900">
        {count}
      </p>
      <p className="mt-1 text-[11px] text-gray-500">{hint}</p>
    </button>
  );
}
