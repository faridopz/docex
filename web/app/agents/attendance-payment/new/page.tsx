"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  CalendarDays,
  CircleDollarSign,
  ExternalLink,
  FileSpreadsheet,
  Link2,
  Loader2,
  Plus,
  Sparkles,
  Upload,
  Users,
  X,
} from "lucide-react";
import { listRateCards, runAttendanceAgentAdvanced } from "@/lib/api";
import type { RateCard } from "@/types";

/**
 * /agents/attendance-payment/new — the upgraded wizard.
 *
 * Three things make this V2:
 *   1. Rate card picker (with inline "flat rate" fallback)
 *   2. Each input accepts EITHER a file OR a Google Sheets URL (toggle)
 *   3. The submit redirects to the detail page where accuracy_flags get
 *      reviewed before the Bank Verify chain fires
 *
 * The toggle on each input is critical for NGO workflows — Google Forms
 * feed Google Sheets directly, so accepting a sheet URL effectively
 * accepts Forms responses with zero extra work on the user side.
 */

type InputMode = "file" | "sheet";

export default function AttendanceAgentNewPage() {
  const router = useRouter();
  const attRef = useRef<HTMLInputElement>(null);
  const payRef = useRef<HTMLInputElement>(null);

  // Event details
  const [eventName, setEventName] = useState("");

  // Rate setup — either a saved card or a flat rate
  const [useCard, setUseCard] = useState(true);
  const [cards, setCards] = useState<RateCard[] | null>(null);
  const [selectedCardId, setSelectedCardId] = useState<string>("");
  const [flatRate, setFlatRate] = useState<string>("");

  // Input 1 — attendance log
  const [attMode, setAttMode] = useState<InputMode>("file");
  const [attFile, setAttFile] = useState<File | null>(null);
  const [attUrl, setAttUrl] = useState("");

  // Input 2 — payment info
  const [payMode, setPayMode] = useState<InputMode>("file");
  const [payFile, setPayFile] = useState<File | null>(null);
  const [payUrl, setPayUrl] = useState("");

  // Form state
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load saved rate cards once; if any exist, default to using a card.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listRateCards();
        if (cancelled) return;
        setCards(list);
        if (list.length > 0) {
          setSelectedCardId(list[0].id);
          setUseCard(true);
        } else {
          setUseCard(false);
        }
      } catch {
        if (!cancelled) {
          setCards([]);
          setUseCard(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function pickXlsx(files: FileList | File[]): File | null {
    return (
      Array.from(files).find(
        (f) =>
          f.name.toLowerCase().endsWith(".xlsx") ||
          f.name.toLowerCase().endsWith(".xlsm"),
      ) ?? null
    );
  }

  async function submit() {
    setError(null);

    // Validate rate setup
    if (useCard && !selectedCardId) {
      setError("Pick a rate card or switch to a flat rate.");
      return;
    }
    let ratePerDay: number | undefined;
    if (!useCard) {
      const r = parseFloat(flatRate);
      if (!Number.isFinite(r) || r <= 0) {
        setError("Flat rate must be a positive number.");
        return;
      }
      ratePerDay = r;
    }

    // Validate event name
    if (!eventName.trim()) {
      setError("Event name is required.");
      return;
    }

    // Validate inputs
    if (attMode === "file" && !attFile) {
      setError("Upload the attendance file or switch to a Google Sheets URL.");
      return;
    }
    if (attMode === "sheet" && !attUrl.trim()) {
      setError("Paste the attendance Google Sheets URL or switch to a file.");
      return;
    }
    if (payMode === "file" && !payFile) {
      setError("Upload the payment info file or switch to a Google Sheets URL.");
      return;
    }
    if (payMode === "sheet" && !payUrl.trim()) {
      setError("Paste the payment info Google Sheets URL or switch to a file.");
      return;
    }

    setSubmitting(true);
    try {
      const run = await runAttendanceAgentAdvanced({
        eventName: eventName.trim(),
        ratePerDay,
        rateCardId: useCard ? selectedCardId : undefined,
        attendanceFile: attMode === "file" ? attFile! : undefined,
        attendanceSheetUrl: attMode === "sheet" ? attUrl.trim() : undefined,
        paymentInfoFile: payMode === "file" ? payFile! : undefined,
        paymentInfoSheetUrl: payMode === "sheet" ? payUrl.trim() : undefined,
      });
      if (run.run_id) {
        router.push(`/agents/attendance-payment/${run.run_id}`);
      } else {
        setError("Run completed but no run id was returned.");
        setSubmitting(false);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not run the agent. Check the backend is up.",
      );
      setSubmitting(false);
    }
  }

  const canSubmit =
    !submitting &&
    eventName.trim().length > 0 &&
    (useCard ? !!selectedCardId : flatRate.trim().length > 0) &&
    (attMode === "file" ? !!attFile : attUrl.trim().length > 0) &&
    (payMode === "file" ? !!payFile : payUrl.trim().length > 0);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between gap-6 px-6">
          <Link
            href="/agents/attendance-payment"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <Sparkles className="h-4 w-4 text-brand-600" />
            New run
          </span>
          <Link
            href="/rate-cards"
            className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
          >
            <CircleDollarSign className="h-3.5 w-3.5" />
            Rate cards
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-12">
        <div className="space-y-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900">
              Run the Attendance & Payment Flow
            </h1>
            <p className="mt-2 max-w-xl text-base text-gray-600">
              Three steps. Tag the event, pick how people get paid, then drop
              in your two files — or paste their Google Sheets links.
            </p>
          </div>

          {/* Step 1 — Event */}
          <Section number={1} title="Event">
            <Field
              icon={<Users className="h-4 w-4 text-gray-400" />}
              label="Event name"
              hint="e.g. 'Q2 Sub-grantee Training — Abuja'"
            >
              <input
                type="text"
                value={eventName}
                onChange={(e) => setEventName(e.target.value)}
                placeholder="What was this event?"
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
            </Field>
          </Section>

          {/* Step 2 — Rate setup */}
          <Section
            number={2}
            title="How do people get paid?"
            hint="Pick a saved rate card for per-role rates, or set a single flat rate for this event."
          >
            <div className="mb-3 inline-flex rounded-lg border border-gray-200 bg-white p-1">
              <ToggleButton
                active={useCard}
                onClick={() => setUseCard(true)}
                disabled={cards?.length === 0}
              >
                Rate card
              </ToggleButton>
              <ToggleButton
                active={!useCard}
                onClick={() => setUseCard(false)}
              >
                Flat rate
              </ToggleButton>
            </div>

            {useCard ? (
              cards === null ? (
                <p className="text-xs text-gray-400">Loading rate cards…</p>
              ) : cards.length === 0 ? (
                <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm">
                  <p className="text-gray-700">
                    No rate cards yet — create one to enable per-role rates.
                  </p>
                  <Link
                    href="/rate-cards"
                    className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand-600 hover:text-brand-700"
                  >
                    Open rate cards
                    <ExternalLink className="h-3 w-3" />
                  </Link>
                </div>
              ) : (
                <div className="grid gap-2">
                  {cards.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setSelectedCardId(c.id)}
                      className={`text-left rounded-xl border p-3 transition ${
                        selectedCardId === c.id
                          ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100"
                          : "border-gray-200 bg-white hover:border-brand-300"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <p
                          className={`text-sm font-medium ${
                            selectedCardId === c.id
                              ? "text-brand-700"
                              : "text-gray-900"
                          }`}
                        >
                          {c.name}
                        </p>
                        <p className="text-xs tabular-nums text-gray-500">
                          ₦{c.default_rate_per_day.toLocaleString()} default
                        </p>
                      </div>
                      {c.roles.length > 0 && (
                        <p className="mt-1 text-[11px] text-gray-500">
                          {c.roles
                            .map(
                              (r) =>
                                `${r.role}: ₦${r.amount_per_day.toLocaleString()}`,
                            )
                            .join(" · ")}
                        </p>
                      )}
                    </button>
                  ))}
                  <Link
                    href="/rate-cards"
                    className="text-center text-[11px] text-gray-400 hover:text-brand-600"
                  >
                    + manage rate cards
                  </Link>
                </div>
              )
            ) : (
              <Field
                icon={<CircleDollarSign className="h-4 w-4 text-gray-400" />}
                label="Per-diem rate (NGN/day)"
                hint="Same rate applied to everyone × their days attended"
              >
                <input
                  type="number"
                  min="0"
                  step="500"
                  value={flatRate}
                  onChange={(e) => setFlatRate(e.target.value)}
                  placeholder="15000"
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </Field>
            )}
          </Section>

          {/* Step 3 — Attendance log */}
          <Section
            number={3}
            title="Attendance log"
            hint="The file your team fills in during the event — one row per attendee, one column per day."
          >
            <DualInput
              mode={attMode}
              onModeChange={setAttMode}
              file={attFile}
              onFile={setAttFile}
              url={attUrl}
              onUrl={setAttUrl}
              fileInputRef={attRef}
              fileHintTitle="Drop the attendance log here"
              fileHintSub="or click to choose"
              urlPlaceholder="https://docs.google.com/spreadsheets/d/..."
              disabled={submitting}
              pickXlsx={pickXlsx}
              setError={setError}
            />
          </Section>

          {/* Step 4 — Payment info */}
          <Section
            number={4}
            title="Payment info form"
            hint="The file with everyone's name, organisation, account number, bank — and optionally a Role column for per-role rates."
          >
            <DualInput
              mode={payMode}
              onModeChange={setPayMode}
              file={payFile}
              onFile={setPayFile}
              url={payUrl}
              onUrl={setPayUrl}
              fileInputRef={payRef}
              fileHintTitle="Drop the payment info form here"
              fileHintSub="or click to choose · Google Forms output works too"
              urlPlaceholder="https://docs.google.com/spreadsheets/d/..."
              disabled={submitting}
              pickXlsx={pickXlsx}
              setError={setError}
            />
          </Section>

          {/* Submit */}
          <div className="border-t border-gray-100 pt-6">
            {error && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {error}
              </div>
            )}
            <button
              type="button"
              disabled={!canSubmit}
              onClick={submit}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-5 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500 disabled:shadow-none"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Matching attendees…
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Run agent
                </>
              )}
            </button>
            <p className="mt-3 text-center text-xs text-gray-500">
              {submitting
                ? "We're fetching, cross-matching names, tallying days. ~3-10 seconds depending on size."
                : "We'll redirect to the review page with accuracy flags BEFORE any bank verification fires."}
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

/* ─── Building blocks ───────────────────────────────────────────────────── */

function Section({
  number,
  title,
  hint,
  children,
}: {
  number: number;
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
        <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-gray-200 text-[11px] font-bold text-gray-700">
          {number}
        </span>
        {title}
      </h2>
      {hint && <p className="text-xs text-gray-500">{hint}</p>}
      {children}
    </section>
  );
}

function Field({
  icon,
  label,
  hint,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="flex items-center gap-1.5 text-xs font-medium text-gray-600">
        {icon}
        {label}
      </label>
      <div className="mt-1.5">{children}</div>
      {hint && <p className="mt-1 text-[11px] text-gray-400">{hint}</p>}
    </div>
  );
}

function ToggleButton({
  active,
  onClick,
  disabled,
  children,
}: {
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md px-3 py-1 text-xs font-medium transition ${
        active
          ? "bg-brand-600 text-white shadow-sm"
          : "text-gray-600 hover:text-gray-900 disabled:opacity-40"
      }`}
    >
      {children}
    </button>
  );
}

function DualInput({
  mode,
  onModeChange,
  file,
  onFile,
  url,
  onUrl,
  fileInputRef,
  fileHintTitle,
  fileHintSub,
  urlPlaceholder,
  disabled,
  pickXlsx,
  setError,
}: {
  mode: InputMode;
  onModeChange: (m: InputMode) => void;
  file: File | null;
  onFile: (f: File | null) => void;
  url: string;
  onUrl: (u: string) => void;
  fileInputRef: React.RefObject<HTMLInputElement>;
  fileHintTitle: string;
  fileHintSub: string;
  urlPlaceholder: string;
  disabled: boolean;
  pickXlsx: (files: FileList | File[]) => File | null;
  setError: (e: string | null) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  return (
    <div className="space-y-3">
      <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1">
        <ToggleButton active={mode === "file"} onClick={() => onModeChange("file")}>
          <span className="inline-flex items-center gap-1.5">
            <Upload className="h-3 w-3" />
            Upload .xlsx
          </span>
        </ToggleButton>
        <ToggleButton active={mode === "sheet"} onClick={() => onModeChange("sheet")}>
          <span className="inline-flex items-center gap-1.5">
            <Link2 className="h-3 w-3" />
            Google Sheets URL
          </span>
        </ToggleButton>
      </div>

      {mode === "file" ? (
        !file ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const f = pickXlsx(e.dataTransfer.files);
              if (f) onFile(f);
              else setError("Please upload an .xlsx (or .xlsm) file.");
            }}
            onClick={() => fileInputRef.current?.click()}
            className={`cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition ${
              dragOver
                ? "border-brand-500 bg-brand-50"
                : "border-gray-200 bg-white hover:border-brand-300 hover:bg-brand-50/30"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xlsm"
              className="hidden"
              onChange={(e) => {
                if (!e.target.files?.length) return;
                const f = pickXlsx(e.target.files);
                if (f) onFile(f);
                else setError("Please upload an .xlsx (or .xlsm) file.");
              }}
            />
            <div className="mx-auto mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
              <Upload className="h-6 w-6" />
            </div>
            <p className="text-sm font-medium text-gray-900">
              {fileHintTitle}
            </p>
            <p className="mt-1 text-xs text-gray-500">{fileHintSub}</p>
          </div>
        ) : (
          <div className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
              <FileSpreadsheet className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-gray-900">
                {file.name}
              </p>
              <p className="text-xs text-gray-500">
                {(file.size / 1024).toFixed(1)} KB · ready
              </p>
            </div>
            <button
              type="button"
              onClick={() => onFile(null)}
              disabled={disabled}
              className="rounded-md p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 disabled:opacity-50"
              title="Remove file"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )
      ) : (
        <div className="space-y-2">
          <input
            type="url"
            value={url}
            onChange={(e) => onUrl(e.target.value)}
            placeholder={urlPlaceholder}
            disabled={disabled}
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <p className="text-[11px] text-gray-500">
            Sheet must be shared with{" "}
            <span className="font-medium">"Anyone with the link can view"</span>{" "}
            · works with Google Forms responses too (forms write to a sheet)
          </p>
        </div>
      )}
    </div>
  );
}
