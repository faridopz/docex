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

const COMPANY = "LIMA TECH";
const body = [];

// Header — deliberately not a full cover page. This is an offer to read and
// sign, not a brochure.
body.push(new Paragraph({
  spacing: { before: 200, after: 100 },
  children: [new TextRun({ text: COMPANY, size: 24, bold: true, color: GREY, font: "Calibri" })],
}));
body.push(new Paragraph({
  spacing: { after: 100 },
  children: [new TextRun({ text: "Offer for Neem Foundation", size: 46, bold: true, color: NAVY, font: "Calibri" })],
}));
body.push(new Paragraph({
  spacing: { after: 320 },
  children: [new TextRun({
    text: "DOCex — every payment checked against your own policy, with the audit trail written as you go",
    size: 24, color: "374151", font: "Calibri",
  })],
}));
body.push(table(null, [
  ["Prepared for", "Neem Foundation"],
  ["Prepared by", COMPANY],
  ["Date", "_______________________"],
  ["Valid for", "30 days from the date above"],
], [2400, 6000]));
body.push(gap(280));

// 1 — the problem
body.push(h1("1.  What this fixes"));
body.push(p("Neem's finance process is unusually well documented. The approval chain is real, the thresholds are written down, and the document packs are specified. The problem is not the policy — it is that running a good policy by hand costs your team days a month and still drifts."));
body.push(rich([["Compliance is checked by memory. ", true], ["Roughly a hundred payments a month pass through six departments and four approval stages. Whether a payment carries the right documents for its category, and whether it crossed a threshold that needed another signature, depends on somebody remembering at the moment they look at it."], ]));
body.push(rich([["Month-end is twenty reconciliations by hand. ", true], ["Twenty project accounts across GTBank, Zenith and Lotus, each reconciled in Excel, with withholding tax putting a second debit on the statement for nearly every vendor payment."], ]));
body.push(gap(60));
body.push(callout([
  ["Two things we found in your own documents. ", true],
  ["Your signed Procurement Policy requires three quotes from ₦200,001. The Finance Processes material your staff are trained on says a direct memo is sufficient to ₦499,999. Those disagree across a ₦300,000 band — and it is the band most of your spending sits in. Separately, we read six months of your CARE/FCDO reconciliation workbook: in two of those months the reconciliation completed without a figure it needed and the maths still balanced, because both sides were drawn from the cashbook. Neither is a criticism. They are the clearest evidence we have that manual control drifts quietly, and that nothing tells you when it has."],
]));
body.push(gap(200));

// 2 — what they get
body.push(h1("2.  What Neem gets"));
body.push(p("The system is already configured from your signed Procurement Policy, Finance Processes material, voucher, memo and advance forms, and your CARE/FCDO cashbook. Not a generic template — your six departments, four approval stages, five spend bands, nineteen document packs, your chart of accounts, project codes and reference format."));
[
  ["Problems surface before an approver sees them. ", "Every request is checked the moment it is raised — amount ceiling, category, required documents for that category, duplicates against the last thirty days, overdue advances. The person raising it fixes the problem while the invoice is still in front of them."],
  ["Your chain, in your order. ", "Line manager, Finance/Audit, Admin, AED — the same people, the same sequence as today. Approvers who are travelling can sign by secure link without an account."],
  ["Policy can be overridden; the override is the record. ", "Releasing a blocked payment requires a written reason and someone with the authority to give it. Both are recorded permanently, so six months later the answer to “why did this go through” is written down rather than remembered."],
  ["An audit trail that cannot be quietly edited. ", "Every step is written to an append-only log, each entry cryptographically linked to the one before it. Alter any historical entry and the chain fails to verify and says so."],
  ["Month-end produced, not assembled. ", "Per-account bank reconciliation that compares individual lines rather than balances — which is what finds the payment nobody entered. Evidence for any month or quarter is a download."],
  ["Advance retirement on your own clock. ", "Your policy gives five working days and escalates from there. The system runs that clock and shows what is overdue before it becomes an audit finding."],
  ["Payment lists import straight from Excel. ", "A stipend or beneficiary schedule of up to a hundred payees, columns in any order, through the same checks and the same chain as a single payment."],
].forEach(([b, rest]) => body.push(rich([[b, true], [rest, false]])));
body.push(gap(140));

