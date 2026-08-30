// Framework / engineering deck for DOCex — portfolio/technical audience.
// Sanitized: no client names, synthetic examples only.
const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
const W = 13.3, H = 7.5;

// ── palette ────────────────────────────────────────────────────────────────
const INK = "0E1B33";      // deep navy (primary dark)
const NAVY = "1B2C4F";
const SLATE = "5B6B85";    // muted text
const EMER = "10B981";     // accent — "verified / cleared / deterministic"
const EMER_DK = "0E9F6E";
const LIGHT = "F4F6FA";    // light content bg
const WHITE = "FFFFFF";
const ICE = "CADCFC";      // soft blue on dark
const CARDLINE = "E3E8F0";

const HEAD = "Cambria";
const BODY = "Calibri";

function bg(slide, color) { slide.background = { color }; }
function shadow() { return { type: "outer", color: "9AA7BD", blur: 8, offset: 3, angle: 90, opacity: 0.35 }; }

// card helper
function card(slide, x, y, w, h, fill) {
  slide.addShape("roundRect", { x, y, w, h, rectRadius: 0.09, fill: { color: fill || WHITE }, line: { color: CARDLINE, width: 1 }, shadow: shadow() });
}
function circle(slide, x, y, d, fill, label, labelColor) {
  slide.addShape("ellipse", { x, y, w: d, h: d, fill: { color: fill } });
  if (label) slide.addText(label, { x, y, w: d, h: d, align: "center", valign: "middle", fontFace: HEAD, fontSize: 15, bold: true, color: labelColor || WHITE, margin: 0 });
}

// ── Slide 1 — Title (dark) ───────────────────────────────────────────────────
let s = p.addSlide(); bg(s, INK);
s.addText("DOCex", { x: 0.9, y: 2.05, w: 8, h: 1.0, fontFace: HEAD, fontSize: 60, bold: true, color: WHITE, margin: 0 });
s.addText("Deterministic-first document intelligence for compliance & finance", {
  x: 0.92, y: 3.05, w: 10.5, h: 0.9, fontFace: BODY, fontSize: 22, color: ICE, margin: 0 });
s.addText([
  { text: "An engine that resolves ~80% of compliance checks ", options: { color: "AEBBD6" } },
  { text: "in code", options: { color: EMER, bold: true } },
  { text: " — reserving the LLM only for genuine judgment.", options: { color: "AEBBD6" } },
], { x: 0.92, y: 3.95, w: 11, h: 0.6, fontFace: BODY, fontSize: 15, margin: 0 });
s.addText("Farid Abdurrahman   ·   Full-stack + AI systems   ·   Independent project (synthetic data)", {
  x: 0.92, y: 6.55, w: 11.4, h: 0.4, fontFace: BODY, fontSize: 12.5, color: "8494B4", margin: 0 });
circle(s, 11.2, 1.5, 1.1, EMER, "✓", WHITE);

// ── Slide 2 — The problem ────────────────────────────────────────────────────
s = p.addSlide(); bg(s, LIGHT);
s.addText("The problem", { x: 0.7, y: 0.55, w: 8, h: 0.7, fontFace: HEAD, fontSize: 34, bold: true, color: INK, margin: 0 });
s.addText("Compliance and finance teams drown in documents — and the obvious AI fix is the wrong one.", {
  x: 0.7, y: 1.35, w: 11.8, h: 0.6, fontFace: BODY, fontSize: 16, color: SLATE, margin: 0 });

// left: manual pain
card(s, 0.7, 2.2, 5.75, 4.4);
s.addText("Today: by hand", { x: 1.0, y: 2.45, w: 5.2, h: 0.5, fontFace: HEAD, fontSize: 20, bold: true, color: INK, margin: 0 });
const pains = [
  "Read every voucher, invoice and application by hand",
  "Cross-check invoice ↔ PO ↔ delivery note manually",
  "Add up receipts; hunt for duplicates",
  "Interpret policy from memory, differently each time",
];
s.addText(pains.map((t, i) => ({ text: t, options: { bullet: { code: "2022" }, color: "3A4763", breakLine: true, paraSpaceAfter: 10 } })),
  { x: 1.0, y: 3.05, w: 5.15, h: 3.3, fontFace: BODY, fontSize: 14.5, margin: 0 });

