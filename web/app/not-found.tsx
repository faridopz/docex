import Link from "next/link";

/**
 * Any address that isn't a page. Next's default is an unstyled "404 | This
 * page could not be found" on a white screen — which, reached from an old
 * bookmark or a mistyped link in an email, reads as the system being down.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#fafaf7] px-6 py-16">
      <div className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
        <p className="text-sm font-semibold text-brand-600">Page not found</p>
        <h1 className="mt-2 text-xl font-bold tracking-tight text-gray-900">
          There&rsquo;s nothing at this address.
        </h1>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-gray-600">
          The link may be old or mistyped. Nothing is wrong with your data — head back to your home
          screen and carry on from there.
        </p>
        <Link
          href="/dashboard"
          className="mt-6 inline-flex items-center rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
        >
          Go to your home screen
        </Link>
      </div>
    </div>
  );
}
