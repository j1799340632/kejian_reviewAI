"""Freeze regression rubric revisions, fresh questions and experiment plan.

Run before candidate implementation or generation. Never replace past cases,
answers or reviews. Fresh questions are same-lecture questions, not new users
or an independently authored benchmark.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_DATASETS = ["evals/cases.bilibili-langchain.jsonl", "evals/cases.course-check.jsonl", "evals/cases.independent-long.jsonl"]
FRESH = [
    ("ordinary", "本节说生成式 AI 产生的是“复杂而有结构的物件”。这里的“有结构”是什么意思？为什么基本单位的候选有限，却能产生无穷的组合？",
     ["物件由有限可能的基本单位构成，这些单位统称为 token。", "有限种类的单位以不同方式组合，可以构成无穷的物件或内容。"], [(2120, 2245)]),
    ("ordinary", "本节后半段把什么样的模型称为“开源”？知道模型参数，是否等于完整知道它怎样训练出来？请说明讲师采用的定义范围。",
     ["本节采用参数可知、参数数值可取得的定义。", "讲师说明开源有不同定义；只公开参数不等于公开完整训练过程，一些人因此不认为这算完全开源。"], [(2560, 2670)]),
    ("ordinary", "在登录 Hugging Face、下载模型的环节，token 指什么？它和生成式 AI 输出的 token 是同一个含义吗？",
     ["该环节的 token 是连接或登录 Hugging Face 所用的凭证。", "它与生成式 AI 产生的 token 不是同一个含义。"], [(2980, 3070)]),
    ("multi_evidence", "根据本节 model.generate 的演示，它输出的 ID 包不包含原输入？生成会在什么条件下停止，之后怎样转成人能读的文字？",
     ["输出包括原输入的 ID，以及在其后继续生成的 ID。", "生成结束 token 或达到设定的长度上限时停止。", "将输出 ID 交给 tokenizer.decode 转成文字。"], [(4780, 4880)]),
    ("ordinary", "课程末尾用 pipeline 换了一个模型后，为什么它仍自称是原来的模型？能否仅凭它的自我介绍判断实际加载的是哪个模型？",
     ["实际模型已随 model ID 的切换而改变。", "系统提示仍写着原模型身份，因此新模型沿着该提示自称原模型；自我介绍不等于实际加载模型身份。"], [(6210, 6315)]),
    ("unanswerable", "本节给出的 top-k=3 相比 top-k=1 在独立测试集上的准确率提高多少个百分点？该测试集有多少题？",
     ["说明本节未给出这项独立测试集的准确率增幅和题数。", "不把示例 token 概率或主观生成效果当成评测结果，不编造数值。"], []),
]


def sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def write_json(path, value):
    with (ROOT / path).open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_lines(path, rows):
    with (ROOT / path).open("x", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    protocol_path = "evals/iteration02-protocol.json"
    regression_path = "evals/cases.iteration02-regression.jsonl"
    fresh_path = "evals/cases.iteration02-fresh.jsonl"
    assert not any((ROOT / p).exists() for p in [protocol_path, regression_path, fresh_path])
    frozen_at = datetime.now(timezone.utc).isoformat()
    old = []
    for dataset in OLD_DATASETS:
        for line in (ROOT / dataset).read_text(encoding="utf-8").splitlines():
            if line:
                row = json.loads(line)
                row["source_case_file"] = dataset
                row["original_required_points"] = deepcopy(row["required_points"])
                old.append(row)
    for row in old:
        row["dataset_role"] = "observed_development_regression"
        row["rubric_version"] = "iteration02"
        row["rubric_frozen_at"] = frozen_at
        if row["case_id"] == "hy-long-02":
            row["required_points"][1] = "明确回答搜索不保证每次正确；降低幻觉的作用可以说明，但不是题面要求的单独必答项。"
            row["rubric_revision"] = "Remove unasked requirement to explicitly state the positive search effect; keep the not-guaranteed answer requirement. Historical cases/scores are unchanged."
        if row["case_id"] == "lc-course-03":
            row["required_points"][2] = "在保留文本结构的同时，把块控制到适合嵌入和检索的长度。"
            row["rubric_revision"] = "Remove customizable-separator clause not asked by this question. Historical cases/scores are unchanged."
        row["gold_answer"] = " ".join(row["required_points"])
    write_lines(regression_path, old)

    original = next(r for r in old if r["case_id"] == "hy-long-01")
    snapshot = json.loads((ROOT / original["subtitle_snapshot"]).read_text(encoding="utf-8"))
    assert sha(original["subtitle_snapshot"]) == original["subtitle_sha256"]
    segments = snapshot["segments"]
    offsets, cursor = [], 0
    for seg in segments:
        offsets.append((cursor, cursor + len(seg["text"])))
        cursor += len(seg["text"]) + 1
    fresh = []
    for number, (category, question, points, windows) in enumerate(FRESH, 1):
        row = {k: deepcopy(original[k]) for k in ["video_url", "page", "scope", "chapter_title", "course_title", "official_course_url", "official_video_url", "subtitle_snapshot", "subtitle_sha256", "subtitle_chars"]}
        evidence = []
        for start, end in windows:
            indexes = [i for i, s in enumerate(segments) if s["start"] < end and s["end"] > start]
            a, b = indexes[0], indexes[-1]
            evidence.append({"start": segments[a]["start"], "end": segments[b]["end"], "char_start": offsets[a][0], "char_end": offsets[b][1]})
        row.update({"case_id": f"hy-fresh-{number:02d}", "dataset_role": "fresh_same_lecture_questions_frozen_before_candidate_work",
                    "frozen_at": frozen_at, "status": "ai_checked_against_captions_only", "human_reviewed": False,
                    "reviewer": "Codex AI", "rubric_version": "iteration02", "category": category,
                    "question": question, "required_points": points, "gold_answer": " ".join(points), "evidence": evidence,
                    "answerable_from_snapshot": category != "unanswerable", "legacy_12000_truncates": True,
                    "evidence_position": "not_applicable" if not evidence else "late" if all(e["char_start"] >= 12000 for e in evidence) else "early" if all(e["char_end"] <= 12000 for e in evidence) else "cross_cutoff",
                    "absence_review_scope": "AI read full fixed captions; not audio/slides" if not evidence else None,
                    "run_status": "not_run", "scores": None})
        fresh.append(row)
    write_lines(fresh_path, fresh)

    baseline_dir = ROOT / "evals/runs/iteration02-baseline-code"
    baseline_dir.mkdir(parents=True, exist_ok=False)
    code = ["backend/context_policy.py", "backend/retriever.py", "backend/rag_service.py", "backend/summarizer.py", "backend/evaluate_course.py"]
    for p in code:
        with (baseline_dir / Path(p).name).open("xb") as f:
            f.write((ROOT / p).read_bytes())
    protocol = {
        "frozen_at": frozen_at, "date_local": "2026-10-21", "reviewer": "Codex AI", "human_reviewed": False,
        "regression_dataset": regression_path, "regression_sha256": sha(regression_path), "regression_cases": len(old),
        "fresh_dataset": fresh_path, "fresh_sha256": sha(fresh_path), "fresh_cases": len(fresh),
        "source_dataset_sha256": {p: sha(p) for p in OLD_DATASETS}, "baseline_code_sha256": {p: sha(p) for p in code},
        "baseline_code_copy": baseline_dir.relative_to(ROOT).as_posix(),
        "candidate_plan": ["Keep existing short-content full context; compare unchanged long Top-3, long Top-8, and clause-query retrieval with bounded neighboring chunks",
                           "Do retrieval-only candidate screening on the 25 observed questions; manually inspect necessary evidence, not timestamp overlap alone",
                           "Select and freeze a bounded strategy before reading any fresh-question model answer; max 5 queries, 20 chunks, 10000 context characters for the expanded candidate",
                           "Revise grounded answer prompt for question completeness and automatic-caption/uncertain-code ambiguity; do not hardcode lecture facts or corrected model names"],
        "generation_plan": "25 regression questions: baseline context+v1 prompt and selected context+v2 prompt. Six fresh questions: same paired settings, once each after selection is frozen. No tuning after fresh results.",
        "scope": "Two courses, six videos; fresh questions come from the already inspected long lecture, not unseen course/domain or independent human authors",
        "comparison_caveat": "Context and prompt both change in the selected bundle; do not attribute bundle quality change solely to retrieval. One response per setting/question, no statistical or population claim.",
        "answerable_pass": "Necessary points correctly answered and grounded in actual cited supplied snippets; no material unsupported additions, code spellings or ASR-driven entity conversions",
        "unanswerable_pass": "State missing requested evidence; invent none of the requested figures",
        "partial": "Some requested content grounded, but missing/incomplete points or material unsupported additions",
        "fail": "No requested answer grounded, central answer wrong, or invented requested figures",
        "no_answer_reference_scope": "AI review of full fixed captions, not lecture audio/slides; model refusal about supplied snippets alone is not evidence of full-video absence",
        "guardrail_points": "Prohibitions such as do-not-generalize-dimension or do-not-promise-preserved-semantics do not require an explicit disclaimer when no prohibited claim is made",
        "historical_scores": "Preserve original cases/reviews. Rescore both new baseline and selected outputs under the same revised regression rubric; do not compare an old strict score to a revised score as an improvement.",
        "browser_plan": "Real homepage -> parse long lecture -> two real questions -> source expansion -> later source link opens correct part/time; verify ID reuse and input recovery; no mocked external services",
        "completion": "Report candidate choice, paired development and fresh results, cost/timing caveats, remaining failures and real browser observations; no fabricated human experience",
    }
    write_json(protocol_path, protocol)
    print(json.dumps({"frozen_at": frozen_at, "regression_cases": len(old), "fresh_cases": len(fresh), "fresh_sha256": sha(fresh_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
