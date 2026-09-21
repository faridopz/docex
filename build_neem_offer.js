const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  LevelFormat, PageBreak, convertInchesToTwip,
} = require("docx");

const NAVY = "1F3A5F";
const GREY = "6B7280";
const RULE = "D1D5DB";

// ── small builders ─────────────────────────────────────────────────────────

const p = (text, opts = {}) => new Paragraph({
  spacing: { after: opts.after ?? 140, line: 276 },
  alignment: opts.align,
  children: [new TextRun({
    text,
    size: opts.size ?? 21,          // half-points → 10.5pt
    bold: opts.bold,
    italics: opts.italics,
    color: opts.color ?? "111827",
    font: "Calibri",
  })],
});

/** A paragraph mixing bold and plain runs: rich(["Bold bit", true], ["rest", false]) */
const rich = (parts, opts = {}) => new Paragraph({
  spacing: { after: opts.after ?? 140, line: 276 },
  children: parts.map(([text, bold]) => new TextRun({
    text, bold: !!bold, size: opts.size ?? 21, font: "Calibri",
    color: opts.color ?? "111827",
  })),
});

const h1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 360, after: 180 },
  children: [new TextRun({ text, size: 30, bold: true, color: NAVY, font: "Calibri" })],
});

const h2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 240, after: 120 },
  children: [new TextRun({ text, size: 23, bold: true, color: NAVY, font: "Calibri" })],
});

const bullet = (text) => new Paragraph({
  numbering: { reference: "dots", level: 0 },
  spacing: { after: 100, line: 276 },
  children: [new TextRun({ text, size: 21, font: "Calibri", color: "111827" })],
});

const numbered = (text, ref = "nums1") => new Paragraph({
  numbering: { reference: ref, level: 0 },
  spacing: { after: 100, line: 276 },
  children: [new TextRun({ text, size: 21, font: "Calibri", color: "111827" })],
});

const hr = () => new Paragraph({
  spacing: { before: 160, after: 160 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: RULE } },
  children: [new TextRun({ text: "", size: 2 })],
});

const cell = (text, { bold, shade, width, align } = {}) => new TableCell({
  width: { size: width, type: WidthType.DXA },
  shading: shade ? { type: ShadingType.CLEAR, fill: shade, color: "auto" } : undefined,
  margins: { top: 80, bottom: 80, left: 120, right: 120 },
  children: [new Paragraph({
    alignment: align,
    spacing: { after: 0, line: 240 },
    children: [new TextRun({
      text, bold, size: 20, font: "Calibri",
      color: shade === NAVY ? "FFFFFF" : "111827",
    })],
  })],
});

/** rows: array of arrays. widths must sum to total. */
const table = (headers, rows, widths) => new Table({
  columnWidths: widths,
  width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
  borders: {
    top: { style: BorderStyle.SINGLE, size: 4, color: RULE },
    bottom: { style: BorderStyle.SINGLE, size: 4, color: RULE },
    left: { style: BorderStyle.SINGLE, size: 4, color: RULE },
    right: { style: BorderStyle.SINGLE, size: 4, color: RULE },
    insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: RULE },
    insideVertical: { style: BorderStyle.SINGLE, size: 4, color: RULE },
  },
  rows: [
    ...(headers ? [new TableRow({
      tableHeader: true,
      children: headers.map((h, i) =>
        cell(h, { bold: true, shade: NAVY, width: widths[i] })),
    })] : []),
    ...rows.map((r, ri) => new TableRow({
      children: r.map((c, i) => cell(String(c), {
        width: widths[i],
        shade: ri % 2 === 1 ? "F9FAFB" : undefined,
        align: i > 0 && headers ? AlignmentType.LEFT : undefined,
      })),
    })),
  ],
});

const sig = (label) => [
  p(label, { bold: true, after: 200 }),
  p("Name:  ______________________________________", { after: 200 }),
  p("Position:  ___________________________________", { after: 200 }),
  p("Signature:  __________________________________", { after: 200 }),
  p("Date:  _______________________________________", { after: 320 }),
];


/** A shaded emphasis block — one cell, no borders, light fill. */
const callout = (parts) => new Table({
  columnWidths: [8400],
  width: { size: 8400, type: WidthType.DXA },
  borders: {
    top: { style: BorderStyle.SINGLE, size: 4, color: "E5E7EB" },
    bottom: { style: BorderStyle.SINGLE, size: 4, color: "E5E7EB" },
    left: { style: BorderStyle.SINGLE, size: 18, color: NAVY },
    right: { style: BorderStyle.SINGLE, size: 4, color: "E5E7EB" },
    insideHorizontal: { style: BorderStyle.NONE },
    insideVertical: { style: BorderStyle.NONE },
  },
  rows: [new TableRow({
    cantSplit: true,
    children: [new TableCell({
      width: { size: 8400, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: "F8FAFC", color: "auto" },
      margins: { top: 160, bottom: 160, left: 220, right: 200 },
      children: [new Paragraph({
        spacing: { after: 0, line: 276 },
        children: parts.map(([text, bold]) => new TextRun({
          text, bold: !!bold, size: 21, font: "Calibri", color: "111827",
        })),
      })],
    })],
  })],
});

