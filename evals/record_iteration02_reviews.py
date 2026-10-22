"""Persist explicit AI judgments after reading answers and actual citations.

No model-based grader or timestamp-overlap auto-scoring. Each row below is an
AI review, not independent human validation. Raw answers are never overwritten.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# id, baseline verdict/points/notes, selected verdict/points/notes
JUDGMENTS = [
    ("lc-course-01", "pass", "cccc", "S1/S2 loading, S2-S4 transformations, S4/S5 embedding and S6 persistence are covered. Exact ASR-derived attribute names were not screen-verified.",
     "pass", "cccc", "S1 loading, S2/S3 transformations, S4 embedding and S6 persistence cover the requested workflow. No extra PDF example; exact attribute spellings remain outside caption-only validation."),
    ("lc-course-02", "pass", "cccc", "S2/S3 boundary break and overlap, S3/S4 recursive handling. Mitigation is qualified rather than an absolute guarantee.",
     "pass", "cccc", "Boundary splitting, shared overlap and finer separators are covered by S2-S4. No claim that semantics can never be lost."),
    ("lc-course-03", "partial", "ccm", "S1/S2 support correct recursive sequence and stopping. Does not explicitly cover the frozen third point's structure-preservation/embedding-retrieval purpose. Main question's algorithm is answered; removed customizable-separator clause is not counted.",
     "partial", "ccm", "S1/S2 support the sequence and size stopping rule. Still does not explicitly state the third point's structure-preservation purpose. Keep partial under the frozen rubric; this does not mean the main sequence is wrong."),
    ("lc-course-04", "pass", "cccc", "Single input/vector in S11/S12, string list/vectors in S13/S14, CSV text preparation in S15/S16. Different dimensions are example-specific, not generalized.",
     "pass", "cccc", "S11-S16 support both input/output structures and CSV extraction. The answer explicitly leaves the exact text-bearing field for screen verification."),
    ("lc-course-05", "partial", "cccc", "All functional points are present, including insufficient-evidence handling in S11. However the answer promotes ambiguous ASR text/test/contest to the exact content key without establishing that code spelling; retain partial for an unsupported code detail.",
     "pass", "cccc", "Formatting, prompt construction, Agent invocation and final reply retrieval are supported by S3-S7; insufficient-evidence behavior by S11. Ambiguous chunk-id wording is explicitly flagged instead of supplying a guessed numeric index."),
    ("lc-check-01", "pass", "cc", "S1 supports format-specific loaders, memory and Document result. Exact attribute spellings not independently verified.",
     "pass", "cc", "S1 supports both necessary points; describes the two attributes by function rather than committing to uncertain field spelling."),
    ("lc-check-02", "pass", "cc", "S6 supports retaining vectors and avoiding per-use conversion.",
     "pass", "cc", "S6 supports avoiding repeated conversion and storage. No invented cost measurements."),
    ("lc-check-03", "pass", "cc", "S3 describes shared overlap; S2/S3 support boundary break mitigation. The phrase guarantee is qualified by in-a-degree, not an absolute never-loss claim.",
     "pass", "cc", "S3 overlap and S2/S3 boundary mitigation are covered; absent overlap parameter value is not guessed."),
    ("lc-check-04", "pass", "ccc", "S4 model/vectorization overhead and slower speed; S5 unequal semantic unit sizes.",
     "pass", "ccc", "All costs and unequal-unit-size reason covered by S4/S5."),
    ("lc-check-05", "pass", "cc", "S3/S10 support customizable separators; S3 includes comma, period, exclamation and ellipsis.",
     "pass", "cc", "S3/S10 support customization; S3 supports all requested punctuation examples."),
    ("lc-check-06", "pass", "cc", "S13/S14 support string-list input and vector-list output; extra comparison with single-query is also supported.",
     "pass", "cc", "String-list to vector-list is supported by S13/S14 and CSV illustration by S15/S16."),
    ("lc-check-07", "partial", "ccc", "All necessary loading/embedding/persistence points are covered, but PDF is added as an S1/S2 format example absent from the complete fixed P103 captions. Do not count full success merely because necessary points are covered.",
     "pass", "ccc", "S1 loading, S4 embedding and S6 persistence. Previously unsupported PDF example is absent. Caption-only attribute spellings are not claimed as screen-verified."),
    ("lc-check-08", "pass", "ccc", "S10-S12 single string/vector, S15 CSV preparation and S13-S16 vector list are supported. Code spellings remain ASR-dependent.",
     "pass", "ccc", "Both chains and output structures are supported by S10-S16; exact method spellings are flagged for video-code verification."),
    ("lc-check-09", "pass", "cc", "No accuracy/recall/sample-size values supplied or invented; scopes absence to provided snippets.",
     "pass", "cc", "Explicitly says the requested metrics/sample count are absent and invents none."),
    ("lc-check-10", "pass", "cc", "No daily-active or conversion figures invented; evidence insufficiency stated.",
     "pass", "cc", "Refuses to invent operating figures. No bracketed citation is used, but the refusal contains no new positive external factual claim."),
    ("hy-long-01", "fail", "mmm", "Top-3 lacks sampling, append-and-repeat-to-EOS and randomness. Honest abstention on an answerable question still fails the requested task.",
     "pass", "ccc", "S5/S6 sampling, S4/S8 append/repeat, S4 EOS and S8 randomness are restored. Extra top-k discussion has S73/S74 support."),
    ("hy-long-02", "partial", "cp", "S3 supports continuation rather than database lookup. Answer says it cannot confirm a guarantee, while supplied sources lack the lecture's explicit not-guaranteed warning. Positive search effect is no longer a separate mandatory item.",
     "pass", "cc", "S20/S21 support hallucination/continuation; S22 contains the explicit search-not-guaranteed warning and the answer states it directly."),
    ("hy-long-03", "partial", "ccc", "All necessary concepts supported by S1-S3, but extra as special token=false is an unverified executable-looking spelling derived from phonetic captions.",
     "pass", "ccc", "S54/S59 encode, S53/S54 decode and S60/S63/S64 starting symbol cover the three points. Raw model still emits as_special_token=false; shared display guard replaces it with a verification notice. Raw-model verdict remains partial."),
    ("hy-long-04", "pass", "cc", "Leading-space distinction in S1 and removal result in S2 are correctly cited.",
     "pass", "cc", "S61/S62 distinction and S62/S63 removal result are supported; numeric token IDs remain caption-derived, not independently screen-verified."),
    ("hy-long-05", "pass", "ccc", "S1 excludes rare candidates and supports k=1; S3 supports top-three randomness. Describes the actual odd outputs too, not a general coherence guarantee.",
     "pass", "ccc", "S73/S74 candidate restriction and k=1; S75 top-three random choice and demonstration results. No new benchmark figures."),
    ("hy-long-06", "partial", "cpc", "S1/S3 contain all necessary evidence, but the answer omits the complex-manual-template/typing-error reason. This is generation omission, not only missing retrieval.",
     "partial", "cpc", "All 102 snippets are supplied and S82 contains the typing-error reason, but answer again omits that part. Official-template behavior and encoding are covered by S81-S84. Retain this unresolved generation omission."),
    ("hy-long-07", "partial", "cppm", "Roles and template/generate portions are supported, but encoding/extraction are incomplete. It additionally misreads the ASR rendering of Gemma as a decoding operation improving Chinese output.",
     "pass", "cccc", "S83/S84 roles, template and ID conversion; S84/S92 generation; S92/S93 decode and S93 actual answer extraction. The previous Gemma-as-decoding interpretation is absent."),
    ("hy-long-08", "partial", "cpu", "S2 supports the early mountain follow-up and history principle. All Top-3 snippets are early; claiming the later answer-update implementation from S2 is unsupported.",
     "pass", "ccc", "S19 supports mountain disambiguation, S89/S95/S96 role-tagged history, S97/S98 adding new outputs for the next turn. The memory explanation is interpreted in the demonstrated explicit-history scope, not as a general claim about all products."),
    ("hy-long-09", "pass", "cc", "No Llama/Gemma accuracy or sample count invented; supplied-snippet limitation explicit.",
     "pass", "cc", "Distinguishes subjective model comparison from unavailable quantitative benchmark figures; invents no metrics."),
    ("hy-long-10", "pass", "cc", "States supplied evidence lacks monthly-active/conversion data and invents none.",
     "pass", "cc", "No invented operating metrics. Refusal has no explicit source bracket but makes no new positive external claim."),
    ("hy-fresh-01", "pass", "cc", "S1/S2 define finite basic units and their combinations. Extra caveat about absent mathematical derivation does not negate the requested conceptual answer.",
     "pass", "cc", "S33/S34 finite units and S36 combinations support both frozen points."),
    ("hy-fresh-02", "pass", "cc", "S1/S2 support the lecturer's parameter-access definition and distinction from complete training disclosure.",
     "pass", "cc", "S40/S41 support the deliberately scoped course definition and training-process qualification."),
    ("hy-fresh-03", "pass", "cc", "S1/S2 support credential vs generated unit; source also contains the extra login illustration and S3 the gated-download discussion. No real credential is present.",
     "pass", "cc", "S46/S47 credential meaning contrasted with generated units in S3/S30/S32. No token value is exposed or invented."),
    ("hy-fresh-04", "pass", "ccc", "S2 output includes input, S1/S2 stopping conditions, S1 decoding and S3 display extraction are supported.",
     "pass", "ccc", "S76 output structure and S76/S77 two stopping conditions; S77 decoding."),
    ("hy-fresh-05", "partial", "cc", "Necessary identity/system-prompt explanation is present, but the final claim that snippets provide no other model-identity basis contradicts S1/S3 explicitly changing model ID. Preserve partial for this extra unsupported denial.",
     "pass", "cc", "S100/S101 model-ID switch and S88/S89/S101 unchanged system identity are covered. Advises checking configured model identity rather than self-description with source support."),
    ("hy-fresh-06", "pass", "cc", "No accuracy improvement or dataset size invented; does not mistake token probabilities in S1/S3 for benchmark results.",
     "pass", "cc", "S74/S75 qualitative sampling demonstration is distinguished from absent benchmark metrics; no numbers invented."),
]


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def main():
    run_files = {
        "regression_baseline": "evals/runs/iteration02-regression-baseline.jsonl",
        "regression_selected": "evals/runs/iteration02-regression-guarded.jsonl",
        "fresh_baseline": "evals/runs/iteration02-fresh-baseline.jsonl",
        "fresh_selected": "evals/runs/iteration02-fresh-selected.jsonl",
    }
    datasets = ["evals/cases.iteration02-regression.jsonl", "evals/cases.iteration02-fresh.jsonl"]
    cases = {r["case_id"]: r for p in datasets for r in (json.loads(x) for x in (ROOT / p).read_text(encoding="utf-8").splitlines() if x)}
    raw = {name: {r["case_id"]: r for r in (json.loads(x) for x in (ROOT / p).read_text(encoding="utf-8").splitlines() if x)} for name, p in run_files.items()}
    labels = {"c": "covered", "p": "partial", "m": "missing", "u": "unsupported"}
    rows = []
    for case_id, bv, bp, bn, sv, sp, sn in JUDGMENTS:
        partition = "fresh" if case_id.startswith("hy-fresh-") else "regression"
        for setting, verdict, points, notes in [("baseline", bv, bp, bn), ("selected", sv, sp, sn)]:
            assert len(points) == len(cases[case_id]["required_points"])
            observation = raw[f"{partition}_{setting}"][case_id]
            rows.append({"case_id": case_id, "partition": partition, "setting": setting,
                         "verdict": verdict, "point_assessments": [labels[c] for c in points],
                         "raw_model_verdict": "partial" if case_id == "hy-long-03" and setting == "selected" else verdict,
                         "output_guard": observation.get("output_guard"), "notes": notes})
    result = {"reviewed_at": datetime.now(timezone.utc).isoformat(), "reviewer": "Codex AI",
              "human_reviewed": False, "blind_review": False,
              "scope": "AI reviews full fixed automatic captions, frozen points, answers and actual citations; no lecture audio/video frames or student participants",
              "rubric": "evals/iteration02-protocol.json; revised regression cases, historical cases/scores untouched",
              "run_files": run_files, "run_sha256": {name: sha(p) for name, p in run_files.items()},
              "dataset_sha256": {p: sha(p) for p in datasets},
              "display_vs_raw": "Selected development answers replay a lexical display guard over the same 25 preserved v3 raw responses. One answer changes; report the raw-model partial separately. Fresh selected answers were generated with this guard already active.",
              "limitations": ["Caption-only source support is not independent real-world fact or exact API spelling validation",
                              "Some frozen explanatory points still exceed the minimal main question, e.g. lc-course-03 purpose; retain both settings' partial judgments",
                              "One output per model setting/question; same-course fresh questions, AI-authored and nonblind AI-reviewed"],
              "rows": rows}
    assert len(rows) == 62
    with (ROOT / "evals/reviews.iteration02.json").open("x", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("Recorded 62 explicit AI reviews; raw model answer error retained separately")


if __name__ == "__main__":
    main()
