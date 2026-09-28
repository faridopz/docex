/**
 * The one page frame inside AppShell: the same width, gutters and heading on
 * every screen.
 *
 * Pages used to set their own — some centred at 2xl, some at 7xl, three core
 * finance screens with no container at all, sitting flush against the
 * sidebar — which read as unfinished even where each page was fine alone.
 * `wide` is for the tables and the board, `narrow` for forms.
 */
export function Page({
  title,
  subtitle,
  aside,
  width = "default",
  children,
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Right-hand side of the heading row: a view switch, a download. */
  aside?: React.ReactNode;
  width?: "narrow" | "default" | "wide";
  children: React.ReactNode;
}) {
  const max = width === "narrow" ? "max-w-3xl" : width === "wide" ? "max-w-7xl" : "max-w-5xl";
  return (
    <div className={`mx-auto w-full ${max} space-y-6 py-6 sm:px-6 lg:px-8`}>
      {title ? (
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">{title}</h1>
            {subtitle ? <p className="mt-1 text-sm text-gray-600">{subtitle}</p> : null}
          </div>
          {aside ? <div className="flex flex-wrap items-center gap-2">{aside}</div> : null}
        </div>
      ) : null}
      {children}
    </div>
  );
}
