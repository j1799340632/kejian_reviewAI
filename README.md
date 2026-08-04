# AI 视频内容问答助手

输入一个视频链接，自动提取字幕，用 AI 生成总结、思维导图，并支持基于视频内容的多轮问答。

答案会标注信息来源的时间点，可以直接跳回视频原处验证。


---

## 功能

- **多平台视频解析下载** —— 基于 yt-dlp，支持 B 站、YouTube 等主流平台，可选清晰度
- **AI 内容总结** —— 提取字幕后调用大模型生成结构化摘要，流式输出
- **思维导图** —— 自动生成层级结构，支持缩放和导出图片
- **视频问答** —— 基于 RAG 检索的问答，答案带时间戳溯源
- **字幕导出** —— 支持 SRT / VTT / TXT 格式
- **用户系统** —— 邮箱注册登录，JWT 鉴权，每日使用次数限额

---

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite + Tailwind CSS |
| 后端 | FastAPI + SQLite |
| 视频解析 | yt-dlp |
| 大模型 | DeepSeek |
| 向量检索 | Milvus + bge-small-zh + BM25 |

---

## 核心设计：为什么要做 RAG

最初的实现把字幕全文截断到 15000 字符后塞进 Prompt：

```python
truncated = subtitle_text[:15000]
prompt = f"请总结以下内容...{truncated}"
```

一个 40 分钟以上的视频，字幕通常有 4~6 万字，**这意味着后面 60%~70% 的内容根本进不了模型的上下文**。用户问的问题只要答案在视频后半段，模型就只能编。

改造后的链路：

```
字幕 segments（带时间戳）
   └→ 滑动窗口分块（400 字，80 字重叠）
        └→ bge 向量化 → 存入 Milvus
                            ↓
用户提问 → 向量检索 + BM25 关键词检索 → RRF 融合 → Top-K 片段 → LLM 生成
```

几个具体的设计取舍：

- **混合检索**：纯向量检索对专有名词不敏感，BM25 能补上。
- **RRF 融合而非加权求和**：余弦相似度和 BM25 分数量纲不同，加权需要反复调参且换个视频就失效；RRF 只用排名，无需调参。
- **所有视频共用一个 collection**：用 `video_id` 字段过滤，而不是每个视频建一个 collection —— Milvus 的 collection 有数量上限，频繁建删会拖慢加载。


---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Docker（运行 Milvus 用）
- 一个 [DeepSeek API Key](https://platform.deepseek.com)

### 1. 后端

```bash
cd backend

pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY 

python main.py
```

启动后访问 <http://localhost:8000/docs> 可看接口文档。

### 2. 前端

新开一个终端：

```bash
cd frontend
npm install
npm run dev
```

访问 <http://localhost:5173>

### 3. Milvus（问答功能需要）

```bash
docker compose -f docker-compose.milvus.yml up -d
```

```bash
docker compose -f docker-compose.milvus.yml ps
```

然后自检：

```bash
cd backend
python check_milvus.py
```

可视化界面在 <http://localhost:8000>。



---

## 项目结构

```
.
├── backend/
│   ├── main.py              FastAPI 入口，视频解析下载接口
│   ├── downloader.py        yt-dlp 封装
│   ├── douyin.py            抖音专用解析
│   ├── summarizer.py        字幕提取 + 大模型调用
│   ├── api_summarize.py     总结 / 问答接口（SSE 流式）
│   ├── api_auth.py          注册登录接口
│   ├── auth.py              JWT 与密码哈希
│   ├── database.py          SQLite 数据层
│   │
│   ├── chunker.py           字幕分块（保留时间戳）
│   ├── embedder.py          bge 向量化
│   ├── vector_store.py      Milvus 读写
│   ├── retriever.py         混合检索 + RRF 融合
│   ├── check_milvus.py      环境自检脚本
│   └── demo_rag.py          端到端演示
│
├── frontend/
│   └── src/
│       ├── App.vue
│       ├── components/      页面组件
│       └── api/             接口封装
│
└── docker-compose.milvus.yml
```

---


## 待办

- [ ] 多轮对话记忆与上下文裁剪
- [ ] 思维导图输出的结构化校验与重试
- [ ] 引入 LangGraph 编排，支持工具调用

---

## 说明

本项目基础功能参考了 [程序员鱼皮](https://www.codefather.cn) 的开源教学项目，在其之上重构了问答链路（RAG 检索、混合排序、答案溯源）。

仅用于技术学习和研究，请只下载你拥有版权或已获授权的内容，遵守所在地区法律法规及各平台服务条款。