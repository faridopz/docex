"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, CheckCheck, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/erpFormat";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/erpApi";
import type { AppNotification, Department } from "@/types/erp";

/**
 * Notification bell — the "action needed" feed for the signed-in user's
 * department. Research: notifications should carry context inline and never
 * overwhelm — so we show a compact unread badge, a tidy dropdown with the
 * transaction reference + one-line detail, and a single "mark all read".
 * Polls every 20s so the badge stays live without a websocket.
 */
export function NotificationBell({ department }: { department: Department }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AppNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  async function refresh() {
    try {
      const r = await listNotifications(department);
      setItems(r.notifications);
      setUnread(r.unread);
    } catch {
      /* stay quiet on transient errors — the bell is ambient */
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 20000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [department]);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  async function openFeed() {
    setOpen((o) => !o);
    if (!open) {
      setLoading(true);
      await refresh();
      setLoading(false);
    }
  }

  async function go(n: AppNotification) {
    setOpen(false);
    if (!n.read) {
      try {
        await markNotificationRead(n.id);
        setUnread((u) => Math.max(0, u - 1));
      } catch {
        /* ignore */
      }
    }
    router.push(`/transactions/${encodeURIComponent(n.txn_ref)}`);
  }

  async function clearAll() {
    try {
      await markAllNotificationsRead(department);
      setUnread(0);
      setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    } catch {
      /* ignore */
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={openFeed}
        aria-label="Notifications"
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900"
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
            <span className="text-sm font-semibold text-gray-900">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                onClick={clearAll}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-gray-500 transition hover:text-gray-900"
              >
                <CheckCheck className="h-3.5 w-3.5" /> Mark all read
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-8 text-gray-400">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            ) : items.length === 0 ? (
              <p className="px-3 py-8 text-center text-xs text-gray-400">
                You&apos;re all caught up.
              </p>
            ) : (
              items.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => go(n)}
                  className={cn(
                    "flex w-full flex-col items-start gap-0.5 border-b border-gray-50 px-3 py-2.5 text-left transition hover:bg-gray-50",
                    !n.read && "bg-brand-50/40",
                  )}
                >
                  <div className="flex w-full items-center gap-2">
                    {!n.read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />}
                    <span className="truncate text-sm font-medium text-gray-900">{n.title}</span>
                    <span className="ml-auto shrink-0 text-[10px] text-gray-400">
                      {relativeTime(n.created_at)}
                    </span>
                  </div>
                  {n.body && <span className="line-clamp-2 text-xs text-gray-500">{n.body}</span>}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
