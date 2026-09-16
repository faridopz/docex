import { redirect } from "next/navigation";

/**
 * The payment pipeline moved to /requisitions/board.
 *
 * It used to live here and be fed by compliance checks, which made the one
 * screen titled "every payment" blind to the requisition engine — the actual
 * payment spine. It now reads requisitions, so it belongs under /requisitions
 * with the rest of that flow rather than under /compliance, which is the
 * policy library.
 *
 * This redirect stays so anyone holding the old link (a bookmark, a link in
 * an email to an approver) still lands on the working board instead of a 404.
 */
export default function LegacyPipelineBoardRedirect() {
  redirect("/requisitions/board");
}
