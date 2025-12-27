from google import genai
import os

# 默认使用环境变量中的 Key
DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY")

def _get_client(api_key: str = None):
    """获取最新的 Google GenAI 客户端"""
    key_to_use = api_key if api_key else DEFAULT_API_KEY
    if not key_to_use:
        # 如果没有 Key，记录日志但抛出明确错误
        print("Error: Gemini API Key is missing.")
        raise ValueError("API Key is missing. Please set GEMINI_API_KEY env var or provide it in Settings.")
    
    return genai.Client(api_key=key_to_use)

def generate_sql_from_text(question: str, schema: str, api_key: str = None) -> str:
    """根据 Schema 生成 SQL"""
    try:
        client = _get_client(api_key)
        prompt = f"""
        You are an expert SQLite Data Analyst. 
        Given the following database schema, write a valid SQL query to answer the user's question.
        
        SCHEMA:
        {schema}
        
        USER QUESTION: "{question}"
        
        INSTRUCTIONS:
        1. Return ONLY the SQL query. Do not include markdown formatting (like ```sql), do not include explanations.
        2. Use SQLite compatible syntax.
        3. If the question cannot be answered by the schema, return SELECT 'I cannot answer this question based on the data' as message;
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        if not response.text:
            return "SELECT 'Error: No response from model' as message"

        sql = response.text.strip()
        
        # 清理可能存在的 Markdown 代码块标记
        if sql.startswith("```"):
            lines = sql.split('\n')
            if lines[0].startswith("```"): lines = lines[1:]
            if lines and lines[-1].startswith("```"): lines = lines[:-1]
            sql = "\n".join(lines).strip()
            
        return sql
    except Exception as e:
        print(f"LLM SQL Generation Error: {e}")
        return f"SELECT 'Error: {str(e)}' as message"

def generate_analysis(question: str, data: list, api_key: str = None) -> str:
    """生成数据分析摘要"""
    try:
        client = _get_client(api_key)
        # 限制数据量以防 Token 溢出
        data_preview = str(data[:20]) 
        prompt = f"""
        User asked: "{question}"
        Data retrieved (first 20 rows): {data_preview}
        
        Provide a very brief (2 sentences) summary of this data in the same language as the question.
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text.strip() if response.text else "Analysis not available."
    except Exception as e:
        print(f"LLM Analysis Error: {e}")
        return f"Could not generate analysis: {str(e)}"

def generate_schema_summary(schema: str, api_key: str = None) -> str:
    """生成数据库结构总结"""
    try:
        client = _get_client(api_key)
        prompt = f"""
        You are a helpful Data Assistant.
        A user has just uploaded a new SQLite database file.
        
        Here is the SCHEMA of the database:
        {schema}
        
        Please provide a friendly summary of this database.
        1. Briefly explain what this database seems to be about (based on table names).
        2. List the main tables and their key fields (in bullet points).
        3. Suggest 3 interesting questions the user could ask about this data.
        
        Output format: Markdown.
        Language: Chinese (Simplified) unless the schema is strictly English.
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text.strip() if response.text else "Summary not available."
    except Exception as e:
        print(f"LLM Summary Error: {e}")
        return f"无法分析数据库结构，请检查 API Key 是否正确或网络连接。错误信息: {str(e)}"