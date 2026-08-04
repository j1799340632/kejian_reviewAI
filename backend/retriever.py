"""
混合检索模块：向量检索 + BM25 关键词检索，用 RRF 融合

为什么需要 BM25？
    纯向量检索对专有名词不敏感。比如问「视频里提到的 SseEmitter 怎么用」，
    向量模型可能把 SseEmitter 泛化成「流式输出」，检索到讲流式概念但没提这个
    类名的片段。BM25 是精确词匹配，能补上这个短板。

为什么用 RRF 而不是加权求和？
    向量的余弦相似度（0~1）和 BM25 分数（无上界）量纲完全不同，直接加权需要
    反复调参且换个视频就失效。RRF 只用排名不用分数，无需调参，工程上更稳。
"""

from typing import List, Dict
from functools import lru_cache

import jieba
from rank_bm25 import BM25Okapi

import vector_store

RRF_K = 60  # RRF 平滑常数，官方论文推荐值，作用是抑制头部排名的权重过大


@lru_cache(maxsize=32)
def _get_bm25(video_id: str):
    """
    构建某视频的 BM25 索引并缓存。
    注意：这里用 lru_cache 缓存，视频重新入库后需要调用 clear_bm25_cache()
    """
    chunks = vector_store.get_all_chunks(video_id)
    if not chunks:
        return None, []
    corpus = [list(jieba.cut(c["text"])) for c in chunks]
    return BM25Okapi(corpus), chunks


def clear_bm25_cache():
    """视频重新入库后调用，避免读到旧索引"""
    _get_bm25.cache_clear()


def _chunk_key(c: Dict) -> str:
    """用时间戳做去重键，同一个块在两路检索中要能对上"""
    return f"{c['start']:.2f}_{c['end']:.2f}"


def hybrid_search(
    video_id: str,
    query: str,
    top_k: int = 3,
    candidate_k: int = 10,
) -> List[Dict]:
    """
    混合检索。

    Args:
        top_k: 最终返回的块数
        candidate_k: 每路召回的候选数，通常取 top_k 的 3 倍左右

    Returns: [{"text", "start", "end", "rrf_score"}, ...]
    """
    pool: Dict[str, Dict] = {}
    scores: Dict[str, float] = {}

    # ---- 第 1 路：向量检索 ----
    vec_hits = vector_store.search(video_id, query, top_k=candidate_k)
    for rank, hit in enumerate(vec_hits):
        key = _chunk_key(hit)
        pool[key] = hit
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)

    # ---- 第 2 路：BM25 关键词检索 ----
    bm25, chunks = _get_bm25(video_id)
    if bm25 is not None:
        tokens = list(jieba.cut(query))
        bm25_scores = bm25.get_scores(tokens)
        ranked_idx = sorted(
            range(len(bm25_scores)),
            key=lambda i: bm25_scores[i],
            reverse=True,
        )[:candidate_k]
        for rank, idx in enumerate(ranked_idx):
            if bm25_scores[idx] <= 0:
                continue
            chunk = chunks[idx]
            key = _chunk_key(chunk)
            pool.setdefault(key, chunk)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)

    # ---- 融合排序 ----
    top_keys = sorted(scores, key=lambda k: scores[k], reverse=True)[:top_k]
    return [{**pool[k], "rrf_score": scores[k]} for k in top_keys]


def vector_only_search(video_id: str, query: str, top_k: int = 3) -> List[Dict]:
    """纯向量检索，作为对照实验的基线之一"""
    return vector_store.search(video_id, query, top_k=top_k)
