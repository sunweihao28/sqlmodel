
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List, Dict, Any, Iterator
import database, models, auth
from utils.db_utils import get_engine_for_source, get_db_schema_from_engine, execute_query_with_engine
from services.llm_service import generate_sql_from_text, generate_analysis, generate_schema_summary, generate_schema_summary_stream, fix_sql_query, agent_analyze_database_stream, summarize_user_history
from services.tools import execute_tool
import os
import json

router = APIRouter(prefix="/api/chat", tags=["chat"])

# --- Request Models ---

class GenerateSqlRequest(BaseModel):
    message: str
    file_id: Optional[int] = None
    connection_id: Optional[int] = None
    history: List[Dict[str, Any]] = [] 
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    use_rag: bool = False

class ExecuteSqlRequest(BaseModel):
    sql: str
    message: str
    file_id: Optional[int] = None
    connection_id: Optional[int] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None

class SummaryRequest(BaseModel):
    file_id: Optional[int] = None
    connection_id: Optional[int] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    session_id: Optional[str] = None

class AgentAnalyzeRequest(BaseModel):
    session_id: str
    message: str
    file_id: Optional[int] = None
    connection_id: Optional[int] = None
    history: List[Dict[str, Any]] = []
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tool_rounds: int = 12
    use_rag: bool = False
    enable_memory: bool = False
    allow_auto_execute: bool = True  # False = 需用户确认后再执行 SQL
    use_sql_expert: bool = False  # True = 使用增强 SQL 生成（仅 SQLite 上传文件）

class ConfirmSqlRequest(BaseModel):
    session_id: str
    sql: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    
class CreateSessionRequest(BaseModel):
    file_id: Optional[int] = None
    connection_id: Optional[int] = None
    title: str = "New Analysis"

class RefreshMemoryRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None

class UpdateMemoryRequest(BaseModel):
    content: str

# --- Endpoints ---

