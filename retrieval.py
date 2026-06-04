"""
DOCex retrieval — lightweight, dependency-free BM25 over document chunks.

The Knowledge Hub originally answered library-wide questions by stuffing
EVERY document into the model's context. That caps out at ~80-100 documents
and gets slow and expensive long before that. For an ERP-scale corpus
(hundreds–thousands of documents) we must retrieve only the most relevant
chunks per query, then answer over those.

This module is the retrieval layer. It indexes each document chunk (a
slide / page / section) and ranks them against a query with BM25 — a strong,
classic lexical ranker that needs no embeddings API, no vector DB, and no
extra dependencies, so it ships today and runs anywhere.

It's deliberately structured so a semantic backend (Voyage/OpenAI embeddings
+ pgvector, when Supabase lands) can slot in behind the same `retrieve()`
interface later without touching callers.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from models import SlideDeck
from slides import chunk_label_for, slide_to_context

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class Passage:
    """One retrievable chunk: the renderable context + its provenance."""
    deck_id: str
    deck_name: str
    content_type: str
    number: int           # 1-indexed chunk number within its document
    label: str            # "Slide" | "Page" | "Section"
    context: str          # rendered block fed to the model (slide_to_context)
    tokens: list[str] = field(default_factory=list)  # tokens used for scoring


def build_passages(decks: list[SlideDeck]) -> list[Passage]:
    """Flatten a library of documents into scored-ready chunk passages.

    The document name, tags, and description are folded into every chunk's
    index text so a query like "anti-fraud policy" matches the right
    *document* even when an individual chunk's body doesn't repeat the title.
    """
    passages: list[Passage] = []
    for d in decks:
        label = chunk_label_for(d.content_type)
        doc_terms = " ".join(
            filter(None, [d.name, " ".join(d.tags or []), d.description or ""])
        )
        for s in d.slides:
            index_text = " ".join(
                filter(
                    None,
                    [
                        doc_terms,
                        s.title or "",
                        " ".join(s.body or []),
                        " ".join(s.table_text or []),
                        s.speaker_notes or "",
                    ],
                )
            )
            passages.append(
                Passage(
                    deck_id=d.id,
                    deck_name=d.name,
                    content_type=d.content_type,
                    number=s.number,
                    label=label,
                    context=slide_to_context(s, label),
                    tokens=_tokenize(index_text),
                )
            )
    return passages


def retrieve(
    query: str,
    passages: list[Passage],
    k: int = 24,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[Passage, float]]:
    """Return the top-k passages for `query`, ranked by BM25 (desc).

    Pure-Python BM25. For a few thousand chunks this scores in well under a
    second. Returns (passage, score) pairs; callers can filter on score > 0
    to drop non-matches.
    """
    q_terms = _tokenize(query)
    if not passages:
        return []
    if not q_terms:
        return [(p, 0.0) for p in passages[:k]]

    n = len(passages)
    avgdl = sum(len(p.tokens) for p in passages) / n or 1.0

    # Document frequency per term.
    df: dict[str, int] = {}
    for p in passages:
        for t in set(p.tokens):
            df[t] = df.get(t, 0) + 1

    idf = {
        t: math.log(1 + (n - dfi + 0.5) / (dfi + 0.5)) for t, dfi in df.items()
    }

    scored: list[tuple[Passage, float]] = []
    q_unique = set(q_terms)
    for p in passages:
        if not p.tokens:
            scored.append((p, 0.0))
            continue
        dl = len(p.tokens)
        # term frequencies for this passage, limited to query terms
        tf: dict[str, int] = {}
        for t in p.tokens:
            if t in q_unique:
                tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for t, f in tf.items():
            term_idf = idf.get(t, 0.0)
            denom = f + k1 * (1 - b + b * dl / avgdl)
            score += term_idf * (f * (k1 + 1)) / denom
        scored.append((p, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


def rank_documents(
    query: str,
    decks: list[SlideDeck],
    k: int = 10,
) -> list[dict]:
    """Document-level discovery: rank whole documents by relevance to a query.

    Aggregates the best chunk score per document, returning a ranked list
    with the single most-relevant chunk as a why-it-matched snippet. This
    powers the "find the right document" search (next build) — exposed now
    so it's ready to wire into the UI.
    """
    passages = build_passages(decks)
    hits = retrieve(query, passages, k=max(k * 4, 40))
    best: dict[str, dict] = {}
    for p, score in hits:
        if score <= 0:
            continue
        cur = best.get(p.deck_id)
        if cur is None or score > cur["score"]:
            best[p.deck_id] = {
                "deck_id": p.deck_id,
                "deck_name": p.deck_name,
                "content_type": p.content_type,
                "best_chunk": p.number,
                "best_label": p.label,
                "snippet": p.context,
                "score": score,
            }
    ranked = sorted(best.values(), key=lambda d: d["score"], reverse=True)
    return ranked[:k]
