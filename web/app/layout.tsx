import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

// This is what a prospect sees in a browser tab, in a Google result, and in
// the preview card when the link is pasted into WhatsApp or an email. It had
// been left on the original extraction product: "documents scored and ranked".
// Anyone who received the proposal and then looked the company up read a
// pitch for something else entirely.
export const metadata: Metadata = {
  title: "DOCex — payment approvals and compliance for donor-funded organisations",
  description:
    "Every payment checked against your own written policy before it reaches an approver, and an audit trail that cannot be quietly edited. Built for finance teams that have to prove how money was spent.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className="min-h-screen">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
