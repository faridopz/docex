"use client";

import { useEffect, useRef, useState } from "react";
import { Eraser, PenLine } from "lucide-react";

/**
 * <SignaturePad>
 *
 * A small HTML canvas the user can draw a signature on with mouse or
 * touch. The canvas exports as a base64 PNG (`data:image/png;base64,...`)
 * that we persist on the relevant DecisionEvent. Paired with a typed-name
 * input so the audit trail captures both: the recognisable mark and the
 * legible name behind it.
 *
 * Why both? The Nigerian Electronic Transactions Bill (and most donor
 * audit regimes) accepts an electronic signature when the identity of
 * the signer can be reasonably established. A drawn squiggle alone is
 * weak; a typed name + drawn signature + timestamp + ip (post-auth)
 * is reasonable evidence in context.
 *
 * Usage:
 *   <SignaturePad
 *     name={name}
 *     onNameChange={setName}
 *     dataUrl={sig}
 *     onChange={setSig}
 *   />
 *
 * The parent owns both pieces of state and submits them to whichever
 * endpoint signed the action (approve, escalate, clarification respond).
 */
export function SignaturePad({
  name,
  onNameChange,
  dataUrl,
  onChange,
  required = false,
  label = "Sign to confirm",
  hint = "Draw your signature with the mouse, then type your full name. Both go to the audit trail.",
}: {
  name: string;
  onNameChange: (v: string) => void;
  dataUrl: string | null;
  onChange: (v: string | null) => void;
  required?: boolean;
  label?: string;
  hint?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const lastPointRef = useRef<{ x: number; y: number } | null>(null);
  const [empty, setEmpty] = useState(!dataUrl);

  // Set up the canvas backing-store at devicePixelRatio so the drawn
  // line stays crisp on retina displays. We do this once per mount.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#111827";
    ctx.lineWidth = 1.8;
  }, []);

  function pointFromEvent(
    e: React.PointerEvent<HTMLCanvasElement>,
  ): { x: number; y: number } {
    const rect = (e.target as HTMLCanvasElement).getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function start(e: React.PointerEvent<HTMLCanvasElement>) {
    drawingRef.current = true;
    lastPointRef.current = pointFromEvent(e);
    (e.target as HTMLCanvasElement).setPointerCapture(e.pointerId);
  }

  function move(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    const canvas = canvasRef.current;
    const last = lastPointRef.current;
    if (!canvas || !last) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const p = pointFromEvent(e);
    ctx.beginPath();
    ctx.moveTo(last.x, last.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    lastPointRef.current = p;
    if (empty) setEmpty(false);
  }

  function end() {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    lastPointRef.current = null;
    const canvas = canvasRef.current;
    if (!canvas) return;
    // Export at moderate quality — signatures are visually simple so
    // PNG compression already gives us a small payload.
    const url = canvas.toDataURL("image/png");
    onChange(url);
  }

  function clear() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    setEmpty(true);
    onChange(null);
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-gray-700">
          <PenLine className="h-3.5 w-3.5" />
          {label}
          {required && <span className="text-rose-500">*</span>}
        </div>
        <button
          type="button"
          onClick={clear}
          disabled={empty}
          className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2 py-1 text-[11px] text-gray-600 transition hover:border-gray-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Eraser className="h-3 w-3" />
          Clear
        </button>
      </div>
      <p className="mt-1 text-[11px] text-gray-500">{hint}</p>

      <div className="mt-2 rounded-lg border border-dashed border-gray-300 bg-white">
        <canvas
          ref={canvasRef}
          onPointerDown={start}
          onPointerMove={move}
          onPointerUp={end}
          onPointerLeave={end}
          onPointerCancel={end}
          className="block h-32 w-full touch-none rounded-lg"
          aria-label="Signature canvas — draw your signature here"
        />
      </div>

      <label className="mt-3 block">
        <span className="text-[11px] font-medium uppercase tracking-wide text-gray-600">
          Typed name {required && <span className="text-rose-500">*</span>}
        </span>
        <input
          type="text"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="Your full name"
          className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
        />
      </label>
    </div>
  );
}
