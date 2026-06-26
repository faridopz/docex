# How financial audit & compliance companies are adopting agentic AI

Research brief for DOCex · June 2026. Cross-check the specifics on Perplexity —
funding numbers and agent counts move fast. Sources listed at the end.

---

## 1. The headline

Agentic AI in audit/compliance moved from pilots to production scale in
2025–2026. This is no longer experimental — the Big Four have committed billions
and deployed thousands of agents, and a funded wave of RegTech startups is
selling "compliance agents" to regulated banks. Critically for us: **the
architecture they've all converged on is the one DOCex already has.**

---

## 2. What the Big Four actually deployed (the "how")

- **EY — EY.ai Agentic Platform.** 150+ *specialized, narrow* agents serving
  ~80,000 tax professionals across 3M+ compliance cases; >$1B/yr AI spend. The
  telling design detail: the agents are "purpose-built with narrow, highly
  reliable task definitions" — tax-research agents, compliance-document agents,
  case-management agents — and explicitly **"do not sign off… they accelerate
  the work done by human professionals."**
- **KPMG — Clara AI + Workbench.** Multi-agent platform (on Azure AI Foundry)
  rolling out to ~95,000 auditors. Agents "automate routine tasks, make
  data-based recommendations, and **draw the audit teams' attention to
  high-risk issues**." ~$2B committed over five years.
- **Deloitte — Zora AI** (built with NVIDIA). Ready-to-deploy agents for
  finance/procurement; the flagship use case is **invoice/AP automation and
  document processing** — matching an invoice to support and flagging anomalies.
- **PwC — Agent OS + GL.ai.** An internal "operating system for AI teammates"
  (reportedly ~25,000 agents); **GL.ai reviews journal entries and the general
  ledger** — exactly the "check the transaction against the rules" pattern.

Common thread: **many narrow agents, not one mega-bot; the agent does the
reading and flagging; a human reviews, decides, and signs off.**

---

## 3. The RegTech / startup wave (closer to DOCex's size)

- **Norm Ai** — "Regulatory AI Agent" platform that **converts regulations into
  operational computer code** (machine-checkable rules). ~$38M raised by early
  2025. *This is precisely DOCex's "policy → rulebook" move.*
- **Greenlite AI** — "trusted AI workforce" of compliance agents for KYC/AML/
  sanctions, used by OCC-regulated banks and SEC-regulated broker-dealers; sells
  on **human oversight + 3–4× ROI without adding headcount**. ~$15M Series A.
- **Sedric AI** — LLM compliance platform for monitoring/risk in financial
  institutions. ~$18.5M Series A.

The pitch across all three is identical to ours: scale compliance review without
scaling headcount, with the AI doing the first pass and humans owning the call.

---

## 4. The architecture everyone converged on

1. **Policy/regulation → machine-checkable rules.** (Norm Ai; DOCex rulebooks.)
2. **Narrow, specialized agents** over a single general assistant.
3. **Human-in-the-loop by design** — the agent accelerates, the human decides
   and signs off. (EY explicitly; the entire Greenlite pitch.)
4. **Flag & prioritize the high-risk** for human attention. (KPMG Clara; DOCex's
   "needs your decision" surfacing.)
5. **Cited evidence + audit trail + explainability** as the trust mechanism —
   this is now a *governance requirement*, not a nicety (EU General-Purpose AI
   Code of Practice, 2025; the rise of "agent governance / observability").
6. **Continuous controls monitoring** — moving from periodic to always-on checks.
7. **Structured, "AI-readable" data** as the prerequisite (a recurring theme:
   PDF-heavy, inconsistent data creates friction for AI audit).

---

## 5. Governance & regulatory backdrop

The EU rolled out a General-Purpose AI Code of Practice (July 2025), and the
language of "agent governance," "agent observability," and "AI agent policing"
is now standard. Open questions the whole industry is wrestling with:
accountability/liability for an agent's action, authentication, and dispute
resolution. The consensus answer that builds trust today: **a human signs off,
and there's a defensible, timestamped audit trail of who decided what.**

