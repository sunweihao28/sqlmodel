
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
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
    use_rag: bool = False # [新增]

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
    session_id: Optional[str] = None

class AgentAnalyzeRequest(BaseModel):
    session_id: str
    message: str
    file_id: int
    history: List[Dict[str, Any]] = []
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tool_rounds: int = 12
    use_rag: bool = False # [新增]

class CreateSessionRequest(BaseModel):
    file_id: int
    title: str = "New Analysis"

# --- Session Management Endpoints ---

@router.get("/sessions")
def get_sessions(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """Get all sessions for the current user, ordered by latest update"""
    sessions = db.query(models.ChatSession).filter(
        models.ChatSession.user_id == current_user.id
    ).order_by(models.ChatSession.updated_at.desc()).all()
    
    return [
        {
            "id": s.id, 
            "title": s.title, 
            "updatedAt": int(s.updated_at.timestamp() * 1000),
            "fileId": s.file_id
        } 
        for s in sessions
    ]

@router.post("/sessions")
def create_session(
    request: CreateSessionRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """Create a new session linked to a file"""
    file_record = db.query(models.UploadedFile).filter(
        models.UploadedFile.id == request.file_id,
        models.UploadedFile.user_id == current_user.id
    ).first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    new_session = models.ChatSession(
        user_id=current_user.id,
        file_id=request.file_id,
        title=request.title
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    return {"id": new_session.id, "title": new_session.title}

@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """Delete a session"""
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    db.delete(session)
    db.commit()
    return {"status": "success"}

@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """Get history for a specific session"""
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    messages = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session_id
    ).order_by(models.ChatMessage.created_at.asc()).all()
    
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "timestamp": int(m.created_at.timestamp() * 1000),
            "steps": m.meta_data.get("steps") if m.meta_data else [],
            "vizConfig": m.meta_data.get("vizConfig") if m.meta_data else None
        }
        for m in messages
    ]

# --- 1. Generate SQL Draft (Legacy) ---
@router.post("/generate")
def generate_sql_draft(
    request: GenerateSqlRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    uploaded_file = db.query(models.UploadedFile).filter(
        models.UploadedFile.id == request.file_id,
        models.UploadedFile.user_id == current_user.id
    ).first()
    
    if not uploaded_file or not os.path.exists(uploaded_file.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        schema = get_db_schema(uploaded_file.file_path)
        
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

# --- 2. Execute SQL ---
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

# --- 3. Summary ---
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

# --- 4. Streaming Summary ---
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
        full_summary = ""
        try:
            schema = get_db_schema(uploaded_file.file_path)

            for chunk in generate_schema_summary_stream(
                schema,
                api_key=request.api_key,
                base_url=request.base_url,
                model=request.model
            ):
                full_summary += chunk
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            
            if request.session_id:
                session = db.query(models.ChatSession).filter(
                    models.ChatSession.id == request.session_id,
                    models.ChatSession.user_id == current_user.id
                ).first()
                
                if session:
                    new_msg = models.ChatMessage(
                        session_id=request.session_id,
                        role="model",
                        content=full_summary,
                        meta_data={"is_summary": True}
                    )
                    db.add(new_msg)
                    session.updated_at = func.now()
                    db.commit()

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# --- 5. Agent Agent Analysis with Streaming ---
@router.post("/agent/stream")
async def agent_analyze_stream(
    request: AgentAnalyzeRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == request.session_id,
        models.ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    uploaded_file = db.query(models.UploadedFile).filter(
        models.UploadedFile.id == session.file_id,
        models.UploadedFile.user_id == current_user.id
    ).first()

    if not uploaded_file or not os.path.exists(uploaded_file.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    file_path = uploaded_file.file_path
    session_id_str = session.id
    
    db_history = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session.id
    ).order_by(models.ChatMessage.created_at.asc()).all()
    
    history_count = len(db_history)

    user_msg = models.ChatMessage(
        session_id=session.id,
        role="user",
        content=request.message
    )
    db.add(user_msg)
    db.commit() 

    async def generate_stream() -> Iterator[str]:
        full_content = ""
        tool_steps = []
        current_tool = None
        viz_config = None

        try:
            schema = get_db_schema(file_path)

            # [修改] 传递 use_rag 参数
            for event in agent_analyze_database_stream(
                question=request.message,
                db_path=file_path,
                schema=schema,
                history=request.history,
                api_key=request.api_key,
                base_url=request.base_url,
                model=request.model,
                max_tool_rounds=request.max_tool_rounds,
                use_rag=request.use_rag # Pass Flag
            ):
                if event["type"] == "text":
                    full_content += event["content"]
                
                elif event["type"] == "tool_call":
                    current_tool = {
                        "tool": event["tool"],
                        "status": "start",
                        "input": event.get("sql_code", "")
                    }
                    tool_steps.append(current_tool)
                
                elif event["type"] == "tool_result":
                    if tool_steps and tool_steps[-1]["tool"] == event["tool"]:
                        tool_steps[-1]["status"] = event["status"]
                        tool_steps[-1]["output"] = str(event["result"])[:2000] 
                        
                        try:
                            res_obj = json.loads(event["result"])
                            if isinstance(res_obj, dict) and res_obj.get("type") == "visualization_config":
                                viz_config = res_obj.get("config")
                        except:
                            pass

                elif event["type"] == "error":
                    full_content += f"\n[Error: {event['error']}]"

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            if history_count == 0:
                db.query(models.ChatSession).filter(models.ChatSession.id == session_id_str).update(
                    {"title": request.message[:30], "updated_at": func.now()}
                )
            else:
                 db.query(models.ChatSession).filter(models.ChatSession.id == session_id_str).update(
                    {"updated_at": func.now()}
                )

            assistant_msg = models.ChatMessage(
                session_id=session_id_str,
                role="model",
                content=full_content,
                meta_data={
                    "steps": tool_steps,
                    "vizConfig": viz_config
                }
            )
            db.add(assistant_msg)
            db.commit()

        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"[ERROR] Exception in generate_stream: {type(e).__name__}: {str(e)}")
            
            err_msg = str(e)
            yield f"data: {json.dumps({'type': 'error', 'error': err_msg}, ensure_ascii=False)}\n\n"
            
            error_msg_db = models.ChatMessage(
                session_id=session_id_str,
                role="model",
                content=f"Error occurred: {err_msg}",
                meta_data={"error": True}
            )
            db.add(error_msg_db)
            db.commit()

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )