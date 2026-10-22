"""Capture a real public long-caption lecture without downloading its media.

Snapshots stay local under ignored evals/data. Refuse to replace an existing
snapshot; a re-fetch is a new observation, not a silent update of test inputs.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from summarizer import SubtitleExtractor

BVID = "BV1pLWFz1Eew"
PAGE = 1
VIDEO_URL = f"https://www.bilibili.com/video/{BVID}/?p={PAGE}"
OFFICIAL_COURSE = "https://speech.ee.ntu.edu.tw/~hylee/GenAI-ML/2025-fall.php"
OFFICIAL_VIDEO = "https://www.youtube.com/watch?v=TigfpYPJk1s"


def main():
    destination = ROOT / f"evals/data/{BVID}/part-001.json"
    if destination.exists():
        raise FileExistsError("Keep the frozen snapshot; use a different location for a new capture")
    response = httpx.get(
        "https://api.bilibili.com/x/web-interface/view", params={"bvid": BVID},
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}, timeout=20,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 0:
        raise ValueError("Public video metadata unavailable")
    view = result["data"]
    part = next(p for p in view["pages"] if p["page"] == PAGE)
    data = SubtitleExtractor()._extract_bilibili(VIDEO_URL)
    if not data["has_subtitle"] or len(data["full_text"]) <= 12000:
        raise ValueError("Source must actually contain more than 12000 caption characters")
    if data["full_text"] != " ".join(s["text"] for s in data["segments"]):
        raise ValueError("Caption text does not match timed segments")
    captured_at = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "url": VIDEO_URL, "bvid": BVID, "page": PAGE,
        "course_title": "Introduction to GenAI and ML 2025 Fall",
        "lecturer": "Hung-yi Lee / 李宏毅", "chapter_title": part["part"],
        "platform_title": view["title"], "platform_uploader": view["owner"]["name"],
        "aid": view["aid"], "cid": part["cid"], "duration_seconds": part["duration"],
        "official_course_url": OFFICIAL_COURSE, "official_video_url": OFFICIAL_VIDEO,
        "caption_source": "Public Bilibili timed captions; mirrored lecture, not the official university upload",
        "provenance_note": "Course and original video identified through the university course page; exact audio alignment between uploads not verified",
        "captured_at": captured_at, **data,
    }
    raw = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(raw)
    # Hash bytes as actually written, avoiding platform newline conversion.
    manifest = {
        "captured_at": captured_at, "video_url": VIDEO_URL,
        "subtitle_snapshot": destination.relative_to(ROOT).as_posix(),
        "subtitle_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "subtitle_chars": len(data["full_text"]), "segments": len(data["segments"]),
        "duration_seconds": part["duration"], "official_course_url": OFFICIAL_COURSE,
        "official_video_url": OFFICIAL_VIDEO, "human_reviewed": False,
    }
    with (destination.parent / "manifest.json").open("x", encoding="utf-8") as output:
        json.dump(manifest, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
