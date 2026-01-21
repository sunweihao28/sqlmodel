
from google import genai
from openai import OpenAI
import os
import json
from typing import List, Dict, Optional, Iterator, Any
from services.tools import TOOLS_MAP, TOOLS_FUNCTIONS, execute_tool

# 默认使用环境变量中的 Key
DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY")

def _call_llm(prompt: str, model_name: str = 'gpt-4o', api_key: str = None, base_url: str = None) -> str:
    """
    统一的 LLM 调用接口
    - 如果提供了 base_url，则使用 OpenAI 客户端
    - 否则默认使用 Google Gemini SDK
    """
    try:
        if base_url:
            # 使用 OpenAI 兼容模式
            client = OpenAI(api_key=api_key or "sk-dummy", base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            print(f"base_url:{base_url},api_key:{api_key} LLM Response ({model_name}): {response}")
            return response.choices[0].message.content
        else:
            # 使用 Google Gemini SDK
            # 注意：Gemini 某些新模型可能需要特定配置
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
        # 如果出错，返回错误信息，方便前端展示
        return f"LLM Error: {str(e)}"

def generate_sql_from_text(question: str, history: List[Dict], schema: str, api_key: str = None, base_url: str = None, model: str = None) -> str:
    """根据 Schema 和对话历史生成 SQL"""
    # 格式化历史记录
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
    """自我修复：当 SQL 执行出错时调用"""
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
    """生成数据分析摘要"""
    data_preview = str(data[:20]) 
    prompt = f"""
    User asked: "{question}"
    Data retrieved (first 20 rows): {data_preview}
    
    Provide a very brief (2 sentences) summary of this data in the same language as the question.
    """
    return _call_llm(prompt, model or 'gemini-2.5-flash', api_key, base_url)

def generate_schema_summary(schema: str, api_key: str = None, base_url: str = None, model: str = None) -> str:
    """生成数据库结构总结"""
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
    """流式生成数据库结构总结"""
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

    # 根据不同的LLM提供商选择流式调用方式
    if base_url:
        # OpenAI兼容流式调用
        yield from _stream_openai_compatible(prompt, model or 'gpt-4o', api_key, base_url)
    else:
        # Gemini流式调用
        yield from _stream_gemini(prompt, model or 'gemini-2.5-flash', api_key)

def _stream_openai_compatible(prompt: str, model: str, api_key: str, base_url: str) -> Iterator[str]:
    """OpenAI兼容流式调用"""
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)

        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,  # 启用流式输出
            temperature=0.7,
        )

        for chunk in stream:
            # 完善的None检查
            if not chunk or not hasattr(chunk, 'choices') or not chunk.choices:
                continue

            choice = chunk.choices[0] if len(chunk.choices) > 0 else None
            if not choice or not hasattr(choice, 'delta'):
                continue

            delta = choice.delta
            if delta and hasattr(delta, 'content') and delta.content:
                yield delta.content

    except Exception as e:
        print(f"OpenAI compatible stream error: {str(e)}")
        yield f"Error: {str(e)}"

def _stream_gemini(prompt: str, model: str, api_key: str) -> Iterator[str]:
    """Gemini流式调用"""
    try:
        # 处理API Key
        key_to_use = api_key or os.environ.get("GEMINI_API_KEY")
        if not key_to_use:
            yield "Error: API Key is missing for Gemini."
            return

        client = genai.Client(api_key=key_to_use)

        # Gemini的流式调用
        response = client.models.generate_content_stream(
            model=model if "gemini" in model else 'gemini-2.5-flash',
            contents=prompt
        )

        for chunk in response:
            # 完善的None检查
            if chunk and hasattr(chunk, 'text') and chunk.text:
                yield chunk.text

    except Exception as e:
        print(f"Gemini stream error: {str(e)}")
        yield f"Error: {str(e)}"

