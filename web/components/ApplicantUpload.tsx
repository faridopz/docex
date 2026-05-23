"use client";

import { useState } from "react";
import { Plus, User, Users, X } from "lucide-react";
import type { ApplicantInput } from "@/types";
import { getWorkflowLabels } from "@/lib/workflow-labels";
import { GuidanceCard } from "./GuidanceCard";
import { DropZone } from "./DropZone";

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
 * File upload behaviour lives in DropZone (./DropZone.tsx) — shared with
 * the Compliance Check feature (policy upload + payment bundles).
 */

interface ApplicantUploadProps {
  mode: "single" | "batch";
  onModeChange: (mode: "single" | "batch") => void;
  applicants: ApplicantInput[];
  onChange: (applicants: ApplicantInput[]) => void;
  // Drives all workflow-aware copy on this page (placeholders, headers,
  // mode toggle labels, etc.). Pass-through from the page-level state.
  templateId?: string | null;
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `a_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

export function ApplicantUpload({
  mode,
  onModeChange,
  applicants,
  onChange,
  templateId,
}: ApplicantUploadProps) {
  const labels = getWorkflowLabels(templateId);

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
            {labels.uploadHeader}
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            {labels.uploadDescription}
          </p>
        </div>
        <ModeToggle
          mode={mode}
          onChange={onModeChange}
          singleLabel={labels.singleModeLabel}
          batchLabel={labels.batchModeLabel}
        />
      </header>

      {mode === "single" ? (
        <GuidanceCard title={labels.singleGuidanceTitle}>
          {labels.singleGuidanceBody}
        </GuidanceCard>
      ) : (
        <GuidanceCard title={labels.batchGuidanceTitle}>
          {labels.batchGuidanceBody}
        </GuidanceCard>
      )}

      {mode === "single" ? (
        <SingleApplicantView
          applicant={singleApplicant}
          onUpdate={(patch) => updateApplicant(singleApplicant.id, patch)}
          namePlaceholder={labels.unitNamePlaceholder}
        />
      ) : (
        <BatchApplicantView
          applicants={applicants}
          onUpdate={updateApplicant}
          onRemove={removeApplicant}
          onAdd={addApplicant}
          namePlaceholder={labels.unitNamePlaceholder}
          addLabel={labels.addUnitButton}
          emptyHint={labels.emptyBatchHint}
          unitSingular={labels.unitSingular}
        />
      )}
    </section>
  );
}

// ── Mode toggle ─────────────────────────────────────────────────────────────

function ModeToggle({
  mode,
  onChange,
  singleLabel,
  batchLabel,
}: {
  mode: "single" | "batch";
  onChange: (m: "single" | "batch") => void;
  singleLabel: string;
  batchLabel: string;
}) {
  return (
    <div className="inline-flex shrink-0 rounded-lg border border-gray-200 bg-gray-50 p-1">
      <ToggleButton active={mode === "single"} onClick={() => onChange("single")}>
        <User className="h-4 w-4" />
        {singleLabel}
      </ToggleButton>
      <ToggleButton active={mode === "batch"} onClick={() => onChange("batch")}>
        <Users className="h-4 w-4" />
        {batchLabel}
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
  namePlaceholder,
}: {
  applicant: ApplicantInput;
  onUpdate: (patch: Partial<ApplicantInput>) => void;
  namePlaceholder: string;
}) {
  return (
    <div className="space-y-4">
      <input
        type="text"
        value={applicant.name}
        onChange={(e) => onUpdate({ name: e.target.value })}
        placeholder={namePlaceholder}
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
  namePlaceholder,
  addLabel,
  emptyHint,
  unitSingular,
}: {
  applicants: ApplicantInput[];
  onUpdate: (id: string, patch: Partial<ApplicantInput>) => void;
  onRemove: (id: string) => void;
  onAdd: () => void;
  namePlaceholder: string;
  addLabel: string;
  emptyHint: string;
  unitSingular: string;
}) {
  return (
    <div className="space-y-4">
      {applicants.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-8 text-center">
          <p className="text-sm text-gray-500">{emptyHint}</p>
        </div>
      ) : (
        applicants.map((a, index) => (
          <ApplicantCard
            key={a.id}
            index={index}
            applicant={a}
            onUpdate={(patch) => onUpdate(a.id, patch)}
            onRemove={() => onRemove(a.id)}
            namePlaceholder={namePlaceholder}
            unitSingular={unitSingular}
          />
        ))
      )}
      <button
        type="button"
        onClick={onAdd}
        className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-blue-600 hover:text-blue-700"
      >
        <Plus className="h-4 w-4" />
        {addLabel}
      </button>
    </div>
  );
}

function ApplicantCard({
  index,
  applicant,
  onUpdate,
  onRemove,
  namePlaceholder,
  unitSingular,
}: {
  index: number;
  applicant: ApplicantInput;
  onUpdate: (patch: Partial<ApplicantInput>) => void;
  onRemove: () => void;
  namePlaceholder: string;
  unitSingular: string;
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
          placeholder={namePlaceholder}
          className="flex-1 border-0 bg-transparent text-base font-medium text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-0"
        />
        <button
          type="button"
          onClick={onRemove}
          className="shrink-0 rounded-md p-1 text-gray-400 transition hover:bg-red-50 hover:text-red-600"
          aria-label={`Remove ${unitSingular} ${index + 1}`}
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
