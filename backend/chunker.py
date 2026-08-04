"""
字幕分块模块

原项目 SubtitleExtractor.extract() 返回的 segments 结构为：
    [{"start": 12.5, "end": 15.2, "text": "..."}, ...]
这些片段过于细碎（通常一句一条），直接向量化会丢失语义完整性。
本模块将其合并为约 target_chars 大小的语义块，并保留时间戳用于答案溯源。
"""

from typing import List, Dict


def chunk_segments(
    segments: List[Dict],
    target_chars: int = 400,
    overlap_chars: int = 80,
) -> List[Dict]:
    """
    将细碎字幕片段合并为语义块。

    Args:
        segments: [{"start": float, "end": float, "text": str}, ...]
        target_chars: 目标块大小（字符数）。中文 400 字约为一段完整论述。
        overlap_chars: 相邻块的重叠字符数，防止答案正好落在块边界被切断。

    Returns:
        [{"text": str, "start": float, "end": float}, ...]
    """
    if not segments:
        return []

    if overlap_chars >= target_chars:
        raise ValueError("overlap_chars 必须小于 target_chars")

    chunks: List[Dict] = []
    buf = ""
    buf_start = None

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue

        if buf_start is None:
            buf_start = float(seg["start"])

        buf += text

        if len(buf) >= target_chars:
            chunks.append({
                "text": buf,
                "start": buf_start,
                "end": float(seg["end"]),
            })
            # 保留尾部重叠内容作为下一块的开头
            buf = buf[-overlap_chars:] if overlap_chars > 0 else ""
            # 下一块的起点从当前片段算起（重叠部分时间上归属前一块）
            buf_start = float(seg["start"]) if buf else None

    # 收尾：剩余不足 target_chars 的内容
    if buf.strip():
        chunks.append({
            "text": buf,
            "start": buf_start if buf_start is not None else float(segments[0]["start"]),
            "end": float(segments[-1]["end"]),
        })

    return chunks


def format_timestamp(seconds: float) -> str:
    """把秒数转成 mm:ss 或 hh:mm:ss，用于答案溯源展示"""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
