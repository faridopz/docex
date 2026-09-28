"use client";

/**
 * Last-resort boundary for an error in the root layout itself (the sign-in
 * provider, the stylesheet import) — the one place app/error.tsx cannot
 * catch, because it renders inside that layout. Plain inline styles on
 * purpose: if the layout failed, the stylesheet may not have loaded either.
 */
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#fafaf7" }}>
        <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
          <div style={{ maxWidth: 420, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 16, padding: 32, textAlign: "center" }}>
            <h1 style={{ fontSize: 20, margin: "0 0 8px", color: "#111827" }}>Something went wrong loading the app.</h1>
            <p style={{ fontSize: 14, color: "#4b5563", lineHeight: 1.5, margin: "0 0 20px" }}>
              Your data is safe. Try again; if it keeps happening, sign out and back in.
            </p>
            <button
              type="button"
              onClick={reset}
              style={{ background: "#2563eb", color: "#fff", border: 0, borderRadius: 8, padding: "10px 16px", fontSize: 14, fontWeight: 600, cursor: "pointer" }}
            >
              Try again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
