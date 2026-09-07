/**
 * The timesheet grid — a month of effort as rows × days.
 *
 * WHY A GRID AND NOT A FORM
 * The obvious build is "add an entry: date, project, hours" repeated twenty
 * times. It is also the slowest possible way to fill a month, and it hides the
 * two things the person filling it needs to see continuously: whether every
 * working day is covered, and how the split is landing.
 *
 * A grid of project rows against day columns fixes both. The month is one
 * screen. A blank column is a missing day, visible at a glance. The running
 * totals move as you type, so somebody who knows they were "about 70% on TB
 * this month" can see whether the record agrees before a supervisor does.
 *
 * HALF-DAYS, NOT JUST HOURS
 * Field staff do not think in hours. They think "I was on the TB project
 * today" or "clinic in the morning, report writing in the afternoon". Forcing
 * decimal hours out of that produces invented precision — someone types 6.5
 * because it looks more diligent than 8, and now the record is a guess dressed
 * as a measurement.
 *
 * So the grid has two modes. Half-day mode makes a cell a three-state click:
 * empty → half → full. Hours mode is there for consultants and anyone billing
 * by the hour. Both write the same thing to the engine — hours — because the
 * allocation maths only ever works on hours.
 *
 * Nothing here computes an allocation. The percentages a grant is charged on
 * come from the server, from stored hours. These helpers are for input only.
 */
import type { TimeEntry } from "@/types/timesheet";

/** Non-project time: leave, admin, training. Must still be recorded — the
 *  total has to cover 100% of paid time or every percentage is off its base. */
export const NON_PROJECT = "NON_PROJECT";

export interface GridCell {
  /** Hours on this project, this day. 0 means empty. */
  hours: number;
}

/** projectCode → (ISO date → hours) */
export type Grid = Record<string, Record<string, number>>;

export interface DayInfo {
  date: string;        // ISO
  day: number;         // 1–31
  weekday: string;     // "Mon"
  isWeekend: boolean;
}

/** Every day in the period, with weekends marked so they read differently. */
export function daysInPeriod(period: string): DayInfo[] {
  const [y, m] = period.split("-").map(Number);
  if (!y || !m) return [];
  const out: DayInfo[] = [];
  const last = new Date(y, m, 0).getDate();
  for (let d = 1; d <= last; d++) {
    const date = new Date(y, m - 1, d);
    const dow = date.getDay();
    out.push({
      date: `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`,
      day: d,
      weekday: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dow],
      isWeekend: dow === 0 || dow === 6,
    });
  }
  return out;
}

/** Existing entries → grid. Several entries on one project/day are summed. */
export function entriesToGrid(entries: TimeEntry[]): Grid {
  const grid: Grid = {};
  for (const e of entries) {
    const row = (grid[e.project_code] ??= {});
    row[e.date] = round2((row[e.date] ?? 0) + e.hours);
  }
  return grid;
}

/** Grid → entries, dropping empties. Zero-hour cells are not "worked nothing",
 *  they are "nothing recorded", and the engine rejects non-positive hours. */
