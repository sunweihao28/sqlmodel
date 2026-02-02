
from google import genai
from openai import OpenAI
import os
import json
from typing import List, Dict, Optional, Iterator, Any
from services.tools import TOOLS_MAP, TOOLS_FUNCTIONS, execute_tool
from services.rag_service import rag_service_instance # Import RAG

# 默认使用环境变量中的 Key
DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY")

def _call_llm(prompt: str, model_name: str = 'gpt-4o', api_key: str = None, base_url: str = None) -> str:
    # ... existing implementation ...
    try:
        if base_url:
            client = OpenAI(api_key=api_key or "sk-dummy", base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        else:
            key_to_use = api_key if api_key else DEFAULT_API_KEY
            if not key_to_use:
                raise ValueError("API Key is missing for Gemini.")
            
            client = genai.Client(api_key=key_to_use)
            response = client.models.generate_content(
                model=model_name if "gemini" in model_name else 'gemini-2.5-flash',
                contents=prompt
            )
            return response.text
    except Exception as e:
        print(f"LLM Call Error ({model_name}): {e}")
        return f"LLM Error: {str(e)}"

# ... existing SQL generation functions (generate_sql_from_text, fix_sql_query, etc.) ...

def generate_sql_from_text(question: str, history: List[Dict], schema: str, api_key: str = None, base_url: str = None, model: str = None) -> str:
    # ... existing code ...
    history_text = ""
    if history:
        history_text = "CONVERSATION HISTORY:\n"
        for msg in history[-5:]: 
            role = "User" if msg['role'] == 'user' else "Assistant"
            content = msg.get('content', '')
            history_text += f"{role}: {content}\n"
    
    prompt = f"""
    You are an expert SQLite Data Analyst. 
    Given the database schema and conversation history, write a valid SQL query to answer the user's *current* question.
    
    SCHEMA:
    {schema}
    
    {history_text}
    
    CURRENT USER QUESTION: "{question}"
    
    INSTRUCTIONS:
    1. Return ONLY the SQL query. Do not include markdown formatting (like ```sql), do not include explanations.
    2. Use SQLite compatible syntax.
    3. If the user asks for a chart or visualization, just select the data needed for it.
    4. If the question cannot be answered by the schema, return SELECT 'I cannot answer this question based on the data' as message;
    """
    
    response = _call_llm(prompt, model or 'gemini-2.5-flash', api_key, base_url)
    return _clean_sql(response)

def fix_sql_query(bad_sql: str, error_msg: str, schema: str, api_key: str = None, base_url: str = None, model: str = None) -> str:
    # ... existing code ...
    prompt = f"""
    You are a SQL debugging expert. 
    I tried to execute a query on this SQLite database, but it failed.
    
    SCHEMA:
    {schema}
    
    FAILED QUERY:
    {bad_sql}
    
    ERROR MESSAGE:
    {error_msg}
    
    INSTRUCTION:
    1. Analyze the error and the schema.
    2. Correct the SQL query to fix the error.
    3. Return ONLY the corrected SQL query. No text.
    """
    
    response = _call_llm(prompt, model or 'gemini-2.5-flash', api_key, base_url)
    return _clean_sql(response)

def generate_analysis(question: str, data: list, api_key: str = None, base_url: str = None, model: str = None) -> str:
    # ... existing code ...
    data_preview = str(data[:20]) 
    prompt = f"""
    User asked: "{question}"
    Data retrieved (first 20 rows): {data_preview}
    
    Provide a very brief (2 sentences) summary of this data in Chinese (Simplified).
    """
    return _call_llm(prompt, model or 'gemini-2.5-flash', api_key, base_url)

def generate_schema_summary(schema: str, api_key: str = None, base_url: str = None, model: str = None) -> str:
    # ... existing code ...
    prompt = f"""
    You are a helpful Data Assistant.
    A user has just uploaded a new SQLite database file.

    Here is the SCHEMA of the database:
    {schema}

    Please provide a friendly summary of this database.
    1. Tell the user what is your model name(gpt-4o, gemini-2.5-flash, or others).
    2. Briefly explain what this database seems to be about (based on table names).
    3. List the main tables and their key fields (in bullet points).
    4. Suggest 3 interesting questions the user could ask about this data.

    Output format: Markdown.
    Language: Chinese (Simplified) .
    """
    return _call_llm(prompt, model or 'gemini-2.5-flash', api_key, base_url)

def generate_schema_summary_stream(schema: str, api_key: str = None, base_url: str = None, model: str = None) -> Iterator[str]:
    # ... existing code ...
    prompt = f"""
    You are a helpful Data Assistant.
    A user has just uploaded a new SQLite database file.

    Here is the SCHEMA of the database:
    {schema}

    Please provide a friendly summary of this database.
    1. Tell the user what is your model name(gpt-4o, gemini-2.5-flash, or others).
    2. Briefly explain what this database seems to be about (based on table names).
    3. List the main tables and their key fields (in bullet points).
    4. Suggest 3 interesting questions the user could ask about this data.

    Output format: Markdown.
    Language: Chinese (Simplified).
    """

    if base_url:
        yield from _stream_openai_compatible(prompt, model or 'gpt-4o', api_key, base_url)
    else:
        yield from _stream_gemini(prompt, model or 'gemini-2.5-flash', api_key)

def summarize_user_history(history_text: str, api_key: str = None, base_url: str = None, model: str = None) -> str:
    """
    生成用户的长期记忆/画像摘要
    """
    prompt = f"""
请阅读以下的历史对话记录，并将其浓缩为一个简洁的用户画像/摘要。

要求：
1. 提取用户的个性化偏好（如喜欢的图表类型、关注的数据领域）。
2. 提取用户经常查询的关键业务指标或结论。
3. 省略日常寒暄和非必要的对话细节。
4. 输出一段连贯的文本，作为后续对话的"长期记忆"背景。
5. 不要添加任何开场白或结束语，直接输出摘要内容。

历史记录内容：
{history_text}
"""
    return _call_llm(prompt, model or 'gemini-2.5-flash', api_key, base_url)

def _stream_openai_compatible(prompt: str, model: str, api_key: str, base_url: str) -> Iterator[str]:
    # ... existing code ...
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            temperature=0.7,
        )
        for chunk in stream:
            if not chunk or not hasattr(chunk, 'choices') or not chunk.choices: continue
            choice = chunk.choices[0] if len(chunk.choices) > 0 else None
            if not choice or not hasattr(choice, 'delta'): continue
            delta = choice.delta
            if delta and hasattr(delta, 'content') and delta.content:
                yield delta.content
    except Exception as e:
        print(f"OpenAI compatible stream error: {str(e)}")
        yield f"Error: {str(e)}"

