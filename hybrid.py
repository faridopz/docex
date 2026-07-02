"""
Hybrid code+LLM strategy — the ONE fallback policy every DOCex engine uses.

Two primitives, one principle: fast deterministic code does as much as it can;
the LLM is invoked only where code is weak, and never left to hang or crash the
request.

  scope_llm(deterministic, needs_llm, llm_fn)
      Code-first. If code resolved everything (`needs_llm` empty) → return
      instantly, no LLM. Otherwise call the LLM for ONLY the unresolved items
      and merge. This is the speed lever: the model generates a fraction of the
      output it otherwise would.

  run_with_fallback(primary, fallback)
      Resilience. Run the primary (usually the LLM); on ANY error/timeout,
      degrade to the deterministic `fallback` so the engine still returns a
      useful (flagged) result instead of hanging or 500-ing.

Every result is wrapped in a HybridResult that records what happened (source,
whether the LLM was used, whether we degraded, latency) — so the audit trail
and the UI can be honest about how each answer was produced.

Pure stdlib. Import into any engine.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class HybridResult:
    value: Any
    source: str                      # deterministic | llm | hybrid | fallback
    used_llm: bool
    degraded: bool = False           # LLM failed → we fell back to code
    error: Optional[str] = None
    ms: float = 0.0
    llm_items: list = field(default_factory=list)


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def scope_llm(
    deterministic: dict,
    needs_llm: list,
    llm_fn: Callable[[list], dict],
) -> HybridResult:
    """Resolve deterministically first; call the LLM only for what's left.

    deterministic: {item: value} the code already resolved (with confidence).
    needs_llm:     items the code could NOT resolve confidently.
    llm_fn:        callable(needs_llm) -> {item: value}, run ONLY on the gap.
    """
    start = time.perf_counter()
    if not needs_llm:
        # Fully deterministic — the fast, common path. No tokens, no waiting.
        return HybridResult(deterministic, "deterministic", used_llm=False, ms=_ms(start))
    try:
        llm_part = llm_fn(needs_llm) or {}
        merged = {**deterministic, **llm_part}
        return HybridResult(
            merged,
            "hybrid" if deterministic else "llm",
            used_llm=True,
            ms=_ms(start),
            llm_items=list(needs_llm),
        )
    except Exception as exc:  # noqa: BLE001 — LLM must never crash the engine
        # Degrade: return what code has, flagged for review.
        return HybridResult(
            deterministic,
            "fallback",
            used_llm=True,
            degraded=True,
            error=str(exc),
            ms=_ms(start),
            llm_items=list(needs_llm),
        )


def run_with_fallback(
    primary: Callable[[], Any],
    fallback: Callable[[], Any],
    *,
    label: str = "",
) -> HybridResult:
    """Try `primary` (typically the LLM). On any failure/timeout, degrade to the
    deterministic `fallback` so the engine always returns something usable.
    Set the timeout on the LLM client itself; its timeout raises here and we
    catch it. Wrap every engine's model call in this."""
    start = time.perf_counter()
    try:
        return HybridResult(primary(), "llm", used_llm=True, ms=_ms(start))
    except Exception as exc:  # noqa: BLE001
        try:
            return HybridResult(
                fallback(),
                "fallback",
                used_llm=False,
                degraded=True,
                error=str(exc),
                ms=_ms(start),
            )
        except Exception as exc2:  # noqa: BLE001
            return HybridResult(
                None,
                "fallback",
                used_llm=False,
                degraded=True,
                error=f"{label or 'primary'} failed: {exc}; fallback failed: {exc2}",
                ms=_ms(start),
            )