export function gridToEntries(grid: Grid, activity: Record<string, string> = {}) {
  const out: { date: string; hours: number; project_code: string; activity?: string }[] = [];
  for (const [project, days] of Object.entries(grid)) {
    for (const [date, hours] of Object.entries(days)) {
      if (!hours || hours <= 0) continue;
      out.push({
        date,
        hours: round2(hours),
        project_code: project,
        activity: activity[`${project}|${date}`] || undefined,
      });
    }
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}

export function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export function dayTotal(grid: Grid, date: string): number {
  return round2(Object.values(grid).reduce((sum, days) => sum + (days[date] ?? 0), 0));
}

export function projectTotal(grid: Grid, project: string): number {
  return round2(Object.values(grid[project] ?? {}).reduce((s, h) => s + h, 0));
}

export function gridTotal(grid: Grid): number {
  return round2(Object.keys(grid).reduce((s, p) => s + projectTotal(grid, p), 0));
}

/**
 * Live preview of the split payroll will use.
 *
 * Chargeable hours only — NON_PROJECT time is excluded from the base, exactly
 * as the server does it, because leave is not charged to a grant. Shown while
 * typing so somebody notices a wrong split now rather than after their salary
 * has been posted against it.
 *
 * The server recomputes this from stored hours; this is a preview, never the
 * number of record.
 */
export function previewAllocation(grid: Grid): Record<string, number> {
  const chargeable = Object.keys(grid).filter((p) => p !== NON_PROJECT);
  const base = chargeable.reduce((s, p) => s + projectTotal(grid, p), 0);
  if (base <= 0) return {};
  const out: Record<string, number> = {};
  for (const p of chargeable) {
    const pct = (projectTotal(grid, p) / base) * 100;
    if (pct > 0) out[p] = round2(pct);
  }
  return out;
}

/**
 * Working days with nothing on them.
 *
 * The single most common reason a timesheet gets sent back, and the easiest
 * thing to miss when you fill it on the last day of the month. Weekends are
 * excluded: an empty Saturday is normal, an empty Tuesday is a question.
 */
export function missingWorkingDays(grid: Grid, days: DayInfo[]): DayInfo[] {
  return days.filter((d) => !d.isWeekend && dayTotal(grid, d.date) === 0);
}

/** A day recorded past what anyone works. The server blocks above 24. */
export function overloadedDays(grid: Grid, days: DayInfo[], limit = 24): DayInfo[] {
  return days.filter((d) => dayTotal(grid, d.date) > limit);
}

// ─── entry modes ────────────────────────────────────────────────────────────

export type EntryMode = "halfday" | "hours";

/**
 * Cycle a cell: empty → half day → full day → empty.
 *
 * Three clicks covers every case a field worker has, with no keyboard. Whole
 * days are the common case, so one click gets there.
 */
export function cycleHalfDay(current: number, hoursPerDay: number): number {
  const half = round2(hoursPerDay / 2);
  if (!current) return half;
  if (current === half) return hoursPerDay;
  return 0;
}

export function halfDayLabel(hours: number, hoursPerDay: number): string {
  if (!hours) return "";
  if (hours === round2(hoursPerDay / 2)) return "½";
  if (hours === hoursPerDay) return "1";
  // Anything else came from hours mode or an import; show it rather than
  // rounding it into a lie.
  return String(round2(hours / hoursPerDay));
}

/**
 * Standard hours in a working day, derived from the org's monthly standard.
 *
 * Configured per organisation as hours-per-period, so this divides by the
 * working days actually in the month rather than assuming 8. A 22-working-day
 * month at 160 standard hours gives 7.27, which is right, and using 8 would
 * quietly push everyone over tolerance.
 */
export function hoursPerDay(standardHoursPerPeriod: number, days: DayInfo[]): number {
  const working = days.filter((d) => !d.isWeekend).length || 1;
  return round2(standardHoursPerPeriod / working);
}

/**
 * Fill every empty working day on one project.
 *
 * The realistic shortcut: most people on a single grant work that grant all
 * month, and typing twenty-two identical cells is how a timesheet becomes a
 * chore nobody does honestly. Only fills days that are empty ACROSS THE WHOLE
 * grid, so it can never overwrite something already recorded.
 */
export function fillWorkingDays(
  grid: Grid,
  project: string,
  days: DayInfo[],
  hours: number,
): Grid {
  const next: Grid = { ...grid, [project]: { ...(grid[project] ?? {}) } };
  for (const d of days) {
    if (d.isWeekend) continue;
    if (dayTotal(grid, d.date) > 0) continue;
    next[project][d.date] = hours;
  }
  return next;
}

/** Remove a project row entirely. */
export function removeProject(grid: Grid, project: string): Grid {
  const next = { ...grid };
  delete next[project];
  return next;
}

export function setCell(grid: Grid, project: string, date: string, hours: number): Grid {
  const row = { ...(grid[project] ?? {}) };
  if (hours > 0) row[date] = round2(hours);
  else delete row[date];
  return { ...grid, [project]: row };
}
