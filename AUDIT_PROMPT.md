# Audit brief for an external agent

Paste everything below the line into the agent. It is written to be
self-contained — it assumes no prior knowledge of DOCex.

---

You are auditing **DOCex**, a production AI-native finance and compliance
platform used by a live client. Your job is to find what is wrong, what is
duplicated, and what is fragile — and to clean up processes without breaking a
system that real people are entering real payments into this week.

Read `CLAUDE.md` and `MASTER_CONTEXT.md` first. They carry the architecture and
every decision already made. Then `DOCEX_ENGINE_BENCHMARK.md`, which compares
this engine to Oracle Fusion, Coupa, Tipalti, Stampli, Sage Intacct and
Camunda, and lists what is already known to be missing.

## What the system is

An NGO finance platform. A department raises a **requisition** (a payment
request), deterministic policy checks run immediately, it moves through the
organisation's own approval chain, and on payment an immutable transaction
record is frozen. Alongside that sits an AI-assisted compliance layer that
reads attached documents against a policy rulebook.

Scale: ~51,000 lines of Python across 123 root modules and 29 API routers,
~37,500 lines of TypeScript across 57 Next.js pages, 52 test suites. Stack is
FastAPI + Next.js 14 + Postgres, deployed on Render and Vercel.

The live client is a Nigerian NGO. Money is in naira, the timezone is WAT
(UTC+1), and their approval chain is Finance/Audit → Admin → AED → ED with
amount thresholds from their signed procurement policy.

## The four rules you must not break

1. **DETERMINISTIC-FIRST.** Code owns every number — amounts, deductions,
   allocations, thresholds, matching, duplicates, reconciliation. The model
   only reads messy documents and judges genuinely semantic policy questions.
   A code-level BLOCK always overrides the model. If you find yourself moving
   a calculation into an LLM call, stop.
2. **One engine, one config file per client, never fork.** A new client is
   `profiles/<client>.json` applied via `org_config.py`, not new code. If you
   ever want to write `if org == "<client>"`, that is a config field or a
   feature flag instead.
3. **The audit log is append-only and hash-chained.** Nothing is ever mutated
   or deleted. `verify_audit_chain()` must keep returning true.
4. **A live client beats a refactor.** If a change risks their stability or
   their go-live, it waits. Say so rather than doing it.

## What has just been done — do not redo it

The last few days consolidated three parallel systems that were all trying to
be "a payment that gets checked and approved":

- The payment pipeline board used to read compliance checks and was blind to
  requisitions. It now reads the requisition engine.
- The post-login dashboard used to read the legacy voucher system and showed
  zeroes to a client who doesn't use it. It now leads with requisitions.
- A saved compliance check used to carry its own three-stage approval chain —
  a second copy of the requisition chain. That is retired; a check is now an
  assessment that authorises nothing, with a "raise a payment request from
  this" bridge.
- Emailed sign-off (signed, expiring magic links for approvers with no
  account) moved from compliance checks onto requisitions.
- Requisitions gained routing: escalate to a later stage or hand back to an
  earlier one, with a mandatory reason, skipped stages named on the trail.

## Already known — report these only if you find something NEW about them

Do not spend your audit rediscovering these. They are documented in
`DOCEX_ENGINE_BENCHMARK.md`:

- **Vendor account gap.** `_check_vendor_bank_match()` in `requisitions.py`
  reads the vendor register's verified account number and reports it as
  confirmed, but never compares it to `req.vendor_account`, the number the
  payment actually goes to. Known, unfixed, highest priority.
- Approval steps condition only on `min_amount` — not category, sourcing
  method or grant — so several of the client's own policy rules cannot be
  expressed.
- No SLA, reminders or automatic escalation. No delegation/out-of-office.
- No parallel approval stages; the chain is strictly sequential.
- `project_code` / `grant_code` / `category` are flat strings where the client's
  data is genuinely dimensional.
- The three-quotes-above-₦200,001 rule from their signed policy is a comment
  in `profiles/neem.json` and is enforced nowhere.
- `PostgresStore` has never been tested against a live database.
- Render is still on the free plan; it sleeps and cold-starts.

## What to audit

Work through these in order and stop to report rather than fixing everything
you find.

1. **Remaining duplication.** The consolidation above is incomplete. The legacy
   transaction/voucher system (`transactions.py`, `vouchers.py`,
   `api/erp_routes.py`, `/transactions`, `/vouchers`) still exists alongside
   requisitions. Map exactly what still reads it, what would break if it were
   retired, and what it does that requisitions cannot. Do not delete anything —
   produce the map and a staged retirement plan.

2. **Module sprawl.** 123 Python modules at the repo root is a lot. Identify
   dead modules, modules with a single caller that should be folded in, and
   genuine duplication of logic across modules. Flag, do not merge.

3. **Correctness of money.** Anywhere a float is used for currency, anywhere a
   total is accepted from a client rather than computed, anywhere rounding
   happens more than once, anywhere a comparison uses `==` on floats. This
   system moves money; these are the bugs that matter most.

4. **Multi-tenancy leaks.** Every store read and write should be org-scoped.
   Find any query, cache, module-level global or default parameter that could
   let one organisation's data reach another.

5. **Auth and authorisation.** `api/security.py` holds a deliberately small
   public allowlist. Verify nothing else is reachable unauthenticated, that
   every state-changing route checks the acting user's department or role, and
   that the emailed sign-off tokens cannot be replayed, forged or used
   cross-org.

6. **The audit trail's integrity.** Prove by test that no code path mutates or
   removes an audit entry, that the hash chain survives every workflow
   transition including the new routing and emailed sign-off, and that
   `TransactionRecord` is genuinely immutable after payment.

7. **Error handling that hides failure.** Find every bare `except: pass`,
   every swallowed exception, and every place a failed write returns success.
   In a finance system a silent failure is worse than a crash.

8. **Test quality, not test count.** 52 suites pass. Check whether they assert
   real behaviour or just status codes, whether the boundaries are tested
   (exactly at a threshold, just under, just over), whether org isolation is
   covered, and whether each feature flag is tested in BOTH states.

9. **Frontend consistency.** 57 pages. Find dead routes, pages that call
   endpoints that no longer exist, inconsistent loading and error states, and
   anywhere the UI enforces a rule the server does not (or vice versa).

## How to report

Produce one document with findings ordered by severity, and for each finding:

- **What** — the specific file and function, with a line reference.
- **Why it matters** — the concrete failure it causes, not a principle.
- **Evidence** — the code path, or the test that proves it.
- **Fix** — the smallest change that closes it, and whether it is safe to do
  while a client is live.

Rules for the report: no finding without a file and a line. No
recommendation to "consider refactoring" without saying what breaks if it
isn't done. If something is fine, say it is fine — a report that finds
problems everywhere is a report nobody can act on. Separate what you would do
now from what should wait until after the pilot.

Do not open pull requests or rewrite modules unprompted. Audit first, propose,
and only then change what is agreed — smallest diff that closes the finding,
with a test that fails before it and passes after.
