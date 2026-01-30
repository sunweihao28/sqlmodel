# RAG 文档问答服务 - 前端开发人员使用说明

> 本说明基于当前 `rag_service.py`（Text-to-SQL 版本）。该模块使用 DashScope Embedding、Chroma 向量库和 BM25 混合检索，使用 RRF（Reciprocal Rank Fusion）进行排序。

## 1. 环境准备

### 1.1 安装依赖
```bash
pip install langchain langchain-community langchain-text-splitters chromadb openai python-dotenv pypdf docx2txt rank_bm25
```


### 1.2 配置环境变量
在项目根目录下（或 `rag/`）创建 `.env` 文件，添加：
```
DASHSCOPE_API_KEY='sk-29e724dbecc44ac39f8932e356d4ea16'
```

模块会使用 `DASHSCOPE_API_KEY` 调用 DashScope 的 `text-embedding-v2` 进行向量化。

### 1.3 准备文档
将需要索引的文档放到 `knowledge_base/docs/` 目录下。
支持格式：TXT / PDF / Word (.docx) / Markdown (.md)

---

## 2. 快速开始

### 2.1 推荐：使用 `RAGService`（Text-to-SQL 场景）
```python
from rag_service import RAGService
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# 创建 LLM 调用函数（示例：使用 DashScope qwen-turbo）
client = OpenAI(api_key=os.getenv('DASHSCOPE_API_KEY'), base_url='https://dashscope.aliyuncs.com/compatible-mode/v1')
def llm_call(prompt: str) -> str:
    resp = client.chat.completions.create(model='qwen-turbo', messages=[{'role':'user','content':prompt}], temperature=0)
    return resp.choices[0].message.content

# 初始化服务（建议在服务启动时调用）
rag = RAGService(llm=llm_call, force_rebuild=False)

# 生成 SQL（Text-to-SQL 接口）
sql = rag.ask_sql('查询计算机系的课程')
print(sql)
```

说明：当前模块以 Text-to-SQL 为主，因此提供 `ask_sql(query: str) -> str`，返回可执行的 SQL（或错误/提示字符串）。

---

## 3. 主要 API 说明（简要）

### 构造函数参数（常用）
- `docs_path: str`：文档目录，默认 `knowledge_base/docs`
- `persist_dir: str`：Chroma 向量库持久化目录，默认 `chroma_db_rag_text2sql`
- `embedding_model_name: str`：保留参数（当前实现使用 DashScope Embedding）
- `chunk_size: int`：切块大小，默认 2000
- `chunk_overlap: int`：切块重叠，默认 100
- `top_k: int`：检索返回数，默认 4
- `force_rebuild: bool`：是否强制重建索引
- `use_rewrite: bool`：查询重写（默认关闭）
- `language: str`：文档语言（默认 `en`）
- `llm`：必须提供的 callable，用于把 prompt 发送给 LLM 并返回字符串结果（示例见上文）

### 重要方法
- `initialize()`：构建或加载向量索引与 BM25 索引（首次运行或 `force_rebuild=True` 时会构建索引）
- `ask_sql(query: str) -> str`：将自然语言问题转换为可执行 SQL（SQLite 语法）；如果无法生成会返回类似 `SELECT '无法生成SQL';` 的提示
- `add_document_from_file(file_path: str, doc_id: str = None) -> str`：动态添加单个文件到向量库并返回生成的 `doc_id`
- `remove_document(doc_id: str) -> bool`：删除指定 `doc_id` 的所有 chunk（向量库 + BM25）
- `rebuild_index() -> bool`：强制重建索引
- `get_indexed_files() -> List[str]`：返回已索引文件路径列表
- `sync_with_local_files() -> bool`：同步本地文件变更，删除已移除文件的向量


---

## 4. 前端 / 服务端集成示例

### 4.1 FastAPI（Text-to-SQL 接口）
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rag_service import RAGService
import os
from dotenv import load_dotenv

load_dotenv()
client = ... # 与上文相同的 LLM client
rag = RAGService(llm=lambda p: client.chat.completions.create(model='qwen-turbo', messages=[{'role':'user','content':p}], temperature=0).choices[0].message.content)

app = FastAPI()

@app.on_event('startup')
def startup():
    rag.initialize()

class Q(BaseModel):
    question: str

@app.post('/api/rag/ask_sql')
def ask_sql(q: Q):
    try:
        sql = rag.ask_sql(q.question)
        return {'success': True, 'sql': sql}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/rag/rebuild')
def rebuild():
    return {'success': rag.rebuild_index()}

@app.post('/api/rag/add')
def add(doc: dict):
    # doc should contain file_path and optional doc_id
    doc_id = rag.add_document_from_file(doc['file_path'], doc.get('doc_id'))
    return {'doc_id': doc_id}

@app.post('/api/rag/remove')
def remove(doc: dict):
    return {'removed': rag.remove_document(doc['doc_id'])}
```

前端只需调用 `/api/rag/ask_sql` 获取 SQL，再在后端执行或展示。

---

## 5. 实现细节 & 注意事项

- Embedding：当前使用 DashScope 的 `text-embedding-v2`（通过 `DASHSCOPE_API_KEY` 调用）。无需本地 HuggingFace 模型下载。
- 排序：移除了专用 reranker 模型，检索过程中采用向量检索 + BM25 检索并用 RRF 融合排名，轻量且无需额外模型。
- LLM：`ask_sql` 依赖你传入的 `llm` callable，模块不会直接调用具体 SDK（示例中使用 `openai.OpenAI` 兼容客户端调用 qwen-turbo）。
- 索引目录：默认持久化在 `chroma_db_rag_text2sql`，可以通过 `persist_dir` 参数修改。

---

## 6. 目录结构（示意）
```
rag/
├── .env
├── rag_service.py
├── RAG_使用说明.md
├── rag_optimization_notebook.ipynb
├── knowledge_base/
│   └── docs/
└── chroma_db_rag_text2sql/   # 向量数据库（默认）
```

---

