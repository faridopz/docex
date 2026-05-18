/**
 * Quarter detection from filenames.
 *
 * NGO partner reports rarely share a naming convention, but the quarter
 * information is almost always in the filename somewhere — either as an
 * explicit "Q1/Q2/Q3/Q4" marker, or as a month range like
 * "January - March 2025". This helper extracts whichever signal it finds,
 * with the most specific pattern winning.
 *
 * Tested mentally against the FALILAHW corpus:
 *   "CHAI_Gombe_..._(January - March 2025)_vF.docx"          → Q1 2025 (range)
 *   "Quarterly Report TAConnect - April - June 2025_..."     → Q2 2025 (range)
 *   "TAConnect Sub-Awardee FY 25 Q1 Report.docx"             → Q1      (explicit)
 *   "Borno ...July to September 2025_TAConnect_FNL.docx"     → Q3 2025 (range)
 *   "Options_..._July to August  2025_vf_approved.pdf"       → Q3 2025 (range)
 *   "Sept_2025_Monthly_Report_WCAHealth.pdf"                 → Q3 2025 (single)
 *
 * Returns null when no signal is found — the caller should treat the file
 * as quarter-less and not invent one.
 */

export interface QuarterInfo {
  quarter: 1 | 2 | 3 | 4;
  year: number | null;
  label: string;  // human-readable, e.g. "Q1 2025" or "Q1"
  source: string; // why we picked this, for tooltips
}

const MONTH_TO_Q: Record<string, 1 | 2 | 3 | 4> = {
  jan: 1, january: 1,
  feb: 1, february: 1,
  mar: 1, march: 1,
  apr: 2, april: 2,
  may: 2,
  jun: 2, june: 2,
  jul: 3, july: 3,
  aug: 3, august: 3,
  sep: 3, sept: 3, september: 3,
  oct: 4, october: 4,
  nov: 4, november: 4,
  dec: 4, december: 4,
};

// Sort longer month names first so "september" beats "sep" inside a regex.
const MONTHS_ALT = Object.keys(MONTH_TO_Q)
  .sort((a, b) => b.length - a.length)
  .join("|");

const Q_REGEX = /\b(?:q|quarter)\s*([1-4])\b/i;
const RANGE_REGEX = new RegExp(
  `\\b(${MONTHS_ALT})\\s*(?:[-–—]|to|through|–|—)\\s*(${MONTHS_ALT})\\b`,
  "i",
);
const SINGLE_MONTH_REGEX = new RegExp(`\\b(${MONTHS_ALT})\\b`, "i");
const YEAR_REGEX = /\b(20\d{2})\b/g;

function pickYear(normalised: string): number | null {
  // Prefer the last year mentioned — filenames often end with the
  // reporting year, e.g. "..._January - March 2025_vF.docx".
  const matches = normalised.match(YEAR_REGEX);
  if (!matches || matches.length === 0) return null;
  return parseInt(matches[matches.length - 1], 10);
}

function labelFor(q: 1 | 2 | 3 | 4, year: number | null): string {
  return year ? `Q${q} ${year}` : `Q${q}`;
}

export function detectQuarter(filename: string): QuarterInfo | null {
  if (!filename) return null;

  // Normalise: underscores and dots become spaces, collapse whitespace.
  // Crucially we DON'T flatten dashes — month ranges depend on them.
  const normalised = filename
    .toLowerCase()
    .replace(/[._]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  const year = pickYear(normalised);

  // 1) Explicit Q-marker — most specific, highest confidence.
  const qMatch = normalised.match(Q_REGEX);
  if (qMatch) {
    const q = parseInt(qMatch[1], 10) as 1 | 2 | 3 | 4;
    return {
      quarter: q,
      year,
      label: labelFor(q, year),
      source: `"Q${q}" marker in filename`,
    };
  }

  // 2) Month range — "January - March 2025" maps from the first month.
  const rangeMatch = normalised.match(RANGE_REGEX);
  if (rangeMatch) {
    const startMonth = rangeMatch[1];
    const q = MONTH_TO_Q[startMonth];
    return {
      quarter: q,
      year,
      label: labelFor(q, year),
      source: `${rangeMatch[1]}–${rangeMatch[2]} → Q${q}`,
    };
  }

  // 3) Single month — covers monthly reports like "Sept 2025".
  const singleMatch = normalised.match(SINGLE_MONTH_REGEX);
  if (singleMatch) {
    const q = MONTH_TO_Q[singleMatch[1]];
    return {
      quarter: q,
      year,
      label: labelFor(q, year),
      source: `${singleMatch[1]} → Q${q}`,
    };
  }

  return null;
}
