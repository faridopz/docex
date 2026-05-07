import type {
  ApplicantInput,
  BatchExtractionResponse,
  Question,
  SingleExtractionResponse,
} from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Health ───────────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

// ─── Single applicant extraction ──────────────────────────────────────────────

export async function extractSingle(
  applicantName: string,
  files: File[],
  questions: Question[],
): Promise<SingleExtractionResponse> {
  const body = new FormData();
  body.append("applicant_name", applicantName);
  body.append("questions", JSON.stringify(questions));
  for (const f of files) body.append("documents", f);

  const res = await fetch(`${BASE}/extract/single`, { method: "POST", body });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  return res.json() as Promise<SingleExtractionResponse>;
}

// ─── Batch extraction ─────────────────────────────────────────────────────────

export async function extractBatch(
  applicants: ApplicantInput[],
  questions: Question[],
): Promise<BatchExtractionResponse> {
  const body = new FormData();
  body.append("questions", JSON.stringify(questions));

  // Map each applicant to their filenames (must match what we upload)
  const applicantMeta = applicants.map((ap) => ({
    id: ap.id,
    name: ap.name,
    filenames: ap.files.map((f) => f.name),
  }));
  body.append("applicants", JSON.stringify(applicantMeta));

  // Upload all files from all applicants together
  for (const ap of applicants) {
    for (const f of ap.files) body.append("documents", f);
  }

  const res = await fetch(`${BASE}/extract/batch`, { method: "POST", body });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  return res.json() as Promise<BatchExtractionResponse>;
}

// ─── Excel export ─────────────────────────────────────────────────────────────
// Uses SheetJS (xlsx). Import is dynamic to avoid SSR issues.

export async function exportToExcel(
  applicants: BatchExtractionResponse["applicants"],
  questions: Question[],
  filename = "docex-results.xlsx",
): Promise<void> {
  const XLSX = await import("xlsx");

  // Build rows: header + one row per applicant
  const header = [
    "Applicant",
    "Documents read",
    ...questions.flatMap((q) => [
      q.text,                        // answer column
      `${q.text} — Source`,          // source doc column
      `${q.text} — Confidence`,      // confidence column
    ]),
    "Errors",
  ];

  const rows = applicants.map((ap) => {
    const answerMap = new Map(ap.answers.map((a) => [a.question_id, a]));

    const cells = questions.flatMap((q) => {
      const a = answerMap.get(q.id);
      if (!a) return ["", "", "not_found"];
      return [
        a.answer ?? "",
        a.source_document ?? "",
        a.confidence,
      ];
    });

    return [
      ap.applicant_name,
      ap.documents.join(", "),
      ...cells,
      ap.error ?? "",
    ];
  });

  const ws = XLSX.utils.aoa_to_sheet([header, ...rows]);

  // Style: freeze the header row and applicant column
  ws["!freeze"] = { xSplit: 1, ySplit: 1 };

  // Auto-width columns (rough estimate)
  const colWidths = header.map((h, i) => {
    const maxLen = Math.max(
      h.length,
      ...rows.map((r) => String(r[i] ?? "").length),
    );
    return { wch: Math.min(maxLen + 2, 60) };
  });
  ws["!cols"] = colWidths;

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Results");
  XLSX.writeFile(wb, filename);
}

// ─── JSON export ──────────────────────────────────────────────────────────────

export function exportJson(data: unknown, filename = "docex-results.json"): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
