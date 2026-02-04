
from google import genai
from google.genai import types
from openai import OpenAI
import os
import json
import time
from typing import List, Dict, Optional, Iterator, Any
from services.tools import TOOLS_MAP, TOOLS_FUNCTIONS, execute_tool
from services.rag_service import rag_service_instance  # Import RAG
from services.enhanced_sql import generate_sql_enhanced

# 加载环境变量中的 Key
DEFAULT_GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DEFAULT_OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

def _should_use_gemini(model_name: str, base_url: str = None) -> bool:
    """
    判断是否应该使用 Google GenAI 原生客户端。
    规则：
    1. 如果提供了 base_url，通常是 OpenAI 兼容接口（DeepSeek, OneAPI等），返回 False。
    2. 如果没有 base_url，且模型名包含 'gemini'，返回 True。
    3. 其他情况（如 gpt-4o 且无 base_url），默认使用 OpenAI 官方接口，返回 False。
    """
    if base_url:
        return False
    if model_name and "gemini" in model_name.lower():
        return True
    return False

def _call_llm(prompt: str, model_name: str = 'gpt-4o', api_key: str = None, base_url: str = None) -> str:
    try:
        use_gemini = _should_use_gemini(model_name, base_url)
        
        if not use_gemini:
            # OpenAI / Compatible
            key = api_key or DEFAULT_OPENAI_KEY
            if not key and not base_url:
                print(f"Warning: No API Key found for OpenAI model {model_name}")
            
            client = OpenAI(api_key=key or "sk-dummy", base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        else:
            # Gemini Native
            key = api_key or DEFAULT_GEMINI_KEY
            if not key:
                raise ValueError("API Key is missing for Gemini.")
            
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            return response.text
    except Exception as e:
        print(f"LLM Call Error ({model_name}): {e}")
        return f"LLM Error: {str(e)}"

def generate_sql_from_text(question: str, history: List[Dict], schema: str, api_key: str = None, base_url: str = None, model: str = None) -> str:
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
    data_preview = str(data[:20]) 
    prompt = f"""
    User asked: "{question}"
    Data retrieved (first 20 rows): {data_preview}
    
    Provide a very brief (2 sentences) summary of this data in Chinese (Simplified).
    """
    return _call_llm(prompt, model or 'gemini-2.5-flash', api_key, base_url)

def generate_schema_summary(schema: str, api_key: str = None, base_url: str = None, model: str = None) -> str:
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

    use_gemini = _should_use_gemini(model, base_url)
    
    if not use_gemini:
        yield from _stream_openai_compatible(prompt, model or 'gpt-4o', api_key, base_url)
    else:
        yield from _stream_gemini(prompt, model or 'gemini-2.5-flash', api_key)

def summarize_user_history(history_text: str, api_key: str = None, base_url: str = None, model: str = None) -> str:
    prompt = f"""
请阅读以下的历史对话记录，并将其浓缩为一个简洁的用户画像/摘要。
历史记录内容：
{history_text}
"""
    return _call_llm(prompt, model or 'gemini-2.5-flash', api_key, base_url)

def _stream_openai_compatible(prompt: str, model: str, api_key: str, base_url: str) -> Iterator[str]:
    try:
        key = api_key or DEFAULT_OPENAI_KEY
        client = OpenAI(api_key=key or "sk-dummy", base_url=base_url)
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
    try:
        key_to_use = api_key or DEFAULT_GEMINI_KEY
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
    allow_auto_execute: bool = True,
    user_memory: str = None,
    use_sql_expert: bool = False,
    user_id: int = None,
) -> Iterator[Dict[str, Any]]:
    """
    流式Agent推理函数 (Supports both OpenAI and Gemini Native)
    """
    # 1. RAG Context
    rag_context = ""
    if use_rag and user_id: 
        try:
            docs = rag_service_instance.hybrid_search(
                user_id,
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

    # 2. Memory Context
    memory_context = ""
    if user_memory:
        memory_context = f"\n\n【用户长期记忆/画像 (User Memory)】:\n{user_memory}\n请基于此画像了解用户的偏好和关注点。\n"
        yield {"type": "text", "content": f"🧠 已加载用户长期记忆...\n\n"}

    # Determine Provider
    is_gemini = _should_use_gemini(model, base_url)
    
    # Initialize Clients
    client = None
    if not is_gemini:
        key = api_key or DEFAULT_OPENAI_KEY
        client = OpenAI(api_key=key or "sk-dummy", base_url=base_url)
    else:
        key_to_use = api_key or DEFAULT_GEMINI_KEY
        if not key_to_use:
            yield {"type": "error", "error": "API Key is missing for Gemini."}
            return
        client = genai.Client(api_key=key_to_use)
    
    # 格式化历史记录
    history_text = ""
    if history:
        history_text = "\nCONVERSATION HISTORY:\n"
        for msg in history[-5:]:
            role = "User" if msg.get('role') == 'user' else "Assistant"
            content = msg.get('content', '')
            history_text += f"{role}: {content}\n"
    
    # 构建系统提示 - 根据是否有 schema 区分模式
    if schema:
        # DB Connected Mode
        system_prompt = f"""你是一位专业的数据分析助手，擅长使用SQL和Python进行数据分析。

数据库Schema信息:
{schema}

{rag_context}
{memory_context}

可用工具:
1. sql_inter: 执行SQL查询，返回结构化数据（columns, rows, row_count）
2. extract_data: 将SQL查询结果加载到pandas DataFrame供Python使用
3. python_inter: 执行Python代码进行数据处理、分析和可视化配置生成

可视化说明：若需在前端展示图表或表格，在 Python 中必须将 visualization_config 赋值为列表（一个或多个配置），由前端按顺序内联渲染：
  visualization_config = [
    {{"type": "table", "title": "图表标题", "data": [{{"列名A": "值1", "列名B": 100}}, {{"列名A": "值2", "列名B": 200}}]}},
    {{"type": "bar", "title": "另一张图", "data": [...]}}
  ]
  type 可为 "table"/"bar"/"line"/"pie"。data 为行列表，每行一个 dict，单元格仅限 str/int/float/bool/None；从 DataFrame 用 to_dict(orient='records') 或先转基本类型。无需 matplotlib。仅生成可视化配置即可；回复正文中禁止用 Markdown 或文字再次输出同一份表格/图表数据，总结时用自然表述即可。

工作流程:
- 根据用户问题{ "、参考的知识库信息" if rag_context else "" }{ "及用户长期记忆" if user_memory else "" }，选择合适的工具进行分析
- 可以连续多次调用工具
- SQL查询会自动添加LIMIT 50限制
- 如果SQL执行失败，分析错误信息并尝试修复

重要要求:
- 优先参考知识库中的业务定义、指标计算公式或字段说明。
- **最终回答必须使用中文(Simplified Chinese)**。
- 如果需要确认执行SQL，请生成相应的工具调用。
- 若已通过 python_inter 的 visualization_config 生成了表格或图表，则**不要在回复正文中用 Markdown 表格（|...|）或逐行数据再次列出**，用简短自然的话概括结论即可，不要套用固定话术。
"""
    else:
        # General Chat Mode (No DB)
        system_prompt = f"""你是一位智能助手。当前用户未连接任何数据库，因此无法执行 SQL 查询或访问数据表。

{rag_context}
{memory_context}

你可以进行通用对话、逻辑推理、代码编写（使用 python_inter）或回答基于知识库/长期记忆的问题。
如果用户要求查询数据库数据，请礼貌地提示用户先连接数据库或上传文件。

可用工具:
1. python_inter: 执行通用 Python 代码计算或逻辑验证。

**最终回答必须使用中文(Simplified Chinese)**。
"""

    # Messages structure
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    if history_text:
        messages.append({"role": "user", "content": history_text})
    messages.append({"role": "user", "content": question})
    
    # Tools definition - Filter SQL tools if no schema
    all_tools = [{"type": "function", "function": tool_def} for tool_def in TOOLS_MAP]
    if not schema:
        # Only keep python_inter for general purpose, remove SQL tools
        tools = [t for t in all_tools if t["function"]["name"] == "python_inter"]
    else:
        tools = all_tools
        
    gemini_tools = [t['function'] for t in tools]
    
    tool_rounds = 0
    
    while tool_rounds < max_tool_rounds:
        tool_rounds += 1
        
        # --- Retry Loop for Network Instability ---
        max_retries = 3
        retry_delay = 1
        
        response_message_content = ""
        tool_calls = []
        
        success = False
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Reset accumulators for this attempt
                response_message_content = ""
                tool_calls = []
                
                if is_gemini:
                    # --- GEMINI NATIVE PATH ---
                    # Convert messages to Gemini Format
                    gemini_contents = []
                    for m in messages:
                        if m['role'] == 'system': continue
                        if m['role'] == 'user':
                            gemini_contents.append(types.Content(role='user', parts=[types.Part(text=m['content'])]))
                        elif m['role'] == 'assistant':
                            parts = []
                            if m.get('content'): parts.append(types.Part(text=m['content']))
                            if m.get('tool_calls'):
                                for tc in m['tool_calls']:
                                    args = {}
                                    try: args = json.loads(tc['function']['arguments'])
                                    except: pass
                                    parts.append(types.Part(function_call=types.FunctionCall(name=tc['function']['name'], args=args)))
                            gemini_contents.append(types.Content(role='model', parts=parts))
                        elif m['role'] == 'tool':
                            gemini_contents.append(types.Content(role='user', parts=[types.Part(
                                function_response=types.FunctionResponse(name=m['name'], response={'result': m['content']})
                            )]))

                    # Prepare config with available tools (might be empty list if no tools allowed, but here we at least have python)
                    gemini_config = types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.1
                    )
                    if gemini_tools:
                         gemini_config.tools = [types.Tool(function_declarations=gemini_tools)]

                    response = client.models.generate_content_stream(
                        model=model or 'gemini-2.5-flash',
                        contents=gemini_contents,
                        config=gemini_config
                    )

                    for chunk in response:
                        if chunk.text:
                            response_message_content += chunk.text
                            yield {"type": "text", "content": chunk.text}
                        if chunk.function_calls:
                            for fc in chunk.function_calls:
                                tool_calls.append({
                                    "id": "gemini_call_id", 
                                    "type": "function",
                                    "function": {
                                        "name": fc.name,
                                        "arguments": json.dumps(fc.args) 
                                    }
                                })
                else:
                    # --- OPENAI COMPATIBLE PATH ---
                    # If no tools available (e.g. extremely restricted mode), don't pass tools param
                    req_kwargs = {
                        "model": model or 'gpt-4o',
                        "messages": messages,
                        "stream": True,
                    }
                    if tools:
                        req_kwargs["tools"] = tools
                        req_kwargs["tool_choice"] = "auto"

                    response = client.chat.completions.create(**req_kwargs)
                    
                    for chunk in response:
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

                success = True
                break  # Break retry loop on success

            except Exception as e:
                last_error = e
                print(f"LLM Stream Error (Attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    yield {"type": "text", "content": "\n⚠️ [网络波动，正在重试...]\n"}
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    # Final attempt failed
                    pass
        
        if not success:
             error_detail = f"Process Error: {str(last_error)}"
             yield {"type": "error", "error": error_detail}
             yield {"type": "done"}
             return

        # --- End of Retry Loop ---

        try:
            # --- COMMON LOGIC: Execute Tools & Update History ---
            
            valid_tool_calls = [tc for tc in tool_calls if tc is not None and tc.get("function", {}).get("name")]
            
            if not valid_tool_calls:
                if not response_message_content:
                    # fallback just in case
                    yield {"type": "text", "content": "分析完成。"}
                yield {"type": "done"}
                return
            
            # Append assistant message to history
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

                # SQL 专家模式
                if use_sql_expert and db_path and function_name in ("sql_inter", "extract_data"):
                    expert_sql = generate_sql_enhanced(
                        question=question,
                        db_path=db_path,
                        api_key=api_key,
                        base_url=base_url,
                        model=model,
                    )
                    if expert_sql:
                        sql_code = expert_sql
                        function_args = {**function_args, "sql_query": expert_sql}

                # Human-in-the-loop SQL Check
                if function_name in ("sql_inter", "extract_data") and not allow_auto_execute:
                    yield {
                        "type": "tool_call",
                        "tool": function_name,
                        "status": "pending_approval",
                        "sql_code": sql_code
                    }
                    yield {"type": "done"}
                    return
                
                # Yield Tool Call Event
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
                        "tool_call_id": tool_call.get("id", "gemini_id"),
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
                        "tool_call_id": tool_call.get("id", "gemini_id"),
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