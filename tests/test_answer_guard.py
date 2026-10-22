"""Protect visible answers without hiding or guessing ASR code spellings."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from answer_guard import guard_source_code, guard_answer_stream


class AnswerGuardTests(unittest.TestCase):
    def test_phonetic_caption_does_not_authorize_invented_executable_parameter(self):
        sources = [{"text": "可以加某 special token 等于 false，不加起始符号。"}]
        raw = "原因是默认加入起始符号。[S1]\n还可用 `invented_special=False` 关闭。"
        shown, audit = guard_source_code(raw, sources, "为什么多出起始符号？")
        self.assertIn("原因是默认加入起始符号。[S1]", shown)
        self.assertNotIn("invented_special", shown)
        self.assertIn("核对视频画面", shown)
        self.assertEqual(audit["replaced_expressions"], ["invented_special=False"])
        self.assertIn("invented_special", raw)

    def test_verbatim_source_and_question_code_survive_but_new_numeric_index_does_not(self):
        raw = "`option=False` 已在原文；top-k=3 是问题条件；`messages[1]` 未确认。[S1]"
        shown, audit = guard_source_code(raw, [{"text": "演示设置 option = False"}], "top-k=3 怎样？")
        self.assertIn("`option=False`", shown)
        self.assertIn("top-k=3", shown)
        self.assertIn("[S1]", shown)
        self.assertNotIn("messages[1]", shown)
        self.assertEqual(audit["replaced_expressions"], ["messages[1]"])

    def test_streaming_split_code_matches_batch_without_leaking_partial_assignment(self):
        deltas = ["已有依据。[S1]\n可设 `unknown_", "flag=", "False`。\n", "结束。"]
        sources, question = [{"text": "自动字幕只给出了含糊读音"}], "说明原因"
        output = list(guard_answer_stream(iter(deltas), sources, question))
        self.assertEqual("".join(output), guard_source_code("".join(deltas), sources, question)[0])
        self.assertTrue(all("unknown_" not in x for x in output))
        self.assertTrue(output[0].endswith("\n"))


if __name__ == "__main__":
    unittest.main()
