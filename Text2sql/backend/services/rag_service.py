
import os
import uuid
import json
import shutil
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_community.document_loaders import (
    TextLoader, PyPDFLoader, Docx2txtLoader
)

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        raise ImportError("缺少 TextSplitter 模块。请运行: pip install langchain-text-splitters")

try:
    from langchain_community.vectorstores import Chroma
except ImportError:
    raise ImportError("缺少 'chromadb'。请运行: pip install chromadb")

try:
    from langchain_openai import OpenAIEmbeddings
except ImportError:
    raise ImportError("缺少 'langchain-openai'。请运行: pip install langchain-openai")

from rank_bm25 import BM25Okapi
from langchain_core.documents import Document

class RAGService:
    def __init__(
        self,
        base_storage_dir: str = "storage",
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
        top_k: int = 4
    ):
        self.base_storage_dir = Path(base_storage_dir)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k
        
        # 移除单例状态，因为每个用户的 DB 不同
        # self._vectordb = None 
        # self._bm25 = None
        
        os.makedirs(self.base_storage_dir, exist_ok=True)

    def _get_user_paths(self, user_id: int):
        """获取特定用户的存储路径"""
        user_dir = self.base_storage_dir / str(user_id)
        docs_path = user_dir / "knowledge_base"
        persist_dir = user_dir / "chroma_db"
        
        os.makedirs(docs_path, exist_ok=True)
        os.makedirs(persist_dir, exist_ok=True)
        
        return docs_path, persist_dir

    def _get_embedding_fn(self, api_key: str = None, base_url: str = None):
        """动态获取 Embedding 函数"""
        key_to_use = api_key or os.environ.get("OPENAI_API_KEY")
        
        if not key_to_use:
            raise ValueError("RAG 操作需要 OpenAI API Key。请在设置中配置或设置环境变量。")

        return OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=key_to_use,
            openai_api_base=base_url, 
            check_embedding_ctx_length=False 
        )

    def _get_vectordb(self, user_id: int, api_key: str = None, base_url: str = None):
        """获取特定用户的向量库实例"""
        _, persist_dir = self._get_user_paths(user_id)
        embedding_fn = self._get_embedding_fn(api_key, base_url)
        return Chroma(
            persist_directory=str(persist_dir),
            embedding_function=embedding_fn
        )

    def _load_bm25(self, user_id: int, api_key: str = None, base_url: str = None):
        """按需构建特定用户的 BM25 索引"""
        try:
            # BM25 需要加载所有文档内容，这里利用 Chroma 作为存储源来读取
            # 注意：如果文档量巨大，这种实时加载可能会慢，需要引入缓存机制
            vectordb = self._get_vectordb(user_id, api_key, base_url)
            
            # 这里的 get() 会获取所有文档
            collection_data = vectordb.get()
            docs = collection_data["documents"]
            metadatas = collection_data["metadatas"]
            
            if not docs:
                return None, []

            reconstructed_docs = []
            for content, meta in zip(docs, metadatas):
                reconstructed_docs.append(Document(page_content=content, metadata=meta))
            
            tokenized_corpus = [doc.page_content.lower().split() for doc in reconstructed_docs]
            bm25 = BM25Okapi(tokenized_corpus)
            return bm25, reconstructed_docs
        except Exception as e:
            print(f"BM25 load error for user {user_id}: {e}")
            return None, []

    def _get_loader(self, file_path: Path):
        suffix = file_path.suffix.lower()
        if suffix == '.txt':
            return TextLoader(str(file_path), encoding='utf-8')
        elif suffix == '.pdf':
            return PyPDFLoader(str(file_path))
        elif suffix == '.docx':
            return Docx2txtLoader(str(file_path))
        elif suffix == '.md':
            return TextLoader(str(file_path), encoding='utf-8')
        elif suffix == '.json':
            return JSONTextLoader(str(file_path))
        elif suffix in ['.xlsx', '.xls']:
            return ExcelTextLoader(str(file_path))
        else:
            raise ValueError(f"不支持的文件格式: {suffix}")

    def _clean_text(self, text: str) -> str:
        return text.replace('\n\n', '\n').strip()

    def add_document(self, user_id: int, file_path: str, filename: str, api_key: str = None, base_url: str = None) -> str:
        """添加文档到特定用户的知识库"""
        docs_path, _ = self._get_user_paths(user_id)
        
        doc_id = str(uuid.uuid4())
        target_path = docs_path / f"{doc_id}_{filename}"
        shutil.copy2(file_path, target_path)
        
        try:
            loader = self._get_loader(target_path)
            documents = loader.load()
            
            for doc in documents:
                doc.metadata.update({
                    "doc_id": doc_id,
                    "original_file": filename,
                    "source": str(target_path)
                })

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap
            )
            chunks = text_splitter.split_documents(documents)
            
            for chunk in chunks:
                chunk.page_content = self._clean_text(chunk.page_content)

            # 获取该用户的向量库并添加
            vectordb = self._get_vectordb(user_id, api_key, base_url)
            vectordb.add_documents(chunks)
            
            return doc_id
        except Exception as e:
            if os.path.exists(target_path):
                os.remove(target_path)
            raise e

    def remove_document(self, user_id: int, doc_id: str, api_key: str = None, base_url: str = None) -> bool:
        """从特定用户知识库删除文档"""
        docs_path, _ = self._get_user_paths(user_id)

        # 1. 从向量库删除
        try:
            vectordb = self._get_vectordb(user_id, api_key, base_url)
            collection = vectordb._collection
            results = collection.get(where={"doc_id": doc_id})
            ids_to_delete = results["ids"]
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
        except Exception as e:
            print(f"Error deleting from Chroma for user {user_id}: {e}")
            # 即使向量库删除失败（可能是 Key 问题），也要尝试删除物理文件

        # 2. 删除物理文件
        deleted = False
        for f in docs_path.glob(f"{doc_id}_*"):
            try:
                os.remove(f)
                deleted = True
            except:
                pass
                
        return deleted

    def list_documents(self, user_id: int) -> List[Dict]:
        """列出特定用户的所有文档"""
        docs_path, _ = self._get_user_paths(user_id)
        docs_map = {}
        
        # 从物理文件推断
        if docs_path.exists():
            for f in docs_path.glob("*_*"):
                try:
                    # filename format: {uuid}_{original_name}
                    parts = f.name.split('_', 1)
                    if len(parts) == 2:
                        did, fname = parts
                        docs_map[did] = {"id": did, "name": fname}
                except:
                    continue
                
        return list(docs_map.values())

    def hybrid_search(self, user_id: int, query: str, k: int = 4, api_key: str = None, base_url: str = None) -> List[Document]:
        """特定用户的混合检索"""
        try:
            vectordb = self._get_vectordb(user_id, api_key, base_url)
            # 检查是否有数据
            if not vectordb._collection.count():
                return []
        except Exception as e:
            print(f"Vector DB init error: {e}")
            return []

        # 1. 向量检索
        try:
            vector_results = vectordb.similarity_search_with_score(query, k=k*2)
            vector_docs = [doc for doc, _ in vector_results]
        except Exception as e:
            print(f"Vector search failed: {e}")
            vector_docs = []

        # 2. BM25 检索 (即时加载)
        bm25, bm25_docs = self._load_bm25(user_id, api_key, base_url)
        bm25_result_docs = []
        
        if bm25 and bm25_docs:
            try:
                bm25_scores = bm25.get_scores(query.lower().split())
                top_n_indices = np.argsort(bm25_scores)[::-1][:k*2]
                bm25_result_docs = [bm25_docs[i] for i in top_n_indices]
            except Exception as e:
                print(f"BM25 search failed: {e}")

        # 3. RRF 融合
        return self._rrf_fusion(vector_docs, bm25_result_docs, k=k)

    def _rrf_fusion(self, list1: List[Document], list2: List[Document], k: int = 4, rrf_k: int = 60):
        scores = {}
        for rank, doc in enumerate(list1):
            key = doc.page_content
            if key not in scores: scores[key] = {"doc": doc, "score": 0.0}
            scores[key]["score"] += 1.0 / (rrf_k + rank + 1)
        for rank, doc in enumerate(list2):
            key = doc.page_content
            if key not in scores: scores[key] = {"doc": doc, "score": 0.0}
            scores[key]["score"] += 1.0 / (rrf_k + rank + 1)
        sorted_items = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        return [item["doc"] for item in sorted_items[:k]]

# --- Custom Loaders (Same as before) ---
class JSONTextLoader:
    def __init__(self, file_path: str): self.file_path = file_path
    def load(self) -> List[Document]:
        with open(self.file_path, 'r', encoding='utf-8') as f: data = json.load(f)
        text_content = json.dumps(data, ensure_ascii=False, indent=2) if isinstance(data, (dict, list)) else str(data)
        return [Document(page_content=text_content, metadata={"source": self.file_path})]

class ExcelTextLoader:
    def __init__(self, file_path: str): self.file_path = file_path
    def load(self) -> List[Document]:
        df = pd.read_excel(self.file_path)
        full_text = "\n".join([", ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)]) for _, row in df.iterrows()])
        return [Document(page_content=full_text, metadata={"source": self.file_path})]

rag_service_instance = RAGService()