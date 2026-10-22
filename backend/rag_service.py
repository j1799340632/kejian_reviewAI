"""Connect the existing subtitle index and hybrid retriever to web questions."""

import hashlib
from threading import Lock
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from chunker import chunk_segments
from context_policy import select_context, format_sources

_index_lock = Lock()


def make_video_id(url: str) -> str:
    """Keep the identifier compatible with demo_rag.py and existing indexes."""
    return hashlib.md5(url.strip().encode()).hexdigest()[:16]


def ensure_video_index(url: str, extractor) -> str:
    """Reuse an index, or extract and index subtitles once in this process."""
    import retriever
    import vector_store

    video_id = make_video_id(url)
    # Avoid duplicate extraction/insertion for simultaneous first questions.
    # This process-local lock is sufficient for the current single-worker app.
    with _index_lock:
        vector_store.init_collection()
        if vector_store.is_indexed(video_id):
            return video_id

        data = extractor.extract(url)
        chunks = chunk_segments(data.get("segments") or [])
        if not data.get("has_subtitle") or not chunks:
            raise ValueError("该视频没有可用字幕，暂时无法根据视频回答问题。")

        vector_store.index_video(video_id, chunks)
        retriever.clear_bm25_cache()
    return video_id


def source_url(url: str, seconds: float) -> str | None:
    """Provide timestamp links only for platforms whose seek URLs we support."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    supported = any(
        host == domain or host.endswith("." + domain)
        for domain in ("bilibili.com", "youtube.com", "youtu.be")
    )
    if parsed.scheme not in ("http", "https") or not supported:
        return None
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["t"] = str(max(0, int(seconds)))
    query.pop("start", None)
    return urlunsplit(parsed._replace(query=urlencode(query), fragment=""))


def retrieve_sources(video_id: str, question: str, url: str = "") -> list[dict]:
    """Use complete indexed context within the budget, RAG beyond it."""
    import retriever
    import vector_store

    if not vector_store.is_indexed(video_id):
        raise ValueError("该视频的问答索引尚未就绪，请重新选择视频后提问。")
    hits, _ = select_context(video_id, question, "bounded_full", vector_store, retriever)
    return format_sources(hits, url)
