"""Compare context strategies against fixed local subtitle snapshots.

No answer-quality score is assigned automatically. Original captions and raw
outputs stay in gitignored evals/data and evals/runs directories.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]


def load_cases(path: Path) -> list[tuple[dict, dict]]:
    loaded = []
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        if case.get("example_only") or case["case_id"] in seen:
            raise ValueError("Evaluation requires distinct, non-example cases")
        seen.add(case["case_id"])
        snapshot_path = (ROOT / case["subtitle_snapshot"]).resolve()
        if not snapshot_path.is_relative_to(ROOT / "evals" / "data"):
            raise ValueError("Snapshot must be under evals/data")
        raw = snapshot_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != case["subtitle_sha256"]:
            raise ValueError(f"Subtitle hash mismatch: {case['case_id']}")
        snapshot = json.loads(raw)
        if len(snapshot["full_text"]) != case["subtitle_chars"]:
            raise ValueError(f"Subtitle length mismatch: {case['case_id']}")
        loaded.append((case, snapshot))
    if not loaded:
        raise ValueError("No cases found")
    return loaded


def legacy_sources(snapshot: dict) -> list[dict]:
    text = snapshot["full_text"][:12000]
    # The source span must stop at the last included caption, not the end of a
    # long video whose later captions were never sent to this baseline.
    cursor, end = 0, 0.0
    for segment in snapshot["segments"]:
        if cursor >= len(text):
            break
        if segment.get("text", "").strip():
            end = float(segment["end"])
        cursor += len(segment.get("text", "")) + 1
    return [{
        "id": "S1", "text": text,
        "start": 0.0, "end": end,
        "timestamp": "00:00", "url": snapshot["url"],
    }]


def retrieval_sources(case: dict, snapshot: dict, mode: str, store, retriever) -> list[dict]:
    return retrieval_context(case, snapshot, mode, store, retriever)[0]


def retrieval_context(case: dict, snapshot: dict, mode: str, store, retriever):
    from chunker import chunk_segments
    from context_policy import select_context, format_sources

    # Include the snapshot hash to avoid reusing an index of different captions.
    video_id = hashlib.sha256(
        (case["video_url"] + "|" + case["subtitle_sha256"]).encode()
    ).hexdigest()[:16]
    if not store.is_indexed(video_id):
        store.index_video(video_id, chunk_segments(snapshot["segments"]))
        retriever.clear_bm25_cache()
    hits, details = select_context(video_id, case["question"], mode, store, retriever)
    return format_sources(hits, case["video_url"]), details


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "evals/cases.bilibili-langchain.jsonl")
    parser.add_argument("--additional-cases", type=Path, nargs="+", default=[], help="Include distinct diagnostic cases from other files")
    parser.add_argument("--modes", nargs="+", choices=["legacy", "vector", "hybrid", "full_short", "hybrid6", "split", "hybrid8", "expanded", "bounded_full"], default=["legacy", "vector", "hybrid"])
    parser.add_argument("--prompt-version", choices=["v1", "v2", "v3"], default="v3")
    parser.add_argument("--output-policy", choices=["none", "source_code_v1"], default="source_code_v1")
    parser.add_argument("--retrieval-only", action="store_true", help="Skip all paid model requests")
    parser.add_argument("--check", action="store_true", help="Validate snapshots only")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    cases = load_cases(args.cases)
    for extra_path in args.additional_cases:
        cases.extend(load_cases(extra_path))
    if len({case["case_id"] for case, _ in cases}) != len(cases):
        raise ValueError("Duplicate case IDs across input files")
    if args.check:
        print(json.dumps({"valid_cases": len(cases), "human_reviewed": sum(bool(c.get("human_reviewed")) for c, _ in cases)}))
        return 0

    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend/.env")
    model = None
    if not args.retrieval_only:
        key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not key or key == "sk-your-deepseek-api-key":
            raise ValueError("Fill DEEPSEEK_API_KEY in backend/.env before generation")
        from summarizer import VideoSummarizer, GROUNDED_SYSTEM_PROMPTS
        model = VideoSummarizer()

    store = retriever = None
    if any(mode != "legacy" for mode in args.modes):
        # A separate collection keeps evaluation indexes out of the web app.
        os.environ["MILVUS_COLLECTION"] = "video_evaluation"
        import vector_store as store
        import retriever
        store.init_collection()

    output = args.output or ROOT / "evals/runs" / (
        datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S") + ".jsonl"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    # Refuse to overwrite previous observations.
    with output.open("x", encoding="utf-8") as stream:
        for case, snapshot in cases:
            for mode in dict.fromkeys(args.modes):
                row = {
                    "case_id": case["case_id"], "mode": mode, "question": case["question"],
                    "video_url": case["video_url"], "subtitle_sha256": case["subtitle_sha256"],
                    "reference_status": case.get("status"), "reference_points": case.get("required_points", []),
                    "scores": None, "review_status": "not_reviewed",
                    "requested_model": model.model if model else None,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "prompt_version": args.prompt_version if model else None,
                    "output_policy": args.output_policy if model else None,
                    "system_prompt_sha256": hashlib.sha256(GROUNDED_SYSTEM_PROMPTS[args.prompt_version].encode()).hexdigest() if model else None,
                    "generation_parameters": {"thinking": "disabled", "temperature": 0.2, "max_tokens": 2048} if model else None,
                    "run_status": "failed",
                }
                try:
                    started = perf_counter()
                    if mode == "legacy":
                        sources = legacy_sources(snapshot)
                        row["context_policy"] = {"strategy": "first_12000_characters", "additional_model_calls": 0}
                    else:
                        sources, row["context_policy"] = retrieval_context(case, snapshot, mode, store, retriever)
                    row["context_preparation_ms"] = round((perf_counter() - started) * 1000, 2)
                    row["sources"] = sources
                    row["context_chars"] = sum(len(source["text"]) for source in sources)
                    if model and sources:
                        started = perf_counter()
                        response = model.answer_with_sources(sources, case["question"], prompt_version=args.prompt_version)
                        row["generation_ms"] = round((perf_counter() - started) * 1000, 2)
                        row["raw_answer"] = response.choices[0].message.content or ""
                        row["answer"] = row["raw_answer"]
                        if args.output_policy == "source_code_v1":
                            from answer_guard import guard_source_code
                            row["answer"], row["output_guard"] = guard_source_code(row["raw_answer"], sources, case["question"])
                        row["finish_reason"] = response.choices[0].finish_reason
                        row["response_model"] = response.model
                        row["usage"] = response.usage.model_dump() if response.usage else None
                        row["run_status"] = "generated" if row["answer"] else "empty_answer"
                    elif args.retrieval_only:
                        row["run_status"] = "retrieval_only"
                    else:
                        row["run_status"] = "empty_retrieval"
                except Exception as exc:
                    # Do not write SDK exception messages that might carry configuration.
                    row["error_type"] = type(exc).__name__
                    failures += 1
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                print(json.dumps({"case_id": case["case_id"], "mode": mode, "status": row["run_status"], "context_chars": row.get("context_chars"), "error_type": row.get("error_type")}), flush=True)
    print(f"Saved: {output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
