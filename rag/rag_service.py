"""
RAG 文档问答服务模块

提供给前端开发人员使用的 RAG 问答 API

使用说明:
    from rag_service import RAGService
    
    # 初始化服务
    rag = RAGService()
    
    # 提问
    answer = rag.ask("student 表有哪些字段？")
    print(answer)
"""

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Optional, List, Dict
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class RAGService:
    """RAG 文档问答服务类"""
    
    def __init__(
        self,
        docs_path: str = "knowledge_base/docs",
        persist_dir: str = "chroma_db_rag",
        llm_model: str = "qwen-turbo",
        chunk_size: int = 256,
        chunk_overlap: int = 30,
        top_k: int = 5,
        force_rebuild: bool = False
    ):
        """
        初始化 RAG 服务
        
        Args:
            docs_path: 文档目录路径
            persist_dir: 向量数据库持久化目录
            llm_model: LLM 模型名称 (qwen-turbo, qwen-plus, qwen-max)
            chunk_size: 文档切片大小
            chunk_overlap: 切片重叠大小
            top_k: 检索返回的文档数量
            force_rebuild: 是否强制重建向量数据库
        """
        self.docs_path = docs_path
        self.persist_dir = persist_dir
        self.llm_model = llm_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k
        self.force_rebuild = force_rebuild
        
        # 内部状态
        self._embed_model = None
        self._vectordb = None
        self._retriever = None
        self._client = None
        self._initialized = False
        
        # 提示词模板
        self.prompt_template = """
你是一个专业、严谨的知识库助手。请基于提供的【参考信息】来回答用户的【问题】。

【重要约束】：
1. 仅根据已知的【参考信息】回答，严禁基于外部知识编造内容
2. 如果【参考信息】中不包含答案，请直接告知用户"根据现有资料无法回答该问题"
3. 禁止产生幻觉，不确定的内容不要回答
4. 回答要简洁、准确，直接给出答案
5. 可以使用 ask_with_sources()获取文件路径。

【参考信息】：
{context}

【问题】：
{query}

【回答】：
"""
    
    def initialize(self) -> Dict[str, bool]:
        """
        初始化所有组件
        
        Returns:
            Dict: 各组件初始化状态
        """
        status = {
            "embed_model": False,
            "vectordb": False,
            "retriever": False,
            "llm_client": False
        }
        
        # 1. 初始化嵌入模型
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError("请设置 DASHSCOPE_API_KEY 环境变量")
        
        try:
            from langchain_community.embeddings import DashScopeEmbeddings
            self._embed_model = DashScopeEmbeddings(
                model="text-embedding-v2", 
                dashscope_api_key=api_key
            )
            # 测试嵌入模型
            self._embed_model.embed_query("测试")
            status["embed_model"] = True
        except Exception as e:
            raise RuntimeError(f"嵌入模型初始化失败: {e}")
        
        # 2. 加载或创建向量数据库
        self._load_or_create_vectordb()
        if self._vectordb:
            status["vectordb"] = True
        if self._retriever:
            status["retriever"] = True
        
        # 3. 初始化 LLM 客户端
        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            status["llm_client"] = True
        except Exception as e:
            raise RuntimeError(f"LLM 客户端初始化失败: {e}")
        
        self._initialized = True
        return status
    
    def _clean_text(self, text: str) -> str:
        """清理文本中的无效字符"""
        text = text.encode('utf-8', errors='ignore').decode('utf-8')
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        return text
    
    def _load_documents(self) -> tuple:
        """加载文档目录下所有支持格式的文件"""
        from langchain_community.document_loaders import TextLoader, Docx2txtLoader
        
        all_docs = []
        failed_files = []
        docs_path = Path(self.docs_path)
        
        if not docs_path.exists():
            os.makedirs(docs_path, exist_ok=True)
            return [], []
        
        # TXT 文件
        for file_path in docs_path.rglob("*.txt"):
            try:
                loader = TextLoader(str(file_path), encoding='utf-8')
                all_docs.extend(loader.load())
            except Exception as e:
                failed_files.append((str(file_path), str(e)[:50]))
        
        # PDF 文件
        try:
            from langchain_community.document_loaders import PyPDFLoader
            for file_path in docs_path.rglob("*.pdf"):
                try:
                    loader = PyPDFLoader(str(file_path))
                    all_docs.extend(loader.load())
                except Exception as e:
                    failed_files.append((str(file_path), str(e)[:50]))
        except ImportError:
            pass
        
        # Word 文件
        for file_path in docs_path.rglob("*.docx"):
            try:
                loader = Docx2txtLoader(str(file_path))
                all_docs.extend(loader.load())
            except Exception as e:
                failed_files.append((str(file_path), str(e)[:50]))
        
        # Markdown 文件
        for file_path in docs_path.rglob("*.md"):
            try:
                loader = TextLoader(str(file_path), encoding='utf-8')
                all_docs.extend(loader.load())
            except Exception as e:
                failed_files.append((str(file_path), str(e)[:50]))
        
        # 记录失败的文件
        self._failed_files = failed_files
        
        return all_docs, failed_files
    
    def _load_or_create_vectordb(self):
        """加载或创建向量数据库"""
        from langchain_community.vectorstores import Chroma
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        
        db_exists = (
            os.path.exists(self.persist_dir) and 
            os.path.exists(os.path.join(self.persist_dir, 'chroma.sqlite3'))
        )
        
        # 如果强制重建，先删除旧数据库
        if self.force_rebuild and db_exists:
            try:
                shutil.rmtree(self.persist_dir)
                db_exists = False
            except Exception:
                self.persist_dir = f'chroma_db_rag_{uuid.uuid4().hex[:8]}'
                db_exists = False
        
        if db_exists and not self.force_rebuild:
            # 加载已有数据库
            try:
                self._vectordb = Chroma(
                    persist_directory=self.persist_dir, 
                    embedding_function=self._embed_model
                )
                count = self._vectordb._collection.count()
                if count > 0:
                    self._retriever = self._vectordb.as_retriever(
                        search_kwargs={"k": self.top_k}
                    )
                    return
            except Exception:
                db_exists = False
        
        # 创建新数据库
        documents, failed_files = self._load_documents()
        if not documents:
            return
        
        # 打印失败的文件
        if failed_files:
            print(f"\n⚠️ {len(failed_files)} 个文件加载失败:")
            for f, err in failed_files[:10]:
                print(f"  - {Path(f).name}: {err}")
            if len(failed_files) > 10:
                print(f"  ... 还有 {len(failed_files) - 10} 个")
        
        # 清理文本
        for doc in documents:
            doc.page_content = self._clean_text(doc.page_content)
        
        # 切分文档
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size, 
            chunk_overlap=self.chunk_overlap
        )
        docs = text_splitter.split_documents(documents)
        
        # 创建向量数据库
        ids = [str(uuid.uuid4()) for _ in docs]
        self._vectordb = Chroma.from_documents(
            documents=docs,
            embedding=self._embed_model,
            ids=ids,
            persist_directory=self.persist_dir
        )
        self._retriever = self._vectordb.as_retriever(
            search_kwargs={"k": self.top_k}
        )
    
    def ask(self, question: str) -> str:
        """
        RAG 问答
        
        Args:
            question: 用户问题
            
        Returns:
            str: 回答
        """
        if not self._initialized:
            self.initialize()
        
        if not self._retriever:
            return "❌ 检索器未初始化，请确保文档目录中有文件"
        
        if not self._client:
            return "❌ LLM 客户端未初始化"
        
        # 1. 向量检索
        docs = self._retriever.invoke(question)
        
        # 2. 格式化上下文
        context_parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get('source', '未知')
            context_parts.append(f"[文档{i}] (来源: {source})\n{doc.page_content}")
        context = "\n\n".join(context_parts) if context_parts else "无相关文档"
        
        # 3. 调用 LLM
        prompt = self.prompt_template.format(context=context, query=question)
        response = self._client.chat.completions.create(
            model=self.llm_model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.choices[0].message.content
    
    def ask_with_sources(self, question: str) -> Dict:
        """
        RAG 问答（返回答案和来源）
        
        Args:
            question: 用户问题
            
        Returns:
            Dict: {"answer": str, "sources": List[Dict]}
        """
        if not self._initialized:
            self.initialize()
        
        if not self._retriever or not self._client:
            return {
                "answer": "❌ 服务未初始化",
                "sources": []
            }
        
        # 检索
        docs = self._retriever.invoke(question)
        
        # 格式化上下文
        context_parts = []
        sources = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get('source', '未知')
            context_parts.append(f"[文档{i}] (来源: {source})\n{doc.page_content}")
            sources.append({
                "id": i,
                "source": source,
                "content": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
            })
        context = "\n\n".join(context_parts) if context_parts else "无相关文档"
        
        # 调用 LLM
        prompt = self.prompt_template.format(context=context, query=question)
        response = self._client.chat.completions.create(
            model=self.llm_model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return {
            "answer": response.choices[0].message.content,
            "sources": sources
        }
    
    def rebuild_index(self) -> bool:
        """
        重建向量索引
        
        Returns:
            bool: 是否成功
        """
        self.force_rebuild = True
        try:
            self._load_or_create_vectordb()
            return self._retriever is not None
        except Exception:
            return False
    
    def get_indexed_files(self) -> List[str]:
        """
        获取已索引的文件列表
        
        Returns:
            List[str]: 文件路径列表
        """
        if not self._vectordb:
            return []
        
        try:
            collection = self._vectordb._collection
            result = collection.get(include=["metadatas"])
            files = set(meta.get('source', '') for meta in result['metadatas'])
            return list(files)
        except Exception:
            return []
    
    def get_failed_files(self) -> List[tuple]:
        """
        获取加载失败的文件列表
        
        Returns:
            List[tuple]: [(文件路径, 错误信息), ...]
        """
        return getattr(self, '_failed_files', [])
    
    def health_check(self) -> Dict:
        """
        健康检查
        
        Returns:
            Dict: 各组件状态
        """
        return {
            "initialized": self._initialized,
            "embed_model": self._embed_model is not None,
            "vectordb": self._vectordb is not None,
            "retriever": self._retriever is not None,
            "llm_client": self._client is not None,
            "docs_path": self.docs_path,
            "persist_dir": self.persist_dir,
            "llm_model": self.llm_model
        }


# =============================================================================
# 便捷函数（兼容原有调用方式）
# =============================================================================
_default_service: Optional[RAGService] = None

def get_rag_service() -> RAGService:
    """获取默认 RAG 服务实例（单例模式）"""
    global _default_service
    if _default_service is None:
        _default_service = RAGService()
        _default_service.initialize()
    return _default_service

def rag_ask(question: str) -> str:
    """
    便捷问答函数
    
    Args:
        question: 用户问题
        
    Returns:
        str: 回答
    """
    return get_rag_service().ask(question)


# =============================================================================
# 测试入口
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("RAG 服务测试")
    print("=" * 60)
    
    # 初始化服务
    rag = RAGService()
    status = rag.initialize()
    print(f"\n初始化状态: {status}")
    
    # 健康检查
    print(f"\n健康检查: {rag.health_check()}")
    
    # 获取已索引文件
    files = rag.get_indexed_files()
    print(f"\n✅ 已索引文件 ({len(files)} 个):")
    for f in files[:5]:
        print(f"  - {Path(f).name}")
    if len(files) > 5:
        print(f"  ... 还有 {len(files) - 5} 个")
    
    # 获取加载失败的文件
    failed = rag.get_failed_files()
    if failed:
        print(f"\n❌ 加载失败的文件 ({len(failed)} 个):")
        for f, err in failed:
            print(f"  - {Path(f).name}: {err}")
    
 