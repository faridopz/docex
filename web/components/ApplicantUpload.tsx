"use client";

import { useState } from "react";
import {
  AlertCircle,
  FileText,
  Plus,
  Upload,
  User,
  Users,
  X,
} from "lucide-react";
import type { ApplicantInput } from "@/types";
import { GuidanceCard } from "./GuidanceCard";

/**
 * ApplicantUpload
 *
 * Where the grants officer brings in the documents.
 *  - Single mode: one applicant, drop in all their documents at once.
 *  - Batch mode:  many applicants, each with their own document set.
 *
 * The data model is the same in both modes (ApplicantInput[]); the parent
 * is responsible for keeping the array consistent with the current mode.
 * In single mode the component renders the first applicant only; in batch
 * mode it renders all of them.
 *
 * Accepts PDF, DOCX, TXT. Anything else is silently rejected with a
 * dismissable amber notice — never a hard error, never a popup.
 */

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt"];
const ACCEPTED_LABEL = "PDF, DOCX, or TXT";

interface ApplicantUploadProps {
  mode: "single" | "batch";
  onModeChange: (mode: "single" | "batch") => void;
  applicants: ApplicantInput[];
  onChange: (applicants: ApplicantInput[]) => void;
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `a_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isAccepted(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export function ApplicantUpload({
  mode,
  onModeChange,
  applicants,
  onChange,
}: ApplicantUploadProps) {
  // Stable id for the placeholder we show in single mode before the user
  // has typed anything. Once they interact, we promote it into real state.
  const [pendingSingleId] = useState(() => newId());

  const singleApplicant: ApplicantInput =
    applicants[0] ?? { id: pendingSingleId, name: "", files: [] };

  const updateApplicant = (id: string, patch: Partial<ApplicantInput>) => {
    const exists = applicants.some((a) => a.id === id);
    if (!exists) {
      onChange([
        ...applicants,
        { id, name: "", files: [], ...patch } as ApplicantInput,
      ]);
      return;
    }
    onChange(applicants.map((a) => (a.id === id ? { ...a, ...patch } : a)));
  };

  const removeApplicant = (id: string) => {
    onChange(applicants.filter((a) => a.id !== id));
  };

  const addApplicant = () => {
    onChange([...applicants, { id: newId(), name: "", files: [] }]);
  };

  return (
    <section className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">
            Upload applications
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            Drop in everything one applicant submitted — registration,
            profile, audit, proposal. DOCex reads them together.
          </p>
        </div>
        <ModeToggle mode={mode} onChange={onModeChange} />
      </header>

      {mode === "single" ? (
        <GuidanceCard title="What to upload">
          Drop in every document the applicant submitted in one go —
          registration certificate, organisational profile, audit report,
          proposal, financials. DOCex reads the full bundle together so an
          answer found in one document can be cross-checked against the
          others.
        </GuidanceCard>
      ) : (
        <GuidanceCard title="How batch mode works">
          Add each applicant and drop in their full document bundle.
          DOCex screens every organisation against your questions and
          returns one row per applicant — built for side-by-side comparison.
          Use this when you have many applications to get through.
        </GuidanceCard>
      )}

      {mode === "single" ? (
        <SingleApplicantView
          applicant={singleApplicant}
          onUpdate={(patch) => updateApplicant(singleApplicant.id, patch)}
        />
      ) : (
        <BatchApplicantView
          applicants={applicants}
          onUpdate={updateApplicant}
          onRemove={removeApplicant}
          onAdd={addApplicant}
        />
      )}
    </section>
  );
}

// ── Mode toggle ─────────────────────────────────────────────────────────────

function ModeToggle({
  mode,
  onChange,
}: {
  mode: "single" | "batch";
  onChange: (m: "single" | "batch") => void;
}) {
  return (
    <div className="inline-flex shrink-0 rounded-lg border border-gray-200 bg-gray-50 p-1">
      <ToggleButton active={mode === "single"} onClick={() => onChange("single")}>
        <User className="h-4 w-4" />
        One applicant
      </ToggleButton>
      <ToggleButton active={mode === "batch"} onClick={() => onChange("batch")}>
        <Users className="h-4 w-4" />
        Batch
      </ToggleButton>
    </div>
  );
}

function ToggleButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition ${
        active
          ? "bg-white text-gray-900 shadow-sm"
          : "text-gray-600 hover:text-gray-900"
      }`}
    >
      {children}
    </button>
  );
}

// ── Single mode ─────────────────────────────────────────────────────────────

function SingleApplicantView({
  applicant,
  onUpdate,
}: {
  applicant: ApplicantInput;
  onUpdate: (patch: Partial<ApplicantInput>) => void;
}) {
  return (
    <div className="space-y-4">
      <input
        type="text"
        value={applicant.name}
        onChange={(e) => onUpdate({ name: e.target.value })}
        placeholder="Applicant organisation name"
        className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder:text-gray-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
      />
      <DropZone
        files={applicant.files}
        onFilesChange={(files) => onUpdate({ files })}
      />
    </div>
  );
}

