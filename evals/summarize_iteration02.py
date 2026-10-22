"""Validate iteration-02 observations and summarize explicit AI reviews."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from statistics import mean
from urllib.parse import parse_qs, urlsplit
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from answer_guard import guard_source_code


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def lines(path):
    return [json.loads(x) for x in (ROOT / path).read_text(encoding="utf-8").splitlines() if x]


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def main():
    protocol = read("evals/iteration02-protocol.json")
    selection = read("evals/iteration02-selection.json")
    review = read("evals/reviews.iteration02.json")
    assert sha(protocol["regression_dataset"]) == protocol["regression_sha256"]
    assert sha(protocol["fresh_dataset"]) == protocol["fresh_sha256"] == selection["fresh_dataset_sha256"]
    assert all(sha(p) == value for p, value in protocol["source_dataset_sha256"].items())
    assert all(sha(p) == value for p, value in selection["code_sha256"].items())
    cases = {c["case_id"]: c for p in [protocol["regression_dataset"], protocol["fresh_dataset"]] for c in lines(p)}
    assert len(cases) == 31 and all(not c["human_reviewed"] for c in cases.values())
    for c in cases.values():
        assert sha(c["subtitle_snapshot"]) == c["subtitle_sha256"]
    expected = {(case_id, setting) for case_id in cases for setting in ["baseline", "selected"]}
    indexed_reviews = {(r["case_id"], r["setting"]): r for r in review["rows"]}
    assert len(indexed_reviews) == len(review["rows"]) == 62 and set(indexed_reviews) == expected
    results, no_citation_refusals = {}, []
    for name, path in review["run_files"].items():
        assert sha(path) == review["run_sha256"][name]
        partition, setting = name.split("_")
        rows = lines(path)
        rr = [r for r in review["rows"] if r["partition"] == partition and r["setting"] == setting]
        assert len(rows) == len(rr) == (25 if partition == "regression" else 6)
        for row in rows:
            case = cases[row["case_id"]]
            assert row["question"] == case["question"] and row["subtitle_sha256"] == case["subtitle_sha256"]
            assert row["run_status"] == "generated" and row["answer"].strip() and row["finish_reason"] == "stop"
            used = set(re.findall(r"\[(S\d+)\]", row["answer"]))
            assert used <= {s["id"] for s in row["sources"]}
            if not used:
                assert not case["answerable_from_snapshot"]
                no_citation_refusals.append({"case_id": row["case_id"], "setting": setting})
            assert len(indexed_reviews[row["case_id"], setting]["point_assessments"]) == len(case["required_points"])
            for source in row["sources"]:
                params = parse_qs(urlsplit(source["url"]).query)
                assert params["p"] == [str(case["page"])]
                assert params["t"] == [str(int(source["start"]))]
            if setting == "selected":
                guarded, audit = guard_source_code(row["raw_answer"], row["sources"], row["question"])
                assert guarded == row["answer"] and audit == row["output_guard"]
                assert row["system_prompt_sha256"] == selection["model_prompt_sha256"]
            if partition == "fresh":
                assert row["started_at"] > selection["frozen_at"] > protocol["frozen_at"]
        results[name] = {
            "questions": len(rows), "verdict_counts": dict(Counter(r["verdict"] for r in rr)),
            "raw_model_verdict_counts": dict(Counter(r["raw_model_verdict"] for r in rr)),
            "prompt_tokens": sum(r["usage"]["prompt_tokens"] for r in rows),
            "completion_tokens": sum(r["usage"]["completion_tokens"] for r in rows),
            "prompt_cache_hit_tokens": sum(r["usage"].get("prompt_cache_hit_tokens", 0) for r in rows),
            "prompt_cache_miss_tokens": sum(r["usage"].get("prompt_cache_miss_tokens", 0) for r in rows),
            "mean_generation_ms": round(mean(r["generation_ms"] for r in rows), 3),
            "strategies": dict(Counter(r["context_policy"]["strategy"] for r in rows)),
            "context_chars_total": sum(r["context_chars"] for r in rows),
            "guard_changed_cases": [r["case_id"] for r in rows if r.get("output_guard", {}).get("replaced_expressions")],
            "verdicts_by_course": {prefix: dict(Counter(r["verdict"] for r in rr if r["case_id"].startswith(prefix))) for prefix in ["lc-", "hy-long-", "hy-fresh-"] if any(r["case_id"].startswith(prefix) for r in rr)},
        }
    # The selected development display is a deterministic replay, not 25 more
    # paid requests. Bind it to the actual raw observations and check replay.
    displayed = lines(review["run_files"]["regression_selected"])
    source_path = "evals/runs/iteration02-regression-final.jsonl"
    raw = {r["case_id"]: r for r in lines(source_path)}
    for row in displayed:
        assert row["derived_from"]["sha256"] == sha(source_path)
        assert row["derived_from"]["additional_model_calls"] == 0
        assert row["raw_answer"] == raw[row["case_id"]]["answer"]
        assert row["usage"] == raw[row["case_id"]]["usage"]
    candidate_paths = ["evals/runs/iteration02-candidates.jsonl", "evals/runs/iteration02-bounded-candidate.jsonl"]
    candidates = [r for p in candidate_paths for r in lines(p)]
    assert len(candidates) == 100 and all(r["run_status"] == "retrieval_only" for r in candidates)
    candidate_summary = {}
    for mode in dict.fromkeys(r["mode"] for r in candidates):
        selected = [r for r in candidates if r["mode"] == mode]
        candidate_summary[mode] = {"records": len(selected), "context_chars_total": sum(r["context_chars"] for r in selected),
                                   "long_course_context_chars": sum(r["context_chars"] for r in selected if r["case_id"].startswith("hy-long-"))}
    browser_path = "evals/runs/iteration02-browser-02.json"
    browser = read(browser_path)
    assert browser["status"] == "passed" and not browser["page_errors"]
    assert len(browser["tasks"]) == 2 and browser["video_id_reused"] and browser["input_recovered"]
    assert all(t["done_event"] and not t["error_event"] for t in browser["tasks"])
    assert not browser["video_playback_verified"] and not browser["human_learning_task"]
    # Verify the live web sources actually match the frozen long snapshot's
    # indexed chunks; this is stronger than checking source counts alone.
    from chunker import chunk_segments
    snapshot = read(cases["hy-long-01"]["subtitle_snapshot"])
    chunks = chunk_segments(snapshot["segments"])
    for task in browser["tasks"]:
        assert len(task["sources"]) == len(chunks) == 102
        assert all(a["text"] == b["text"] and abs(a["start"] - b["start"]) < 0.001 and abs(a["end"] - b["end"]) < 0.001 for a, b in zip(task["sources"], chunks))
    paid_paths = [review["run_files"]["regression_baseline"], "evals/runs/iteration02-regression-selected.jsonl", source_path,
                  review["run_files"]["fresh_baseline"], review["run_files"]["fresh_selected"]]
    live_calls = sum(len(lines(p)) for p in paid_paths)
    assert live_calls == 87
    bound_files = ["evals/iteration02-protocol.json", "evals/iteration02-candidate-amendment.json", "evals/iteration02-selection.json",
                   "evals/reviews.iteration02.json", *candidate_paths, *paid_paths, review["run_files"]["regression_selected"],
                   browser_path, "evals/runs/iteration02-browser.json", protocol["regression_dataset"], protocol["fresh_dataset"]]
    summary = {
        "recorded_at": datetime.now(timezone.utc).isoformat(), "reviewer": "Codex AI", "human_reviewed": False,
        "courses": 2, "videos": 6, "different_questions": 31,
        "paired_reviewed_observations": 62, "development_live_model_calls": 75,
        "fresh_live_model_calls": 12, "successful_browser_live_model_calls": 2,
        "all_iteration_live_model_calls": 89, "deterministic_replay_extra_calls": 0,
        "candidate_observations": 100, "additional_ad_hoc_retrieval_probes": 3,
        "candidates": candidate_summary, "results": results,
        "selected_bundle": {"mode": selection["mode"], "prompt_version": selection["prompt_version"],
                            "output_policy": selection["output_policy"], "indexed_context_budget_chars": 48000,
                            "oversized_fallback": "Unchanged hybrid Top-3; no true >48000-character quality sample in this iteration"},
        "checks": {"62_nonempty_stop_answers": True, "all_emitted_source_ids_exist": True,
                   "all_evaluation_source_links_preserve_part_and_timestamp": True,
                   "frozen_datasets_and_snapshots_unchanged": True,
                   "selected_code_unchanged_before_and_after_fresh_inference": True,
                   "display_guard_replay_matches_live_policy": True,
                   "live_web_102_source_texts_match_frozen_long_snapshot_chunks": True,
                   "backend_tests_passed": 36, "frontend_tests_passed": 3, "frontend_build_passed": True},
        "no_citation_bracket_refusals": no_citation_refusals,
        "browser": {"record": browser_path, "parse_ms": browser["parse"]["elapsed_ms"],
                    "questions_elapsed_ms": [t["elapsed_ms"] for t in browser["tasks"]],
                    "source_count_each": [t["source_count"] for t in browser["tasks"]],
                    "source_click": browser["source_click"], "page_errors": browser["page_errors"],
                    "first_attempt": "Script-only exact accessible-name mismatch before submitting any chat; raw failure record retained",
                    "video_playback_verified": False, "human_learning_task": False},
        "bound_files_sha256": {p: sha(p) for p in dict.fromkeys(bound_files)},
        "limitations": ["Both contexts and prompt/output policies change; cannot attribute the bundle result solely to retrieval",
                        "AI-authored, nonblind AI review against automatic captions, not human/audio or user feedback",
                        "Fresh questions are from an already inspected lecture, not independent-course generalization",
                        "Raw selected model still emits an unverified parameter; visible guard replacement is counted separately",
                        "No semantic code validator; lexical guard may miss other constructs or replace valid but unverified code",
                        "Short early baseline/selected development requests overlapped in time; all timing is descriptive, not a controlled performance comparison",
                        "Input budgets are engineering presets; larger-context and cache observations do not establish billing or learning-efficiency improvement",
                        "No real quality validation above the new 48000-character indexed budget"]}
    with (ROOT / "evals/iteration02-summary.json").open("x", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"results": {k: v["verdict_counts"] for k, v in results.items()}, "checks": summary["checks"], "live_model_calls": 89}, ensure_ascii=False))


if __name__ == "__main__":
    main()