// right: the naive AI trap
card(s, 6.85, 2.2, 5.75, 4.4, INK);
s.addText("The naive fix: “throw it at an LLM”", { x: 7.15, y: 2.45, w: 5.2, h: 0.6, fontFace: HEAD, fontSize: 19, bold: true, color: WHITE, margin: 0 });
const trap = [
  ["Slow", "seconds per document, per rule"],
  ["Expensive", "tokens for work code does free"],
  ["Non-deterministic", "the same input can vary"],
  ["Unsafe for payments", "“usually right” isn’t good enough"],
];
let ty = 3.15;
trap.forEach(([h1, h2]) => {
  circle(s, 7.15, ty + 0.02, 0.32, EMER, "", WHITE);
  s.addText([{ text: h1 + "  ", options: { bold: true, color: WHITE } }, { text: "— " + h2, options: { color: ICE } }],
    { x: 7.62, y: ty - 0.05, w: 4.85, h: 0.5, fontFace: BODY, fontSize: 14, margin: 0, valign: "middle" });
  ty += 0.82;
});

// ── Slide 3 — Core insight ───────────────────────────────────────────────────
s = p.addSlide(); bg(s, INK);
s.addText("The core decision", { x: 0.9, y: 0.9, w: 8, h: 0.6, fontFace: BODY, fontSize: 18, color: EMER, bold: true, margin: 0 });
s.addText([
  { text: "Know when ", options: { color: WHITE } },
  { text: "not", options: { color: EMER, italic: true } },
  { text: " to use the LLM.", options: { color: WHITE } },
], { x: 0.9, y: 1.55, w: 11.5, h: 1.4, fontFace: HEAD, fontSize: 46, bold: true, margin: 0 });
s.addText("Reading a number off a labelled field, matching a PO to an invoice, summing receipts, spotting a duplicate — these are solved, deterministic problems. Code does them in microseconds, for free, and never hallucinates. The model is the last resort, not the first.", {
  x: 0.9, y: 3.4, w: 10.8, h: 1.6, fontFace: BODY, fontSize: 18, color: ICE, margin: 0, lineSpacingMultiple: 1.15 });
s.addText("Most “AI products” wrap an LLM. DOCex uses it as little as possible — which is exactly what makes it fast, cheap, auditable, and model-proof.", {
  x: 0.9, y: 5.5, w: 11, h: 1.0, fontFace: BODY, fontSize: 15, italic: true, color: "8FA0C2", margin: 0 });

// ── Slide 4 — Architecture ───────────────────────────────────────────────────
s = p.addSlide(); bg(s, LIGHT);
s.addText("Architecture: a layered pipeline", { x: 0.7, y: 0.5, w: 11, h: 0.7, fontFace: HEAD, fontSize: 32, bold: true, color: INK, margin: 0 });
s.addText("Each layer is as cheap and reliable as possible. Work only escalates when it truly needs judgment.", {
  x: 0.7, y: 1.28, w: 11.8, h: 0.5, fontFace: BODY, fontSize: 15, color: SLATE, margin: 0 });

// deterministic band
card(s, 0.7, 2.05, 11.9, 2.55, "E8F7F0");
s.addText([{ text: "DETERMINISTIC — code, runs first  ", options: { bold: true, color: EMER_DK } }, { text: "~milliseconds · zero tokens", options: { color: "3A4763" } }],
  { x: 1.0, y: 2.25, w: 11, h: 0.4, fontFace: BODY, fontSize: 13.5, margin: 0 });
const steps = ["Parse\n(PDF/DOCX/XLSX)", "Extract\nfields", "Check\ncompleteness", "Deterministic\ncontrols", "Policy → \nrules"];
const sw = 2.16, gap = 0.15; let sx = 1.0;
steps.forEach((t, i) => {
  s.addShape("roundRect", { x: sx, y: 2.85, w: sw, h: 1.45, rectRadius: 0.07, fill: { color: WHITE }, line: { color: EMER, width: 1.25 } });
  s.addText(t, { x: sx, y: 2.85, w: sw, h: 1.45, align: "center", valign: "middle", fontFace: BODY, fontSize: 13.5, bold: true, color: INK, margin: 0.05 });
  if (i < steps.length - 1) s.addText("›", { x: sx + sw - 0.02, y: 2.85, w: gap + 0.08, h: 1.45, align: "center", valign: "middle", fontFace: HEAD, fontSize: 22, bold: true, color: EMER, margin: 0 });
  sx += sw + gap;
});
// arrow down
s.addText("▼  escalate only what needs judgment", { x: 0.7, y: 4.7, w: 11.9, h: 0.4, align: "center", fontFace: BODY, fontSize: 12.5, italic: true, color: SLATE, margin: 0 });
// LLM band
card(s, 3.05, 5.2, 7.2, 1.55, INK);
s.addText([{ text: "LLM — judgment only", options: { bold: true, color: EMER, breakLine: true } },
  { text: "messy extraction · nuanced rules · explanation · drafting — grounded with the code-extracted facts", options: { color: ICE } }],
  { x: 3.35, y: 5.35, w: 6.7, h: 1.25, fontFace: BODY, fontSize: 14, margin: 0, valign: "middle", lineSpacingMultiple: 1.1 });