// 3 — cost
body.push(h1("3.  What it costs"));
body.push(p("What you are buying is one disallowed cost not happening. A single unsupported expenditure on a donor grant runs into millions of naira, and unretired advances are the most common source of one."));
body.push(table(null, [
  ["Implementation and onboarding — one-off", "₦450,000"],
  ["Subscription — per month", "₦450,000"],
], [5600, 2800]));
body.push(gap(180));
body.push(rich([["The implementation fee covers work done once: ", true], ["translating your policies into system configuration, your departments, stages, spend bands, document packs, account and project codes, reference format, registers and user accounts; testing everything against your real payments; two training sessions; and attended support through your first full payment cycle and first month-end."]]));
body.push(rich([["The monthly fee covers everything ongoing: ", true], ["the platform, unlimited users, all configuration changes, support, further training, and platform improvements as they are released. We do not charge per user — you should be able to give visibility to everyone who needs it without that decision costing anything."]]));
body.push(p("Implementation is invoiced on signature. The subscription is invoiced monthly in advance, payable within 14 days."));
body.push(rich([["Initial term: three months from go-live", true], [", with a review at the end covering how the system performed and what Neem wants next. After that it continues monthly, and either party can end it on 30 days' notice."]]));
body.push(gap(60));
body.push(callout([
  ["Three commitments, so the risk is ours. ", true],
  ["We do not invoice a subscription month until you are live. If go-live slips past four weeks from the date we receive the items in section 5, that month is not billed. And whenever you leave, you take a complete readable export of everything — we send you one every month anyway, so the copy is routine rather than an emergency."],
]));
body.push(gap(200));

// 4 — already done
body.push(h1("4.  Most of week one is already done"));
body.push(p("Five working sessions with your team have already gone into this — reading your documents, building your configuration, and demonstrating it back to you on your own policies rather than on a demo dataset. That work is not re-charged and it is not repeated. It is why the timeline below is four weeks and not three months."));
body.push(gap(140));

// 5 — what we need
body.push(h1("5.  What we need from Neem"));
body.push(p("Short, and mostly things you already hold."));
[
  "A named contact who can confirm configuration decisions.",
  "Which governs in the ₦200,001–₦499,999 band — the signed Procurement Policy or the Finance Processes material. We will enforce whichever you confirm.",
  "Your withholding tax rates, and whether the GAPS statement shows one debit per payee or one per weekly batch.",
  "One representative bank statement per bank — GTBank, Zenith and Lotus.",
  "A set of recent payments we can test the configuration against.",
  "How many overdue advances make a collective default. Your policy does not say; we have assumed two.",
].forEach((t) => body.push(numbered(t, "nums1")));
body.push(gap(140));

// 6 — timeline
body.push(h1("6.  Timeline"));
body.push(table(["Week", "What happens"], [
  ["1", "Kick-off. We collect the outstanding items above and confirm the configuration already built from your documents."],
  ["2", "We finish your workflow, thresholds, categories, document packs, account codes, references, registers and users."],
  ["3", "We test the configuration against your real payments and give you a written configuration document to sign off."],
  ["4", "Training, then go-live."],
  ["5–8", "We run your first full weekly payment cycle and your first month-end alongside your team."],
], [1100, 7300]));
body.push(gap(180));
body.push(p("We will not go live until Neem has signed off the configuration."));
body.push(gap(140));

// 7 — not included
body.push(h1("7.  What is deliberately not included"));
body.push(p("We would rather tell you now than have you find it later."));
body.push(rich([["Payroll is switched off ", true], ["until Neem confirms PAYE bands and pension rates. A payroll run on assumed rates produces payslips that look right and are wrong — the kind of error an accountant finds months later. Send us your tax schedule and it becomes one setting."]]));
body.push(rich([["Tax-ID checking confirms a TIN is well formed. ", true], ["Confirming it is registered to that company needs a paid provider, and we would rather say so than imply a check we are not making."]]));
body.push(rich([["Direct bank integration is not in this deployment. ", true], ["Payments are prepared and evidenced here, then uploaded to GAPS as they are today."]]));
body.push(gap(140));

// 8 — data
body.push(h1("8.  Your data"));
body.push(p("Named accounts with role-based permissions, approval actions restricted to the department that owns each stage, all traffic encrypted, and records in a managed database with nightly backups — each one verified by an actual restore. Multi-factor authentication is available and switched on in agreement with Neem once your team has settled."));
body.push(rich([["Neem's data belongs to Neem. ", true], ["Exportable in full at any time including on exit. It is not used for any purpose other than providing this service, and it is not used to train any model."]]));
body.push(rich([["We can read your database; we cannot approve anything in it. ", true], ["Somebody has to be able to operate and repair the system, and we would rather say so. Every approval is recorded against a named Neem account in a tamper-evident chain, so no payment can be authorised without one of your people doing it."]]));
body.push(p("A Data Processing Agreement is signed alongside the service agreement. Real payment data enters the system only once that is executed."));
body.push(gap(140));

// 9 — next steps
body.push(h1("9.  Next steps"));
[
  "Neem confirms the items in section 5.",
  "Service agreement and Data Processing Agreement issued.",
  "Signature, and we begin within a week.",
].forEach((t) => body.push(numbered(t, "nums2")));
body.push(gap(200));

// 10 — acceptance
body.push(h1("10.  Acceptance"));
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
