import { redirect } from "next/navigation";

/**
 * The old launcher ("What would you like to do?") was built on compliance
 * checks and only reachable from a navigation bar the app no longer uses.
 * Home is /dashboard; this keeps any saved link working.
 */
export default function LegacyHomeRedirect() {
  redirect("/dashboard");
}