// ── Slide 5 — The deterministic engine (modules) ─────────────────────────────
s = p.addSlide(); bg(s, LIGHT);
s.addText("The deterministic engine — the moat", { x: 0.7, y: 0.5, w: 11.5, h: 0.7, fontFace: HEAD, fontSize: 30, bold: true, color: INK, margin: 0 });
s.addText("Reusable, domain-agnostic modules. All code, all fast — the part a next-gen model can’t commoditise.", {
  x: 0.7, y: 1.28, w: 11.8, h: 0.5, fontFace: BODY, fontSize: 15, color: SLATE, margin: 0 });
const mods = [
  ["fast_extract", "Parsing — PDF/DOCX/Excel to text (PyMuPDF, fallbacks)"],
  ["fast_fields", "Labelled-regex field pull — amounts, invoice/PO/GRN, dates"],
  ["doc_completeness", "Signature-matching — are the required documents present?"],
  ["policy_rules", "Policy → structured, citeable rulebook — no model call"],
  ["payment_checks", "Three-way match + duplicate-payment detection"],
  ["receipts", "Travel-advance retirement reconciliation"],
];
const cw = 3.83, ch = 1.65, cgx = 0.2, cgy = 0.25; let cx = 0.7, cy = 2.1;
mods.forEach((m, i) => {
  const col = i % 3, row = Math.floor(i / 3);
  const X = 0.7 + col * (cw + cgx), Y = 2.1 + row * (ch + cgy);
  card(s, X, Y, cw, ch);
  circle(s, X + 0.28, Y + 0.3, 0.42, EMER, "‹›", WHITE);
  s.addText(m[0], { x: X + 0.85, y: Y + 0.28, w: cw - 1.0, h: 0.45, fontFace: "Courier New", fontSize: 15, bold: true, color: INK, margin: 0, valign: "middle" });
  s.addText(m[1], { x: X + 0.3, y: Y + 0.85, w: cw - 0.55, h: 0.7, fontFace: BODY, fontSize: 12.5, color: SLATE, margin: 0 });
});

// ── Slide 6 — Where the LLM earns its place ──────────────────────────────────
s = p.addSlide(); bg(s, LIGHT);
s.addText("Where the LLM earns its place", { x: 0.7, y: 0.55, w: 11, h: 0.7, fontFace: HEAD, fontSize: 32, bold: true, color: INK, margin: 0 });
s.addText("Used deliberately, as one layer — with the code-extracted facts as grounding, citations, and a human in the loop.", {
  x: 0.7, y: 1.35, w: 11.8, h: 0.5, fontFace: BODY, fontSize: 15, color: SLATE, margin: 0 });
const uses = [
  ["Messy extraction", "Read fields from an ugly scanned invoice or a photographed receipt the regex can’t."],
  ["Nuanced rules", "Judge policy clauses that need real reading comprehension, not a pattern match."],
  ["Explanation", "Say, in plain English, why a deterministic control flagged a payment."],
  ["Drafting", "Write the memo, the follow-up, the exception note for a human to approve."],
];
let uy = 2.2;
uses.forEach(([h1, h2], i) => {
  card(s, 0.7, uy, 11.9, 1.0);
  circle(s, 1.0, uy + 0.29, 0.42, INK, String(i + 1), WHITE);
  s.addText(h1, { x: 1.6, y: uy + 0.12, w: 3.2, h: 0.75, fontFace: HEAD, fontSize: 16, bold: true, color: INK, margin: 0, valign: "middle" });
  s.addText(h2, { x: 4.9, y: uy + 0.12, w: 7.5, h: 0.75, fontFace: BODY, fontSize: 13.5, color: SLATE, margin: 0, valign: "middle" });
  uy += 1.12;
});

