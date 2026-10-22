"""Freeze a different-course, real long-caption check before model inference.

References are checked by AI against public automatic captions, not by people
against audio or slides. This script refuses to overwrite a frozen test set.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "evals/data/BV1pLWFz1Eew/part-001.json"
SPECS = [
    ("early", "ordinary", "根据本节解释，语言模型得到下一个 token 的概率分布后，怎样选出输出并继续生成？为什么同一问题可能得到不同回答？",
     ["根据候选 token 的概率分布抽样选择下一个 token。", "把生成的 token 接回输入，重复生成，直到结束符号。", "抽样具有随机性，因此同一输入可能产生不同回答。"],
     [(200, 535)]),
    ("early", "ordinary", "为什么语言模型会编造看似合理的答案？根据本节，开启搜索能否保证答案正确？",
     ["模型做的是文字接龙，而不是从数据库查出保证正确的事实。", "搜索或 RAG 可以降低胡编乱造，但不保证每次都正确。"],
     [(1280, 1475)]),
    ("late", "ordinary", "tokenizer.encode 和 tokenizer.decode 分别转换什么？为什么本节演示中“大家好”先编码再解码可能多出 begin_of_text？",
     ["encode 把文字转成 token 编号。", "decode 把 token 编号转回文字。", "本节 tokenizer 的 encode 默认加入起始符号，解码后显示为 begin_of_text。"],
     [(3380, 3430), (3980, 4065)]),
    ("late", "ordinary", "为什么本节的 good 在 good morning 和 I am good 里可能是不同 token？去掉 am 和 good 之间的空格后，演示结果发生了什么变化？",
     ["演示中的 tokenizer 将有前导空格和没有前导空格的 good 当成不同 token。", "去掉空格后，good 的 token 与 good morning 中句首的 good 相同。"],
     [(3880, 3990)]),
    ("late", "ordinary", "为什么讲师建议只从概率最高的 top-k 候选中抽样？top-k=1 和 top-k=3 在本节演示中各有什么表现？",
     ["排除概率很低的 token，降低抽到奇怪 token 后续接龙失常的风险。", "top-k=1 相当于选最高概率的 token，结果固定。", "top-k=3 从前三名中按概率抽样，仍有随机性，可得到不同结果。"],
     [(4550, 4760)]),
    ("late", "ordinary", "为什么本节改用官方 chat template，而不继续手写“使用者说／AI回答”？apply_chat_template 在演示中还顺便完成了什么转换？",
     ["随手写的模板使模型没有在适当位置结束；应使用适配模型的官方模板。", "官方模板复杂，手写容易出错，可用 apply_chat_template 添加。", "本节调用还完成 encode，将加模板后的文字转成 token 编号。"],
     [(5090, 5290)]),
    ("late", "multi_evidence", "从用户输入到页面只显示模型答案，本节演示了哪些处理步骤？请包括带角色的消息、模板与编码、生成、解码和提取回答。",
     ["把用户输入组织成包含 user 角色的 messages。", "用 apply_chat_template 添加模板并在本节调用中编码成 token ID。", "把 ID 交给 model.generate，再用 tokenizer.decode 转回文字。", "解码文字含输入及输出，应提取模型回答部分再显示给用户。"],
     [(5150, 5290), (5715, 5795)]),
    ("cross_cutoff", "multi_evidence", "本节前半段怎样解释模型能理解“第二高的呢”这种追问？结合后半段实现，多轮对话下一轮应传哪些消息，得到回答后又该怎样更新？",
     ["把之前问答放在当前问题前，模型据此理解省略了对象的追问。", "后半段实现需按角色传入之前的 user 和 assistant 消息及新的用户问题，不能只传最新一句。", "将新产生的模型回答也加入历史，下一轮带上更新后的历史和新输入。"],
     [(1215, 1280), (5870, 6070)]),
    ("not_applicable", "unanswerable", "本节对 Llama 和 Gemma 的中文问答对比，分别给出了多少准确率、用了多少道评测题？",
     ["说明本节没有给出这项对比的准确率和评测题数。", "不把 token 概率或主观演示评价当成评测准确率，不编造百分比或题数。"], []),
    ("not_applicable", "unanswerable", "讲师演示的聊天应用上线后的月活用户数、付费转化率分别是多少？",
     ["说明本节没有给出上线后的月活和付费转化数据。", "不编造用户规模或付费转化率。"], []),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    destination = ROOT / "evals/cases.independent-long.jsonl"
    protocol_path = ROOT / "evals/independent-long-protocol.json"
    if destination.exists() or protocol_path.exists():
        raise FileExistsError("Preserve frozen questions and rules")
    snapshot_path = ROOT / SNAPSHOT
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    manifest = json.loads((snapshot_path.parent / "manifest.json").read_text(encoding="utf-8"))
    digest = sha(snapshot_path)
    assert digest == manifest["subtitle_sha256"]
    segments, text = snapshot["segments"], snapshot["full_text"]
    assert text == " ".join(s["text"] for s in segments) and len(text) > 12000
    offsets, cursor = [], 0
    for segment in segments:
        offsets.append((cursor, cursor + len(segment["text"])))
        cursor += len(segment["text"]) + 1
    crossing = next(i for i, (start, end) in enumerate(offsets) if start <= 12000 < end)
    frozen_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for number, (position, category, question, points, windows) in enumerate(SPECS, 1):
        evidence = []
        for start, end in windows:
            indexes = [i for i, s in enumerate(segments) if s["start"] < end and s["end"] > start]
            first, last = indexes[0], indexes[-1]
            evidence.append({"start": segments[first]["start"], "end": segments[last]["end"],
                             "char_start": offsets[first][0], "char_end": offsets[last][1]})
        if position == "late":
            assert all(e["char_start"] >= 12000 for e in evidence)
        if position == "early":
            assert all(e["char_end"] <= 12000 for e in evidence)
        if position == "cross_cutoff":
            assert any(e["char_end"] <= 12000 for e in evidence)
            assert any(e["char_start"] >= 12000 for e in evidence)
        answerable = category != "unanswerable"
        rows.append({
            "case_id": f"hy-long-{number:02d}", "dataset_role": "different_course_first_check",
            "frozen_at": frozen_at, "status": "ai_checked_against_captions_only",
            "human_reviewed": False, "reviewer": "Codex AI",
            "course_title": snapshot["course_title"], "chapter_title": snapshot["chapter_title"],
            "video_url": snapshot["url"], "page": snapshot["page"], "scope": "single_lecture",
            "official_course_url": snapshot["official_course_url"],
            "official_video_url": snapshot["official_video_url"],
            "subtitle_snapshot": SNAPSHOT, "subtitle_sha256": digest, "subtitle_chars": len(text),
            "category": category, "evidence_position": position, "question": question,
            "answerable_from_snapshot": answerable, "required_points": points,
            "gold_answer": " ".join(points), "evidence": evidence,
            "absence_review_scope": "AI read full automatic caption snapshot, not audio, video frames or external course materials" if not answerable else None,
            "legacy_12000_truncates": True,
            "legacy_missing_required_evidence": position in {"late", "cross_cutoff"},
            "run_status": "not_run", "scores": None,
        })
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    code_paths = ["backend/context_policy.py", "backend/rag_service.py", "backend/retriever.py",
                  "backend/chunker.py", "backend/vector_store.py", "backend/summarizer.py",
                  "backend/evaluate_course.py"]
    protocol = {
        "frozen_at": frozen_at, "dataset": destination.relative_to(ROOT).as_posix(),
        "dataset_sha256": sha(destination), "subtitle_sha256": digest,
        "scope": "10 AI-authored questions from one different-course lecture; 2 early, 5 entirely late, 1 cross-cutoff, 2 unanswerable",
        "first_run_before_strategy_tuning_on_this_course": True,
        "caption_chars": len(text), "caption_segments": len(segments),
        "video_duration_seconds": snapshot["duration_seconds"],
        "legacy_budget_chars": 12000,
        "legacy_cutoff_caption": {"start": segments[crossing]["start"], "end": segments[crossing]["end"],
                                  "char_start": offsets[crossing][0], "char_end": offsets[crossing][1]},
        "modes": ["legacy", "full_short"],
        "web_strategy": "all indexed chunks up to 12000 chars including overlap; otherwise hybrid Top-3 (10 candidates per route)",
        "code_sha256": {p: sha(ROOT / p) for p in code_paths},
        "model_setup": "Same configured model and grounded prompt; temperature 0.2, max_tokens 2048, thinking disabled, one answer call per case/mode",
        "answerable_pass": "All required points correct and grounded in valid cited supplied sources; no material unsupported additions",
        "unanswerable_pass": "Clearly state missing evidence and invent none of the requested figures; do not conflate token probability with accuracy",
        "partial": "At least one required point grounded but one or more missing or unsupported; or material unsupported additions",
        "fail": "No required answer point grounded, incorrect core answer, or invented requested figures",
        "review": "AI checks frozen points against full automatic captions, answers and actual cited snippets; evaluator knows modes; no human, audio or blind review",
        "retrieval_analysis": "Record frozen evidence-window overlap for diagnostics only; semantic support must be read, not inferred from timestamp overlap",
        "runtime": "Single sequential non-streaming request per question/mode; generation time excludes context preparation/indexing; no stable speed claim",
        "structural_checks": ["20 nonempty answers with stop finish_reason", "Valid source IDs for citations", "Preserved part and timestamp links in current mode", "Dataset, snapshot and strategy hashes unchanged"],
        "no_test_driven_tuning_in_this_run": True,
        "after_run_role": "Observed regression cases, not an untouched holdout for subsequent changes",
        "causal_or_population_inference": False,
    }
    with protocol_path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(protocol, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"frozen_at": frozen_at, "cases": len(rows), "dataset_sha256": sha(destination),
                      "caption_chars": len(text), "legacy_cutoff": protocol["legacy_cutoff_caption"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
