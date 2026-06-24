# DOCex ⇄ Outlook approvals (via Power Automate) — integration guide

DOCex routes sign-off requests to an external workflow engine and receives the
decision back through **one normalized contract**. Power Automate is the first
target (native Outlook + Teams Approvals), but the *same* contract works for
Zapier, n8n, or a Slack/Teams flow — DOCex is not hard-wired to any vendor.

## Architecture

```
 voucher reaches a stage
        │
        ▼
 DOCex  ──POST approval.requested──▶  Power Automate (HTTP trigger)
        │                                    │
        │                            "Start and wait for an approval"
        │                            (Approve/Reject) → Outlook + Teams
        │                                    │
        │                            approver clicks Approve/Reject
        │                                    │
 DOCex  ◀──POST /approval-callback───  Power Automate (HTTP action)
   records verified sign-off (actor + M365 identity + IP),
   advances the workflow, marks voucher approved on final stage
```

Because the approver acts through their real **Microsoft 365 login**, the
sign-off is tied to an authenticated identity — stronger than the email
magic-link (which only proves mailbox access).

## What's built in DOCex (done — code committed)

- `approval_webhook.py` — `emit_approval_request()` (outbound) + `verify_callback_secret()` (fail-closed).
- `POST /compliance/approval-callback` — secret-gated endpoint that applies an external decision.
- `request-signoff` now also emits the outbound event when a webhook is configured.
- One shared `_apply_signoff()` helper — magic-link and webhook converge on the **same** audit representation.
- **Inert until configured:** with no env vars set, nothing changes; the magic-link email flow is the fallback.

### Config (env vars)
- `APPROVAL_WEBHOOK_URL` — the Power Automate HTTP-trigger URL. Unset ⇒ no emit.
- `APPROVAL_CALLBACK_SECRET` — shared secret. Sent outbound as header `X-DOCex-Secret`; **required** to accept callbacks.

### Outbound payload (DOCex → Power Automate)
```json
{
  "type": "approval.requested",
  "check_id": "pay_…", "stage": "Approval",
  "approver_email": "head.finance@taconnect.org",
  "payment_label": "PV-2026-0142 · Vendor X",
  "rulebook_name": "TA Connect Procurement Policy 2025",
  "overall_verdict": "flagged",
  "summary": "…", "deep_link": "https://app/approve/<token>"
}
```

### Inbound callback (Power Automate → DOCex)
`POST /compliance/approval-callback`, header `X-DOCex-Secret: <secret>`:
```json
{
  "check_id": "pay_…", "stage": "Approval",
  "outcome": "approve",            // or "reject" / "return"
  "responder": "head.finance@taconnect.org",
  "comments": "Looks good.",
  "source": "power-automate"
}
```

---

## ⚠️ THE ONE PART THAT NEEDS YOUR MICROSOFT ACCESS

Everything above is built. The remaining piece must be created **inside TA
Connect's Microsoft 365 tenant** (needs a Power Automate licence + their IT):

**Build this 3-step cloud flow in Power Automate:**

1. **Trigger:** *"When an HTTP request is received."* Paste the JSON schema of the
   outbound payload above. Save → Power Automate generates the trigger URL →
   that becomes DOCex's `APPROVAL_WEBHOOK_URL`.
   *(Note: Microsoft moved these URLs to `*.environment.api.powerplatform.com`;
   old `logic.azure.com` URLs retire 30 Nov 2025 — just use the new one.)*
2. **Action:** *"Start and wait for an approval"* → type **Approve/Reject – First
   to respond**. Assigned to `@{triggerBody()?['approver_email']}`, with the
   voucher label, summary, and `deep_link` in the body. This is what shows up in
   Outlook and Teams with Approve/Reject buttons.
3. **Action:** *"HTTP"* → POST to `https://<docex-api>/compliance/approval-callback`
   with header `X-DOCex-Secret` = the shared secret, and a body mapping the
   approval outcome/responder/comments into the inbound shape above.

Then set the two env vars on Railway (`APPROVAL_WEBHOOK_URL`,
`APPROVAL_CALLBACK_SECRET`) and it's live. Until then DOCex keeps using the
magic-link email flow with zero change.

**Async note:** the flow doesn't need to respond to DOCex synchronously — DOCex
fires the request and waits for the callback whenever the human acts (could be
days). Don't try to return the decision on the trigger's 120s response window.

## Reusing this for other orgs (no code change)
The contract is vendor-neutral. A different client can point
`APPROVAL_WEBHOOK_URL` at a **Zapier** catch-hook, an **n8n** webhook node, or a
**Slack** workflow — anything that can receive JSON, ask a human, and POST the
normalized result back with the secret. One DOCex integration, many channels.
