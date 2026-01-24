
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
    session_id: Optional[str] = None # Added: Optional session ID to save summary

class AgentAnalyzeRequest(BaseModel):
    session_id: str
    message: str
    file_id: int
    history: List[Dict[str, Any]] = []
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tool_rounds: int = 12

class CreateSessionRequest(BaseModel):
    file_id: int
    title: str = "New Analysis"

# --- Session Management Endpoints ---

# [修改] 获取会话列表：前端左侧栏使用
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

# [修改] 创建新会话：上传文件后或点击"New Chat"时调用
@router.post("/sessions")
def create_session(
    request: CreateSessionRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """Create a new session linked to a file"""
    # 验证文件归属
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

# [新增] 删除会话
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

# [修改] 获取某个会话的详细历史消息：点击侧边栏会话时调用
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
            "steps": m.meta_data.get("steps") if m.meta_data else [], # 恢复思考步骤
            "vizConfig": m.meta_data.get("vizConfig") if m.meta_data else None # 恢复图表配置
        }
        for m in messages
    ]

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
        full_summary = ""
        try:
            schema = get_db_schema(uploaded_file.file_path)

            # 使用流式LLM调用
            for chunk in generate_schema_summary_stream(
                schema,
                api_key=request.api_key,
                base_url=request.base_url,
                model=request.model
            ):
                full_summary += chunk
                # SSE 格式: "data: {json}\n\n"
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            
            # [Added] Save summary to database if session_id is provided
            if request.session_id:
                # 简单验证 session 所有权
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
                    # 更新 session 时间戳
                    session.updated_at = func.now()
                    db.commit()

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
    # 1. 验证 Session 和关联的文件
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

    # [FIX] 提前提取需要的属性，防止进入 async generator 后发生 DetachedInstanceError
    # 因为 db.commit() 会导致 session 中的对象过期
    file_path = uploaded_file.file_path
    session_id_str = session.id
    
    # [修改] 2. 从数据库加载历史记录，构建上下文
    db_history = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session.id
    ).order_by(models.ChatMessage.created_at.asc()).all()
    
    history_count = len(db_history)

    history_context = [
        {"role": "user" if msg.role == "user" else "assistant", "content": msg.content}
        for msg in db_history
    ]

    # [修改] 3. 立即保存用户的提问到数据库
    user_msg = models.ChatMessage(
        session_id=session.id,
        role="user",
        content=request.message
    )
    db.add(user_msg)
    db.commit() # 这里 commit 后，session 和 uploaded_file 对象会过期

    async def generate_stream() -> Iterator[str]:
        full_content = ""
        tool_steps = []
        current_tool = None
        viz_config = None

        try:
            # 使用预先提取的 file_path
            schema = get_db_schema(file_path)

            # 使用流式Agent分析
            for event in agent_analyze_database_stream(
                question=request.message,
                db_path=file_path, # 使用预先提取的 path
                schema=schema,
                history=request.history,
                api_key=request.api_key,
                base_url=request.base_url,
                model=request.model,
                max_tool_rounds=request.max_tool_rounds
            ):
                # [修改] 收集流式过程中的数据，用于最后存库
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
                        # 截断过长的输出以节省数据库空间
                        tool_steps[-1]["output"] = str(event["result"])[:2000] 
                        
                        # 如果是可视化配置，提取出来单独存
                        try:
                            res_obj = json.loads(event["result"])
                            if isinstance(res_obj, dict) and res_obj.get("type") == "visualization_config":
                                viz_config = res_obj.get("config")
                        except:
                            pass

                elif event["type"] == "error":
                    full_content += f"\n[Error: {event['error']}]"

                # 实时推送到前端
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # [修改] 4. 流式结束后，保存 AI 的完整回复到数据库
            
            # 使用预先提取的 session_id_str
            # 如果是新会话（历史记录为0），自动生成标题
            if history_count == 0:
                # 注意：这里需要重新获取 session 对象或者直接更新，因为 session 对象可能已 detached
                # 简单起见，我们直接执行 update 语句
                db.query(models.ChatSession).filter(models.ChatSession.id == session_id_str).update(
                    {"title": request.message[:30], "updated_at": func.now()}
                )
            else:
                 db.query(models.ChatSession).filter(models.ChatSession.id == session_id_str).update(
                    {"updated_at": func.now()}
                )

            assistant_msg = models.ChatMessage(
                session_id=session_id_str, # 使用 ID 字符串
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
            print(f"[ERROR] Traceback:\n{error_traceback}")
            
            err_msg = str(e)
            yield f"data: {json.dumps({'type': 'error', 'error': err_msg}, ensure_ascii=False)}\n\n"
            
            # 出错也记录一下
            error_msg_db = models.ChatMessage(
                session_id=session_id_str,
                role="model",
                content=f"Error occurred: {err_msg}",
                meta_data={"error": True}
            )
            db.add(error_msg_db)
            db.commit()

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