def _stream_gemini(prompt: str, model: str, api_key: str) -> Iterator[str]:
    # ... existing code ...
    try:
        key_to_use = api_key or os.environ.get("GEMINI_API_KEY")
        if not key_to_use:
            yield "Error: API Key is missing for Gemini."
            return
        client = genai.Client(api_key=key_to_use)
        response = client.models.generate_content_stream(
            model=model if "gemini" in model else 'gemini-2.5-flash',
            contents=prompt
        )
        for chunk in response:
            if chunk and hasattr(chunk, 'text') and chunk.text:
                yield chunk.text
    except Exception as e:
        print(f"Gemini stream error: {str(e)}")
        yield f"Error: {str(e)}"

def _clean_sql(text: str) -> str:
    # ... existing code ...
    if not text: return ""
    sql = text.strip()
    if sql.startswith("```"):
        lines = sql.split('\n')
        if lines[0].startswith("```"): lines = lines[1:]
        if lines and lines[-1].startswith("```"): lines = lines[:-1]
        sql = "\n".join(lines).strip()
    return sql

def agent_analyze_database_stream(
    question: str,
    schema: str,
    db_path: str = None, 
    connection_url: str = None, 
    history: List[Dict] = None,
    api_key: str = None,
    base_url: str = None,
    model: str = None,
    max_tool_rounds: int = 12,
    use_rag: bool = False,
    allow_auto_execute: bool = False,
    user_memory: str = None # [New Param]
) -> Iterator[Dict[str, Any]]:
    """
    流式Agent推理函数
    """
    # 1. RAG Context
    rag_context = ""
    if use_rag:
        try:
            docs = rag_service_instance.hybrid_search(
                question, 
                api_key=api_key, 
                base_url=base_url
            )
            if docs:
                rag_context = "\n\n【知识库参考信息 (RAG Retrieval)】:\n"
                for i, doc in enumerate(docs):
                    rag_context += f"文档片段 {i+1} (来源: {doc.metadata.get('original_file', 'unknown')}):\n{doc.page_content}\n---\n"
                
                yield {"type": "text", "content": f"📚 已检索到 {len(docs)} 条相关知识库文档...\n\n"}
        except Exception as e:
            print(f"RAG search error: {e}")
            yield {"type": "error", "error": f"RAG检索失败: {str(e)}"}

    # 2. Memory Context [New]
    memory_context = ""
    if user_memory:
        memory_context = f"\n\n【用户长期记忆/画像 (User Memory)】:\n{user_memory}\n请基于此画像了解用户的偏好和关注点。\n"
        yield {"type": "text", "content": f"🧠 已加载用户长期记忆...\n\n"}

    # 初始化客户端
    if base_url:
        client = OpenAI(api_key=api_key or "sk-dummy", base_url=base_url)
    else:
        key_to_use = api_key or os.environ.get("GEMINI_API_KEY")
        if not key_to_use:
            yield {"type": "error", "error": "API Key is missing."}
            return
        client = OpenAI(api_key=key_to_use)
    
    # 格式化历史记录
    history_text = ""
    if history:
        history_text = "\nCONVERSATION HISTORY:\n"
        for msg in history[-5:]:
            role = "User" if msg.get('role') == 'user' else "Assistant"
            content = msg.get('content', '')
            history_text += f"{role}: {content}\n"
    
    # 构建系统提示 (注入 RAG Context 和 Memory Context)
    system_prompt = f"""你是一位专业的数据分析助手，擅长使用SQL和Python进行数据分析。

数据库Schema信息:
{schema}

{rag_context}
{memory_context}

可用工具:
1. sql_inter: 执行SQL查询，返回结构化数据（columns, rows, row_count）
2. extract_data: 将SQL查询结果加载到pandas DataFrame供Python使用
3. python_inter: 执行Python代码进行数据处理、分析和可视化配置生成

可视化说明:
- 如需生成图表，在Python代码中创建 'visualization_config' 字典变量
- 配置格式：{{"type": "bar|line|pie|table", "title": "...", "xAxis": {{"key": "..."}}, "data": [...]}}
- 前端会根据配置自动渲染图表，无需使用matplotlib

工作流程:
- 根据用户问题{ "、参考的知识库信息" if rag_context else "" }{ "及用户长期记忆" if user_memory else "" }，选择合适的工具进行分析
- 可以连续多次调用工具
- SQL查询会自动添加LIMIT 50限制
- 如果SQL执行失败，分析错误信息并尝试修复

重要要求:
- 优先参考知识库中的业务定义、指标计算公式或字段说明。
- **最终回答必须使用中文(Simplified Chinese)**。
- 如果需要确认执行SQL，请生成相应的工具调用。
"""
    
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    
    if history_text:
        messages.append({"role": "user", "content": history_text})
    
    messages.append({"role": "user", "content": question})
    
    tools = [{"type": "function", "function": tool_def} for tool_def in TOOLS_MAP]
    
    tool_rounds = 0
    
    while tool_rounds < max_tool_rounds:
        tool_rounds += 1
        
        try:
            try:
                response = client.chat.completions.create(
                    model=model or ('gpt-4o' if base_url else 'gemini-2.5-flash'),
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    stream=True,
                )
            except Exception as api_error:
                error_msg = f"LLM API调用失败: {type(api_error).__name__}: {str(api_error)}"
                yield {"type": "error", "error": error_msg}
                return
            
            response_message_content = ""
            tool_calls = []
            
            for chunk in response:
                try:
                    if not chunk or not hasattr(chunk, 'choices') or not chunk.choices: continue
                    if len(chunk.choices) == 0: continue
                    choice = chunk.choices[0]
                    if not choice or not hasattr(choice, 'delta'): continue
                    delta = choice.delta
                    if not delta: continue
                    
                    if hasattr(delta, 'content') and delta.content:
                        response_message_content += delta.content
                        yield {"type": "text", "content": delta.content}
                    
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            if not hasattr(tc_delta, 'index'): continue
                            idx = tc_delta.index
                            if idx >= len(tool_calls):
                                tool_calls.extend([None] * (idx + 1 - len(tool_calls)))
                            if tool_calls[idx] is None:
                                tool_calls[idx] = {
                                    "id": getattr(tc_delta, 'id', '') or "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""}
                                }
                            if hasattr(tc_delta, 'function') and tc_delta.function:
                                if hasattr(tc_delta.function, 'name') and tc_delta.function.name:
                                    tool_calls[idx]["function"]["name"] = tc_delta.function.name
                                if hasattr(tc_delta.function, 'arguments') and tc_delta.function.arguments:
                                    tool_calls[idx]["function"]["arguments"] += tc_delta.function.arguments
                except Exception as e:
                    continue
            
            valid_tool_calls = [tc for tc in tool_calls if tc is not None and tc.get("function", {}).get("name")]
            
            if not valid_tool_calls:
                if not response_message_content:
                    yield {"type": "text", "content": "分析完成。"}
                yield {"type": "done"}
                return
            
            assistant_msg = {
                "role": "assistant",
                "content": response_message_content,
                "tool_calls": valid_tool_calls
            }
            messages.append(assistant_msg)
            
            for tool_call in valid_tool_calls:
                function_name = tool_call["function"]["name"]
                function_args_str = tool_call["function"]["arguments"]
                
                try:
                    function_args = json.loads(function_args_str)
                except json.JSONDecodeError:
                    if function_name == "python_inter": function_args = {"py_code": function_args_str}
                    elif function_name == "sql_inter": function_args = {"sql_query": function_args_str}
                    elif function_name == "extract_data": function_args = {"sql_query": function_args_str, "df_name": "df"}
                    else: function_args = {}
                
                sql_code = None
                if function_name == "sql_inter" and "sql_query" in function_args:
                    sql_code = function_args["sql_query"]
                if function_name == "extract_data" and "sql_query" in function_args:
                    sql_code = function_args["sql_query"]
                
                # Intercept SQL execution OR Data Extraction if auto_execute is False
                if function_name in ("sql_inter", "extract_data") and not allow_auto_execute:
                    yield {
                        "type": "tool_call",
                        "tool": function_name,
                        "status": "pending_approval",
                        "sql_code": sql_code
                    }
                    yield {"type": "done"}
                    return
                
                # Normal execution
                tool_call_event = {"type": "tool_call", "tool": function_name, "status": "start"}
                if sql_code: tool_call_event["sql_code"] = sql_code
                yield tool_call_event
                
                try:
                    session_id = db_path if db_path else "remote_db"
                    
                    if function_name in ("sql_inter", "extract_data"):
                        result = execute_tool(
                            function_name, 
                            function_args, 
                            db_path=db_path, 
                            connection_url=connection_url,
                            session_id=session_id
                        )
                    else:
                        result = execute_tool(function_name, function_args, session_id=session_id)
                    
                    yield {
                        "type": "tool_result",
                        "tool": function_name,
                        "result": result,
                        "status": "success"
                    }
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": function_name,
                        "content": result
                    })
                except Exception as e:
                    error_msg = f"Error ({function_name}): {str(e)}"
                    yield {
                        "type": "tool_result",
                        "tool": function_name,
                        "result": error_msg,
                        "status": "error"
                    }
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": function_name,
                        "content": error_msg
                    })
            
        except Exception as e:
            error_detail = f"Process Error: {str(e)}"
            yield {"type": "error", "error": error_detail}
            yield {"type": "done"}
            return
    
    yield {"type": "error", "error": "Max tool rounds reached."}
    yield {"type": "done"}