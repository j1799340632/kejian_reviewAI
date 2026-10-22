"""Bounded context candidates shared by offline evaluation and the web app.

Question splitting is a deterministic experiment, not an extra model call.
The short-context budget counts indexed text, including chunk overlap.
"""

import re

SHORT_CONTEXT_MAX_CHARS = 12000
EXTENDED_CONTEXT_MAX_CHARS = 48000
LONG_CONTEXT_MAX_CHARS = 10000
LONG_CONTEXT_MAX_CHUNKS = 20


def split_question(question: str, max_queries: int = 4) -> list[str]:
    """Keep the full question and add at most three explicit subquestions."""
    parts = re.split(
        r"[？?；;]+|[,，](?=(?:为什么|为何|如何|怎样|怎么|每|是否|哪些|什么))"
        r"|[,，]?(?=并(?:说明|解释|列出|比较))",
        question,
    )
    queries, seen = [], set()
    for part in [question, *parts]:
        part = part.strip(" \n\t？?；;，,。")
        key = re.sub(r"\s+", "", part)
        if len(part) >= 4 and key not in seen:
            queries.append(part)
            seen.add(key)
        if len(queries) >= max_queries:
            break
    return queries or [question.strip()]


def clause_queries(question: str, max_queries: int = 5) -> list[str]:
    """Keep original intent plus bounded clauses; no model or topic dictionary."""
    parts = re.split(r"[？?；;，,]+|(?:并且|以及|同时)(?=说明|解释|比较|列出)", question)
    queries, seen = [], set()
    for part in [question, *parts]:
        part = part.strip(" \n\t？?；;，,。")
        key = re.sub(r"\s+", "", part)
        if len(key) >= 5 and key not in seen:
            queries.append(part)
            seen.add(key)
        if len(queries) >= max_queries:
            break
    return queries or [question.strip()]


def _hit_key(hit):
    return (round(float(hit["start"]), 2), round(float(hit["end"]), 2), hit["text"])


def expanded_context(video_id, question, chunks, retriever):
    """Retrieve complementary clauses, then retain bounded neighboring text.

    Seed snippets get priority over neighbors. Whole snippets are kept, never
    character-sliced. Sources are finally ordered by video time for readability.
    """
    queries = clause_queries(question)
    ranked = [retriever.hybrid_search(video_id, q, top_k=4 if i == 0 else 2, candidate_k=20)
              for i, q in enumerate(queries)]
    seeds, seen = [], set()
    for rank in range(4):
        for result in ranked:
            if rank < len(result) and _hit_key(result[rank]) not in seen:
                seen.add(_hit_key(result[rank]))
                seeds.append(result[rank])
    positions = {_hit_key(c): i for i, c in enumerate(chunks)}
    neighbors = []
    for seed in seeds:
        index = positions.get(_hit_key(seed))
        if index is None:
            continue
        for neighbor in (index - 1, index + 1):
            if 0 <= neighbor < len(chunks):
                neighbors.append(chunks[neighbor])
    hits, seen, chars = [], set(), 0
    for hit in [*seeds, *neighbors]:
        key = _hit_key(hit)
        if key in seen or not hit.get("text", "").strip():
            continue
        if chars + len(hit["text"]) > LONG_CONTEXT_MAX_CHARS:
            continue
        hits.append(hit)
        seen.add(key)
        chars += len(hit["text"])
        if len(hits) >= LONG_CONTEXT_MAX_CHUNKS:
            break
    hits.sort(key=lambda h: (float(h["start"]), float(h["end"])))
    return hits, {"queries": queries, "retrieval_calls": len(queries),
                  "seed_chunks": len(seeds), "selected_chunks": len(hits),
                  "context_char_budget": LONG_CONTEXT_MAX_CHARS,
                  "context_chunk_budget": LONG_CONTEXT_MAX_CHUNKS,
                  "additional_model_calls": 0}


def select_context(video_id, question, mode, store, retriever):
    """Return hits plus an audit trail, without changing indexed captions."""
    details = {"strategy": mode, "queries": [question], "additional_model_calls": 0}
    if mode in {"full_short", "hybrid8", "expanded", "bounded_full"}:
        chunks = [c for c in store.get_all_chunks(video_id) if c.get("text", "").strip()]
        chunks.sort(key=lambda c: (float(c["start"]), float(c["end"])))
        indexed_chars = sum(len(c["text"]) for c in chunks)
        details["indexed_context_chars"] = indexed_chars
        details["short_context_budget_chars"] = SHORT_CONTEXT_MAX_CHARS
        if chunks and indexed_chars <= SHORT_CONTEXT_MAX_CHARS:
            details["strategy"] = "all_indexed_short_context"
            return chunks, details
        if mode == "bounded_full":
            details["extended_context_budget_chars"] = EXTENDED_CONTEXT_MAX_CHARS
            if chunks and indexed_chars <= EXTENDED_CONTEXT_MAX_CHARS:
                details["strategy"] = "all_indexed_extended_context"
                return chunks, details
        if mode == "hybrid8":
            details["strategy"] = "hybrid_top8_long"
            return retriever.hybrid_search(video_id, question, top_k=8, candidate_k=20), details
        if mode == "expanded":
            hits, audit = expanded_context(video_id, question, chunks, retriever)
            details.update(audit, strategy="clause_queries_with_neighbors_long")
            return hits, details
        details["strategy"] = "hybrid_top3_long_fallback"
        return retriever.hybrid_search(video_id, question, top_k=3, candidate_k=10), details
    if mode == "hybrid6":
        return retriever.hybrid_search(video_id, question, top_k=6, candidate_k=10), details
    if mode == "split":
        queries = split_question(question)
        details["queries"] = queries
        ranked = [retriever.hybrid_search(video_id, query, top_k=3, candidate_k=10) for query in queries]
        # Interleave lists so that one subquestion cannot occupy the entire budget.
        hits, seen = [], set()
        for rank in range(3):
            for result in ranked:
                if rank >= len(result):
                    continue
                hit = result[rank]
                key = (round(float(hit["start"]), 2), round(float(hit["end"]), 2), hit["text"])
                if key not in seen:
                    hits.append(hit)
                    seen.add(key)
                if len(hits) == 8:
                    return hits, details
        return hits, details
    if mode == "hybrid":
        return retriever.hybrid_search(video_id, question, top_k=3, candidate_k=10), details
    if mode == "vector":
        return retriever.vector_only_search(video_id, question, top_k=3), details
    raise ValueError(f"Unknown context strategy: {mode}")


def format_sources(hits, url):
    """Use identical source identifiers and time links in evaluation and API."""
    from chunker import format_timestamp
    from rag_service import source_url

    return [{
        "id": f"S{number}", "text": hit["text"],
        "start": float(hit["start"]), "end": float(hit["end"]),
        "timestamp": format_timestamp(hit["start"]),
        "url": source_url(url, hit["start"]),
    } for number, hit in enumerate((h for h in hits if h.get("text", "").strip()), 1)]
