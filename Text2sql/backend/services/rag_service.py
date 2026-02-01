
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
    # 新版本路径 (LangChain v0.1+)
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        # 旧版本路径
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        # 如果都失败，提示安装
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
        docs_path: str = "storage/knowledge_base",
        persist_dir: str = "storage/chroma_db",
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
        top_k: int = 4
    ):
        self.docs_path = Path(docs_path)
        self.persist_dir = persist_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k

        # 确保存储目录存在
        os.makedirs(self.docs_path, exist_ok=True)
        os.makedirs(self.persist_dir, exist_ok=True)

        # 不再在初始化时强制创建 Embedding，改为动态创建
        self._vectordb = None 
        self._bm25 = None
        self._bm25_docs = []
        
        # 尝试加载 BM25 (不需要 Key)
        self._load_bm25_only()

    def _get_embedding_fn(self, api_key: str = None, base_url: str = None):
        """动态获取 Embedding 函数"""
        # 优先使用传入的 Key，否则回退到环境变量
        key_to_use = api_key or os.environ.get("OPENAI_API_KEY")
        
        if not key_to_use:
            raise ValueError("RAG 操作需要 OpenAI API Key。请在设置中配置或设置环境变量。")

        return OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=key_to_use,
            openai_api_base=base_url, # 支持自定义 Base URL
            check_embedding_ctx_length=False 
        )

    def _get_vectordb(self, api_key: str = None, base_url: str = None):
        """动态获取向量库实例"""
        embedding_fn = self._get_embedding_fn(api_key, base_url)
        return Chroma(
            persist_directory=self.persist_dir,
            embedding_function=embedding_fn
        )

    def _load_bm25_only(self):
        """仅加载 BM25 索引（不需要 API Key），用于快速启动"""
        try:
            # 这是一个简化的加载方式，实际上 BM25 需要文档内容
            # 这里我们尝试从 Chroma 的持久化存储中读取数据（如果有的话），但不初始化 Embedding
            # 由于 Chroma 需要 Embedding Fn 才能初始化 collection，这里我们先跳过深度加载
            # 实际的加载推迟到第一次需要搜索或添加文档时
            pass 
        except Exception as e:
            print(f"⚠️ BM25 init skipped: {e}")

    def _ensure_indexes_loaded(self, api_key: str = None, base_url: str = None):
        """确保索引已加载（需要 Key）"""
        if self._vectordb is not None and self._bm25 is not None:
            return

        try:
            if os.path.exists(self.persist_dir) and os.listdir(self.persist_dir):
                self._vectordb = self._get_vectordb(api_key, base_url)
                
                # 重建 BM25
                docs = self._vectordb.get()["documents"]
                metadatas = self._vectordb.get()["metadatas"]
                
                if docs:
                    reconstructed_docs = []
                    for content, meta in zip(docs, metadatas):
                        reconstructed_docs.append(Document(page_content=content, metadata=meta))
                    
                    self._bm25_docs = reconstructed_docs
                    tokenized_corpus = [doc.page_content.lower().split() for doc in self._bm25_docs]
                    self._bm25 = BM25Okapi(tokenized_corpus)
        except Exception as e:
            print(f"Index loading warning: {e}")

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

    def add_document(self, file_path: str, filename: str, api_key: str = None, base_url: str = None) -> str:
        """添加文档到知识库"""
        # 确保资源已初始化
        self._ensure_indexes_loaded(api_key, base_url)
        
        doc_id = str(uuid.uuid4())
        target_path = self.docs_path / f"{doc_id}_{filename}"
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

            # 重新获取带 Key 的 VectorDB 实例
            vectordb = self._get_vectordb(api_key, base_url)
            vectordb.add_documents(chunks)
            
            # 更新内存中的引用
            self._vectordb = vectordb

            # 更新 BM25
            self._bm25_docs.extend(chunks)
            tokenized_corpus = [doc.page_content.lower().split() for doc in self._bm25_docs]
            self._bm25 = BM25Okapi(tokenized_corpus)

            return doc_id
        except Exception as e:
            if os.path.exists(target_path):
                os.remove(target_path)
            raise e

    def remove_document(self, doc_id: str, api_key: str = None, base_url: str = None) -> bool:
        """删除文档"""
        # 即使没有 Key 也要尝试物理删除
        # 但要操作 VectorDB 需要 Key
        
        # 1. 尝试初始化
        try:
            self._ensure_indexes_loaded(api_key, base_url)
        except:
            pass

        # 2. 从向量库删除
        if self._vectordb:
            try:
                collection = self._vectordb._collection
                results = collection.get(where={"doc_id": doc_id})
                ids_to_delete = results["ids"]
                if ids_to_delete:
                    collection.delete(ids=ids_to_delete)
            except Exception as e:
                print(f"Error deleting from Chroma: {e}")

        # 3. 从 BM25 列表删除
        original_len = len(self._bm25_docs)
        self._bm25_docs = [d for d in self._bm25_docs if d.metadata.get("doc_id") != doc_id]
        
        if len(self._bm25_docs) < original_len and self._bm25_docs:
            tokenized_corpus = [doc.page_content.lower().split() for doc in self._bm25_docs]
            self._bm25 = BM25Okapi(tokenized_corpus)
        elif not self._bm25_docs:
            self._bm25 = None

        # 4. 删除物理文件
        for f in self.docs_path.glob(f"{doc_id}_*"):
            try:
                os.remove(f)
            except:
                pass
                
        return True

    def list_documents(self) -> List[Dict]:
        """列出所有已索引的文档 (尝试读取 Chroma 磁盘文件)"""
        # 这里有一个 tricky 的地方：如果没初始化 _vectordb，怎么读元数据？
        # 我们可以尝试无 Key 初始化 Chroma (仅读取模式)，但 Chroma Client 通常需要 Embedding Fn
        # 简单的做法：只在内存有 _vectordb 时返回，或者依赖文件名
        
        docs_map = {}
        
        # 1. 从物理文件推断 (最稳妥，不依赖向量库状态)
        for f in self.docs_path.glob("*_*"):
            try:
                # filename format: {uuid}_{original_name}
                parts = f.name.split('_', 1)
                if len(parts) == 2:
                    did, fname = parts
                    docs_map[did] = {"id": did, "name": fname}
            except:
                continue
                
        return list(docs_map.values())

    def hybrid_search(self, query: str, k: int = 4, api_key: str = None, base_url: str = None) -> List[Document]:
        """混合检索"""
        self._ensure_indexes_loaded(api_key, base_url)
        
        if not self._vectordb or not self._bm25:
            # 尝试重新加载
            self._ensure_indexes_loaded(api_key, base_url)
            if not self._vectordb:
                print("RAG not initialized or empty.")
                return []

        # 1. 向量检索
        try:
            vector_results = self._vectordb.similarity_search_with_score(query, k=k*2)
            vector_docs = [doc for doc, _ in vector_results]
        except Exception as e:
            print(f"Vector search failed: {e}")
            vector_docs = []

        # 2. BM25 检索
        try:
            bm25_scores = self._bm25.get_scores(query.lower().split())
            top_n_indices = np.argsort(bm25_scores)[::-1][:k*2]
            bm25_docs = [self._bm25_docs[i] for i in top_n_indices]
        except Exception as e:
            print(f"BM25 search failed: {e}")
            bm25_docs = []

        # 3. RRF 融合
        return self._rrf_fusion(vector_docs, bm25_docs, k=k)

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

# --- Custom Loaders (保持不变) ---
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