// ── Slide 7 — What it does (outcomes) ────────────────────────────────────────
s = p.addSlide(); bg(s, INK);
s.addText("What it delivers", { x: 0.9, y: 0.55, w: 10, h: 0.7, fontFace: HEAD, fontSize: 32, bold: true, color: WHITE, margin: 0 });
s.addText("Outcomes, not features — the finished work handed back.", { x: 0.9, y: 1.35, w: 11, h: 0.5, fontFace: BODY, fontSize: 15, color: ICE, margin: 0 });
const outs = [
  ["~1 sec", "Policy → rulebook", "A procurement or travel policy becomes a structured, citeable rulebook — no model call for the common case."],
  ["3-way", "Payment checks", "Invoice ↔ PO ↔ GRN reconciled, duplicates caught, verdict with citations — instantly."],
  ["auto", "Travel retirement", "Receipts reconciled against the advance: “recover ₦X / reimburse ₦Y,” problems flagged. No OCR."],
  ["append-only", "Audit trail", "Every decision logged and exportable — provenance a compliance tool lives or dies on."],
];
const ow = 5.75, oh = 2.2; let ox, oy;
outs.forEach((o, i) => {
  const col = i % 2, row = Math.floor(i / 2);
  ox = 0.9 + col * (ow + 0.35); oy = 2.15 + row * (oh + 0.3);
  card(s, ox, oy, ow, oh, NAVY);
  s.addText(o[0], { x: ox + 0.35, y: oy + 0.28, w: ow - 0.7, h: 0.7, fontFace: HEAD, fontSize: 30, bold: true, color: EMER, margin: 0 });
  s.addText(o[1], { x: ox + 0.35, y: oy + 0.95, w: ow - 0.7, h: 0.45, fontFace: HEAD, fontSize: 17, bold: true, color: WHITE, margin: 0 });
  s.addText(o[2], { x: ox + 0.35, y: oy + 1.4, w: ow - 0.7, h: 0.7, fontFace: BODY, fontSize: 12.5, color: ICE, margin: 0 });
});

// ── Slide 8 — Reliability engineering ────────────────────────────────────────
s = p.addSlide(); bg(s, LIGHT);
s.addText("Reliability is a feature", { x: 0.7, y: 0.55, w: 11, h: 0.7, fontFace: HEAD, fontSize: 32, bold: true, color: INK, margin: 0 });
s.addText("The system is built to fail safe — a bug in the fast path degrades gracefully, it never lies about progress.", {
  x: 0.7, y: 1.35, w: 11.8, h: 0.5, fontFace: BODY, fontSize: 15, color: SLATE, margin: 0 });
const rel = [
  ["Graceful degradation", "A fault in the deterministic path falls back to the LLM — a bug can’t break a check."],
  ["Code-level block wins", "If a duplicate or mismatch already blocks a payment, the slow model call is skipped."],
  ["Stale-guard", "A stuck background job surfaces an honest error instead of spinning forever."],
  ["CI before deploy", "Imports the backend + builds the frontend on every push — broken code can’t ship silently."],
];
let rx = 0.7, ry = 2.15;
rel.forEach((r, i) => {
  const col = i % 2, row = Math.floor(i / 2);
  const X = 0.7 + col * (5.95 + 0.25), Y = 2.15 + row * (1.9 + 0.25);
  card(s, X, Y, 5.95, 1.9);
  circle(s, X + 0.3, Y + 0.32, 0.46, EMER, "✓", WHITE);
  s.addText(r[0], { x: X + 0.9, y: Y + 0.3, w: 4.9, h: 0.5, fontFace: HEAD, fontSize: 16.5, bold: true, color: INK, margin: 0, valign: "middle" });
  s.addText(r[1], { x: X + 0.35, y: Y + 0.95, w: 5.3, h: 0.8, fontFace: BODY, fontSize: 13, color: SLATE, margin: 0 });
});

// ── Slide 9 — Defensible & model-proof ───────────────────────────────────────
s = p.addSlide(); bg(s, INK);
s.addText("Defensible & model-proof", { x: 0.9, y: 0.9, w: 10, h: 0.6, fontFace: BODY, fontSize: 18, color: EMER, bold: true, margin: 0 });
s.addText("Every time AI gets better, the work gets better — at the same price.", {
  x: 0.9, y: 1.5, w: 11.3, h: 1.3, fontFace: HEAD, fontSize: 34, bold: true, color: WHITE, margin: 0, lineSpacingMultiple: 1.05 });
const moat = [
  ["Low marginal cost", "Code does ~80% of the work, so each additional check costs almost nothing."],
  ["Model gains compound", "A stronger LLM improves the judgment layer without changing the architecture or price."],
  ["The moat is the workflow", "Domain rules, the pipeline, and accumulated data — not copyable code."],
];
let mx = 0.9;
moat.forEach((m) => {
  card(s, mx, 3.5, 3.77, 2.8, NAVY);
  s.addText(m[0], { x: mx + 0.3, y: 3.8, w: 3.2, h: 0.9, fontFace: HEAD, fontSize: 17, bold: true, color: EMER, margin: 0 });
  s.addText(m[1], { x: mx + 0.3, y: 4.7, w: 3.2, h: 1.4, fontFace: BODY, fontSize: 13.5, color: ICE, margin: 0, lineSpacingMultiple: 1.1 });
  mx += 3.77 + 0.28;
});

