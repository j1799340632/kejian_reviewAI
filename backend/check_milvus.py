"""
Milvus 连通性自检脚本

用途：在写业务代码之前，先确认 Milvus 真的能读能写。
运行：python check_milvus.py

每一步失败时都会给出具体的排查建议，不要跳过这个脚本直接写业务代码——
新手 90% 的时间浪费在「以为 Milvus 好了其实没好」上。
"""

import sys
import os
import time

ENDPOINT = os.getenv("MILVUS_ENDPOINT", "http://localhost:19530")
TEST_COLLECTION = "healthcheck_demo"
DIM = 8


def fail(step: str, err: Exception, hints: list):
    print(f"\n  [X] {step} 失败")
    print(f"      错误：{type(err).__name__}: {err}")
    print("\n      排查建议：")
    for h in hints:
        print(f"        - {h}")
    sys.exit(1)


def main():
    print("=" * 56)
    print(f"Milvus 自检   目标地址：{ENDPOINT}")
    print("=" * 56)

    # ---------- 1. 导入客户端 ----------
    try:
        from pymilvus import MilvusClient, DataType
        import pymilvus
        print(f"\n  [1/6] pymilvus 已安装，版本 {pymilvus.__version__}")
    except ImportError as e:
        fail("导入 pymilvus", e, [
            "执行 pip install 'pymilvus>=2.6,<3'",
            "确认用的是项目虚拟环境的 pip，不是系统 pip",
        ])

    # ---------- 2. 建立连接 ----------
    try:
        client = MilvusClient(uri=ENDPOINT)
        client.list_collections()
        print("  [2/6] 连接成功")
    except Exception as e:
        fail("连接 Milvus", e, [
            "确认容器在跑：docker compose -f docker-compose.milvus.yml ps",
            "standalone 容器状态必须是 Up (healthy)，Up (starting) 说明还在启动，等 1-2 分钟",
            "看日志：docker compose -f docker-compose.milvus.yml logs --tail 50 standalone",
            "端口被占用：lsof -i:19530（macOS/Linux）或 netstat -ano | findstr 19530（Windows）",
            "注意不要设置名为 MILVUS_URI 的环境变量，它会和 pymilvus 内部配置冲突",
        ])

    # ---------- 3. 建集合 ----------
    try:
        if client.has_collection(TEST_COLLECTION):
            client.drop_collection(TEST_COLLECTION)

        schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("text", DataType.VARCHAR, max_length=512)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=DIM)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 200},
        )
        client.create_collection(
            collection_name=TEST_COLLECTION,
            schema=schema,
            index_params=index_params,
        )
        print("  [3/6] 创建 collection 成功")
    except Exception as e:
        fail("创建 collection", e, [
            "Milvus 可能还没完全就绪，等 30 秒重试",
            "磁盘空间不足也会导致建集合失败，检查 df -h",
        ])

    # ---------- 4. 写入 ----------
    try:
        rows = [
            {"text": f"测试文本 {i}", "vector": [float((i + j) % 5) / 5 for j in range(DIM)]}
            for i in range(10)
        ]
        client.insert(collection_name=TEST_COLLECTION, data=rows)
        client.flush(TEST_COLLECTION)
        print("  [4/6] 写入 10 条数据成功")
    except Exception as e:
        fail("写入数据", e, [
            "检查 vector 维度是否和建表时的 dim 一致",
            "VARCHAR 字段超过 max_length 会报错，注意截断",
        ])

    # ---------- 5. 检索 ----------
    try:
        t0 = time.time()
        res = client.search(
            collection_name=TEST_COLLECTION,
            data=[[0.2, 0.4, 0.6, 0.8, 0.0, 0.2, 0.4, 0.6]],
            limit=3,
            output_fields=["text"],
            search_params={"metric_type": "COSINE", "params": {"ef": 64}},
        )
        cost = (time.time() - t0) * 1000
        hits = res[0]
        if not hits:
            raise RuntimeError("检索返回空结果")
        print(f"  [5/6] 检索成功，耗时 {cost:.1f}ms，Top-3：")
        for h in hits:
            print(f"          score={h['distance']:.4f}  {h['entity']['text']}")
    except Exception as e:
        fail("检索", e, [
            "写入后没有 flush 会查不到数据，确认调用了 client.flush()",
            "确认建 collection 时创建了索引，没索引无法检索",
        ])

    # ---------- 6. 清理 ----------
    try:
        client.drop_collection(TEST_COLLECTION)
        print("  [6/6] 清理测试数据成功")
    except Exception as e:
        print(f"  [!] 清理失败（不影响使用）：{e}")

    print("\n" + "=" * 56)
    print("  全部通过，Milvus 可以正常使用")
    print("  可视化界面：http://localhost:8000")
    print("=" * 56)


if __name__ == "__main__":
    main()