@router.get("/memory")
def get_user_memory(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """Get raw long-term memory"""
    return {"memory": current_user.long_term_memory or ""}

@router.post("/memory")
def update_user_memory(
    request: UpdateMemoryRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """Manually update long-term memory"""
    current_user.long_term_memory = request.content
    db.commit()
    return {"status": "success", "memory": current_user.long_term_memory}

@router.post("/memory/refresh")
def refresh_memory(
    request: RefreshMemoryRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Summarize all past chat sessions to generate/update the user's long-term memory.
    """
    # 1. Gather recent history from all sessions
    # Limit to last 500 messages to fit in context window approx
    recent_messages = db.query(models.ChatMessage).join(models.ChatSession).filter(
        models.ChatSession.user_id == current_user.id
    ).order_by(models.ChatMessage.created_at.desc()).limit(200).all()
    
    if not recent_messages:
        return {"status": "skipped", "message": "No history to summarize"}
    
    # Reorder to chronological
    recent_messages.reverse()
    
    history_text = ""
    for msg in recent_messages:
        role = "User" if msg.role == 'user' else "Assistant"
        history_text += f"{role}: {msg.content}\n"
        
    try:
        summary = summarize_user_history(
            history_text, 
            api_key=request.api_key, 
            base_url=request.base_url, 
            model=request.model
        )
        
        current_user.long_term_memory = summary
        db.commit()
        
        return {"status": "success", "memory": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate memory: {str(e)}")

@router.get("/sessions")
def get_sessions(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    sessions = db.query(models.ChatSession).filter(
        models.ChatSession.user_id == current_user.id
    ).order_by(models.ChatSession.updated_at.desc()).all()
    
    return [
        {
            "id": s.id, 
            "title": s.title, 
            "updatedAt": int(s.updated_at.timestamp() * 1000),
            "fileId": s.file_id,
            "connectionId": s.connection_id
        } 
        for s in sessions
    ]

@router.post("/sessions")
def create_session(
    request: CreateSessionRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    new_session = models.ChatSession(
        user_id=current_user.id,
        file_id=request.file_id,
        connection_id=request.connection_id,
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
            "vizConfig": m.meta_data.get("vizConfig") if m.meta_data else None,
            "status": m.meta_data.get("status") if m.meta_data else None,
            "sqlQuery": m.meta_data.get("sqlQuery") if m.meta_data else None
        }
        for m in messages
    ]

@router.post("/generate")
def generate_sql_draft(
    request: GenerateSqlRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    try:
        engine = get_engine_for_source(db, request.file_id, request.connection_id, current_user.id)
        schema = get_db_schema_from_engine(engine)
        
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

@router.post("/execute")
def execute_sql_command(
    request: ExecuteSqlRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    try:
        engine = get_engine_for_source(db, request.file_id, request.connection_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    result = execute_query_with_engine(engine, request.sql)
    
    if result.get("error"):
        try:
            schema = get_db_schema_from_engine(engine)
            fixed_sql = fix_sql_query(
                request.sql, 
                result['error'], 
                schema, 
                api_key=request.api_key, 
                base_url=request.base_url, 
                model=request.model
            )
            retry_result = execute_query_with_engine(engine, fixed_sql)
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

@router.post("/summary/stream")
async def get_database_summary_stream(
    request: SummaryRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    try:
        engine = get_engine_for_source(db, request.file_id, request.connection_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    async def generate_stream() -> Iterator[str]:
        full_summary = ""
        try:
            schema = get_db_schema_from_engine(engine)
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
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

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

    # [Fix] Extract primitive values from current_user before any commit/stream
    # This avoids DetachedInstanceError when accessing user attributes inside the async stream
    user_id_int = current_user.id
    user_memory_str = current_user.long_term_memory if request.enable_memory else None

    db_path = None
    connection_url = None
    schema = None # Default schema to None if no DB
    
    try:
        if session.file_id:
            file_record = db.query(models.UploadedFile).filter(models.UploadedFile.id == session.file_id).first()
            if file_record: db_path = file_record.file_path
        elif session.connection_id:
            conn_record = db.query(models.DatabaseConnection).filter(models.DatabaseConnection.id == session.connection_id).first()
            if conn_record:
                if conn_record.db_type == 'mysql':
                    connection_url = f"mysql+pymysql://{conn_record.username}:{conn_record.password}@{conn_record.host}:{conn_record.port}/{conn_record.database_name}"
                elif conn_record.db_type == 'postgres':
                    connection_url = f"postgresql+psycopg2://{conn_record.username}:{conn_record.password}@{conn_record.host}:{conn_record.port}/{conn_record.database_name}"
    except Exception:
        pass

    # [Fix] Allow processing without DB source (General Chat / Memory Chat)
    if db_path or connection_url:
        try:
            engine = get_engine_for_source(db, session.file_id, session.connection_id, user_id_int)
            schema = get_db_schema_from_engine(engine)
        except Exception as e:
             # If DB connection fails, we log it but continue so user can still chat
             print(f"Failed to inspect schema: {str(e)}")

    session_id_str = session.id
    
    # Save user message
    user_msg = models.ChatMessage(session_id=session.id, role="user", content=request.message)
    db.add(user_msg)
    db.commit() # This commits and expires ORM objects (current_user, session)
    
    # Use scalar query for count to avoid object expiration issues if possible, or simple query
    history_count = db.query(func.count(models.ChatMessage.id)).filter(models.ChatMessage.session_id == session_id_str).scalar()

    async def generate_stream() -> Iterator[str]:
        full_content = ""
        tool_steps = []
        current_tool = None
        viz_config = None
        needs_approval = False
        pending_sql = ""

        try:
            for event in agent_analyze_database_stream(
                question=request.message,
                db_path=db_path,
                connection_url=connection_url,
                schema=schema,
                history=request.history,
                api_key=request.api_key,
                base_url=request.base_url,
                model=request.model,
                max_tool_rounds=request.max_tool_rounds,
                use_rag=request.use_rag,
                allow_auto_execute=request.allow_auto_execute,
                user_memory=user_memory_str, # Use extracted string
                use_sql_expert=request.use_sql_expert,
                user_id=user_id_int, # Use extracted int
            ):
                if event["type"] == "text":
                    full_content += event["content"]
                elif event["type"] == "tool_call":
                    # If pending approval, we handle it differently
                    if event.get("status") == "pending_approval":
                         needs_approval = True
                         pending_sql = event.get("sql_code", "")
                         current_tool = {"tool": event["tool"], "status": "pending_approval", "input": pending_sql}
                         tool_steps.append(current_tool)
                    else:
                        current_tool = {"tool": event["tool"], "status": "start", "input": event.get("sql_code", "")}
                        tool_steps.append(current_tool)
                elif event["type"] == "tool_result":
                    if tool_steps and tool_steps[-1]["tool"] == event["tool"]:
                        tool_steps[-1]["status"] = event["status"]
                        tool_steps[-1]["output"] = str(event["result"])[:2000]
                        try:
                            res_obj = json.loads(event["result"])
                            # [Fix] Check for BOTH 'configs' (list) and 'config' (single)
                            if isinstance(res_obj, dict) and res_obj.get("type") == "visualization_config":
                                viz_config = res_obj.get("configs") or res_obj.get("config")
                        except: pass
                elif event["type"] == "error":
                    full_content += f"\n[Error: {event['error']}]"

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # Re-fetch session to ensure it's attached for update
            sess = db.query(models.ChatSession).filter(models.ChatSession.id == session_id_str).first()
            if sess:
                if history_count == 1: 
                    # Note: We rely on frontend to update title smartly, but backend can do a basic update if needed.
                    # If the frontend title generation works, this might be overwritten later or ignored.
                    # We only update if title is default.
                    if sess.title == "New Analysis" or sess.title.endswith(".sqlite") or sess.title.endswith(".db"):
                         sess.title = request.message[:30]
                sess.updated_at = func.now()
            
            # Save message to DB
            meta = {"steps": tool_steps}
            if viz_config:
                meta["vizConfig"] = viz_config
                
            if needs_approval:
                meta["status"] = "pending_approval"
                meta["sqlQuery"] = pending_sql
                
            assistant_msg = models.ChatMessage(
                session_id=session_id_str,
                role="model",
                content=full_content,
                meta_data=meta
            )
            db.add(assistant_msg)
            db.commit()

        except Exception as e:
            err_msg = str(e)
            yield f"data: {json.dumps({'type': 'error', 'error': err_msg}, ensure_ascii=False)}\n\n"
            # Try to log error to DB if possible
            try:
                db.add(models.ChatMessage(session_id=session_id_str, role="model", content=f"Error: {err_msg}", meta_data={"error": True}))
                db.commit()
            except: pass

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

@router.post("/agent/confirm")
async def confirm_and_resume_stream(
    request: ConfirmSqlRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Execute a pending SQL and resume agent generation.
    """
    # [Fix] Extract ID early
    user_id_int = current_user.id
    
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == request.session_id,
        models.ChatSession.user_id == user_id_int
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 1. Update previous message status to 'executed' AND append the user confirmation text
    last_msg = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session.id,
        models.ChatMessage.role == 'model'
    ).order_by(models.ChatMessage.created_at.desc()).first()
    
    if last_msg and last_msg.meta_data and last_msg.meta_data.get('status') == 'pending_approval':
        meta = dict(last_msg.meta_data)
        meta['status'] = 'executed'
        
        # [Fix] Append confirmation text to the content so it appears in history
        if "用户确认执行" not in last_msg.content and "User confirmed execution" not in last_msg.content:
            last_msg.content += "\n\n🚀 用户确认执行..."
            
        last_msg.meta_data = meta
        db.commit()

    # 2. Execute the Tool (SQL)
    db_path = None
    connection_url = None
    try:
        if session.file_id:
            file_record = db.query(models.UploadedFile).filter(models.UploadedFile.id == session.file_id).first()
            if file_record: db_path = file_record.file_path
        elif session.connection_id:
            conn_record = db.query(models.DatabaseConnection).filter(models.DatabaseConnection.id == session.connection_id).first()
            if conn_record:
                if conn_record.db_type == 'mysql':
                    connection_url = f"mysql+pymysql://{conn_record.username}:{conn_record.password}@{conn_record.host}:{conn_record.port}/{conn_record.database_name}"
                elif conn_record.db_type == 'postgres':
                    connection_url = f"postgresql+psycopg2://{conn_record.username}:{conn_record.password}@{conn_record.host}:{conn_record.port}/{conn_record.database_name}"
    except Exception:
        pass

    try:
        session_id_source = db_path if db_path else "remote_db"
        result = execute_tool(
            "sql_inter", 
            {"sql_query": request.sql}, 
            db_path=db_path, 
            connection_url=connection_url,
            session_id=session_id_source
        )
    except Exception as e:
        result = f"Error: {str(e)}"

    # 3. Resume the Stream
    msgs = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session.id
    ).order_by(models.ChatMessage.created_at.asc()).all()
    
    history_for_agent = []
    for m in msgs:
        history_for_agent.append({"role": m.role, "content": m.content})
    
    prompt = f"I have executed the SQL. Here is the result:\n{result}\n\nPlease analyze this data and answer my original question in Chinese (Simplified)."

    try:
        engine = get_engine_for_source(db, session.file_id, session.connection_id, user_id_int)
        schema = get_db_schema_from_engine(engine)
    except:
        schema = ""

    async def generate_resume_stream() -> Iterator[str]:
        full_content = ""
        tool_steps = []
        viz_config = None

        # [Important] First, yield the tool result so frontend can show "Success" immediately
        yield f"data: {json.dumps({'type': 'tool_result', 'tool': 'sql_inter', 'result': result, 'status': 'success'}, ensure_ascii=False)}\n\n"

        try:
            for event in agent_analyze_database_stream(
                question=prompt, 
                db_path=db_path,
                connection_url=connection_url,
                schema=schema,
                history=history_for_agent,
                api_key=request.api_key,
                base_url=request.base_url,
                model=request.model,
                max_tool_rounds=5, 
                use_rag=False, 
                allow_auto_execute=True,
                user_id=user_id_int # [New Param]
            ):
                if event["type"] == "text":
                    full_content += event["content"]
                elif event["type"] == "tool_call":
                    current_tool = {"tool": event["tool"], "status": "start", "input": event.get("sql_code", "")}
                    tool_steps.append(current_tool)
                elif event["type"] == "tool_result":
                    if tool_steps and tool_steps[-1]["tool"] == event["tool"]:
                        tool_steps[-1]["status"] = event["status"]
                        tool_steps[-1]["output"] = str(event["result"])[:2000]
                        try:
                            res_obj = json.loads(event["result"])
                            if isinstance(res_obj, dict) and res_obj.get("type") == "visualization_config":
                                viz_config = res_obj.get("configs") or res_obj.get("config")
                        except: pass
                elif event["type"] == "error":
                    full_content += f"\n[Error: {event['error']}]"

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # Re-fetch session to ensure update
            sess = db.query(models.ChatSession).filter(models.ChatSession.id == request.session_id).first()
            if sess:
                 sess.updated_at = func.now()
            
            # Save the new analysis as a new message
            meta = {"steps": tool_steps}
            # [Fix] Persist vizConfig if it exists in the resumed stream
            if viz_config:
                meta["vizConfig"] = viz_config
                
            assistant_msg = models.ChatMessage(
                session_id=request.session_id,
                role="model",
                content=full_content,
                meta_data=meta
            )
            db.add(assistant_msg)
            db.commit()

        except Exception as e:
            err_msg = str(e)
            yield f"data: {json.dumps({'type': 'error', 'error': err_msg}, ensure_ascii=False)}\n\n"
            try:
                db.add(models.ChatMessage(session_id=request.session_id, role="model", content=f"Error: {err_msg}", meta_data={"error": True}))
                db.commit()
            except: pass

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_resume_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )