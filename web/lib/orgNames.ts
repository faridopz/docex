"use client";

/**
 * The organisation's own names for its departments ("Finance / Audit",
 * "Assistant Executive Director"), shared by every screen.
 *
 * Screens used to either fetch these themselves or fall back to a built-in
 * table of labels ("Program / M&E") that belonged to one early client, so a
 * NEEM user saw somebody else's department name on their own dashboard.
 * The engine carries no department names; the org's profile does.
 */
import { useEffect, useState } from "react";
import { listDepartments } from "@/lib/erpApi";
import { humanise } from "@/lib/requisitionFormat";

let cached: Promise<Record<string, string>> | null = null;

function load(): Promise<Record<string, string>> {
  if (!cached) {
    cached = listDepartments()
      .then((r) => Object.fromEntries(r.departments.map((d) => [d.key, d.name])))
      .catch(() => {
        cached = null; // try again next time rather than caching a failure
        return {};
      });
  }
  return cached;
}

/** Returns a function key → display name; falls back to the key, humanised. */
export function useDepartmentNames(): (key?: string | null) => string {
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => {
    let live = true;
    void load().then((n) => {
      if (live) setNames(n);
    });
    return () => {
      live = false;
    };
  }, []);
  return (key?: string | null) => (key ? names[key] || humanise(key) : "—");
}
