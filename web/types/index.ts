// ── Questions ─────────────────────────────────────────────────────────────────

export interface Question {
  id: string;
  text: string; // plain language, e.g. "What states does this org work in?"
}

// ── Extraction answers ────────────────────────────────────────────────────────

export type Confidence = "found" | "inferred" | "not_found";

export interface ExtractionAnswer {
  question_id: string;
  question_text: string;
  answer: string | null;           // null when not_found
  confidence: Confidence;
  source_document: string | null;  // filename the answer came from
  quote: string | null;            // verbatim excerpt from the document
}

// ── Single applicant result ───────────────────────────────────────────────────

export interface SingleExtractionResponse {
  applicant_name: string;
  documents: string[];             // list of filenames that were read
  answers: ExtractionAnswer[];
  error?: string | null;
}

// ── Batch result ──────────────────────────────────────────────────────────────

export interface ApplicantExtraction {
  applicant_id: string;
  applicant_name: string;
  documents: string[];
  answers: ExtractionAnswer[];
  error?: string | null;
}

export interface BatchExtractionResponse {
  total: number;
  succeeded: number;
  failed: number;
  applicants: ApplicantExtraction[];
}

// ── UI state — applicant being assembled before submission ────────────────────

export interface ApplicantInput {
  id: string;
  name: string;
  files: File[];
}

// ── Confidence display helpers ────────────────────────────────────────────────

export const confidenceLabel: Record<Confidence, string> = {
  found: "Found",
  inferred: "Inferred",
  not_found: "Not found",
};

export const confidenceColor: Record<Confidence, string> = {
  found: "text-emerald-700 bg-emerald-50 border-emerald-200",
  inferred: "text-amber-700 bg-amber-50 border-amber-200",
  not_found: "text-gray-500 bg-gray-50 border-gray-200",
};

export const confidenceDot: Record<Confidence, string> = {
  found: "bg-emerald-500",
  inferred: "bg-amber-400",
  not_found: "bg-gray-300",
};
