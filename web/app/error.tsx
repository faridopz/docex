"use client";

import Link from "next/link";
import { useEffect } from "react";
import { AlertTriangle, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Global error boundary — caught by Next.js when any client component
 * throws during render. Previously a thrown error would white-screen
 * the user; now they get a calm "something went wrong" page with a
 * retry button + a back-to-home link.
 *
 * The actual error is logged to the dev console (via useEffect) and
 * available on `error.digest` for production diagnosis. We deliberately
 * don't show the raw message to the user — most React/Next.js errors
 * are infrastructure noise that won't help a finance officer.
 */
export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to console for development. In production with Sentry / similar,
    // this is also where reportError(error) would land.
    console.error("[DOCex render error]", error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#fafaf7] px-6 py-16">
      <div className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-card">
        <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-100">
          <AlertTriangle className="h-7 w-7" />
        </div>
        <h1 className="text-xl font-bold tracking-tight text-gray-900">
          Something went wrong.
        </h1>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-gray-600">
          DOCex hit an error while rendering this page. Your data is safe —
          this is a UI problem, not a data problem. Try again, or head back
          to the home page and try a different action.
        </p>
        {error.digest && (
          <p className="mt-4 font-mono text-[11px] text-gray-400">
            Reference: {error.digest}
          </p>
        )}
        <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Button onClick={reset} className="gap-2">
            <RotateCw className="h-4 w-4" />
            Try again
          </Button>
          <Link
            href="/"
            className="text-sm font-medium text-gray-600 hover:text-gray-900"
          >
            Back to home →
          </Link>
        </div>
      </div>
    </div>
  );
}
