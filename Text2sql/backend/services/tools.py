"""
工具函数模块
提供 SQL 执行、Python 代码执行和数据提取等功能
"""

import json
import pandas as pd
import re
from typing import Dict, Any
from sqlalchemy import create_engine, text

# ============================================================================
# 共享执行环境（按会话管理）
# ============================================================================

_PYTHON_EXEC_ENVIRONMENTS: Dict[str, Dict[str, Any]] = {}

def _get_exec_environment(session_id: str = "default") -> Dict[str, Any]:
    if session_id not in _PYTHON_EXEC_ENVIRONMENTS:
        _PYTHON_EXEC_ENVIRONMENTS[session_id] = {
            '__builtins__': __builtins__,
            'pd': pd,
            'json': json,
        }
    return _PYTHON_EXEC_ENVIRONMENTS[session_id]

# Helper to reconstruct engine from arguments passed by LLM service
def _get_engine_from_args(kwargs):
    if kwargs.get("db_path"):
        return create_engine(f"sqlite:///{kwargs['db_path']}")
    
    if kwargs.get("connection_url"):
        return create_engine(kwargs['connection_url'])
        
    raise ValueError("Missing database configuration (db_path or connection_url)")

def sql_inter(sql_query: str, db_path: str = None, connection_url: str = None) -> str:
    """
    SQL查询执行器
    """
    actual_sql = sql_query
    try:
        obj = json.loads(sql_query)
        if isinstance(obj, dict):
            for key in ("sql_query", "query", "sql", "sqlQuery"):
                if key in obj and isinstance(obj[key], str):
                    actual_sql = obj[key]
                    break
    except (json.JSONDecodeError, TypeError):
        pass

    # Ensure LIMIT for SELECT
    q = _ensure_select_limit(actual_sql, default_limit=50)

    try:
        engine = _get_engine_from_args({"db_path": db_path, "connection_url": connection_url})
        with engine.connect() as conn:
            df = pd.read_sql_query(text(q), conn)
            # Handle non-serializable types
            df = df.applymap(lambda x: str(x) if isinstance(x, (pd.Timestamp, pd.Timedelta)) else x)
            
            columns = df.columns.tolist()
            rows = df.values.tolist()
            row_count = len(rows)
            
            return json.dumps(
                {"columns": columns, "rows": rows, "row_count": row_count},
                ensure_ascii=False,
            )
    except Exception as e:
        return json.dumps(
            {"columns": [], "rows": [], "row_count": 0, "error": str(e)},
            ensure_ascii=False,
        )

def python_inter(py_code: str, session_id: str = "default") -> str:
    """
    Python代码执行器 (Standard implementation)
    """
    actual_code = py_code
    try:
        obj = json.loads(py_code)
        if isinstance(obj, dict):
            for key in ("py_code", "code", "python", "script", "source"):
                if key in obj and isinstance(obj[key], str):
                    actual_code = obj[key]
                    break
            if "session_id" in obj and isinstance(obj["session_id"], str):
                session_id = obj["session_id"]
    except (json.JSONDecodeError, TypeError):
        pass

    if "plt." in actual_code or "matplotlib" in actual_code:
        font_config = """
import matplotlib.pyplot as plt
import matplotlib
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
"""
        actual_code = font_config + actual_code

    exec_globals = _get_exec_environment(session_id)
    global_vars_before = set(exec_globals.keys())

    try:
        exec(actual_code, exec_globals)
        
        if 'visualization_config' in exec_globals:
            viz_config = exec_globals['visualization_config']
            if isinstance(viz_config, dict) and 'type' in viz_config and 'data' in viz_config:
                return json.dumps({"type": "visualization_config", "config": viz_config}, ensure_ascii=False)
        
        global_vars_after = set(exec_globals.keys())
        new_vars = global_vars_after - global_vars_before

        if new_vars:
            result = {var: str(exec_globals[var]) for var in new_vars if not var.startswith('_')}
            return str(result) if result else "Success"
        else:
            try:
                return str(eval(actual_code, exec_globals))
            except:
                return "Success"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"

