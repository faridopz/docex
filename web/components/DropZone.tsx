"use client";

import { useState } from "react";
import { AlertCircle, FileText, Upload, X } from "lucide-react";
import { detectQuarter } from "@/lib/quarter-detect";

/**
 * DropZone
 *
 * The drag-and-drop file uploader used wherever DOCex needs files from
 * the user. Originally lived inside ApplicantUpload — lifted out so the
 * policy upload (Compliance create flow) and the payment-bundle upload
 * (Compliance check flow) can share it without duplication.
 *
 * Behaviour:
 *   - Accepts PDF, DOCX, TXT. Anything else is silently rejected with a
 *     dismissable amber notice — never a hard error, never a popup.
 *   - Deduplicates by (filename, size) so re-dragging the same file is
 *     a no-op instead of doubling up.
 *   - Detects quarter labels from filenames (Q3-2024 etc.) and shows a
 *     small chip alongside each file. Invisible if the regex doesn't
 *     match, so harmless for non-quarterly use cases.
 *
 * Visual rule: never red, never alarming. Files are tools, not threats.
 */

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt"];
const ACCEPTED_LABEL = "PDF, DOCX, or TXT";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isAccepted(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

interface DropZoneProps {
  files: File[];
  onFilesChange: (files: File[]) => void;
}

export function DropZone({ files, onFilesChange }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [rejectedCount, setRejectedCount] = useState(0);

  const addFiles = (incoming: File[]) => {
    const accepted: File[] = [];
    let rejected = 0;
    for (const f of incoming) {
      if (isAccepted(f)) accepted.push(f);
      else rejected += 1;
    }
    // Avoid duplicates by filename + size
    const existing = new Set(files.map((f) => `${f.name}:${f.size}`));
    const fresh = accepted.filter((f) => !existing.has(`${f.name}:${f.size}`));
    if (fresh.length > 0) onFilesChange([...files, ...fresh]);
    setRejectedCount(rejected);
  };

  const removeFile = (name: string, size: number) => {
    onFilesChange(files.filter((f) => !(f.name === name && f.size === size)));
  };

  const totalBytes = files.reduce((sum, f) => sum + f.size, 0);

  return (
    <div className="space-y-2">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          if (!isDragging) setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          addFiles(Array.from(e.dataTransfer.files));
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition ${
          isDragging
            ? "border-blue-600 bg-blue-50"
            : "border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-gray-100"
        }`}
      >
        <Upload
          className={`h-6 w-6 ${isDragging ? "text-blue-600" : "text-gray-400"}`}
        />
        <p className="mt-2 text-sm font-medium text-gray-700">
          Drop documents here or click to browse
        </p>
        <p className="mt-1 text-xs text-gray-500">{ACCEPTED_LABEL}</p>
        <input
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(",")}
          onChange={(e) => {
            if (e.target.files) addFiles(Array.from(e.target.files));
            // Reset so the same file can be re-added after removal
            e.target.value = "";
          }}
          className="hidden"
        />
      </label>

      {rejectedCount > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1">
            Skipped {rejectedCount} {rejectedCount === 1 ? "file" : "files"} —
            only {ACCEPTED_LABEL} are supported.
          </span>
          <button
            type="button"
            onClick={() => setRejectedCount(0)}
            className="shrink-0 text-amber-600 hover:text-amber-800"
            aria-label="Dismiss notice"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {files.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2 text-xs text-gray-500">
            <span>
              {files.length} {files.length === 1 ? "file" : "files"}
            </span>
            <span>{formatBytes(totalBytes)}</span>
          </div>
          <ul className="divide-y divide-gray-100">
            {files.map((f) => {
              // Cheap regex over the filename — no API call, no state.
              // Returns null if we can't tell, in which case we just don't
              // render a chip. The reviewer can still proceed.
              const quarter = detectQuarter(f.name);
              return (
                <li
                  key={`${f.name}:${f.size}`}
                  className="flex items-center gap-3 px-3 py-2"
                >
                  <FileText className="h-4 w-4 shrink-0 text-gray-400" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-gray-900">{f.name}</p>
                    <div className="flex items-center gap-2">
                      <p className="text-xs text-gray-500">
                        {formatBytes(f.size)}
                      </p>
                      {quarter && (
                        <span
                          title={`Detected: ${quarter.source}`}
                          className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700 ring-1 ring-blue-100"
                        >
                          {quarter.label}
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeFile(f.name, f.size)}
                    className="shrink-0 rounded-md p-1 text-gray-400 transition hover:bg-red-50 hover:text-red-600"
                    aria-label={`Remove ${f.name}`}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