const gap = (after = 160) => new Paragraph({ spacing: { after }, children: [new TextRun({ text: "", size: 2 })] });

// ── content ────────────────────────────────────────────────────────────────

const COMPANY = "MICHIKA LABS LIMITED";
const body = [];

body.push(new Paragraph({
  spacing: { before: 200, after: 100 },
  children: [new TextRun({ text: COMPANY, size: 24, bold: true, color: GREY, font: "Calibri" })],
}));
body.push(new Paragraph({
  spacing: { after: 100 },
  children: [new TextRun({ text: "Offer for Neem Foundation", size: 46, bold: true, color: NAVY, font: "Calibri" })],
}));
body.push(new Paragraph({
  spacing: { after: 300 },
  children: [new TextRun({
    text: "Payment requisition, compliance and approval workflow",
    size: 24, color: "374151", font: "Calibri" })],
}));
body.push(table(null, [
  ["Prepared for", "Neem Foundation"],
  ["Prepared by", COMPANY],
  ["Date", "_______________________"],
  ["Valid for", "30 days from the date above"],
], [2400, 6000]));
body.push(gap(280));

// 1
body.push(h1("1.  The offer in one page"));
body.push(p("Neem asked to begin using the system in January. This offer is built around that date, in two phases."));
body.push(table(["", "Deployment", "Service"], [
  ["When", "November to December 2026", "From 1 January 2027"],
  ["What", "We deploy the software, configure it against your policies, run it alongside your team, and train your staff", "Neem runs its payments on the platform; we operate and support it"],
  ["Cost", "₦300,000 per month", "₦450,000 per month"],
], [1300, 3550, 3550]));
body.push(gap(200));
body.push(rich([
  ["The software is ours, and Neem is licensed to use it. ", true],
  ["This is not bespoke development commissioned by Neem. The platform is built, owned and maintained by Michika Labs Limited, already running, and already configured from the documents Neem has provided. What Neem is buying is the right to use it, configured to Neem's own policies, with us operating it. Section 7 sets out what that means for ownership."],
]));
body.push(rich([
  ["Why two phases rather than a long unpaid setup. ", true],
  ["Configuring a finance system against a real organisation is the work, not the preparation for it. During deployment your policies are translated into the system, your people are trained on it, and your first payments run through it with us sitting alongside. Charging for that period keeps it short and keeps it finished. An open ended setup has no date on which anybody has to be ready."],
]));
body.push(gap(140));

// 2
body.push(h1("2.  Deployment, November and December"));
body.push(p("₦300,000 per month, invoiced monthly. This is a reduced rate for the period in which Neem is not yet relying on the system."));
[
  ["Your policies become the system's rules. ", "Your approval chain, spend bands, the nineteen document packs from your Finance Processes deck, your chart of accounts, project codes and reference format. Much of this is already built from the documents you have given us."],
  ["We test it against payments you have already made. ", "We run historical payments through the configuration and confirm the system reaches the same answers your team did. You see that comparison before you rely on it."],
  ["Your people are trained on it. ", "Two sessions plus a written guide reflecting your own configuration rather than a generic manual. Further sessions during the period at no charge."],
  ["We run your first cycles with you. ", "Your first weekly payment run and your first month end, alongside your team rather than handed over with a phone number."],
  ["Adjustments during this period are included. ", "Thresholds, categories, document packs, approval stages, users, new accounts and new grant codes. This is what the deployment period is for."],
].forEach(([b, rest]) => body.push(rich([[b, true], [rest, false]])));
body.push(gap(60));
body.push(callout([
  ["At the end of December, Neem decides. ", true],
  ["If the system has done what this document says it will, it converts to the service in section 3 from 1 January. If it has not, Neem owes nothing further and walks away with a complete export of everything in it. There is no penalty and no notice period to serve."],
]));
body.push(gap(200));

// 3
body.push(h1("3.  Service, from January"));
body.push(p("₦450,000 per month, invoiced monthly in advance, payable within 14 days. No charge per user, because everyone at Neem who needs visibility should have it without that decision costing anything."));
body.push(rich([["Included: ", true], ["the platform, unlimited users, hosting, all configuration changes, support with a named contact, further training, monthly data exports, and platform improvements as they are released."]]));
body.push(rich([["Initial term: six months from 1 January", true], [", reviewed at the end. After that it continues monthly and either party may end it on 30 days' notice."]]));
body.push(gap(140));

