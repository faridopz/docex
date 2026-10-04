# WO-76 — Timesheets people actually fill in

Agreed with Farid on 4 Oct 2026, after comparing the Smart HR Africa demo.
Timesheets stay optional (the `timesheets` flag). When an organisation does
use them, recording time must take seconds, and getting everyone's time in
before payroll must take one click. Everything builds on the existing engine
(`timesheets.py`), payroll split (`payroll.py`), projects (`grants.py`,
`projects.py`), in-app notifications and the org's email setting.

## For staff
1. **My projects.** The list comes from the projects that name the person as
   planned staff, plus any project they have recorded time on before. Leave
   and admin are always there. Nobody types a code.
2. **Log today.** A card on the home screen: pick a project, then half day,
   full day or hours. It opens the month's sheet if needed and records the
   entry. If the month is already submitted, approved or recorded by week or
   month, it says so plainly instead.
3. **Fill my month from my usual split.** Fills empty working days up to
   today (never the future: timesheets are after the fact) from the
   person's planned percentages. They then fix the days that were different.
4. **Settle an advance with receipts** from the Advances page (links to the
   expense claim with the advance chosen).

## For supervisors and Finance
5. **Who hasn't started.** The period summary lists everyone expected to
   record time who has no sheet, plus drafts and returned sheets.
   "Expected" is either everyone or only project staff (a setting).
6. **Remind them.** One button sends an in-app notice, and an email when the
   organisation has email switched on, to everyone still outstanding.
7. **Grace period (optional).** After the month ends plus N days, the
   employee can no longer change entries. Finance or an admin can reopen
   one sheet for a few days, and that is recorded.
8. **Optional second approval.** After the supervisor, a Finance (or HR)
   approver signs too. Not the same person, and never the employee.

## For the administrator
9. **One settings card.** Timesheets on or off, how time is recorded (day,
   week or month), standard hours, grace period, second approval, and who
   is expected to record time.
10. **Setup wizard question:** "Do your staff charge time to donor projects?"
    Yes switches timesheets on.

Tests first, named for the failure each prevents. Full suite, web
type-check, and a browser walk-through before delivery.
