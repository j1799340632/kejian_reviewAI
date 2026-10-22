"""Freeze a same-course diagnostic set before requesting model answers.

References are AI-reviewed against caption snapshots, not human/audio reviewed.
This set overlaps the original development topics and is not an unseen-course
benchmark. Raw captions and answers remain local in the ignored directories.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = [
    (103, "ordinary", "不同格式的数据用相应加载器加载后，统一得到什么对象？加载这一步的作用是什么？",
     ["按数据格式选择相应的加载器。", "将数据加载到内存中，形成 Document 对象。"], [(17.92, 58.749)]),
    (103, "ordinary", "为什么文档向量要持久化保存，而不是每次使用时重新生成？",
     ["保存已经生成的向量。", "后续复用，避免每次使用都重新向量化文档。"], [(248.79, 279.77)]),
    (108, "ordinary", "固定字符数切分里的重叠窗口具体怎么做？它要缓解什么问题？",
     ["相邻文本块之间保留一部分重复内容。", "缓解切分边界造成的语义断裂。"], [(84.77, 140.62)]),
    (108, "ordinary", "按语义内容切分有哪些代价？为什么切出来的块可能大小不均？",
     ["语义相似性判断需要向量化或模型参与。", "可能增加成本并降低速度。", "语义单元长度不同，可能出现很大的块和很小的块。"], [(183.4, 234.79)]),
    (110, "ordinary", "递归切分可以自定义分隔符吗？老师举了哪些适合加入的标点例子？",
     ["可以自定义 separators。", "例子包括逗号、句号、感叹号、省略号。"], [(108.37, 138.67)]),
    (112, "ordinary", "embed_documents 应该接收一个字符串，还是字符串列表？返回的是一个向量，还是向量列表？",
     ["输入为字符串列表。", "返回各字符串对应的向量构成的列表。"], [(631.66, 680.05)]),
    (103, "multi_evidence", "把本节的加载、嵌入、持久化三个步骤串起来：各处理什么对象，分别解决什么问题？",
     ["加载：按格式使用加载器，将数据读入内存形成 Document。", "嵌入：使用嵌入模型把文本块转成向量，便于相似度检索。", "持久化：保存向量，避免每次使用重新转换。"], [(17.92, 58.749), (163.43, 203.13), (248.79, 279.77)]),
    (112, "multi_evidence", "请根据本节整理“单句到向量”和“CSV 到批量向量”两条处理链，并说明两条链的输入、输出结构有什么区别。",
     ["单句：字符串传给 embed_query，得到一个向量。", "CSV：加载并切分文档，从各 Document 提取文本组成字符串列表。", "字符串列表传给 embed_documents，得到对应的向量列表。"], [(511.88, 566.609), (631.66, 680.05), (715.12, 779.5)]),
    (108, "unanswerable", "本节对比的不同切分策略各自准确率和召回率是多少？请给出评测样本量。",
     ["明确说明本节字幕没有给出这些量化评测数据。", "不编造准确率、召回率或样本量。"], []),
    (120, "unanswerable", "这节客服知识库项目上线后的日活用户数、付费转化率分别是多少？",
     ["明确说明本节字幕没有给出这些上线运营数据。", "不编造日活用户数或付费转化率。"], []),
]


def main():
    base = {}
    for line in (ROOT / "evals/cases.bilibili-langchain.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            base[case["page"]] = case
    frozen_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for number, (page, category, question, points, windows) in enumerate(SPECS, 1):
        original = base[page]
        raw = (ROOT / original["subtitle_snapshot"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != original["subtitle_sha256"]:
            raise ValueError(f"Changed snapshot for P{page}")
        snapshot = json.loads(raw)
        segments = snapshot["segments"]
        if snapshot["full_text"] != " ".join(s["text"] for s in segments):
            raise ValueError("Cannot map segment offsets to full_text")
        offsets, position = [], 0
        for segment in segments:
            offsets.append((position, position + len(segment["text"])))
            position += len(segment["text"]) + 1
        evidence = []
        for start, end in windows:
            indexes = [i for i, s in enumerate(segments) if s["start"] < end and s["end"] > start]
            first, last = indexes[0], indexes[-1]
            evidence.append({
                "start": segments[first]["start"], "end": segments[last]["end"],
                "char_start": offsets[first][0], "char_end": offsets[last][1],
            })
        answerable = category != "unanswerable"
        rows.append({
            "case_id": f"lc-check-{number:02d}",
            "dataset_role": "same_course_supplemental_diagnostic",
            "frozen_at": frozen_at, "status": "ai_checked_against_captions_only",
            "human_reviewed": False, "reviewer": "Codex AI",
            "video_url": original["video_url"], "page": page,
            "chapter_title": original["chapter_title"], "scope": "single_part",
            "subtitle_snapshot": original["subtitle_snapshot"],
            "subtitle_sha256": original["subtitle_sha256"],
            "subtitle_chars": len(snapshot["full_text"]),
            "category": category, "question": question,
            "answerable_from_snapshot": answerable,
            "required_points": points, "gold_answer": " ".join(points),
            "evidence": evidence,
            "absence_review_scope": "Full caption snapshot; not audio or video frames" if not answerable else None,
            "legacy_12000_truncates": False,
            "run_status": "not_run", "scores": None,
        })
    destination = ROOT / "evals/cases.course-check.jsonl"
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    protocol = {
        "frozen_at": frozen_at,
        "dataset": str(destination.relative_to(ROOT)).replace("\\", "/"),
        "dataset_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "scope": "10 same-course diagnostic questions; overlapping development topics, no independent-course or long-caption claim",
        "modes": ["hybrid"],
        "quality_review": "AI assessment against full captions and retrieved evidence; no human or audio review",
        "answerable_pass": "All required points covered correctly AND critical claims supported by valid cited sources",
        "unanswerable_pass": "Explicitly state missing evidence AND invent no requested figures",
        "partial": "Some necessary points supported but one or more missing or not supported by citations",
        "structural_checks": ["Nonempty answer", "Stop finish_reason", "Existing source IDs for citations", "Correct part and timestamp parameters"],
        "causal_or_population_inference": False,
    }
    with (ROOT / "evals/course-check-protocol.json").open("x", encoding="utf-8") as output:
        json.dump(protocol, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(f"Frozen {len(rows)} questions: {destination}")


if __name__ == "__main__":
    main()
