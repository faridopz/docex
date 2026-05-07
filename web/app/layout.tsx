import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DOCex — AI document extraction",
  description:
    "Upload documents in bulk, define what to look for, get every document scored and ranked instantly. PDFs, Word docs, any volume.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
