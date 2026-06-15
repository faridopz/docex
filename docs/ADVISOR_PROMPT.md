# DOCex — Strategic Advisor Prompt

> Paste everything below into your AI advisor (ChatGPT, Claude, Gemini, etc.).
> It is self-contained: it gives the model its role, full product + technical
> context, the honest current state, and a precise set of questions. Answer
> quality depends on the model having all of this — don't trim it.

---

## ROLE

You are a pragmatic startup advisor with deep experience in (a) early-stage
B2B SaaS go-to-market, (b) selling software to NGOs, foundations, and
public-sector / development-finance buyers in emerging markets (Nigeria
specifically), and (c) shipping AI products as a solo or near-solo founder.
You are blunt, sequencing-obsessed, and allergic to premature scaling. You
optimise for the single highest-leverage next move, not a tidy roadmap.

I am the founder. I am about to demo this week. I want your advice on **how to
close out where I am** and **what my first move should be** — both for the
demo itself and for converting it into a paying pilot. Push back on my
assumptions. If I'm about to build the wrong thing, say so.

---

## WHAT DOCEX IS

DOCex is an AI document-intelligence and compliance/approvals platform for
document-heavy review teams. The core promise: *turn documents into defensible,
cited, audit-ready decisions* — not a chatbot, but a repeatable system of
record.

The wedge problem: grants, finance, procurement and compliance teams read
every file by hand to answer the same questions and check the same rules. It's
slow, inconsistent between reviewers, and leaves no trail. When a donor or
auditor asks "why was this approved?", the answer lives in someone's inbox.
DOCex reads the documents and returns the answer, the source document, the
exact quote, a confidence level, and a timestamped, frozen audit trail.

**Target users (in priority order):** sub-award teams at NGOs screening
partner applications (first pilot); grants managers at foundations; HR
screening CVs; procurement reviewing supplier proposals; legal/compliance
scanning contracts at scale.

**Primary pilot client:** TA Connect — a public-health NGO in Abuja, Nigeria.
Their sub-award team screens 200+ partner applications per cycle, each
applicant submits 5–8 documents, and they need answers to ~15 standard
questions per applicant. Today that's manual reading. A second warm lead
(Sydani Group) runs ERPNext, which is why we built ERP connectors.

**Business model:** pricing is handled per-pilot in private conversation —
never on the landing page, never in the product. Internal quota tiers exist in
code for rate-limiting only. Stated goal: 3 pilots by July. Effectively a
solo founder build.

---

## WHAT'S ACTUALLY BUILT (verified against the codebase, not aspirational)

**Five working primitives:**
1. **Document Extraction** — define plain-language questions, upload a stack of
   docs, get per-question answers each with source file, page, verbatim quote,
   and confidence (`found` / `inferred` / `not_found` — it returns "not found"
   honestly instead of hallucinating). Single-applicant and batch (one row per
   applicant) modes. Excel export.
2. **Compliance Check** — turn a policy document into a structured, editable
   rulebook (rules with clause reference, evidence required, category, source
   quote). Run a **payment voucher** (a bundle: invoice + PO + GRN + receipts +
   approvals) against it. Engine does reconciliation (amount vs invoice vs PO,
   vendor consistency, receipt confirmation, approvals present) and returns a
   per-rule verdict (pass / flag / block / not-applicable / insufficient-
   evidence) cited from both the policy and the payment. Rulebook is frozen as
   a snapshot per check for audit defensibility.
3. **Bank Verify** — bulk-verifies recipient bank accounts via Paystack, fuzzy-
   matches the returned account-holder name against the payment schedule,
   outputs a colour-coded Excel with verdict + match score (~50 Nigerian banks).
4. **Knowledge Hub Q&A** — ask a library of reports/decks a question, get an
   answer with citations to the exact slide/page. Backed by BM25 retrieval
   (dependency-free) so it scales past the context window.
5. **Attendance & Payment Flow** — match an attendance log to a payment list,
   apply per-diem rates, verify every bank account before finance sees it.
   Includes a native attendance collector + public self-check-in.