---

## 6. What this means for DOCex (the useful part)

**You are already building the pattern the market validated.** Point by point:

- Policy → reusable rulebook = Norm Ai's core idea, applied to NGO procurement/
  donor/travel policy.
- Per-rule verdict (pass/flag/block) *cited from both the policy and the
  payment* = the "explainable, evidence-backed" requirement, built in.
- "Needs your decision" surfacing = KPMG Clara's "draw attention to high-risk."
- **Verified email magic-link sign-off + audit-grade decision log** = the exact
  governance/accountability layer every source says is the trust unlock. This is
  arguably your strongest, most current differentiator — most tools bolt audit
  trails on; yours is the spine.
- Human-in-the-loop (the award/approval decision stays human) = the EY stance,
  and the right posture for a regulated/donor-funded buyer.

**Where you're differentiated:** the Big Four serve enterprises; the RegTech
startups serve banks (KYC/AML/financial crime). **Nobody in this list is serving
sub-award/grants/procurement teams at NGOs and foundations** — your wedge.
Same agentic compliance capability, priced and shaped for teams that will never
hire Deloitte.

**Gaps worth a roadmap line (not pre-demo):**
- *Continuous monitoring* — today DOCex checks on demand; "always-on" checks of
  new vouchers is the natural next step and a recognized market direction.
- *Multi-agent framing* — you have specialized engines (extraction, compliance,
  bank-verify, attendance); naming them as a coordinated "agent" suite mirrors
  how the Big Four describe theirs.
- *ERP-connected, structured data* — you've started (ERPNext/Odoo connectors);
  the "your data must be AI-readable" narrative is a real wedge into finance ops.

**Demo talking points this unlocks:**
- *"Isn't this just ChatGPT?"* → No — it turns a policy into a reusable rulebook,
  cites both sides of every verdict, and freezes an audit trail. A chat prompt
  can't give a team that consistency or defensibility.
- *"The Big Four have AI now."* → Right — and they've proven the model. DOCex
  brings the same agentic-compliance pattern (policy-as-rules, flag-the-risk,
  human-signs-off, full audit trail) to the sub-award and procurement teams the
  Big Four will never serve, at a price they can actually adopt.

---

## Sources

- [The Big 4 AI Takeover (ChatFin, 2026)](https://chatfin.ai/blog/big-4-ai-agents-ey-kpmg-deloitte-pwc-finance-teams-2026/)
- [Big 4 scale AI agents across audit, tax, consulting (Financial World)](https://www.financial-world.org/news/news/financial/30088/deloitte-ey-pwc-and-kpmg-scale-ai-agents-across-audit-tax-and-consulting/)
- [Deloitte unveils Zora AI (Deloitte press room)](https://www.deloitte.com/us/en/about/press-room/deloitte-unveils-zora-ai-agentic-ai-for-tomorrows-workforce.html)
- [KPMG integrates AI agents into Clara AI (KPMG)](https://kpmg.com/de/en/home/media/press-releases/2025/04/kpmg-integrates-ai-agents-in-global-audit-platform-clara-ai.html)
- [The Big 4 AI Agents of 2025 — overview (Unity Connect)](https://unity-connect.com/our-resources/blog/big-4-ai-agents/)
- [Norm Ai raises $27M Series A (FinTech Futures)](https://www.fintechfutures.com/fintech-start-ups/us-regtech-start-up-norm-ai-raises-27m-series-a-funding)
- [Greenlite AI secures $15M for compliance agents (FinTech Global)](https://fintech.global/2025/05/22/regtech-innovator-greenlite-ai-secures-15m-to-scale-trusted-ai-compliance-agents/)
- [Sedric AI raises $18.5M Series A (FinTech Futures)](https://www.fintechfutures.com/regulations-compliance/llm-powered-compliance-platform-sedric-ai-secures-18-5m-series-a)
- [EU General-Purpose AI Code of Practice (overview)](https://en.wikipedia.org/wiki/General-Purpose_AI_Code_of_Practice)
