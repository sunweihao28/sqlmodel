# rag_service_text2sql.py

import os
import uuid
import json
import shutil
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from langchain_community.document_loaders import (
    TextLoader, PyPDFLoader, Docx2txtLoader, UnstructuredMarkdownLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from rank_bm25 import BM25Okapi
from langchain_core.documents import Document

class RAGService:
    def __init__(
        self,
        docs_path: str = "knowledge_base/docs",
        persist_dir: str = "chroma_db_rag_text2sql",
        embedding_model_name: str = "BAAI/bge-small-en-v1.5",  # 英文模型（因数据库内容为英文）
        chunk_size: int = 2000,      # 增大：避免切碎 schema
        chunk_overlap: int = 100,
        top_k: int = 4,              # 多召回：schema + 多个示例
        force_rebuild: bool = False,
        use_rewrite: bool = False,   # ❌ 关闭查询重写（防止丢失实体）
        language: str = "en",        # 数据库内容为英文
        llm=None  # 需传入一个 callable: llm(prompt: str) -> str
    ):
        self.docs_path = Path(docs_path)
        self.persist_dir = persist_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k
        self.force_rebuild = force_rebuild
        self.use_rewrite = use_rewrite
        self.language = language
        self.llm = llm

        # 初始化组件
        self._vectordb = None
        self._bm25 = None
        self._bm25_docs = []


        # 加载 DashScope Embedding 模型
        # 需设置环境变量 DASHSCOPE_API_KEY
        self._embedding = DashScopeEmbeddings(
            model="text-embedding-v2",
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY")
        )

        self.initialize()

    def _load_documents(self) -> List[Document]:
        """加载所有支持格式的文档"""
        documents = []
        supported_ext = {'.txt', '.pdf', '.docx', '.md'}
        for file_path in self.docs_path.rglob('*'):
            if file_path.suffix.lower() not in supported_ext:
                continue
            try:
                loader = self._get_loader(file_path)
                docs = loader.load()
                for doc in docs:
                    doc.metadata["source"] = str(file_path.resolve())
                documents.extend(docs)
            except Exception as e:
                print(f"⚠️ 加载文件失败: {file_path} | 错误: {e}")
        return documents

    def _get_loader(self, file_path: Path):
        suffix = file_path.suffix.lower()
        if suffix == '.txt':
            return TextLoader(file_path, encoding='utf-8')
        elif suffix == '.pdf':
            return PyPDFLoader(file_path)
        elif suffix == '.docx':
            return Docx2txtLoader(file_path)
        elif suffix == '.md':
            return UnstructuredMarkdownLoader(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {suffix}")

    def _clean_text(self, text: str) -> str:
        return text.replace('\n\n', '\n').strip()

    def _build_index(self):
        print("🔄 正在构建 Text-to-SQL 向量索引与BM25索引...")
        documents = self._load_documents()
        if not documents:
            raise ValueError("知识库中未找到任何有效文档！")

        # 文本切片（大 chunk）
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )
        all_chunks = text_splitter.split_documents(documents)
        for doc in all_chunks:
            doc.page_content = self._clean_text(doc.page_content)

        # 构建向量数据库
        self._vectordb = Chroma.from_documents(
            documents=all_chunks,
            embedding=self._embedding,
            persist_directory=self.persist_dir
        )

        # 构建 BM25 索引（英文直接 split）
        self._bm25_docs = all_chunks
        tokenized_corpus = [doc.page_content.lower().split() for doc in all_chunks]
        self._bm25 = BM25Okapi(tokenized_corpus)

        print(f"✅ Text-to-SQL 索引构建完成！共 {len(all_chunks)} 个文本块。")

    def initialize(self):
        db_exists = os.path.exists(self.persist_dir)
        if self.force_rebuild or not db_exists:
            if db_exists:
                shutil.rmtree(self.persist_dir)
            self._build_index()
        else:
            self._vectordb = Chroma(
                persist_directory=self.persist_dir,
                embedding_function=self._embedding
            )
            # 重建 BM25（简化处理）
            documents = self._load_documents()
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap
            )
            all_chunks = text_splitter.split_documents(documents)
            for doc in all_chunks:
                doc.page_content = self._clean_text(doc.page_content)
            self._bm25_docs = all_chunks
            tokenized_corpus = [doc.page_content.lower().split() for doc in all_chunks]
            self._bm25 = BM25Okapi(tokenized_corpus)

    def _rewrite_query(self, query: str) -> List[str]:
        # 已关闭，直接返回原查询
        return [query]

    def _hybrid_search(self, query: str, k: int = 5) -> List[Document]:
        """混合检索：向量 + BM25，使用 RRF 融合排序"""
        queries = self._rewrite_query(query)

        # 向量检索（带分数）
        vector_results_with_scores = []
        for q in queries:
            results = self._vectordb.similarity_search_with_score(q, k=k*2)
            vector_results_with_scores.extend(results)
        
        # 按向量相似度排序，建立排名
        vector_results_with_scores.sort(key=lambda x: x[1])  # 分数越小越相似
        vector_rank = {self._doc_key(doc): rank for rank, (doc, _) in enumerate(vector_results_with_scores)}

        # BM25 检索
        bm25_scores = self._bm25.get_scores(query.lower().split())
        top_indices = np.argsort(bm25_scores)[::-1][:k*2]
        bm25_rank = {self._doc_key(self._bm25_docs[i]): rank for rank, i in enumerate(top_indices)}

        # RRF 融合（Reciprocal Rank Fusion）
        rrf_k = 60  # RRF 常数
        all_docs = {}
        
        # 收集所有文档
        for doc, _ in vector_results_with_scores:
            key = self._doc_key(doc)
            if key not in all_docs:
                all_docs[key] = doc
        for i in top_indices:
            doc = self._bm25_docs[i]
            key = self._doc_key(doc)
            if key not in all_docs:
                all_docs[key] = doc
        
        # 计算 RRF 分数
        rrf_scores = []
        for key, doc in all_docs.items():
            score = 0.0
            if key in vector_rank:
                score += 1.0 / (rrf_k + vector_rank[key])
            if key in bm25_rank:
                score += 1.0 / (rrf_k + bm25_rank[key])
            rrf_scores.append((doc, score))
        
        # 按 RRF 分数排序
        rrf_scores.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in rrf_scores[:k]]
    
    def _doc_key(self, doc: Document) -> str:
        """生成文档唯一标识"""
        return f"{doc.metadata.get('source', '')}:{doc.page_content[:100]}"

    def sync_with_local_files(self):
        if not self._vectordb:
            return False
        try:
            collection = self._vectordb._collection
            all_metadatas = collection.get(include=["metadatas"])["metadatas"]
            ids_to_delete = []
            for idx, meta in enumerate(all_metadatas):
                source = meta.get("source")
                if source and not os.path.exists(source):
                    ids_to_delete.append(collection.get()["ids"][idx])
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
                print(f"🗑️ 已删除 {len(ids_to_delete)} 个失效文档的向量")
            return True
        except Exception as e:
            print(f"Sync failed: {e}")
            return False

    def rebuild_index(self):
        self.force_rebuild = True
        try:
            self.initialize()
            return True
        except Exception as e:
            print(f"Rebuild failed: {e}")
            return False

    def get_indexed_files(self) -> List[str]:
        if not self._vectordb:
            return []
        metadatas = self._vectordb._collection.get(include=["metadatas"])["metadatas"]
        return list(set(meta.get("source") for meta in metadatas if meta.get("source")))

    def ask_sql(self, query: str) -> str:
        """Text-to-SQL 专用接口"""
        if not query.strip():
            return "SELECT '请输入有效问题';"
        if not self._vectordb:
            return "SELECT 'RAG服务未初始化';"

        retrieved_docs = self._hybrid_search(query, k=self.top_k)
        context = "\n".join([doc.page_content for doc in retrieved_docs])

        prompt = f"""You are an expert Text-to-SQL system for a university database.
Convert the user's question into a correct and executable SQL query using SQLite syntax.

Database Schema and Examples:
{context}

Instructions:
- Output ONLY the SQL query, no explanation.
- Use exact table and column names from the schema (e.g., 'dept_name', 'tot_cred').
- For text values, use single quotes (e.g., 'Comp. Sci.').
- If unsure, return: SELECT '无法生成SQL';
- Do not hallucinate tables or columns.

Question: {query}
SQL:"""

        try:
            sql = self.llm(prompt).strip()
            if not sql.upper().startswith("SELECT") and "无法生成SQL" not in sql:
                return "SELECT '生成的SQL无效';"
            return sql
        except Exception as e:
            return f"SELECT 'LLM调用失败: {str(e)}';"
    
    # ======================
    # 🔹 新增：添加单个文档
    # ======================
    def add_document_from_file(self, file_path: str, doc_id: str = None) -> str:
        """
        从文件路径添加一个新文档到向量库和BM25索引
        :param file_path: 文件绝对路径或相对路径
        :param doc_id: 可选，若未提供则自动生成UUID
        :return: 实际使用的 doc_id
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_path = Path(file_path)
        suffix = file_path.suffix.lower()
        if suffix not in {'.txt', '.pdf', '.docx', '.md'}:
            raise ValueError(f"不支持的文件格式: {suffix}")

        # 生成或使用指定 doc_id
        actual_doc_id = doc_id or str(uuid.uuid4())

        # 加载文档
        loader = self._get_loader(file_path)
        documents = loader.load()

        # 添加统一元数据
        for doc in documents:
            doc.metadata.update({
                "doc_id": actual_doc_id,
                "original_file": str(file_path.name),
                "source_type": "dynamic_upload"
            })

        # 切块
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )
        chunks = text_splitter.split_documents(documents)
        for chunk in chunks:
            chunk.page_content = self._clean_text(chunk.page_content)

        # 添加到向量库
        self._vectordb.add_documents(chunks)

        # 合并到 BM25 文档列表
        self._bm25_docs.extend(chunks)
        tokenized_corpus = [doc.page_content.lower().split() for doc in self._bm25_docs]
        self._bm25 = BM25Okapi(tokenized_corpus)

        print(f"✅ 已添加文档 '{file_path.name}' (doc_id={actual_doc_id})")
        return actual_doc_id

    # ======================
    # 🔹 新增：删除指定文档
    # ======================
    def remove_document(self, doc_id: str) -> bool:
        """
        从向量库和BM25中删除指定 doc_id 的所有 chunks
        :param doc_id: 文档唯一ID
        :return: 是否删除成功（至少删除1个chunk）
        """
        if not self._vectordb:
            return False

        collection = self._vectordb._collection

        # 步骤1: 从向量库中查找并删除
        try:
            results = collection.get(where={"doc_id": doc_id}, include=[])
            ids_to_delete = results["ids"]
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
                print(f"🗑️ 从向量库删除 {len(ids_to_delete)} 个 chunks (doc_id={doc_id})")
            else:
                print(f"⚠️ 未找到 doc_id={doc_id} 的向量")
        except Exception as e:
            print(f"❌ 向量库删除失败: {e}")
            return False

        # 步骤2: 从 BM25 文档列表中移除
        before_count = len(self._bm25_docs)
        self._bm25_docs = [
            doc for doc in self._bm25_docs
            if doc.metadata.get("doc_id") != doc_id
        ]
        after_count = len(self._bm25_docs)
        removed_count = before_count - after_count

        # 重建 BM25 索引
        if removed_count > 0:
            tokenized_corpus = [doc.page_content.lower().split() for doc in self._bm25_docs]
            self._bm25 = BM25Okapi(tokenized_corpus)
            print(f"🧹 从 BM25 移除 {removed_count} 个 chunks")

        return (len(ids_to_delete) > 0) or (removed_count > 0)