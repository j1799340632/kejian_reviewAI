"""
Milvus 向量库封装

设计说明：
- 所有视频共用一个 collection，用 video_id 字段区分，检索时过滤。
  （不要每个视频建一个 collection —— Milvus 的 collection 有数量上限，
   而且频繁建删会拖慢加载速度，这是新手最常踩的坑。）
- 使用 MilvusClient 简化接口，不用旧版的 Collection/connections API。
"""

import os
from typing import List, Dict, Optional

from pymilvus import MilvusClient, DataType

from embedder import DIMENSION, embed_documents, embed_query

MILVUS_ENDPOINT = os.getenv("MILVUS_ENDPOINT", "http://localhost:19530")
COLLECTION = os.getenv("MILVUS_COLLECTION", "video_subtitles")

_client: Optional[MilvusClient] = None


def get_client() -> MilvusClient:
    """获取 Milvus 客户端（单例）"""
    global _client
    if _client is None:
        _client = MilvusClient(uri=MILVUS_ENDPOINT)
    return _client


def init_collection(drop_existing: bool = False) -> None:
    """
    初始化 collection。服务启动时调用一次。

    字段设计：
        id        自增主键
        video_id  视频标识，检索时按它过滤
        text      字幕块原文
        start/end 时间戳，用于答案溯源
        vector    512 维稠密向量
    """
    client = get_client()

    if drop_existing and client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)

    if client.has_collection(COLLECTION):
        return

    schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("video_id", DataType.VARCHAR, max_length=128)
    schema.add_field("text", DataType.VARCHAR, max_length=4096)
    schema.add_field("start", DataType.FLOAT)
    schema.add_field("end", DataType.FLOAT)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=DIMENSION)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="HNSW",          # 中小规模数据下召回率和速度的平衡点
        metric_type="COSINE",       # 向量已归一化，用余弦相似度
        params={"M": 16, "efConstruction": 200},
    )

    client.create_collection(
        collection_name=COLLECTION,
        schema=schema,
        index_params=index_params,
    )


def is_indexed(video_id: str) -> bool:
    """检查某个视频是否已入库，避免重复向量化"""
    client = get_client()
    if not client.has_collection(COLLECTION):
        return False
    rows = client.query(
        collection_name=COLLECTION,
        filter=f'video_id == "{video_id}"',
        output_fields=["id"],
        limit=1,
    )
    return len(rows) > 0


def index_video(video_id: str, chunks: List[Dict], force: bool = False) -> int:
    """
    把分块后的字幕写入 Milvus。

    Returns: 实际写入的块数（若已存在且 force=False 则返回 0）
    """
    if not chunks:
        return 0

    client = get_client()
    init_collection()

    if is_indexed(video_id):
        if not force:
            return 0
        delete_video(video_id)

    vectors = embed_documents([c["text"] for c in chunks])

    rows = [
        {
            "video_id": video_id,
            "text": c["text"][:4096],
            "start": float(c["start"]),
            "end": float(c["end"]),
            "vector": vectors[i],
        }
        for i, c in enumerate(chunks)
    ]

    client.insert(collection_name=COLLECTION, data=rows)
    # Milvus 写入后需要 flush 才能被检索到（新手常见坑：插入完立刻查询返回空）
    client.flush(COLLECTION)
    return len(rows)


def delete_video(video_id: str) -> None:
    """删除某个视频的所有向量"""
    client = get_client()
    if client.has_collection(COLLECTION):
        client.delete(
            collection_name=COLLECTION,
            filter=f'video_id == "{video_id}"',
        )


def search(video_id: str, query: str, top_k: int = 5) -> List[Dict]:
    """
    向量检索，返回该视频下最相关的字幕块。

    Returns: [{"text", "start", "end", "score"}, ...] 按相关性降序
    """
    client = get_client()
    qv = embed_query(query)

    results = client.search(
        collection_name=COLLECTION,
        data=[qv],
        filter=f'video_id == "{video_id}"',
        limit=top_k,
        output_fields=["text", "start", "end"],
        search_params={"metric_type": "COSINE", "params": {"ef": 64}},
    )

    hits = []
    for hit in results[0]:
        entity = hit.get("entity", {})
        hits.append({
            "text": entity.get("text", ""),
            "start": entity.get("start", 0.0),
            "end": entity.get("end", 0.0),
            "score": hit.get("distance", 0.0),
        })
    return hits


def get_all_chunks(video_id: str) -> List[Dict]:
    """取出某视频全部块，供 BM25 检索使用"""
    client = get_client()
    if not client.has_collection(COLLECTION):
        return []
    rows = client.query(
        collection_name=COLLECTION,
        filter=f'video_id == "{video_id}"',
        output_fields=["text", "start", "end"],
        limit=16384,
    )
    return [{"text": r["text"], "start": r["start"], "end": r["end"]} for r in rows]