// ── Slide 10 — Tech stack ────────────────────────────────────────────────────
s = p.addSlide(); bg(s, LIGHT);
s.addText("Built & shipped", { x: 0.7, y: 0.55, w: 10, h: 0.7, fontFace: HEAD, fontSize: 32, bold: true, color: INK, margin: 0 });
s.addText("Full-stack, AI, and infrastructure — designed, built, and deployed to production solo.", {
  x: 0.7, y: 1.35, w: 11.8, h: 0.5, fontFace: BODY, fontSize: 15, color: SLATE, margin: 0 });
const stack = [
  ["Frontend", "Next.js 14 · TypeScript (strict) · Tailwind · shadcn/ui"],
  ["Backend", "FastAPI · Python · Pydantic v2 · PyMuPDF · openpyxl"],
  ["AI", "Anthropic Claude — Sonnet for judgment, Haiku for light tasks · prompt caching"],
  ["Infra & CI/CD", "AWS ECS / Terraform · Railway · Vercel · GitHub Actions"],
];
let hy = 2.2;
stack.forEach(([h1, h2]) => {
  card(s, 0.7, hy, 11.9, 1.0);
  s.addText(h1, { x: 1.0, y: hy, w: 2.8, h: 1.0, fontFace: HEAD, fontSize: 17, bold: true, color: EMER_DK, margin: 0, valign: "middle" });
  s.addText(h2, { x: 3.9, y: hy, w: 8.5, h: 1.0, fontFace: BODY, fontSize: 14.5, color: INK, margin: 0, valign: "middle" });
  hy += 1.12;
});

// ── Slide 11 — What I learned ────────────────────────────────────────────────
s = p.addSlide(); bg(s, LIGHT);
s.addText("What building it taught me", { x: 0.7, y: 0.6, w: 11, h: 0.7, fontFace: HEAD, fontSize: 32, bold: true, color: INK, margin: 0 });
const lessons = [
  ["Judgment > wrapping", "Knowing when NOT to reach for the model is the senior skill. Most of the problem is better solved in fast, testable, auditable code."],
  ["Reliability is designed", "Graceful degradation, fail-safe fallbacks, and honest error states are features you build in, not afterthoughts."],
  ["Shipping is a discipline", "Boot crashes, middleware deadlocks, build-time env baking, broken pipelines — diagnosing production is half the craft."],
];
let ly = 1.7;
lessons.forEach((l, i) => {
  card(s, 0.7, ly, 11.9, 1.55);
  circle(s, 1.05, ly + 0.5, 0.55, INK, String(i + 1), WHITE);
  s.addText(l[0], { x: 1.85, y: ly + 0.22, w: 10.4, h: 0.5, fontFace: HEAD, fontSize: 18, bold: true, color: INK, margin: 0 });
  s.addText(l[1], { x: 1.85, y: ly + 0.72, w: 10.4, h: 0.7, fontFace: BODY, fontSize: 13.5, color: SLATE, margin: 0 });
  ly += 1.72;
});

// ── Slide 12 — Closing ───────────────────────────────────────────────────────
s = p.addSlide(); bg(s, INK);
s.addText("DOCex", { x: 0.9, y: 2.2, w: 9, h: 1.0, fontFace: HEAD, fontSize: 52, bold: true, color: WHITE, margin: 0 });
s.addText([
  { text: "Code does the certain. The model does the judgment. ", options: { color: ICE } },
  { text: "The work gets better as AI does.", options: { color: EMER, bold: true } },
], { x: 0.92, y: 3.35, w: 11, h: 0.9, fontFace: BODY, fontSize: 19, margin: 0 });
s.addText([
  { text: "Live demo:  ", options: { bold: true, color: WHITE } }, { text: "[your link]        ", options: { color: ICE } },
  { text: "Walkthrough:  ", options: { bold: true, color: WHITE } }, { text: "[video]        ", options: { color: ICE } },
  { text: "Code:  ", options: { bold: true, color: WHITE } }, { text: "[repo]", options: { color: ICE } },
], { x: 0.92, y: 5.2, w: 11.4, h: 0.5, fontFace: BODY, fontSize: 14, margin: 0 });
s.addText("Farid Abdurrahman", { x: 0.92, y: 6.5, w: 8, h: 0.4, fontFace: BODY, fontSize: 13, color: "8494B4", margin: 0 });
circle(s, 11.1, 2.0, 1.0, EMER, "✓", WHITE);

p.writeFile({ fileName: "DOCex_Framework_Deck.pptx" }).then((f) => console.log("WROTE", f));