def extract_data(sql_query: str, df_name: str = "df", db_path: str = None, connection_url: str = None, session_id: str = "default") -> str:
    """
    Extract data to DataFrame
    """
    actual_sql = sql_query
    actual_df_name = df_name

    try:
        obj = json.loads(sql_query)
        if isinstance(obj, dict):
            for key in ("sql_query", "query", "sql"):
                if key in obj and isinstance(obj[key], str):
                    actual_sql = obj[key]
                    break
            if "df_name" in obj: actual_df_name = obj["df_name"]
            if "session_id" in obj: session_id = obj["session_id"]
    except:
        pass

    try:
        engine = _get_engine_from_args({"db_path": db_path, "connection_url": connection_url})
        with engine.connect() as conn:
            df = pd.read_sql_query(text(actual_sql), conn)
            
        exec_globals = _get_exec_environment(session_id)
        exec_globals[actual_df_name] = df
        
        return f"Created variable {actual_df_name} with {len(df)} rows, {len(df.columns)} columns"
    except Exception as e:
        return f"Extraction Failed: {str(e)}"

def _ensure_select_limit(sql: str, default_limit: int = 50) -> str:
    sql_stripped = sql.strip()
    if re.match(r"^\s*SELECT\s+", sql_stripped, re.IGNORECASE):
        if "LIMIT" not in sql_stripped.upper():
            if sql_stripped.rstrip().endswith(";"):
                sql_stripped = sql_stripped.rstrip()[:-1]
                return f"{sql_stripped} LIMIT {default_limit};"
            else:
                return f"{sql_stripped} LIMIT {default_limit}"
    return sql_stripped

TOOLS_MAP = [
    {
        "name": "sql_inter",
        "description": "Execute SQL query on the database. Returns JSON result. SELECT queries are automatically limited to 50 rows.",
        "parameters": {
            "type": "object",
            "properties": {
                "sql_query": {"type": "string", "description": "Standard SQL Query (MySQL/PostgreSQL/SQLite compatible)"}
            },
            "required": ["sql_query"],
        },
    },
    {
        "name": "python_inter",
        "description": "Execute Python code for data analysis/visualization. Use 'visualization_config' variable for charts.",
        "parameters": {
            "type": "object",
            "properties": {
                "py_code": {"type": "string", "description": "Python script"}
            },
            "required": ["py_code"],
        },
    },
    {
        "name": "extract_data",
        "description": "Run SQL and load result into a pandas DataFrame variable.",
        "parameters": {
            "type": "object",
            "properties": {
                "sql_query": {"type": "string", "description": "SQL query"},
                "df_name": {"type": "string", "description": "Target variable name (default: df)", "default": "df"},
            },
            "required": ["sql_query"],
        },
    },
]

TOOLS_FUNCTIONS = {
    "sql_inter": sql_inter,
    "python_inter": python_inter,
    "extract_data": extract_data,
}

def get_tool_function(tool_name: str):
    if tool_name not in TOOLS_FUNCTIONS:
        raise ValueError(f"Unknown tool: {tool_name}")
    return TOOLS_FUNCTIONS[tool_name]

def execute_tool(tool_name: str, arguments: Dict[str, Any], db_path: str = None, connection_url: str = None, session_id: str = None) -> str:
    tool_func = get_tool_function(tool_name)
    
    if tool_name in ("sql_inter", "extract_data"):
        if not db_path and not connection_url:
             raise ValueError(f"{tool_name} requires a database source (db_path or connection_url)")
        arguments["db_path"] = db_path
        arguments["connection_url"] = connection_url
    
    if session_id is None:
        session_id = db_path if db_path else (connection_url if connection_url else "default")
    
    if tool_name in ("python_inter", "extract_data"):
        arguments["session_id"] = session_id
    
    return tool_func(**arguments)
