import Link from "next/link";
import { LayoutGrid, List } from "lucide-react";

/**
 * List ⇄ Board for the same payment requests. The board used to be its own
 * menu item ("Pipeline") showing the same records as the list; one place,
 * two views, is one less thing to learn.
 */
export function ViewSwitch({ current }: { current: "list" | "board" }) {
  const base = "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition";
  return (
    <div className="inline-flex rounded-lg border border-gray-300 bg-white p-0.5" role="group" aria-label="View">
      <Link
        href="/requisitions?tab=all"
        aria-current={current === "list" ? "page" : undefined}
        className={`${base} ${current === "list" ? "bg-gray-900 text-white" : "text-gray-600 hover:text-gray-900"}`}
      >
        <List className="h-3.5 w-3.5" /> List
      </Link>
      <Link
        href="/requisitions/board"
        aria-current={current === "board" ? "page" : undefined}
        className={`${base} ${current === "board" ? "bg-gray-900 text-white" : "text-gray-600 hover:text-gray-900"}`}
      >
        <LayoutGrid className="h-3.5 w-3.5" /> Board
      </Link>
    </div>
  );
}
