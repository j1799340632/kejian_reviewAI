"""
端到端示例：真实视频 → 字幕提取 → 分块 → 入库 → 混合检索

运行前提：
    1. Milvus 已启动（先跑通 check_milvus.py）
    2. 本文件放在原项目 backend/ 目录下（需要 import 原项目的 summarizer）

运行：
    python demo_rag.py "https://www.bilibili.com/video/BVxxxxxxx" "你的问题"
"""

import sys
import hashlib

from chunker import chunk_segments, format_timestamp
import vector_store
import retriever


def make_video_id(url: str) -> str:
    """用 URL 的哈希做视频唯一标识，避免不同平台 ID 格式不统一"""
    return hashlib.md5(url.encode()).hexdigest()[:16]


def build_index(url: str, force: bool = False) -> str:
    """提取字幕 → 分块 → 入库，返回 video_id"""
    video_id = make_video_id(url)

    if vector_store.is_indexed(video_id) and not force:
        print(f"[跳过] 该视频已入库（video_id={video_id}）")
        return video_id

    print("[1/3] 提取字幕中...")
    from summarizer import SubtitleExtractor   # 原项目模块
    extractor = SubtitleExtractor()
    data = extractor.extract(url)

    if not data["has_subtitle"]:
        raise RuntimeError("该视频没有可用字幕，换一个有字幕的视频试试")

    segments = data["segments"]
    total_chars = len(data["full_text"])
    print(f"      字幕片段 {len(segments)} 条，共 {total_chars} 字，"
          f"类型 {data['subtitle_type']}，语言 {data['language']}")

    if total_chars > 15000:
        lost = (1 - 15000 / total_chars) * 100
        print(f"      注意：原方案截断到 15000 字，将丢失约 {lost:.0f}% 的内容")

    print("[2/3] 分块中...")
    chunks = chunk_segments(segments, target_chars=400, overlap_chars=80)
    print(f"      生成 {len(chunks)} 个语义块，"
          f"平均 {sum(len(c['text']) for c in chunks) // len(chunks)} 字")

    print("[3/3] 向量化入库中（首次会下载 embedding 模型，约 100MB）...")
    n = vector_store.index_video(video_id, chunks, force=force)
    retriever.clear_bm25_cache()
    print(f"      写入 {n} 条，video_id={video_id}")

    return video_id


def ask(video_id: str, question: str, top_k: int = 3):
    """检索并展示结果"""
    hits = retriever.hybrid_search(video_id, question, top_k=top_k)

    if not hits:
        print("没有检索到相关内容")
        return

    print(f"\n检索结果（问题：{question}）")
    print("-" * 56)
    for i, h in enumerate(hits, 1):
        ts = format_timestamp(h["start"])
        print(f"{i}. [{ts}] rrf={h['rrf_score']:.4f}")
        print(f"   {h['text'][:120]}...")
        print()

    # 拼装成给大模型的 Prompt（替换原项目的 _build_chat_prompt）
    context = "\n\n".join(
        f"[{format_timestamp(h['start'])}] {h['text']}" for h in hits
    )
    prompt = f"""根据以下视频片段回答问题，并在答案中标注信息来源的时间点。
如果片段中没有相关信息，请明确回答"视频中未提及"，不要编造。

视频片段：
{context}

问题：{question}"""

    print("-" * 56)
    print(f"生成的 Prompt 长度：{len(prompt)} 字")
    print("（对比：原方案会塞入 12000 字的字幕全文）")
    return prompt


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    url, question = sys.argv[1], sys.argv[2]
    vector_store.init_collection()
    vid = build_index(url)
    ask(vid, question)
