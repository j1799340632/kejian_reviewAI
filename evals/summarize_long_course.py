"""Validate frozen long-course observations and summarize AI review counts.

This does not assign quality judgments. Those are recorded separately after
reading the actual answers and captions in reviews.independent-long.json.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from statistics import mean
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def main():
    protocol_path = "evals/independent-long-protocol.json"
    protocol = read_json(protocol_path)
    review_path = "evals/reviews.independent-long.json"
    review = read_json(review_path)
    run_path = review["run_file"]
    assert digest(run_path) == review["run_sha256"]
    assert digest(protocol["dataset"]) == protocol["dataset_sha256"] == review["dataset_sha256"]
    assert all(digest(p) == value for p, value in protocol["code_sha256"].items())
    cases = [json.loads(x) for x in (ROOT / protocol["dataset"]).read_text(encoding="utf-8").splitlines() if x]
    rows = [json.loads(x) for x in (ROOT / run_path).read_text(encoding="utf-8").splitlines() if x]
    index_path = "evals/runs/independent-long-index-check-20261021.json"
    index_check = read_json(index_path)
    assert index_check["exact_chunk_text_and_approx_time_match"]
    assert index_check["whitespace_normalized_deduplicated_reconstruction_matches_snapshot"]
    assert len(rows) == len(cases) * len(protocol["modes"]) == 20
    case_map = {c["case_id"]: c for c in cases}
    expected_keys = {(c["case_id"], m) for c in cases for m in protocol["modes"]}
    assert {(r["case_id"], r["mode"]) for r in rows} == expected_keys
    reviews = {(r["case_id"], r["mode"]): r for r in review["rows"]}
    assert len(reviews) == len(review["rows"]) == 20 and set(reviews) == expected_keys
    for case in cases:
        assert digest(case["subtitle_snapshot"]) == case["subtitle_sha256"]
    for row in rows:
        case = case_map[row["case_id"]]
        assert row["run_status"] == "generated" and row["answer"].strip()
        assert row["finish_reason"] == "stop"
        assert row["subtitle_sha256"] == case["subtitle_sha256"]
        assert row["question"] == case["question"]
        assert len(reviews[row["case_id"], row["mode"]]["point_assessments"]) == len(case["required_points"])
        ids = {s["id"] for s in row["sources"]}
        used = set(re.findall(r"\[(S\d+)\]", row["answer"]))
        assert used and used <= ids
        assert row["context_chars"] == sum(len(s["text"]) for s in row["sources"])
        if row["mode"] == "full_short":
            assert row["context_policy"]["strategy"] == "hybrid_top3_long_fallback"
            assert row["context_policy"]["indexed_context_chars"] == index_check["indexed_chars_including_overlap"]
            assert len(row["sources"]) == 3
            for source in row["sources"]:
                params = parse_qs(urlparse(source["url"]).query)
                assert params["p"] == ["1"] and params["t"] == [str(int(source["start"]))]
        else:
            assert row["context_chars"] == 12000
            assert row["sources"][0]["end"] == protocol["legacy_cutoff_caption"]["end"]

    modes = {}
    for mode in protocol["modes"]:
        selected = [r for r in rows if r["mode"] == mode]
        verdicts = [reviews[r["case_id"], mode] for r in selected]
        by_position = {}
        for position in dict.fromkeys(c["evidence_position"] for c in cases):
            subset = [r for r in selected if case_map[r["case_id"]]["evidence_position"] == position]
            by_position[position] = dict(Counter(reviews[r["case_id"], mode]["verdict"] for r in subset))
        modes[mode] = {
            "cases": len(selected), "verdict_counts": dict(Counter(r["verdict"] for r in verdicts)),
            "verdicts_by_evidence_position": by_position,
            "prompt_tokens": sum(r["usage"]["prompt_tokens"] for r in selected),
            "completion_tokens": sum(r["usage"]["completion_tokens"] for r in selected),
            "prompt_cache_hit_tokens": sum(r["usage"].get("prompt_cache_hit_tokens", 0) for r in selected),
            "prompt_cache_miss_tokens": sum(r["usage"].get("prompt_cache_miss_tokens", 0) for r in selected),
            "mean_generation_ms": round(mean(r["generation_ms"] for r in selected), 3),
            "context_chars_total": sum(r["context_chars"] for r in selected),
            "first_context_preparation_ms": selected[0]["context_preparation_ms"],
            "remaining_context_preparation_mean_ms": round(mean(r["context_preparation_ms"] for r in selected[1:]), 3),
            "context_strategies": dict(Counter(r["context_policy"]["strategy"] for r in selected)),
        }
    summary = {
        "date": review["date"], "human_reviewed": False, "reviewer": review["reviewer"],
        "run_file": run_path, "run_sha256": digest(run_path),
        "protocol_file": protocol_path, "protocol_sha256": digest(protocol_path),
        "dataset_file": protocol["dataset"], "dataset_sha256": protocol["dataset_sha256"],
        "review_file": review_path, "review_sha256": digest(review_path),
        "source": {"video_url": cases[0]["video_url"], "official_course_url": cases[0]["official_course_url"],
                   "subtitle_snapshot": cases[0]["subtitle_snapshot"], "subtitle_sha256": protocol["subtitle_sha256"],
                   "subtitle_chars": protocol["caption_chars"], "segments": protocol["caption_segments"],
                   "duration_seconds": protocol["video_duration_seconds"],
                   "legacy_cutoff_caption": protocol["legacy_cutoff_caption"]},
        "index_check_file": index_path, "index_check_sha256": digest(index_path),
        "index_check": index_check,
        "requested_models": sorted({r["requested_model"] for r in rows}),
        "response_models": sorted({r["response_model"] for r in rows}),
        "generation_parameters": rows[0]["generation_parameters"],
        "checks": {"20_nonempty_stop_answers": True, "cited_source_ids_exist": True,
                   "current_mode_30_part_and_time_links_valid": True, "snapshot_and_dataset_hashes_unchanged": True,
                   "strategy_code_hashes_unchanged_since_freeze": True,
                   "102_stored_chunks_match_complete_caption": True},
        "modes": modes,
        "limitations": ["One different-course lecture, ten deliberately constructed questions, one response per mode/question",
                        "AI-authored and nonblind AI review of automatic captions; no human/audio/slide verification",
                        "No strategy tuning on these results; future use is regression, not untouched holdout",
                        review["rubric_limitation"],
                        "Generation timing excludes context preparation, networking setup and user review; no speed or billing claim"],
    }
    destination = ROOT / "evals/independent-long-summary.json"
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(summary, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"checks": summary["checks"], "modes": modes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
