"""
工具函数模块
提供 SQL 执行、Python 代码执行和数据提取等功能
"""

import ast
import json
import pandas as pd
import re
from typing import Dict, Any, List, Optional, Union
from sqlalchemy import create_engine, text


def _normalize_visualization_data(data: Any) -> List[Dict[str, Any]]:
    """
    将 visualization_config 的 data 规范为扁平行数组，且每个单元格为可序列化基本类型。
    避免前端收到嵌套 list/dict 时显示为 [object Object]。
    """
    if data is None:
        return []
    if isinstance(data, pd.DataFrame):
        try:
            data = data.applymap(lambda x: str(x) if isinstance(x, (pd.Timestamp, pd.Timedelta)) else x)
            data = data.to_dict(orient='records')
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    out = []
    for row in data:
        if not isinstance(row, dict):
            continue
        new_row = {}
        for k, v in row.items():
            if v is None or isinstance(v, (str, int, float, bool)):
                new_row[k] = v
            elif isinstance(v, (pd.Timestamp, pd.Timedelta)):
                new_row[k] = str(v)
            elif isinstance(v, list):
                if len(v) == 0:
                    new_row[k] = ""
                elif all(isinstance(x, (str, int, float, bool)) for x in v):
                    new_row[k] = ", ".join(str(x) for x in v)
                else:
                    new_row[k] = f"[{len(v)} 条记录]"
            elif isinstance(v, dict):
                try:
                    s = json.dumps(v, ensure_ascii=False)
                    new_row[k] = s if len(s) <= 200 else s[:200] + "..."
                except (TypeError, ValueError):
                    new_row[k] = "[对象]"
            else:
                new_row[k] = str(v)
        out.append(new_row)
    return out


def _extract_viz_config(value: Any) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    从任意变量值中尝试提取符合前端要求的可视化配置（dict 含 type 和 data）。
    支持：单个 dict、list 单元素、list 中每个元素均为 config 时展开为多个、字符串（JSON 或 Python 字面量）。
    返回单个 dict、或 list of dict（多个 config），或 None。
    """
    if value is None:
        return None
    if isinstance(value, dict) and "type" in value and "data" in value:
        return dict(value)
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        d = value[0]
        if "type" in d and "data" in d:
            return dict(d)
    if isinstance(value, list) and len(value) > 0 and all(isinstance(x, dict) for x in value):
        if all("type" in x and "data" in x for x in value):
            return [dict(x) for x in value]
        return {"type": "table", "title": "数据", "data": value}
    if isinstance(value, str):
        for parse_fn in (json.loads, ast.literal_eval):
            try:
                parsed = parse_fn(value)
                if isinstance(parsed, dict) and "type" in parsed and "data" in parsed:
                    return dict(parsed)
                if isinstance(parsed, list) and len(parsed) > 0 and all(isinstance(x, dict) for x in parsed):
                    if all("type" in x and "data" in x for x in parsed):
                        return [dict(x) for x in parsed]
                    return {"type": "table", "title": "数据", "data": parsed}
            except (json.JSONDecodeError, SyntaxError, ValueError, TypeError):
                continue
    return None


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
        
        def _to_config_list(raw: Any) -> List[Dict[str, Any]]:
            """统一转为 config 列表：单个 dict 包装成 [dict]，list 取其中符合 type+data 的项。"""
            if raw is None:
                return []
            if isinstance(raw, dict) and "type" in raw and "data" in raw:
                return [dict(raw)]
            if isinstance(raw, list):
                out = []
                for x in raw:
                    if isinstance(x, dict) and "type" in x and "data" in x:
                        out.append(dict(x))
                return out
            return []

        configs = []
        if "visualization_config" in exec_globals:
            configs = _to_config_list(exec_globals["visualization_config"])
        if not configs:
            global_vars_after = set(exec_globals.keys())
            new_vars = global_vars_after - global_vars_before
            for key in sorted(new_vars):
                if key.startswith("_"):
                    continue
                result = _extract_viz_config(exec_globals[key])
                if result is None:
                    continue
                configs.extend(_to_config_list(result))

        if configs:
            for c in configs:
                c["data"] = _normalize_visualization_data(c.get("data"))
            def _config_key(c):
                data = c.get("data")
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    return (c.get("title"), tuple(sorted(data[0].keys())), len(data))
                return (c.get("title"), (), len(data) if isinstance(data, list) else 0)
            seen = set()
            unique = [c for c in configs if (k := _config_key(c)) not in seen and not seen.add(k)]
            return json.dumps({"type": "visualization_config", "configs": unique}, ensure_ascii=False)

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
        "description": "Execute Python code for data analysis/visualization. Set 'visualization_config' for charts/tables. Do NOT duplicate the same table or chart in your text response (no markdown tables or row-by-row data); summarize briefly in your own words.",
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
