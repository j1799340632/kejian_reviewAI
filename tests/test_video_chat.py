"""Web integration regressions. External extraction, storage and LLM are fakes.

Run: .venv/Scripts/python -m unittest discover -s tests -v
These checks do not measure real-video answer quality.
"""

import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_summarize
import rag_service
from summarizer import SubtitleExtractor, VideoSummarizer

VIDEO_URL = "https://www.bilibili.com/video/BVtest"
VIDEO_ID = rag_service.make_video_id(VIDEO_URL)
SOURCE = {
    "id": "S1", "text": "课程后段讲到间隔复习。", "start": 1800.0,
    "end": 1810.0, "timestamp": "30:00", "url": VIDEO_URL + "?t=1800",
}


def sse_events(response):
    events = []
    for block in response.text.replace("\r\n", "\n").split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key] = value.lstrip()
        if "event" in fields:
            events.append((fields["event"], fields.get("data", "")))
    return events


class WebChatTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(api_summarize.router)
        self.client = TestClient(app)
        self.rag = SimpleNamespace(
            make_video_id=rag_service.make_video_id,
            ensure_video_index=Mock(return_value=VIDEO_ID),
            retrieve_sources=Mock(return_value=[SOURCE]),
        )
        self.model = SimpleNamespace(
            chat_with_sources_stream=Mock(return_value=iter(["间隔复习", "。[S1]"])),
        )
        self.extractor = Mock()
        for name, value in (
            ("_get_rag_service", self.rag), ("_get_summarizer", self.model),
            ("_get_extractor", self.extractor),
        ):
            mock = patch.object(api_summarize, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_first_question_indexes_and_streams_real_source_fields(self):
        response = self.client.post("/api/chat", json={"url": VIDEO_URL, "question": "如何复习？"})
        self.assertEqual(response.status_code, 200)
        events = sse_events(response)
        self.assertEqual([e for e, _ in events], ["status", "video", "status", "sources", "answer", "answer", "done"])
        self.assertEqual(json.loads(dict(events)["video"]), {"video_id": VIDEO_ID})
        self.assertEqual(json.loads(dict(events)["sources"])["sources"], [SOURCE])
        self.rag.ensure_video_index.assert_called_once_with(VIDEO_URL, self.extractor)
        self.model.chat_with_sources_stream.assert_called_once_with([SOURCE], "如何复习？")

    def test_existing_video_uses_id_without_reextracting(self):
        response = self.client.post("/api/chat", json={"video_id": VIDEO_ID, "question": "如何复习？"})
        self.assertEqual(sse_events(response)[-1], ("done", "[DONE]"))
        self.rag.ensure_video_index.assert_not_called()
        self.rag.retrieve_sources.assert_called_once_with(VIDEO_ID, "如何复习？", "")

    def test_empty_retrieval_does_not_call_model(self):
        self.rag.retrieve_sources.return_value = []
        events = sse_events(self.client.post("/api/chat", json={"url": VIDEO_URL, "question": "如何复习？"}))
        self.assertIn("未检索到", json.loads(dict(events)["answer"]))
        self.model.chat_with_sources_stream.assert_not_called()

    def test_no_subtitles_emits_actionable_error(self):
        self.rag.ensure_video_index.side_effect = ValueError("该视频没有可用字幕")
        events = sse_events(self.client.post("/api/chat", json={"url": VIDEO_URL, "question": "如何复习？"}))
        self.assertEqual(events[-1][0], "error")
        self.assertIn("没有可用字幕", json.loads(events[-1][1])["message"])
        self.model.chat_with_sources_stream.assert_not_called()

    def test_service_failure_does_not_expose_internal_exception(self):
        self.rag.retrieve_sources.side_effect = RuntimeError("internal-service-details")
        with self.assertLogs(api_summarize.logger, level="ERROR"):
            response = self.client.post("/api/chat", json={"url": VIDEO_URL, "question": "如何复习？"})
        self.assertEqual(sse_events(response)[-1][0], "error")
        self.assertNotIn("internal-service-details", response.text)

    def test_invalid_or_empty_inputs_are_rejected_before_streaming(self):
        for payload in (
            {"url": VIDEO_URL, "question": "   "},
            {"question": "如何复习？"},
            {"video_id": "bad-id", "question": "如何复习？"},
            {"url": "javascript:alert(1)", "question": "如何复习？"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/chat", json=payload).status_code, 422)
        self.rag.ensure_video_index.assert_not_called()

    def test_video_id_must_match_supplied_url(self):
        response = self.client.post("/api/chat", json={"url": VIDEO_URL, "video_id": "0" * 16, "question": "如何复习？"})
        error = json.loads(dict(sse_events(response))["error"])
        self.assertIn("视频已发生变化", error["message"])
        self.rag.retrieve_sources.assert_not_called()

    def test_long_summary_reports_its_partial_scope(self):
        self.extractor.extract.return_value = {"has_subtitle": True, "full_text": "课" * 16000}
        self.model.summarize_stream = Mock(return_value=iter(["摘要"]))
        self.model.generate_mindmap = Mock(return_value="# 课程")
        response = self.client.post("/api/summarize", json={"url": VIDEO_URL})
        events = dict(sse_events(response))
        scope = json.loads(events["summary_scope"])
        self.assertEqual(scope, {"partial": True, "processed_chars": 15000, "total_chars": 16000})
        self.assertEqual(events["done"], "[DONE]")
        self.assertNotIn("quota", events)
        self.assertNotIn("need_login", response.text)
        self.model.summarize_stream.assert_called_once()
        self.model.generate_mindmap.assert_called_once()

    def test_subtitle_tab_reads_all_segments_anonymously_without_calling_model(self):
        captions = {"has_subtitle": True, "full_text": "开头结尾", "segments": [
            {"text": "开头", "start": 0, "end": 1}, {"text": "结尾", "start": 600, "end": 601},
        ]}
        self.extractor.extract.return_value = captions
        response = self.client.post("/api/subtitles", json={"url": VIDEO_URL})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), captions)
        self.extractor.extract.assert_called_once_with(VIDEO_URL)
        self.model.chat_with_sources_stream.assert_not_called()

    def test_subtitle_failure_does_not_expose_service_exception(self):
        self.extractor.extract.side_effect = RuntimeError("internal-service-details")
        with self.assertLogs(api_summarize.logger, level="ERROR"):
            response = self.client.post("/api/subtitles", json={"url": VIDEO_URL})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("internal-service-details", response.text)

    def test_personal_demo_does_not_expose_account_routes(self):
        from main import app
        paths = app.openapi()["paths"]
        self.assertFalse(any(path.startswith("/api/auth") for path in paths))
        client = TestClient(app)
        for name in ("register", "login", "me"):
            self.assertEqual(client.post(f"/api/auth/{name}", json={}).status_code, 404)


class IndexAndSourceTests(unittest.TestCase):
    def setUp(self):
        self.store = SimpleNamespace(
            init_collection=Mock(), is_indexed=Mock(return_value=False), index_video=Mock(),
            get_all_chunks=Mock(return_value=[]),
        )
        self.retriever = SimpleNamespace(clear_bm25_cache=Mock(), hybrid_search=Mock(return_value=[SOURCE]))
        modules = patch.dict(sys.modules, {"vector_store": self.store, "retriever": self.retriever})
        modules.start()
        self.addCleanup(modules.stop)

    def test_existing_index_skips_extraction(self):
        self.store.is_indexed.return_value = True
        extractor = Mock()
        self.assertEqual(rag_service.ensure_video_index(VIDEO_URL, extractor), VIDEO_ID)
        extractor.extract.assert_not_called()
        self.store.index_video.assert_not_called()

    def test_new_index_uses_segments_after_legacy_cutoff(self):
        segments = [
            {"start": i * 10, "end": i * 10 + 9, "text": "课程内容" * 100}
            for i in range(40)
        ]
        segments.append({"start": 1800, "end": 1810, "text": "课程最后讲到间隔复习。"})
        extractor = SimpleNamespace(extract=Mock(return_value={"has_subtitle": True, "segments": segments}))
        rag_service.ensure_video_index(VIDEO_URL, extractor)
        chunks = self.store.index_video.call_args.args[1]
        self.assertIn("间隔复习", chunks[-1]["text"])
        self.retriever.clear_bm25_cache.assert_called_once()

    def test_empty_extraction_is_not_marked_indexed(self):
        extractor = SimpleNamespace(extract=Mock(return_value={"has_subtitle": True, "segments": []}))
        with self.assertRaisesRegex(ValueError, "没有可用字幕"):
            rag_service.ensure_video_index(VIDEO_URL, extractor)
        self.store.index_video.assert_not_called()

    def test_sources_keep_timestamp_and_excerpt(self):
        self.store.is_indexed.return_value = True
        sources = rag_service.retrieve_sources(VIDEO_ID, "如何复习？", VIDEO_URL)
        self.assertEqual(sources, [SOURCE])
        self.retriever.hybrid_search.assert_called_once_with(VIDEO_ID, "如何复习？", top_k=3, candidate_k=10)

    def test_web_sources_include_all_short_caption_evidence(self):
        self.store.is_indexed.return_value = True
        self.store.get_all_chunks.return_value = [
            {"text": "课程末段的向量输出", "start": 600, "end": 610},
            {"text": "课程开头的加载步骤", "start": 10, "end": 20},
        ]
        sources = rag_service.retrieve_sources(VIDEO_ID, "加载和向量输出有什么关系？", VIDEO_URL)
        self.assertEqual([s["text"] for s in sources], ["课程开头的加载步骤", "课程末段的向量输出"])
        self.assertEqual([s["id"] for s in sources], ["S1", "S2"])
        self.retriever.hybrid_search.assert_not_called()

    def test_web_long_caption_within_extended_budget_keeps_early_and_late_sources(self):
        self.store.is_indexed.return_value = True
        self.store.get_all_chunks.return_value = [
            {"text": "开头依据" + "课" * 13000, "start": 0, "end": 2000},
            {"text": "页面回答提取依据", "start": 5700, "end": 5800},
        ]
        sources = rag_service.retrieve_sources(VIDEO_ID, "页面怎样只显示模型回答？", VIDEO_URL + "?p=1")
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[-1]["text"], "页面回答提取依据")
        self.assertIn("p=1&t=5700", sources[-1]["url"])
        self.retriever.hybrid_search.assert_not_called()

    def test_unindexed_video_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "尚未就绪"):
            rag_service.retrieve_sources(VIDEO_ID, "如何复习？")

    def test_timestamp_links_preserve_video_parameters(self):
        self.assertEqual(rag_service.source_url(VIDEO_URL + "?p=2&t=1#old", 65.8), VIDEO_URL + "?p=2&t=65")
        self.assertEqual(rag_service.source_url("https://youtu.be/abc?t=1", 65), "https://youtu.be/abc?t=65")
        self.assertIsNone(rag_service.source_url("https://unsupported.example/video", 65))
        self.assertIsNone(rag_service.source_url("javascript:alert(1)", 65))