// ── Batch mode ──────────────────────────────────────────────────────────────

function BatchApplicantView({
  applicants,
  onUpdate,
  onRemove,
  onAdd,
}: {
  applicants: ApplicantInput[];
  onUpdate: (id: string, patch: Partial<ApplicantInput>) => void;
  onRemove: (id: string) => void;
  onAdd: () => void;
}) {
  return (
    <div className="space-y-4">
      {applicants.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-8 text-center">
          <p className="text-sm text-gray-500">
            No applicants yet. Add the first one to get started.
          </p>
        </div>
      ) : (
        applicants.map((a, index) => (
          <ApplicantCard
            key={a.id}
            index={index}
            applicant={a}
            onUpdate={(patch) => onUpdate(a.id, patch)}
            onRemove={() => onRemove(a.id)}
          />
        ))
      )}
      <button
        type="button"
        onClick={onAdd}
        className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-blue-600 hover:text-blue-700"
      >
        <Plus className="h-4 w-4" />
        Add applicant
      </button>
    </div>
  );
}

function ApplicantCard({
  index,
  applicant,
  onUpdate,
  onRemove,
}: {
  index: number;
  applicant: ApplicantInput;
  onUpdate: (patch: Partial<ApplicantInput>) => void;
  onRemove: () => void;
}) {
  return (
    <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-100 text-xs font-medium text-gray-600">
          {index + 1}
        </span>
        <input
          type="text"
          value={applicant.name}
          onChange={(e) => onUpdate({ name: e.target.value })}
          placeholder="Applicant organisation name"
          className="flex-1 border-0 bg-transparent text-base font-medium text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-0"
        />
        <button
          type="button"
          onClick={onRemove}
          className="shrink-0 rounded-md p-1 text-gray-400 transition hover:bg-red-50 hover:text-red-600"
          aria-label={`Remove applicant ${index + 1}`}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <DropZone
        files={applicant.files}
        onFilesChange={(files) => onUpdate({ files })}
      />
    </div>
  );
}

// ── Drop zone + file list ───────────────────────────────────────────────────

function DropZone({
  files,
  onFilesChange,
}: {
  files: File[];
  onFilesChange: (files: File[]) => void;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const [rejectedCount, setRejectedCount] = useState(0);

  const addFiles = (incoming: File[]) => {
    const accepted: File[] = [];
    let rejected = 0;
    for (const f of incoming) {
      if (isAccepted(f)) accepted.push(f);
      else rejected += 1;
    }
    // Avoid duplicates by filename + size
    const existing = new Set(files.map((f) => `${f.name}:${f.size}`));
    const fresh = accepted.filter((f) => !existing.has(`${f.name}:${f.size}`));
    if (fresh.length > 0) onFilesChange([...files, ...fresh]);
    setRejectedCount(rejected);
  };

  const removeFile = (name: string, size: number) => {
    onFilesChange(files.filter((f) => !(f.name === name && f.size === size)));
  };

  const totalBytes = files.reduce((sum, f) => sum + f.size, 0);

  return (
    <div className="space-y-2">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          if (!isDragging) setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          addFiles(Array.from(e.dataTransfer.files));
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition ${
          isDragging
            ? "border-blue-600 bg-blue-50"
            : "border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-gray-100"
        }`}
      >
        <Upload
          className={`h-6 w-6 ${isDragging ? "text-blue-600" : "text-gray-400"}`}
        />
        <p className="mt-2 text-sm font-medium text-gray-700">
          Drop documents here or click to browse
        </p>
        <p className="mt-1 text-xs text-gray-500">{ACCEPTED_LABEL}</p>
        <input
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(",")}
          onChange={(e) => {
            if (e.target.files) addFiles(Array.from(e.target.files));
            // Reset so the same file can be re-added after removal
            e.target.value = "";
          }}
          className="hidden"
        />
      </label>

      {rejectedCount > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1">
            Skipped {rejectedCount} {rejectedCount === 1 ? "file" : "files"} —
            only {ACCEPTED_LABEL} are supported.
          </span>
          <button
            type="button"
            onClick={() => setRejectedCount(0)}
            className="shrink-0 text-amber-600 hover:text-amber-800"
            aria-label="Dismiss notice"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {files.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2 text-xs text-gray-500">
            <span>
              {files.length} {files.length === 1 ? "file" : "files"}
            </span>
            <span>{formatBytes(totalBytes)}</span>
          </div>
          <ul className="divide-y divide-gray-100">
            {files.map((f) => (
              <li
                key={`${f.name}:${f.size}`}
                className="flex items-center gap-3 px-3 py-2"
              >
                <FileText className="h-4 w-4 shrink-0 text-gray-400" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-gray-900">{f.name}</p>
                  <p className="text-xs text-gray-500">{formatBytes(f.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={() => removeFile(f.name, f.size)}
                  className="shrink-0 rounded-md p-1 text-gray-400 transition hover:bg-red-50 hover:text-red-600"
                  aria-label={`Remove ${f.name}`}
                >
                  <X className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
