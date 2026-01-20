
from google import genai
from openai import OpenAI
import os
from typing import List, Dict, Optional

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