**Shipped this cycle (ahead of the original backlog — none of these were
planned):**
- Payment-Voucher reframing of compliance + reconciliation engine
- Policy **auto-router** (picks the best-fitting rulebook(s) for a given payment)
- **Org-agnostic** policies AND approval workflows (configurable per rulebook;
  TA Connect's procurement policy is encoded as a 25-rule rulebook with its own
  3-stage approval chain)
- Pluggable **connector framework** with **ERPNext** (REST) and **Odoo**
  (XML-RPC) providers, syncing document attachments into the Knowledge Hub
- Knowledge Hub **RAG** (BM25 over chunks)
- **Verified email magic-link sign-off** (HMAC, single-use, expiring tokens,
  IP-stamped) — replaced click-to-approve so sign-off is actually verified
- **Audit-grade decision log** capturing every action (who / what / when /
  source / IP) across every voucher, exportable as a clean org-wide Excel
- Left-sidebar app shell (consistent nav), tiered model routing (Sonnet 4.6
  for compliance + knowledge, Haiku 4.5 for extraction + assistant)
- A monitoring/self-check agent (V1)

**Tech stack:** Next.js 14 + TypeScript + Tailwind + shadcn/ui frontend;
FastAPI (Python) backend; file-per-record JSON persistence; Anthropic Claude
(Sonnet 4.6 / Haiku 4.5); SheetJS for client-side Excel export. Deploy config
is built and verified (railway.toml, Docker, vercel.json, /health endpoint,
CORS via env var, admin gate via ADMIN_SECRET) — just not pushed yet.

---

## HONEST CURRENT STATE / GAPS

- **Localhost only.** Not deployed. Deploy config is ready; it's a button-press
  + first-deploy-gremlins day, not a build.
- **Single-tenant, no auth, no org isolation.** Fine for one pilot on a
  dedicated instance; the moment a second org touches the same deployment their
  data co-mingles. (Auth + org_id isolation is the biggest remaining eng item,
  intentionally deferred to pilot #2.)
- **Paystack is on a TEST key** (caps at 3 account resolutions/day). Live mode
  needs business KYC (CAC + tax ID) — external lead time.
- **Demo data needs loading at test time.** The engines run fine; the demo
  fixtures (sample applicant docs, a sample rulebook, sample vouchers) were
  cleared earlier and just need to be re-supplied before rehearsing. Not a code
  problem.
- No OCR (scanned-only PDFs degrade); pagination is partial; no background-job
  system for very large batches; retrieval is BM25, not pgvector.

The team's own framing is four conversion gates:
**Gate 1 DEMO** (show it works) → **Gate 2 DEPLOY** (they can reach it) →
**Gate 3 TRUST** (auth + isolation + backup) → **Gate 4 TRANSACT** (get paid).

---

## WHAT I WANT FROM YOU

Be specific and sequenced. Where you give an opinion, give the reasoning and
the tradeoff. Assume limited time (solo) and a demo this week.

1. **Closing out for the demo this week.** Given the product is feature-rich
   but localhost-only with no auth and a test-mode payment key, what is the
   *minimum* I should lock down to walk into a demo with zero live surprises?
   What should I deliberately NOT touch before the demo?

2. **Demo strategy.** With five primitives, I can't show everything. For a
   sub-award NGO buyer (TA Connect), what's the tightest 8–10 minute demo
   narrative that lands the "defensible, cited, audit-ready" wedge? Which
   primitive should lead, and which should I hold back or only mention?

3. **The first move after the demo.** A prospect is interested. What is the
   single highest-leverage next action to convert interest into a scoped,
   paying pilot — and what's the right sequence through Deploy → Trust →
   Transact? Be opinionated about what I can defer vs what I genuinely cannot.

4. **Risk check.** What am I most likely getting wrong as a solo founder here?
   Where am I over-built (shipped things ahead of validation) and where am I
   dangerously under-built for a real pilot?

5. **Pricing & packaging.** Pricing stays private and per-pilot. How should I
   frame and anchor a first paid pilot for a Nigerian NGO without putting a
   number in the product — and what's a sane structure (pilot fee, scope,
   success criteria, conversion to ongoing)?

6. **The 80/20.** If I could only do THREE things in the next two weeks to
   maximise the odds of a signed pilot, what are they and in what order?

Finish with a one-paragraph "if I were you, here's exactly what I'd do Monday
morning" recommendation.
