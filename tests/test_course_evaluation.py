"""Checks that experiment inputs and comparison settings stay consistent."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import evaluate_course
from summarizer import VideoSummarizer, GROUNDED_SYSTEM_PROMPTS


class CourseEvaluationTests(unittest.TestCase):
    def test_changed_source_snapshot_is_rejected(self):
        parent = ROOT / "evals/data"
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        folder = Path(temporary.name).resolve()
        self.assertTrue(folder.is_relative_to(parent.resolve()))
        self.addCleanup(temporary.cleanup)
        snapshot = folder / "source.json"
        raw = json.dumps({"full_text": "课程文本"}).encode()
        snapshot.write_bytes(raw)
        case = {
            "case_id": "fixture", "subtitle_snapshot": snapshot.relative_to(ROOT).as_posix(),
            "subtitle_sha256": hashlib.sha256(raw).hexdigest(), "subtitle_chars": 4,
        }
        cases = folder / "cases.jsonl"
        cases.write_text(json.dumps(case) + "\n", encoding="utf-8")
        self.assertEqual(len(evaluate_course.load_cases(cases)), 1)
        with self.assertRaisesRegex(ValueError, "Duplicate case IDs"):
            evaluate_course.main(["--cases", str(cases), "--additional-cases", str(cases), "--check"])
        snapshot.write_bytes(raw + b" ")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            evaluate_course.load_cases(cases)

    def test_legacy_context_preserves_the_original_12000_character_limit(self):
        snapshot = {
            "full_text": "课" * 12000 + " 后段证据",
            "segments": [
                {"start": 0.0, "end": 60.0, "text": "课" * 12000},
                {"start": 80.0, "end": 100.0, "text": "后段证据"},
            ], "url": "https://example.test",
        }
        source = evaluate_course.legacy_sources(snapshot)[0]
        self.assertEqual(len(source["text"]), 12000)
        self.assertNotIn("后段证据", source["text"])
        self.assertTrue(snapshot["full_text"].endswith("后段证据"))
        self.assertEqual(source["end"], 60.0)

    def test_streaming_and_batch_answers_use_the_same_messages(self):
        model = VideoSummarizer.__new__(VideoSummarizer)
        model.client = Mock()
        model.model = "configured-model"
        source = {"id": "S1", "timestamp": "00:10", "text": "依据"}
        model.answer_with_sources([source], "问题")
        batch = model.client.chat.completions.create.call_args.kwargs.copy()
        model._sources_completion([source], "问题", stream=True)
        streamed = model.client.chat.completions.create.call_args.kwargs.copy()
        self.assertFalse(batch.pop("stream"))
        self.assertTrue(streamed.pop("stream"))
        self.assertEqual(batch, streamed)
        self.assertEqual(batch["extra_body"]["thinking"]["type"], "disabled")

    def test_model_name_is_configurable_without_real_api_access(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "configured-model"}):
            with patch("summarizer.OpenAI"):
                model = VideoSummarizer()
        self.assertEqual(model.model, "configured-model")

    def test_old_prompt_can_be_replayed_without_changing_model_or_source_text(self):
        model = VideoSummarizer.__new__(VideoSummarizer)
        model.client, model.model = Mock(), "configured-model"
        sources = [{"id": "S1", "timestamp": "00:10", "text": "未确定的代码字段"}]
        model.answer_with_sources(sources, "原理是什么？", prompt_version="v1")
        previous = model.client.chat.completions.create.call_args.kwargs
        model.answer_with_sources(sources, "原理是什么？", prompt_version="v2")
        current = model.client.chat.completions.create.call_args.kwargs
        self.assertEqual(previous["messages"][1], current["messages"][1])
        self.assertEqual(previous["messages"][0]["content"], GROUNDED_SYSTEM_PROMPTS["v1"])
        self.assertNotEqual(previous["messages"][0], current["messages"][0])
        for option in ["model", "temperature", "max_tokens", "stream", "extra_body"]:
            self.assertEqual(previous[option], current[option])


if __name__ == "__main__":
    unittest.main()
