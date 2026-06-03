"""
Central AI model configuration for DOCex — tiered routing.

Single source of truth for which Claude model every engine calls. Tasks are
routed by how much they actually need: accuracy-critical reasoning gets the
stronger model; fast, lower-stakes work gets the cheap, quick one.

  Tier 1  — accuracy-critical reasoning (Sonnet 4.6)
            · Compliance: policy interpretation + payment checks (legal risk)
            · Knowledge Q&A (citations must be exact)
  Tier 2  — fast extraction / structured pulls (Haiku 4.5)
            · Document extraction (screener)
  Tier 3  — quick summaries where speed matters most (Haiku 4.5)
            · Assistant briefs

Note: Bank Verify and the Attendance Agent make NO LLM calls — they resolve
accounts via Paystack and match names with rapidfuzz (pure Python), so there
is no model to configure for them.

Each tier can be overridden at deploy time via env var.
"""
import os

MODEL_TIER_1 = os.environ.get("DOCEX_MODEL_TIER1", "claude-sonnet-4-6")
MODEL_TIER_2 = os.environ.get("DOCEX_MODEL_TIER2", "claude-haiku-4-5-20251001")
MODEL_TIER_3 = os.environ.get("DOCEX_MODEL_TIER3", "claude-haiku-4-5-20251001")

# Semantic aliases — engines import these, not the raw tier names, so intent
# stays readable at the call site.
COMPLIANCE_MODEL = MODEL_TIER_1
KNOWLEDGE_MODEL = MODEL_TIER_1
EXTRACTION_MODEL = MODEL_TIER_2
ASSISTANT_MODEL = MODEL_TIER_3
