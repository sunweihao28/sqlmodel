
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any, Iterator
import database, models, auth
from utils.db_utils import get_db_schema, execute_query
from services.llm_service import generate_sql_from_text, generate_analysis, generate_schema_summary, generate_schema_summary_stream, fix_sql_query, agent_analyze_database_stream
import os
import json

router = APIRouter(prefix="/api/chat", tags=["chat"])

# --- 请求模型定义 (Request Models) ---

class GenerateSqlRequest(BaseModel):
    message: str
    file_id: int
    history: List[Dict[str, Any]] = [] 
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None

class ExecuteSqlRequest(BaseModel):
    sql: str
    message: str # 原始问题，用于生成分析摘要
    file_id: int
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None

class SummaryRequest(BaseModel):
    file_id: int
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None

class AgentAnalyzeRequest(BaseModel):
    message: str
    file_id: int
    history: List[Dict[str, Any]] = []
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tool_rounds: int = 12

# --- 1. 生成 SQL 草稿 (Generate Draft) ---
@router.post("/generate")
def generate_sql_draft(
    request: GenerateSqlRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    # 验证文件权限
    uploaded_file = db.query(models.UploadedFile).filter(
        models.UploadedFile.id == request.file_id,
        models.UploadedFile.user_id == current_user.id
    ).first()
    
    if not uploaded_file or not os.path.exists(uploaded_file.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        schema = get_db_schema(uploaded_file.file_path)
        
        # 传入 base_url 和 model
        sql = generate_sql_from_text(
            request.message, 
            request.history, 
            schema, 
            api_key=request.api_key, 
            base_url=request.base_url,
            model=request.model
        )
        
        return {"sql": sql}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation Error: {str(e)}")

# --- 2. 执行 SQL (Execute Query) ---
@router.post("/execute")
def execute_sql_command(
    request: ExecuteSqlRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    uploaded_file = db.query(models.UploadedFile).filter(
        models.UploadedFile.id == request.file_id,
        models.UploadedFile.user_id == current_user.id
    ).first()
    
    if not uploaded_file or not os.path.exists(uploaded_file.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    result = execute_query(uploaded_file.file_path, request.sql)
    
    # 自动修复逻辑
    if result.get("error"):
        try:
            schema = get_db_schema(uploaded_file.file_path)
            fixed_sql = fix_sql_query(
                request.sql, 
                result['error'], 
                schema, 
                api_key=request.api_key,
                base_url=request.base_url,
                model=request.model
            )
            
            retry_result = execute_query(uploaded_file.file_path, fixed_sql)
            
            if not retry_result.get("error"):
                result = retry_result
                request.sql = fixed_sql
        except Exception as e:
            pass 

    if result.get("error"):
        return {
            "success": False,
            "error": result['error'],
            "sql": request.sql,
            "answer": f"Error executing SQL: {result['error']}",
            "columns": [],
            "data": []
        }

    # 分析摘要
    analysis = generate_analysis(
        request.message, 
        result['data'], 
        api_key=request.api_key,
        base_url=request.base_url,
        model=request.model
    )

    return {
        "success": True,
        "answer": analysis,
        "sql": request.sql, 
        "columns": result['columns'],
        "data": result['data'],
        "chart_type": "bar" 
    }

# --- 3. 获取摘要 (Summary) ---
@router.post("/summary")
def get_database_summary(
    request: SummaryRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    uploaded_file = db.query(models.UploadedFile).filter(
        models.UploadedFile.id == request.file_id,
        models.UploadedFile.user_id == current_user.id
    ).first()

    if not uploaded_file:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        schema = get_db_schema(uploaded_file.file_path)
        summary = generate_schema_summary(
            schema,
            api_key=request.api_key,
            base_url=request.base_url,
            model=request.model
        )
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 4. 流式获取摘要 (Streaming Summary) ---
@router.post("/summary/stream")
async def get_database_summary_stream(
    request: SummaryRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    uploaded_file = db.query(models.UploadedFile).filter(
        models.UploadedFile.id == request.file_id,
        models.UploadedFile.user_id == current_user.id
    ).first()

    if not uploaded_file:
        raise HTTPException(status_code=404, detail="File not found")

    async def generate_stream() -> Iterator[str]:
        try:
            schema = get_db_schema(uploaded_file.file_path)

            # 使用流式LLM调用
            for chunk in generate_schema_summary_stream(
                schema,
                api_key=request.api_key,
                base_url=request.base_url,
                model=request.model
            ):
                # SSE 格式: "data: {json}\n\n"
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        # 结束标志
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# --- 5. Agent模式流式分析 (Agent Analysis with Streaming) ---
@router.post("/agent/stream")
async def agent_analyze_stream(
    request: AgentAnalyzeRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    uploaded_file = db.query(models.UploadedFile).filter(
        models.UploadedFile.id == request.file_id,
        models.UploadedFile.user_id == current_user.id
    ).first()

    if not uploaded_file or not os.path.exists(uploaded_file.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    async def generate_stream() -> Iterator[str]:
        try:
            schema = get_db_schema(uploaded_file.file_path)

            # 使用流式Agent分析
            for event in agent_analyze_database_stream(
                question=request.message,
                db_path=uploaded_file.file_path,
                schema=schema,
                history=request.history,
                api_key=request.api_key,
                base_url=request.base_url,
                model=request.model,
                max_tool_rounds=request.max_tool_rounds
            ):
                # SSE 格式: "data: {json}\n\n"
                print(f"[DEBUG] Event: {event}")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"[ERROR] Exception in generate_stream: {type(e).__name__}: {str(e)}")
            print(f"[ERROR] Traceback:\n{error_traceback}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

        # 结束标志
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