// 4
body.push(h1("4.  What is the system, and what is extra"));
body.push(p("The core system is payment requisition, compliance checking and the approval workflow: everything a payment passes through from memo to bank, and the audit trail it leaves behind. That is what the monthly fee buys."));
body.push(p("Other capabilities are built and available, and are priced separately because not every organisation needs them:"));
body.push(table(["Module", "What it does", "Monthly"], [
  ["Timesheets & grant allocation", "Approved staff effort decides what each grant is charged for a salary, instead of a budgeted percentage nobody revisits. Answers the donor question “can you prove this person's time on this project”", "₦100,000"],
  ["Bank account verification", "Confirms an account number resolves to the name on the invoice before money moves. The check that catches a redirected payment", "₦60,000"],
  ["Document screening", "Ask plain language questions across a stack of documents, such as sub award applications or partner due diligence, and get answers with the source, the quote and a confidence level", "Quoted on scope"],
], [2100, 4500, 1800]));
body.push(gap(180));
body.push(rich([["Configuration is included; new systems are quoted. ", true], ["Moving a threshold, adding a category, changing the approval chain or opening a new grant account is a setting, and it is part of the service. Building something that does not exist today, such as a different workflow, another department's process, or an integration with a system you already run, is separate work, scoped and priced before anything begins. We would rather say which is which at the start than discover the disagreement later."]]));
body.push(gap(140));

// 5
body.push(h1("5.  Other systems at Neem"));
body.push(p("Through deployment we will see how Neem's other processes work, including procurement, grant reporting and programme data. Where we can help, we will say so and quote it separately. Nothing in this offer commits Neem to any of it, and nothing in it is contingent on Neem buying any of it."));
body.push(gap(140));

// 6 (was 7)
body.push(h1("6.  What is deliberately not included"));
body.push(p("We would rather tell you now than have you find it later."));
body.push(rich([["Payroll is switched off ", true], ["until Neem confirms PAYE bands and pension rates. A payroll run on assumed rates produces payslips that look right and are wrong."]]));
body.push(rich([["Tax identification checking confirms a TIN is well formed. ", true], ["Confirming it is registered to that company needs a paid provider, and we would rather say so than imply a check we are not making."]]));
body.push(rich([["There is no direct bank integration. ", true], ["Payments are prepared, checked and evidenced on the platform, then uploaded to GAPS as they are today."]]));
body.push(gap(140));

// 7 (was 8) — data AND software ownership
body.push(h1("7.  Your data, and our software"));
body.push(rich([["Neem's data belongs to Neem. ", true], ["Exportable in full at any time including on exit. It is not used for any purpose other than providing this service, and it is not used to train any model. You receive a complete readable copy every month without having to ask."]]));
body.push(rich([["The software belongs to Michika Labs Limited. ", true], ["The platform, its source code, and the engine underneath it remain our property throughout and after this agreement. Neem receives a licence to use it for the term, not ownership of it. Configuration built for Neem, meaning your policies, thresholds, document packs, codes and workflow, is yours and leaves with your data if you go."]]));
body.push(rich([["Improvements are shared. ", true], ["Work done for Neem that improves the platform itself becomes part of the product every client receives. That is why the price is a subscription rather than a development budget, and it is why Neem keeps receiving improvements it did not pay for separately."]]));
body.push(p("Named accounts with role based permissions, approval actions restricted to the department that owns each stage, all traffic encrypted, and records held in a managed database with nightly backups, each one verified by an actual restore."));
body.push(rich([["We can read your database; we cannot approve anything in it. ", true], ["Somebody has to be able to operate and repair the system, and we would rather say so. Every approval is recorded against a named Neem account in a tamper evident chain, so no payment can be authorised without one of your people doing it."]]));
body.push(p("A Data Processing Agreement is signed alongside the service agreement. Real payment data enters the system only once that is executed."));
body.push(gap(140));

// 8 (was 9)
body.push(h1("8.  Next steps"));
[
  "Neem confirms acceptance of this offer.",
  "Service agreement and Data Processing Agreement issued.",
  "Signature, and deployment begins within a week.",
].forEach((t) => body.push(numbered(t, "nums2")));
body.push(gap(200));

// 9 (was 10)
body.push(h1("9.  Acceptance"));
body.push(p("By signing below, Neem Foundation accepts the scope and commercial terms in this offer, subject to a service agreement and Data Processing Agreement."));
body.push(hr());
sig("For Neem Foundation").forEach((x) => body.push(x));
sig(`For ${COMPANY}`).forEach((x) => body.push(x));

// ── document ───────────────────────────────────────────────────────────────

const doc = new Document({
  creator: COMPANY,
  title: "Offer for Neem Foundation",
  description: "DOCex — finance and compliance workflow platform",
  numbering: {
    config: [
      {
        reference: "dots",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "•",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 420, hanging: 240 } } },
        }],
      },
      ...["nums1", "nums2"].map((reference) => ({
        reference,
        levels: [{
          level: 0, format: LevelFormat.DECIMAL, text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 460, hanging: 280 } } },
        }],
      })),
    ],
  },
  sections: [{
    properties: {
      page: {
        margin: {
          top: convertInchesToTwip(0.9), bottom: convertInchesToTwip(0.9),
          left: convertInchesToTwip(0.95), right: convertInchesToTwip(0.95),
        },
      },
    },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(process.argv[2] || "offer.docx", buf);
  console.log("written");
});
