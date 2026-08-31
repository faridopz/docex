/**
 * Friendly error mapping for DOCex API calls.
 *
 * Every call in lib/api.ts used to throw `Error("API error ${status}: ${raw body}")`,
 * which surfaced Pydantic stack traces, Anthropic 401 internals, and Paystack
 * JSON noise directly to users. This helper takes a Response + the raw body
 * and returns a single user-facing sentence — actionable, calm, no stack
 * traces. The original raw error is preserved on the thrown Error as `.cause`
 * so the diagnostic page + Sentry (when adopted) can still see it.
 *
 * The mapping is opinionated by status code first, then by message
 * heuristics for the few cases where the message tells us something useful
 * (Anthropic billing, Paystack quota, etc.). Anything else falls through to
 * a calm generic "something went wrong" with a request-id-style hint.
 */

export type FriendlyErrorReason =
  | "auth"
  | "validation"
  | "not_found"
  | "quota"
  | "upstream"
  | "network"
  | "server"
  | "unknown";

export interface FriendlyError {
  message: string; // the sentence shown in the UI
  reason: FriendlyErrorReason;
  status: number;
  raw: string; // preserved for logs / debugging
}

/** Convert an HTTP status + raw body into a calm, user-friendly message. */
export function friendlyError(status: number, rawBody: string): FriendlyError {
  const raw = rawBody.trim();
  const lower = raw.toLowerCase();

  // ─── 4xx ────────────────────────────────────────────────────────────────

  if (status === 401 || status === 403) {
    if (lower.includes("anthropic") || lower.includes("sk-ant")) {
      return {
        status,
        reason: "auth",
        raw,
        message:
          "DOCex couldn't reach its AI service. The API key looks invalid or expired — check it in the backend's .env file.",
      };
    }
    if (lower.includes("paystack")) {
      return {
        status,
        reason: "auth",
        raw,
        message:
          "Paystack rejected the request. Your secret key may be invalid — verify it at dashboard.paystack.com/#/settings/developers.",
      };
    }
    // A rejected sign-in is a different situation from a signed-in user
    // hitting something above their role, and telling someone standing at
    // the login form to "sign in" is useless. The backend says "Invalid
    // email or password" for exactly this case.
    if (lower.includes("invalid email or password")) {
      return {
        status,
        reason: "auth",
        raw,
        message: "That email and password don't match an account.",
      };
    }
    if (lower.includes("account is disabled")) {
      return {
        status,
        reason: "auth",
        raw,
        message: "That account has been disabled. Ask an admin to re-enable it.",
      };
    }
    if (status === 401) {
      return {
        status,
        reason: "auth",
        raw,
        message: "Your session has expired. Please sign in again.",
      };
    }
    return {
      status,
      reason: "auth",
      raw,
      message: "You're not allowed to do that. Check your permissions.",
    };
  }

  if (status === 404) {
    // 404 from the admin gate means the secret was wrong, not that the
    // resource is missing. Don't try to distinguish here — the admin page
    // handles auth flow separately via AdminAuthError.
    return {
      status,
      reason: "not_found",
      raw,
      message:
        "That item couldn't be found. It may have been deleted or moved.",
    };
  }

  if (status === 422) {
    // Validation errors carry useful info — try to extract the FastAPI
    // "detail" field if it's a string, else give a generic hint.
    const detail = extractDetail(raw);
    if (detail) {
      return {
        status,
        reason: "validation",
        raw,
        message: detail,
      };
    }
    return {
      status,
      reason: "validation",
      raw,
      message:
        "The file or data didn't match what DOCex expected. Check the format and try again.",
    };
  }

  if (status === 429) {
    if (lower.includes("paystack") || lower.includes("test mode daily limit")) {
      return {
        status,
        reason: "quota",
        raw,
        message:
          "Paystack test mode is capped at 3 bank resolutions per day. Upgrade to live mode at dashboard.paystack.com/#/settings/business to remove the cap.",
      };
    }
    return {
      status,
      reason: "quota",
      raw,
      message: "You've hit a rate limit. Wait a minute and try again.",
    };
  }

  if (status >= 400 && status < 500) {
    return {
      status,
      reason: "validation",
      raw,
      message:
        "DOCex rejected the request. Check the inputs and try again — the details are in the dev console.",
    };
  }

  // ─── 5xx ────────────────────────────────────────────────────────────────

  if (status === 502 || status === 503 || status === 504) {
    return {
      status,
      reason: "upstream",
      raw,
      message:
        "DOCex couldn't reach an upstream service (its AI service or the bank API). It's usually transient — try again in a moment.",
    };
  }

  if (status === 0) {
    // status 0 in fetch usually means a network/CORS failure
    return {
      status,
      reason: "network",
      raw,
      message:
        "Couldn't reach the DOCex backend. Check your internet connection, or confirm the API is running at the URL configured in NEXT_PUBLIC_API_URL.",
    };
  }

  if (status >= 500) {
    return {
      status,
      reason: "server",
      raw,
      message:
        "Something went wrong on our side. Refresh and try again — if it keeps happening, check the backend logs.",
    };
  }

  return {
    status,
    reason: "unknown",
    raw,
    message: "Something unexpected went wrong. Try again — if it keeps happening, check the dev console for details.",
  };
}

/**
 * Pull a useful sentence out of a FastAPI error body. FastAPI returns
 * either:
 *   {"detail": "some string"}
 *   {"detail": [{"loc": [...], "msg": "...", "type": "..."}, ...]}
 *   plain text
 * We handle the first two; fall through to null for the third (caller
 * uses a generic message).
 */
function extractDetail(raw: string): string | null {
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === "string") {
      return parsed.detail;
    }
    if (Array.isArray(parsed?.detail) && parsed.detail.length > 0) {
      // Pydantic validation list — take the first error's msg as the
      // user-facing sentence. The full list still ends up on .raw.
      const first = parsed.detail[0];
      if (typeof first?.msg === "string") {
        // Strip Pydantic's leading "Value error, " prefix which adds noise.
        return first.msg.replace(/^Value error,\s*/i, "");
      }
    }
  } catch {
    // Not JSON — fall through.
  }
  return null;
}

/**
 * Throw a FriendlyError-shaped Error. Use this everywhere we currently
 * have `throw new Error("API error ${status}: ${detail}")`. Preserves the
 * raw body on `.cause` so debug consoles still see everything.
 */
export async function throwFriendly(res: Response): Promise<never> {
  let raw = "";
  try {
    raw = await res.text();
  } catch {
    raw = "";
  }
  const fe = friendlyError(res.status, raw);
  const err = new Error(fe.message);
  // `cause` is supported by all modern runtimes and current TS lib defs.
  err.cause = { reason: fe.reason, status: fe.status, raw: fe.raw };
  throw err;
}