class GroundedPromptTests(unittest.TestCase):
    def test_context_preserves_source_ids_and_question(self):
        prompt = VideoSummarizer._build_sources_prompt([SOURCE], "怎么复习？")
        self.assertIn("[S1] 30:00", prompt)
        self.assertIn(SOURCE["text"], prompt)
        self.assertIn("怎么复习？", prompt)


class BilibiliPartTests(unittest.TestCase):
    def test_requested_part_uses_its_own_subtitle_cid(self):
        view = {"data": {"cid": 11, "aid": 42, "pages": [
            {"page": 1, "cid": 11}, {"page": 103, "cid": 10399},
        ]}}
        dm = {"data": {"subtitle": {"subtitles": [{
            "lan": "ai-zh", "subtitle_url": "https://captions.example/test",
        }]}}}
        captions = {"body": [{"from": 1.0, "to": 2.0, "content": "本集的 RAG 流程"}]}
        with patch("summarizer.httpx.get", side_effect=[
            Mock(json=Mock(return_value=data)) for data in (view, dm, captions)
        ]) as get:
            result = SubtitleExtractor()._extract_bilibili(VIDEO_URL + "?p=103")
        self.assertIn("oid=10399", get.call_args_list[1].args[0])
        self.assertEqual(result["full_text"], "本集的 RAG 流程")

    def test_missing_part_does_not_silently_use_first_part(self):
        view = {"data": {"cid": 11, "aid": 42, "pages": [{"page": 1, "cid": 11}]}}
        with patch("summarizer.httpx.get", return_value=Mock(json=Mock(return_value=view))) as get:
            result = SubtitleExtractor()._extract_bilibili(VIDEO_URL + "?p=103")
        self.assertFalse(result["has_subtitle"])
        get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
