"""
Embedding 模块

使用 BAAI/bge-small-zh-v1.5：中文效果好、512 维、CPU 也能跑、完全免费。
首次运行会自动下载模型（约 100MB），之后从本地缓存加载。
"""

from functools import lru_cache
from typing import List

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DIMENSION = 512

# bge 系列官方推荐：检索时给「查询」加指令前缀，给「文档」不加
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


@lru_cache(maxsize=1)
def _get_model():
    """懒加载模型，避免导入时就占内存"""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def embed_documents(texts: List[str]) -> List[List[float]]:
    """把文档块转成向量（入库用）"""
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [v.tolist() for v in vecs]


def embed_query(query: str) -> List[float]:
    """把用户问题转成向量（检索用），带 bge 指令前缀"""
    model = _get_model()
    vec = model.encode([QUERY_INSTRUCTION + query], normalize_embeddings=True)[0]
    return vec.tolist()
