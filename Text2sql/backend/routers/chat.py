from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List, Any
import database, models, auth
from utils.db_utils import get_db_schema, execute_query
from services.llm_service import generate_sql_from_text, generate_analysis, generate_schema_summary
import os

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    file_id: int
    api_key: Optional[str] = None

class SummaryRequest(BaseModel):
    file_id: int
    api_key: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    sql: str
    columns: List[str]
    data: List[dict]
    chart_type: str = "bar"

@router.post("/summary")
def get_database_summary(
    request: SummaryRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    获取数据库的结构摘要和推荐问题
    """
    # 1. 获取文件
    uploaded_file = db.query(models.UploadedFile).filter(
        models.UploadedFile.id == request.file_id,
        models.UploadedFile.user_id == current_user.id
    ).first()
    
    if not uploaded_file:
        raise HTTPException(status_code=404, detail="File not found")
    
    db_path = uploaded_file.file_path
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="File missing on server")

    # 2. 提取 Schema
    try:
        schema = get_db_schema(db_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read schema: {str(e)}")

    # 3. 调用 LLM 生成总结
    try:
        summary = generate_schema_summary(schema, api_key=request.api_key)
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Error: {str(e)}")


@router.post("/analyze", response_model=ChatResponse)
def analyze_data(
    request: ChatRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    # 1. 获取文件记录
    uploaded_file = db.query(models.UploadedFile).filter(
        models.UploadedFile.id == request.file_id,
        models.UploadedFile.user_id == current_user.id
    ).first()
    
    if not uploaded_file:
        raise HTTPException(status_code=404, detail="File not found or access denied")
    
    db_path = uploaded_file.file_path
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Database file missing on server")

    # 2. 提取 Schema
    try:
        schema = get_db_schema(db_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read database schema: {str(e)}")

    # 3. 生成 SQL
    try:
        sql = generate_sql_from_text(request.message, schema, api_key=request.api_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Error: {str(e)}")

    # 4. 执行 SQL
    result = execute_query(db_path, sql)
    if result.get("error"):
        return {
            "answer": f"SQL Execution Failed: {result['error']}",
            "sql": sql,
            "columns": [],
            "data": [],
            "chart_type": "none"
        }

    # 5. 生成简短分析
    analysis = generate_analysis(request.message, result['data'], api_key=request.api_key)

    return {
        "answer": analysis,
        "sql": sql,
        "columns": result['columns'],
        "data": result['data'],
        "chart_type": "bar"
    }