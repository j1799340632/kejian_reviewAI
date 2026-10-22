"""AI 视频总结相关 API 路由（独立模块，通过 include_router 挂载）"""

import asyncio
import json
import logging
from collections.abc import AsyncIterable
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import iterate_in_threadpool

router = APIRouter(prefix="/api", tags=["AI 总结"])
logger = logging.getLogger(__name__)


class SummarizeRequest(BaseModel):
    url: str
    language: str = "zh"


class ChatRequest(BaseModel):
    url: str = ""
    video_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{16}$")
    question: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_question(self):
        self.question = self.question.strip()
        self.url = self.url.strip()
        if not self.question:
            raise ValueError("请输入问题")
        if not self.url and not self.video_id:
            raise ValueError("请提供视频链接或 video_id")
        if self.url:
            parsed = urlsplit(self.url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("请提供有效的视频链接")
        return self


def _get_rag_service():
    import rag_service
    return rag_service


def _get_summarizer():
    """延迟初始化 VideoSummarizer（仅在首次调用时创建）"""
    from summarizer import VideoSummarizer
    if not hasattr(_get_summarizer, "_instance"):
        try:
            _get_summarizer._instance = VideoSummarizer()
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
    return _get_summarizer._instance


def _get_extractor():
    """延迟初始化 SubtitleExtractor"""
    from summarizer import SubtitleExtractor
    if not hasattr(_get_extractor, "_instance"):
        _get_extractor._instance = SubtitleExtractor()
    return _get_extractor._instance


@router.post("/summarize", response_class=EventSourceResponse)
async def summarize_video(req: SummarizeRequest) -> AsyncIterable[ServerSentEvent]:
    """
    AI 视频总结（SSE 流式）
    事件类型: subtitle / summary_scope / summary / mindmap / done / error
    """
    try:
        loop = asyncio.get_event_loop()
        extractor = _get_extractor()
        subtitle_data = await loop.run_in_executor(
            None, extractor.extract, req.url
        )

        yield ServerSentEvent(
            raw_data=json.dumps(subtitle_data, ensure_ascii=False),
            event="subtitle",
        )

        if not subtitle_data["has_subtitle"]:
            yield ServerSentEvent(
                raw_data=json.dumps({"message": "该视频没有可用的字幕，无法生成总结"}, ensure_ascii=False),
                event="error",
            )
            return

        full_text = subtitle_data["full_text"]
        yield ServerSentEvent(data={
            "partial": len(full_text) > 15000,
            "processed_chars": min(len(full_text), 15000),
            "total_chars": len(full_text),
        }, event="summary_scope")
        summarizer = _get_summarizer()

        for token in summarizer.summarize_stream(full_text, req.language):
            yield ServerSentEvent(raw_data=json.dumps(token, ensure_ascii=False), event="summary")

        mindmap_md = await loop.run_in_executor(
            None, summarizer.generate_mindmap, full_text, req.language
        )
        yield ServerSentEvent(
            raw_data=json.dumps({"markdown": mindmap_md}, ensure_ascii=False),
            event="mindmap",
        )

        yield ServerSentEvent(raw_data="[DONE]", event="done")

    except Exception:
        logger.exception("Video summary failed")
        yield ServerSentEvent(
            data={"message": "暂时无法生成摘要，请稍后重试。"},
            event="error",
        )


@router.post("/subtitles")
async def video_subtitles(req: SummarizeRequest):
    """Read captions independently; opening this tab never calls the model."""
    try:
        return await asyncio.to_thread(_get_extractor().extract, req.url)
    except Exception:
        logger.exception("Video subtitle extraction failed")
        raise HTTPException(status_code=502, detail="暂时无法读取字幕，请稍后重试。")


@router.post("/chat", response_class=EventSourceResponse)
async def chat_with_video(req: ChatRequest) -> AsyncIterable[ServerSentEvent]:
    """Index/reuse subtitles, retrieve sources, then stream a grounded answer."""
    try:
        rag = _get_rag_service()
        if req.video_id:
            video_id = req.video_id
            if req.url and rag.make_video_id(req.url) != video_id:
                raise ValueError("视频已发生变化，请重新选择视频后提问。")
        else:
            yield ServerSentEvent(data={"message": "正在准备视频问答，首次提问可能需要一些时间…"}, event="status")
            video_id = await asyncio.to_thread(
                rag.ensure_video_index, req.url, _get_extractor()
            )

        yield ServerSentEvent(data={"video_id": video_id}, event="video")
        yield ServerSentEvent(data={"message": "正在整理视频依据…"}, event="status")
        sources = await asyncio.to_thread(
            rag.retrieve_sources, video_id, req.question, req.url
        )
        yield ServerSentEvent(data={"sources": sources}, event="sources")

        if not sources:
            yield ServerSentEvent(data="未检索到可用的视频片段，暂时无法根据视频回答。请尝试更具体的问题。", event="answer")
            yield ServerSentEvent(raw_data="[DONE]", event="done")
            return

        summarizer = _get_summarizer()
        async for token in iterate_in_threadpool(
            summarizer.chat_with_sources_stream(sources, req.question)
        ):
            yield ServerSentEvent(raw_data=json.dumps(token, ensure_ascii=False), event="answer")

        yield ServerSentEvent(raw_data="[DONE]", event="done")

    except ValueError as e:
        yield ServerSentEvent(
            data={"message": str(e)},
            event="error",
        )
    except Exception:
        logger.exception("Video question failed")
        yield ServerSentEvent(data={"message": "视频问答暂时不可用，请稍后重试。"}, event="error")
