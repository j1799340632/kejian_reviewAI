"""Regression guards for bounded context routing and source preservation."""

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from context_policy import (
    SHORT_CONTEXT_MAX_CHARS, EXTENDED_CONTEXT_MAX_CHARS, LONG_CONTEXT_MAX_CHARS,
    LONG_CONTEXT_MAX_CHUNKS, select_context, split_question, format_sources,
)


def chunk(start, text):
    return {"start": start, "end": start + 10, "text": text}


class ContextPolicyTests(unittest.TestCase):
    def setUp(self):
        self.store = SimpleNamespace(get_all_chunks=Mock())
        self.retriever = SimpleNamespace(hybrid_search=Mock(return_value=[chunk(0, "检索片段")]))

    def test_short_route_keeps_early_and_late_evidence_in_time_order(self):
        self.store.get_all_chunks.return_value = [chunk(90, "后段输出结构"), chunk(0, "前段加载步骤")]
        hits, details = select_context("video", "流程和输出", "full_short", self.store, self.retriever)
        self.assertEqual([c["text"] for c in hits], ["前段加载步骤", "后段输出结构"])
        self.retriever.hybrid_search.assert_not_called()
        self.assertEqual(details["strategy"], "all_indexed_short_context")

    def test_short_budget_boundary_includes_overlap_and_never_slices_long_context(self):
        self.store.get_all_chunks.return_value = [chunk(0, "课" * SHORT_CONTEXT_MAX_CHARS)]
        hits, _ = select_context("video", "问题", "full_short", self.store, self.retriever)
        self.assertEqual(len(hits[0]["text"]), SHORT_CONTEXT_MAX_CHARS)
        self.store.get_all_chunks.return_value.append(chunk(100, "后段必要依据"))
        hits, details = select_context("video", "问题", "full_short", self.store, self.retriever)
        self.assertEqual(hits[0]["text"], "检索片段")
        self.assertEqual(details["strategy"], "hybrid_top3_long_fallback")
        self.assertEqual(self.store.get_all_chunks.return_value[-1]["text"], "后段必要依据")

    def test_empty_stored_context_uses_retrieval_instead_of_claiming_full_coverage(self):
        self.store.get_all_chunks.return_value = []
        _, details = select_context("video", "问题", "full_short", self.store, self.retriever)
        self.assertEqual(details["strategy"], "hybrid_top3_long_fallback")

    def test_extended_budget_keeps_complete_evidence_and_falls_back_without_slicing(self):
        original = [chunk(100, "后段" * (EXTENDED_CONTEXT_MAX_CHARS // 2 - 1)), chunk(0, "前段")]
        self.store.get_all_chunks.return_value = original
        hits, details = select_context("video", "跨片段问题", "bounded_full", self.store, self.retriever)
        self.assertEqual(sum(len(c["text"]) for c in hits), EXTENDED_CONTEXT_MAX_CHARS)
        self.assertEqual([c["start"] for c in hits], [0, 100])
        self.assertEqual(details["strategy"], "all_indexed_extended_context")
        self.retriever.hybrid_search.assert_not_called()
        original.append(chunk(200, "超预算的必要结尾"))
        hits, details = select_context("video", "跨片段问题", "bounded_full", self.store, self.retriever)
        self.assertEqual(details["strategy"], "hybrid_top3_long_fallback")
        self.assertEqual(hits[0]["text"], "检索片段")
        self.assertEqual(original[-1]["text"], "超预算的必要结尾")

    def test_expanded_candidate_preserves_neighbor_evidence_and_source_order(self):
        chunks = [chunk(n * 10, f"第{n}块证据") for n in range(5)]
        self.store.get_all_chunks.return_value = [dict(c, text=c["text"] + "课" * 3000) for c in chunks]
        middle = self.store.get_all_chunks.return_value[2]
        self.retriever.hybrid_search.return_value = [middle]
        hits, details = select_context("video", "原理是什么？输出怎样处理？", "expanded", self.store, self.retriever)
        self.assertEqual([h["start"] for h in hits], [10, 20, 30])
        self.assertEqual(details["additional_model_calls"], 0)
        self.assertLessEqual(len(details["queries"]), 5)

    def test_expanded_candidate_obeys_both_budgets_and_deduplicates(self):
        chunks = [chunk(n * 10, f"证据{n}" + "课" * 700) for n in range(40)]
        self.store.get_all_chunks.return_value = chunks
        def search(video_id, query, **kwargs):
            offset = sum(map(ord, query)) % 30
            return chunks[offset:offset + kwargs["top_k"]]
        self.retriever.hybrid_search.side_effect = search
        hits, details = select_context("video", "如何加载？如何切分？如何编码？如何输出？如何持久化？", "expanded", self.store, self.retriever)
        self.assertLessEqual(sum(len(h["text"]) for h in hits), LONG_CONTEXT_MAX_CHARS)
        self.assertLessEqual(len(hits), LONG_CONTEXT_MAX_CHUNKS)
        self.assertEqual(len({h["start"] for h in hits}), len(hits))
        self.assertLessEqual(details["retrieval_calls"], 5)

    def test_subquestions_preserve_original_and_limit_query_fanout(self):
        question = "如何加载文档？怎样嵌入？为什么持久化？如何检索？怎样生成？"
        queries = split_question(question)
        self.assertEqual(queries[0], question.rstrip("？"))
        self.assertIn("如何加载文档", queries)
        self.assertLessEqual(len(queries), 4)

    def test_split_interleaves_distinct_evidence_and_caps_context(self):
        question = "如何加载文档？为什么需要持久化？"
        def search(video_id, query, **kwargs):
            return [chunk(0, "公共片段"), chunk(len(query), query), chunk(len(query) + 100, "补充" + query)]
        self.retriever.hybrid_search.side_effect = search
        hits, details = select_context("video", question, "split", self.store, self.retriever)
        self.assertEqual(sum(c["text"] == "公共片段" for c in hits), 1)
        self.assertIn("如何加载文档", [c["text"] for c in hits])
        self.assertIn("为什么需要持久化", [c["text"] for c in hits])
        self.assertLessEqual(len(hits), 8)
        self.assertEqual(details["additional_model_calls"], 0)

    def test_sources_have_contiguous_ids_and_keep_part_and_seek(self):
        hits = [chunk(65.5, "早段证据"), chunk(70, " "), chunk(120, "后段证据")]
        sources = format_sources(hits, "https://www.bilibili.com/video/BVtest/?p=112")
        self.assertEqual([s["id"] for s in sources], ["S1", "S2"])
        self.assertEqual(sources[0]["url"], "https://www.bilibili.com/video/BVtest/?p=112&t=65")
        self.assertEqual(sources[1]["text"], "后段证据")


if __name__ == "__main__":
    unittest.main()
