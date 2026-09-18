/**
 * The error mapper decides what a person is told when the engine refuses.
 *
 * The failure this suite exists to prevent: the engine writes a careful,
 * specific sentence explaining why a payment cannot move — "REQ-0001 is with
 * finance; you are in program" — and the UI throws it away and says "check
 * the dev console". 75 of the backend's refusals are 400s and another 10 are
 * 409s; every one of them was landing in that generic branch.
 *
 * Run: npx tsx web/lib/__tests__/errors.test.ts
 */
import { friendlyError } from "../errors";

let failed = 0;

function check(name: string, cond: boolean) {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}`);
  if (!cond) failed += 1;
}

const body = (detail: unknown) => JSON.stringify({ detail });

// ─── the engine's own refusals reach the user, word for word ──────────────
// These three strings are copied from a live run against the API.

const NO_REASON =
  "Sending a requisition to another stage requires a written reason.";
const WRONG_DEPT =
  "REQ-0001 is with finance (Finance / Audit review); you are in program. " +
  "Only finance can move it from here.";
const BELOW_THRESHOLD =
  "'ED + AED joint approval' does not apply to a 500000.0 NGN payment — it " +
  "engages from 7000001.0. Routing there would invent an approval this " +
  "organisation's policy does not require.";

check(
  "a 400 shows the engine's reason, not the dev-console message",
  friendlyError(400, body(NO_REASON)).message === NO_REASON,
);
check(
  "a 400 naming the department that holds it survives intact",
  friendlyError(400, body(WRONG_DEPT)).message === WRONG_DEPT,
);
check(
  "a threshold explanation survives intact",
  friendlyError(400, body(BELOW_THRESHOLD)).message === BELOW_THRESHOLD,
);
check(
  "nobody is told to open the dev console any more",
  !friendlyError(400, body(NO_REASON)).message.includes("dev console"),
);
check(
  "a 409 conflict is explained too",
  friendlyError(409, body("This stage has already been signed off.")).message ===
    "This stage has already been signed off.",
);
check(
  "422 still works the way it always did",
  friendlyError(422, body("payees must be a JSON array.")).message ===
    "payees must be a JSON array.",
);
check(
  "a Pydantic error list still yields its first message",
  friendlyError(422, body([{ loc: ["body", "amount"], msg: "Value error, amount must be positive", type: "value_error" }]))
    .message === "amount must be positive",
);

// ─── but only when the body is fit to show ────────────────────────────────

check(
  "a traceback is never shown",
  !friendlyError(400, body('Traceback (most recent call last):\n  File "x.py"'))
    .message.toLowerCase().includes("traceback"),
);
check(
  "an HTML error page from a proxy is never shown",
  !friendlyError(400, "<!DOCTYPE html><html><body>502</body></html>")
    .message.includes("DOCTYPE"),
);
check(
  "a leaked key is never shown",
  !friendlyError(400, body("upstream rejected sk-ant-abc123")).message
    .includes("sk-ant"),
);
check(
  "a body long enough to be a dump is never shown",
  !friendlyError(400, body("x".repeat(500))).message.includes("xxxx"),
);
check(
  "a multi-line dump is never shown",
  friendlyError(400, body("one\ntwo\nthree\nfour\nfive")).message ===
    "DOCex couldn't accept that. Check the details you entered and try again.",
);
check(
  "when nothing is presentable the fallback is still calm and actionable",
  friendlyError(400, "not json at all").message ===
    "DOCex couldn't accept that. Check the details you entered and try again.",
);
check(
  "the raw body is always preserved for diagnostics",
  friendlyError(400, body('Traceback (most recent call last):')).raw.includes(
    "Traceback",
  ),
);

// ─── the branches above the generic one are untouched ─────────────────────

check(
  "401 still asks them to sign in again",
  friendlyError(401, body("Not authenticated")).message.includes("sign in"),
);
check(
  "a bad sign-in is still its own message, not a session-expired one",
  friendlyError(401, body("Invalid email or password")).message ===
    "That email and password don't match an account.",
);
check(
  "403 still talks about permissions",
  friendlyError(403, body("Forbidden")).reason === "auth",
);
check(
  "404 is still not-found, not a validation refusal",
  friendlyError(404, body("No such requisition")).reason === "not_found",
);
check(
  "a Paystack 429 keeps its specific guidance",
  friendlyError(429, body("Paystack test mode daily limit")).message.includes(
    "3 bank resolutions",
  ),
);
check(
  "500 is still a server error, not something the user can fix",
  friendlyError(500, body("boom")).reason === "server",
);

if (failed) {
  console.log(`\n${failed} check(s) FAILED.`);
  process.exit(1);
}
console.log("\nAll error-mapping checks passed.");
