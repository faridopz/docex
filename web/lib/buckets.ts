/**
 * Applicant bucketing — deterministic, transparent, no LLM in the loop.
 *
 * The buckets describe HOW COMPLETE an applicant's data is, NOT how good
 * the applicant is. That distinction matters: DOCex extracts evidence and
 * the reviewer assesses. Buckets are a summarisation aid, not a judgement.
 *
 * Why deterministic rules instead of asking Claude to cluster:
 *   • The same answer profile must always produce the same bucket. Auditors
 *     need that.
 *   • The justification is the actual counts ("3 of 12 not found") — the
 *     user can verify it instantly without trusting a model.
 *   • Zero extra API cost per run.
 *
 * Thresholds were chosen against the FALILAHW data so most real reports
 * land somewhere sensible — none of the demo set will be "Complete" out of
 * the box, most will be "Has gaps" or "Major gaps", which is honest.
 */

import type { ExtractionAnswer } from "@/types";

export type BucketId =
  | "complete"
  | "near-complete"
  | "has-gaps"
  | "major-gaps"
  | "empty";

export interface Bucket {
  id: BucketId;
  label: string;            // shown on badges
  description: string;      // shown on hover / in legend
  // Tailwind utility classes for the badge look. Kept inside this file so
  // every consumer renders the same colours.
  colorClasses: string;
  dotClasses: string;
  order: number;            // for sorting buckets in the UI
}

export const BUCKETS: Record<BucketId, Bucket> = {
  complete: {
    id: "complete",
    label: "Complete record",
    description:
      "Every question answered with explicit evidence in the documents.",
    colorClasses: "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200",
    dotClasses: "bg-emerald-500",
    order: 0,
  },
  "near-complete": {
    id: "near-complete",
    label: "Near complete",
    description:
      "Most questions answered; a small number relied on inference or were not found.",
    colorClasses: "bg-teal-50 text-teal-800 ring-1 ring-teal-200",
    dotClasses: "bg-teal-500",
    order: 1,
  },
  "has-gaps": {
    id: "has-gaps",
    label: "Has gaps",
    description:
      "A meaningful portion of questions could not be answered from the documents.",
    colorClasses: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",
    dotClasses: "bg-amber-500",
    order: 2,
  },
  "major-gaps": {
    id: "major-gaps",
    label: "Major gaps",
    description:
      "More than a third of questions were not found in the documents.",
    colorClasses: "bg-rose-50 text-rose-800 ring-1 ring-rose-200",
    dotClasses: "bg-rose-500",
    order: 3,
  },
  empty: {
    id: "empty",
    label: "No data",
    description: "No answers were returned (extraction failed or empty input).",
    colorClasses: "bg-gray-100 text-gray-600 ring-1 ring-gray-200",
    dotClasses: "bg-gray-400",
    order: 4,
  },
};

export interface BucketAssignment {
  bucket: Bucket;
  // Counts that drove the assignment. Shown on hover and exported to Excel
  // as the audit-defensible "why this bucket" line.
  counts: {
    total: number;
    found: number;
    inferred: number;
    notFound: number;
  };
  // Human-readable single-line justification, e.g.:
  // "8 of 12 found, 2 inferred, 2 not found (17% gaps)"
  justification: string;
  // 0-1 ratio of not_found answers — useful for sorting.
  gapRatio: number;
}

/**
 * Classify an applicant by their answer profile.
 *
 * Rules (in priority order, evaluated top to bottom):
 *   • empty:         total == 0
 *   • complete:      every answer is "found"
 *   • major-gaps:    > 33% of answers are "not_found"
 *   • has-gaps:      10-33% are "not_found"
 *   • near-complete: ≤ 10% are "not_found" (everything else)
 */
export function assignBucket(answers: ExtractionAnswer[]): BucketAssignment {
  const total = answers.length;

  if (total === 0) {
    return {
      bucket: BUCKETS.empty,
      counts: { total: 0, found: 0, inferred: 0, notFound: 0 },
      justification: "No answers returned for this applicant.",
      gapRatio: 1,
    };
  }

  let found = 0;
  let inferred = 0;
  let notFound = 0;
  for (const a of answers) {
    if (a.confidence === "found") found++;
    else if (a.confidence === "inferred") inferred++;
    else notFound++;
  }

  const gapRatio = notFound / total;

  let bucketId: BucketId;
  if (found === total) bucketId = "complete";
  else if (gapRatio > 1 / 3) bucketId = "major-gaps";
  else if (gapRatio > 0.1) bucketId = "has-gaps";
  else bucketId = "near-complete";

  const justification = `${found} of ${total} found, ${inferred} inferred, ${notFound} not found (${Math.round(gapRatio * 100)}% gaps)`;

  return {
    bucket: BUCKETS[bucketId],
    counts: { total, found, inferred, notFound },
    justification,
    gapRatio,
  };
}

/**
 * Group applicants by their bucket, preserving the canonical bucket order
 * (Complete first, then Near complete, etc.).
 */
export function groupByBucket<T extends { answers: ExtractionAnswer[] }>(
  applicants: T[],
): { bucket: Bucket; members: T[]; assignments: BucketAssignment[] }[] {
  const groups = new Map<
    BucketId,
    { bucket: Bucket; members: T[]; assignments: BucketAssignment[] }
  >();

  for (const ap of applicants) {
    const assignment = assignBucket(ap.answers);
    const existing = groups.get(assignment.bucket.id);
    if (existing) {
      existing.members.push(ap);
      existing.assignments.push(assignment);
    } else {
      groups.set(assignment.bucket.id, {
        bucket: assignment.bucket,
        members: [ap],
        assignments: [assignment],
      });
    }
  }

  return Array.from(groups.values()).sort(
    (a, b) => a.bucket.order - b.bucket.order,
  );
}