def _clean_sql(text: str) -> str:
    """辅助函数：清理 Markdown 标记"""
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
    db_path: str,
    schema: str,
    history: List[Dict] = None,
    api_key: str = None,
    base_url: str = None,
    model: str = None,
    max_tool_rounds: int = 12
) -> Iterator[Dict[str, Any]]:
    """
    流式Agent推理函数：自主调用工具函数进行数据库分析（流式输出）
    
    参数:
        question: 用户问题
        db_path: SQLite数据库文件路径
        schema: 数据库schema信息
        history: 对话历史记录（可选）
        api_key: LLM API Key
        base_url: LLM Base URL（如果提供则使用OpenAI兼容模式）
        model: 模型名称
        max_tool_rounds: 最大工具调用轮数（防止无限循环）
    
    返回:
        生成器，yield字典格式：
        - {"type": "text", "content": "..."}  # 模型生成的文本
        - {"type": "tool_call", "tool": "sql_inter", "status": "start"}  # 工具调用开始
        - {"type": "tool_result", "tool": "sql_inter", "result": "..."}  # 工具执行结果
        - {"type": "done"}  # 完成标志
        - {"type": "error", "error": "..."}  # 错误信息
    """
    # 初始化客户端
    if base_url:
        client = OpenAI(api_key=api_key or "sk-dummy", base_url=base_url)
    else:
        key_to_use = api_key or os.environ.get("GEMINI_API_KEY")
        if not key_to_use:
            yield {"type": "error", "error": "API Key is missing. Please provide api_key or set GEMINI_API_KEY."}
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
    
    # 构建系统提示
    system_prompt = f"""你是一位专业的数据分析助手，擅长使用SQL和Python进行数据分析。

数据库Schema信息:
{schema}

可用工具:
1. sql_inter: 执行SQL查询，返回结构化数据（columns, rows, row_count）
2. extract_data: 将SQL查询结果加载到pandas DataFrame供Python使用
3. python_inter: 执行Python代码进行数据处理、分析和可视化配置生成

可视化说明:
- 如需生成图表，在Python代码中创建 'visualization_config' 字典变量
- 配置格式：{{"type": "bar|line|pie|table", "title": "...", "xAxis": {{"key": "..."}}, "data": [...]}}
- 前端会根据配置自动渲染图表，无需使用matplotlib

工作流程:
- 根据用户问题，选择合适的工具进行分析
- 可以连续多次调用工具（例如：先查询数据，再提取到DataFrame，最后生成可视化配置）
- SQL查询会自动添加LIMIT 50限制（如需更多数据可使用extract_data）
- 如果SQL执行失败，分析错误信息并尝试修复或使用其他方法

重要要求:
- 每次工具调用完成后，必须在下一轮响应中生成文本回答，总结分析结果
- 如果工具执行成功，请解释结果的含义，并基于数据给出洞察
- 如果工具执行失败，请分析原因并提出解决方案
- 最终必须给出完整的、有意义的文本回答，不能只调用工具而不给出结论

请根据用户需求自主决定调用哪些工具以及调用顺序，最终给出完整的分析结果。
"""
    
    # 构建初始消息
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    
    if history_text:
        messages.append({"role": "user", "content": history_text})
    
    messages.append({"role": "user", "content": question})
    
    # 准备工具配置
    tools = [{"type": "function", "function": tool_def} for tool_def in TOOLS_MAP]
    
    # 工具调用循环
    tool_rounds = 0
    
    while tool_rounds < max_tool_rounds:
        tool_rounds += 1
        
        try:
            # 调用LLM（支持工具调用和流式输出）
            try:
                response = client.chat.completions.create(
                    model=model or ('gpt-4o' if base_url else 'gemini-2.5-flash'),
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    stream=True,  # 启用流式输出
                )
            except Exception as api_error:
                error_msg = f"LLM API调用失败: {type(api_error).__name__}: {str(api_error)}"
                print(f"Error calling LLM API: {error_msg}")
                yield {"type": "error", "error": error_msg}
                return
            
            response_message_content = ""
            tool_calls = []
            
            # 处理流式响应
            chunk_count = 0
            for chunk in response:
                chunk_count += 1
                try:
                    if not chunk or not hasattr(chunk, 'choices') or not chunk.choices:
                        continue
                    
                    if len(chunk.choices) == 0:
                        continue
                    
                    choice = chunk.choices[0]
                    if not choice or not hasattr(choice, 'delta'):
                        continue
                    
                    delta = choice.delta
                    if not delta:
                        continue
                    
                    # 收集文本内容
                    if hasattr(delta, 'content') and delta.content:
                        response_message_content += delta.content
                        yield {"type": "text", "content": delta.content}
                        print(f"DEBUG: Received text content chunk: {len(delta.content)} chars")
                    
                    # 收集工具调用
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            if not hasattr(tc_delta, 'index'):
                                continue
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
                    # 记录错误但继续处理
                    print(f"Error processing chunk in agent_analyze_database_stream: {e}")
                    continue
            
            # 流式响应处理完成后，检查是否有工具调用
            print(f"DEBUG: Stream processing complete. Chunks processed: {chunk_count}, Content length: {len(response_message_content)}, Tool calls: {len(tool_calls)}")
            
            # 过滤掉 None 值和无效的工具调用
            valid_tool_calls = [
                tc for tc in tool_calls 
                if tc is not None and tc.get("function", {}).get("name")
            ]
            
            print(f"DEBUG: Valid tool calls: {len(valid_tool_calls)}")
            
            if not valid_tool_calls:
                # 如果没有工具调用，返回最终结果
                # 检查是否有之前的工具调用历史
                has_tool_history = any(
                    msg.get("role") == "tool" for msg in messages
                )
                
                if not response_message_content:
                    # 如果没有任何内容，但有工具执行历史，说明工具已执行但没有生成文本回答
                    if has_tool_history:
                        print("DEBUG: Tool execution completed but no text response generated")
                        # 尝试基于工具执行结果生成一个总结
                        last_tool_results = [
                            msg.get("content", "") for msg in messages[-3:] 
                            if msg.get("role") == "tool"
                        ]
                        if last_tool_results:
                            # 基于最后一个工具结果生成简单总结
                            last_result = last_tool_results[-1]
                            try:
                                result_obj = json.loads(last_result)
                                if isinstance(result_obj, dict) and "columns" in result_obj:
                                    row_count = result_obj.get("row_count", len(result_obj.get("rows", [])))
                                    response_message_content = f"查询已完成，共返回 {row_count} 条结果。"
                                else:
                                    response_message_content = "工具执行已完成。"
                            except:
                                response_message_content = "分析已完成。"
                        else:
                            response_message_content = "分析已完成。"
                    else:
                        print("DEBUG: No content and no tool calls, yielding default message")
                        response_message_content = "分析完成。"
                    yield {"type": "text", "content": response_message_content}
                else:
                    print(f"DEBUG: No tool calls but has content ({len(response_message_content)} chars)")
                yield {"type": "done"}
                return
            
            # 构建完整的响应消息
            assistant_msg = {
                "role": "assistant",
                "content": response_message_content,
                "tool_calls": valid_tool_calls
            }
            messages.append(assistant_msg)
            
            # 执行所有工具调用
            for tool_call in valid_tool_calls:
                function_name = tool_call["function"]["name"]
                function_args_str = tool_call["function"]["arguments"]
                
                # 解析参数
                try:
                    function_args = json.loads(function_args_str)
                except json.JSONDecodeError:
                    if function_name == "python_inter":
                        function_args = {"py_code": function_args_str}
                    elif function_name == "sql_inter":
                        function_args = {"sql_query": function_args_str}
                    elif function_name == "extract_data":
                        function_args = {"sql_query": function_args_str, "df_name": "df"}
                    else:
                        function_args = {}
                
                # 提取SQL代码（如果是sql_inter工具）
                sql_code = None
                if function_name == "sql_inter" and "sql_query" in function_args:
                    sql_code = function_args["sql_query"]
                
                # 通知工具调用开始（包含SQL代码，如果有）
                tool_call_event = {"type": "tool_call", "tool": function_name, "status": "start"}
                if sql_code:
                    tool_call_event["sql_code"] = sql_code
                yield tool_call_event
                
                # 执行工具函数
                try:
                    # 使用db_path作为session_id，确保同一数据库的请求共享执行环境
                    session_id = db_path
                    
                    if function_name in ("sql_inter", "extract_data"):
                        result = execute_tool(function_name, function_args, db_path=db_path, session_id=session_id)
                    else:
                        result = execute_tool(function_name, function_args, session_id=session_id)
                    
                    # 通知工具执行结果
                    yield {
                        "type": "tool_result",
                        "tool": function_name,
                        "result": result,
                        "status": "success"
                    }
                    
                    # 将工具执行结果添加到消息
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": function_name,
                        "content": result
                    })
                    
                except Exception as e:
                    error_msg = f"工具执行错误 ({function_name}): {type(e).__name__}: {str(e)}"
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
            import traceback
            error_detail = f"分析过程中出错: {type(e).__name__}: {str(e)}"
            print(f"Error in agent_analyze_database_stream: {error_detail}")
            print(traceback.format_exc())
            yield {"type": "error", "error": error_detail}
            yield {"type": "done"}  # 确保前端知道流已结束
            return
    
    # 达到最大轮数
    error_msg = f"已达到最大工具调用轮数（{max_tool_rounds}），分析已中断。"
    yield {"type": "error", "error": error_msg}
    # 即使出错也要确保完成事件被发送
    yield {"type": "done"}
