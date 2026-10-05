# WO-77 — Timesheets as a list of entries

Agreed with Farid on 5 Oct 2026. He prefers the entry-list layout he saw in
the Smart HR Africa demo: add an entry (date, project, hours, what you did),
see your entries as cards with a status, and a supervisor approves or
rejects each one. Our own design and words, on the same engine. The month
grid stays, behind a "Month view" toggle.

## Engine (`timesheets.py`)
1. Every entry gets an `id` and a review `status`: pending, approved or
   rejected (with the reviewer's reason). An `overtime` tick is a flag the
   supervisor sees; it does not change pay.
2. Old records: entries without an id get one the first time they are read
   and saved. On an approved or processed sheet they count as approved.
3. Staff add, edit and remove single entries while the sheet is a draft or
   returned. An approved entry can't be edited or removed: it is evidence.
   Editing a rejected entry clears the rejection and puts it back to pending.
4. A supervisor rejects one entry with a written reason, and can undo that.
   "Approve" then approves every other entry. If any were rejected the sheet
   goes back to the employee listing the rejected ones; otherwise it is
   approved exactly as today, including the optional second signature.
5. A sheet can't be sent while a rejected entry is still on it.
6. The month grid can't overwrite a sheet that has approved entries; "log
   today" can't replace an approved entry.
7. Payroll and the donor report are unchanged: an approved sheet has every
   entry approved.

## Routes
- POST `/timesheets/{id}/items`, PUT/DELETE `/timesheets/{id}/items/{entry}`
  — the employee (or an admin).
- POST `/timesheets/{id}/items/{entry}/reject` (reason) and `/clear`
  — whoever may sign the sheet now.
- GET `/timesheets/team?period=` — supervisors see their department,
  Finance and admins see everyone: counts and one row per person.

## Screens
- `/timesheets`: my months as cards (hours, entries by status, "View
  entries"), and "Where my time went" by project.
- `/timesheets/[id]`: counters, "Add entry" form, entries grouped by day as
  cards with status, reason, edit/remove; for the supervisor, Reject with a
  reason on each card and "Approve the rest". "Month view" shows the grid.
- Team view for supervisors and Finance with counters and the reminder.

Tests first (`test_timesheet_entries.py`), full suite, web type-check,
browser walk-through, then delivery.
