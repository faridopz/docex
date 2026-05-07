import { Lightbulb } from "lucide-react";

/**
 * GuidanceCard
 *
 * The small blue-tinted explainer used at the top of each step in the
 * DOCex flow. One per section, max. Tells the user — in two or three
 * sentences — what the section is for and how to get good results.
 *
 * Visual rule: never red, never alarming. Guidance is help, not warning.
 */

interface GuidanceCardProps {
  title: string;
  children: React.ReactNode;
}

export function GuidanceCard({ title, children }: GuidanceCardProps) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-blue-100 bg-blue-50/60 px-4 py-3">
      <Lightbulb
        className="mt-0.5 h-4 w-4 shrink-0 text-blue-600"
        aria-hidden="true"
      />
      <div className="space-y-1 text-sm text-gray-700">
        <p className="font-medium text-gray-900">{title}</p>
        <p className="leading-relaxed">{children}</p>
      </div>
    </div>
  );
}
