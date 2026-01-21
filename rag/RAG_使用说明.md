# RAG 文档问答服务 - 前端开发人员使用说明

## 1. 环境准备

### 1.1 安装依赖
```bash
pip install langchain langchain-community langchain-text-splitters chromadb openai python-dotenv pypdf docx2txt
```

### 1.2 配置环境变量
在 `rag/` 目录下创建 `.env` 文件：
```
DASHSCOPE_API_KEY=your-api-key-here
DASHSCOPE_API_KEY='sk-29e724dbecc44ac39f8932e356d4ea16'
```

### 1.3 准备文档
将需要索引的文档放到 `knowledge_base/docs/` 目录下。
支持格式：**TXT / PDF / Word (.docx) / Markdown (.md)**

---

## 2. 快速开始

### 2.1 最简单的使用方式
```python
from rag_service import rag_ask

# 直接提问
answer = rag_ask("student 表有哪些字段？")
print(answer)
```

### 2.2 使用服务类（推荐）
```python
from rag_service import RAGService

# 初始化
rag = RAGService()
rag.initialize()

# 提问
answer = rag.ask("instructor 和 department 有什么关系？")
print(answer)
```

---

## 3. API 接口说明

### 3.1 RAGService 类

#### 初始化参数
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `docs_path` | str | "knowledge_base/docs" | 文档目录路径 |
| `persist_dir` | str | "chroma_db_rag" | 向量数据库目录 |
| `llm_model` | str | "qwen-turbo" | LLM 模型 |
| `chunk_size` | int | 256 | 文档切片大小 |
| `chunk_overlap` | int | 30 | 切片重叠大小 |
| `top_k` | int | 5 | 检索返回数量 |
| `force_rebuild` | bool | False | 强制重建索引 |

#### 主要方法

**`initialize() -> Dict`**
初始化所有组件，返回各组件状态。

**`ask(question: str) -> str`**
提问并返回答案。

**`ask_with_sources(question: str) -> Dict`**
提问并返回答案及来源信息。
```python
result = rag.ask_with_sources("student 表有哪些字段？")
# 返回: {"answer": "...", "sources": [{"id": 1, "source": "...", "content": "..."}]}
```

**`rebuild_index() -> bool`**
重建向量索引（添加新文档后调用）。

**`get_indexed_files() -> List[str]`**
获取已索引的文件列表。

**`health_check() -> Dict`**
健康检查，返回各组件状态。

---

## 4. 前端集成示例

### 4.1 FastAPI 接口封装
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rag_service import RAGService

app = FastAPI()
rag = RAGService()

@app.on_event("startup")
async def startup():
    rag.initialize()

class Question(BaseModel):
    question: str

@app.post("/api/rag/ask")
async def ask(q: Question):
    try:
        result = rag.ask_with_sources(q.question)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/rag/health")
async def health():
    return rag.health_check()

@app.post("/api/rag/rebuild")
async def rebuild():
    success = rag.rebuild_index()
    return {"success": success}
```

### 4.2 前端调用示例 (JavaScript)
```javascript
// 提问
async function askRAG(question) {
    const response = await fetch('/api/rag/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question })
    });
    const data = await response.json();
    return data.data;
}

// 使用
const result = await askRAG('student 表有哪些字段？');
console.log(result.answer);
console.log(result.sources);
```

---

## 5. 注意事项

### 5.1 首次使用
1. 确保 `DASHSCOPE_API_KEY` 环境变量已设置
2. 确保 `knowledge_base/docs/` 目录下有文档文件
3. 首次运行会自动创建向量数据库

### 5.2 添加新文档
```python
# 添加文档后，调用重建索引
rag.rebuild_index()
```

### 5.3 错误处理
```python
try:
    answer = rag.ask("问题")
except ValueError as e:
    print(f"配置错误: {e}")  # 如 API Key 未设置
except RuntimeError as e:
    print(f"运行时错误: {e}")  # 如模型加载失败
```

### 5.4 性能优化建议
- 首次初始化后，服务会保持在内存中，后续请求很快
- 向量数据库会持久化到磁盘，重启后自动加载
- 建议在服务启动时调用 `initialize()`，而不是每次请求时

---

## 6. 目录结构
```
rag/
├── .env                      # 环境变量配置
├── rag_service.py            # RAG 服务模块 ⭐
├── rag_optimization_notebook.ipynb  # 开发调试用
├── knowledge_base/
│   └── docs/                 # 文档目录
│       └── college_db_schema.txt
└── chroma_db_rag/            # 向量数据库（自动生成）
```

---

## 7. 常见问题

**Q: 提示 "DASHSCOPE_API_KEY 未设置"**
A: 在 `.env` 文件中添加 `DASHSCOPE_API_KEY=your-key`

**Q: 回答 "根据现有资料无法回答该问题"**
A: 说明文档中没有相关内容，检查文档是否正确加载

**Q: 首次启动很慢**
A: 正在创建向量索引，后续启动会自动加载缓存

**Q: 添加新文档后没有生效**
A: 调用 `rag.rebuild_index()` 重建索引
