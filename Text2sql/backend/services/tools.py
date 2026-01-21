"""
工具函数模块
提供 SQL 执行、Python 代码执行和数据提取等功能
"""

import json
import sqlite3
import pandas as pd
import re
from typing import Dict, Any

# ============================================================================
# 共享执行环境（按会话管理）
# ============================================================================

# 存储每个会话的Python执行环境
# key: 会话标识符（可以是db_path或其他唯一标识）
# value: 执行环境的全局变量字典
_PYTHON_EXEC_ENVIRONMENTS: Dict[str, Dict[str, Any]] = {}

def _get_exec_environment(session_id: str = "default") -> Dict[str, Any]:
    """
    获取或创建指定会话的Python执行环境
    
    参数:
        session_id: 会话标识符（默认使用"default"）
    
    返回:
        执行环境的全局变量字典
    """
    if session_id not in _PYTHON_EXEC_ENVIRONMENTS:
        _PYTHON_EXEC_ENVIRONMENTS[session_id] = {
            '__builtins__': __builtins__,
            'pd': pd,
            'json': json,
        }
    return _PYTHON_EXEC_ENVIRONMENTS[session_id]

def _clear_exec_environment(session_id: str = "default"):
    """
    清除指定会话的执行环境（可选，用于清理资源）
    """
    if session_id in _PYTHON_EXEC_ENVIRONMENTS:
        del _PYTHON_EXEC_ENVIRONMENTS[session_id]


def sql_inter(sql_query: str, db_path: str = None) -> str:
    """
    SQL查询执行器（结构化输出）
    
    参数:
        sql_query: SQL查询语句（支持JSON格式的字符串）
        db_path: SQLite数据库文件路径（可选，如果不提供则需要外部设置）
    
    返回:
        JSON格式字符串: {"columns": [...], "rows": [...], "row_count": n}
        SELECT查询默认自动添加 LIMIT 50（如果用户没有指定LIMIT）
    
    支持:
        - 直接传入SQL字符串
        - JSON格式的参数: {"sql_query": "..."}
    """
    if not db_path:
        raise ValueError("db_path参数是必需的，请提供SQLite数据库文件路径")
    
    # 先尝试从 JSON 中提取 SQL（容错处理）
    actual_sql = sql_query
    try:
        obj = json.loads(sql_query)
        if isinstance(obj, dict):
            # 尝试多种可能的 key
            for key in ("sql_query", "query", "sql", "sqlQuery"):
                if key in obj and isinstance(obj[key], str):
                    actual_sql = obj[key]
                    break
    except (json.JSONDecodeError, TypeError):
        # 不是 JSON 格式，直接使用原始字符串
        pass

    # 确保SELECT查询有LIMIT（默认50）
    q = _ensure_select_limit(actual_sql, default_limit=50)

    try:
        conn = sqlite3.connect(db_path)
        
        # 使用pandas读取SQL查询结果
        df = pd.read_sql_query(q, conn)
        
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
    finally:
        if conn:
            conn.close()


def python_inter(py_code: str, session_id: str = "default") -> str:
    """
    Python代码执行器
    
    参数:
        py_code: Python代码字符串（支持JSON格式的参数）
        session_id: 会话标识符，用于共享执行环境（默认"default"）
    
    返回:
        执行结果字符串，如果有错误则返回错误信息
    
    支持:
        - 直接传入Python代码字符串
        - JSON格式的参数: {"py_code": "..."}
        - 自动注入matplotlib中文字体配置
        - 可以访问extract_data创建的DataFrame变量
    """
    # 先尝试从 JSON 中提取代码（容错处理）
    actual_code = py_code
    try:
        obj = json.loads(py_code)
        if isinstance(obj, dict):
            # 尝试多种可能的 key
            for key in ("py_code", "code", "python", "script", "source"):
                if key in obj and isinstance(obj[key], str):
                    actual_code = obj[key]
                    break
            # 检查是否包含session_id
            if "session_id" in obj and isinstance(obj["session_id"], str):
                session_id = obj["session_id"]
    except (json.JSONDecodeError, TypeError):
        # 不是 JSON 格式，直接使用原始字符串
        pass

    # 检测是否包含 matplotlib 绘图代码，如果是则注入中文字体配置
    if "plt." in actual_code or "matplotlib" in actual_code:
        font_config = """
# ===== 自动注入：中文字体配置 =====
import matplotlib.pyplot as plt
import matplotlib
# Windows 系统常用中文字体
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'SimSun', 'KaiTi', 'FangSong', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
# ===== 中文字体配置结束 =====

"""
        actual_code = font_config + actual_code

    # 获取共享的执行环境
    exec_globals = _get_exec_environment(session_id)
    
    # 获取执行前的全局变量（用于检测新创建的变量）
    global_vars_before = set(exec_globals.keys())

    try:
        exec(actual_code, exec_globals)
        
        # 检查是否生成了可视化配置
        if 'visualization_config' in exec_globals:
            viz_config = exec_globals['visualization_config']
            if isinstance(viz_config, dict):
                # 验证配置格式
                if 'type' in viz_config and 'data' in viz_config:
                    # 返回可视化配置JSON
                    return json.dumps({
                        "type": "visualization_config",
                        "config": viz_config
                    }, ensure_ascii=False)
        
        # 获取执行后新创建的变量
        global_vars_after = set(exec_globals.keys())
        new_vars = global_vars_after - global_vars_before

        if new_vars:
            result = {var: str(exec_globals[var]) for var in new_vars if not var.startswith('_')}
            return str(result) if result else "已经顺利执行代码"
        else:
            # 尝试eval获取返回值
            try:
                return str(eval(actual_code, exec_globals))
            except:
                return "已经顺利执行代码"
    except Exception as e:
        return f"执行错误: {type(e).__name__}: {str(e)}"


def extract_data(sql_query: str, df_name: str = "df", db_path: str = None, session_id: str = "default") -> str:
    """
    将SQL查询结果加载到pandas DataFrame变量中
    
    参数:
        sql_query: SQL查询语句（支持JSON格式的参数）
        df_name: DataFrame变量名（默认"df"）
        db_path: SQLite数据库文件路径（可选，如果不提供则需要外部设置）
        session_id: 会话标识符，用于共享执行环境（默认"default"）
    
    返回:
        确认消息字符串
    
    支持:
        - 将数据库数据加载到共享执行环境供后续Python代码使用
        - 支持自定义DataFrame变量名
        - JSON格式的参数解析
    """
    if not db_path:
        raise ValueError("db_path参数是必需的，请提供SQLite数据库文件路径")
    
    # 先尝试从 JSON 中提取参数（容错处理）
    actual_sql = sql_query
    actual_df_name = df_name

    # 如果 sql_query 是 JSON 格式，尝试解析
    try:
        obj = json.loads(sql_query)
        if isinstance(obj, dict):
            for key in ("sql_query", "query", "sql", "sqlQuery"):
                if key in obj and isinstance(obj[key], str):
                    actual_sql = obj[key]
                    break
            # 同时检查是否包含 df_name 和 session_id
            if "df_name" in obj and isinstance(obj["df_name"], str):
                actual_df_name = obj["df_name"]
            if "session_id" in obj and isinstance(obj["session_id"], str):
                session_id = obj["session_id"]
    except (json.JSONDecodeError, TypeError):
        pass

    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql(actual_sql, conn)
        conn.close()

        # 将DataFrame存储到共享的执行环境中
        exec_globals = _get_exec_environment(session_id)
        exec_globals[actual_df_name] = df
        
        return f"已成功完成 {actual_df_name} 变量创建（共 {len(df)} 行，{len(df.columns)} 列）"
    except Exception as e:
        return f"提取数据失败: {type(e).__name__}: {str(e)}"


# ============================================================================
# 辅助函数
# ============================================================================

def _ensure_select_limit(sql: str, default_limit: int = 50) -> str:
    """
    确保SELECT查询有LIMIT子句（如果没有则添加）
    
    参数:
        sql: SQL查询语句
        default_limit: 默认限制行数
    
    返回:
        添加了LIMIT的SQL语句（如果原本没有）
    """
    sql_stripped = sql.strip()
    # 检查是否是SELECT查询且没有LIMIT
    if re.match(r"^\s*SELECT\s+", sql_stripped, re.IGNORECASE):
        if "LIMIT" not in sql_stripped.upper():
            # 简单处理：在末尾添加LIMIT（如果最后有分号则插入分号之前）
            if sql_stripped.rstrip().endswith(";"):
                sql_stripped = sql_stripped.rstrip()[:-1]
                return f"{sql_stripped} LIMIT {default_limit};"
            else:
                return f"{sql_stripped} LIMIT {default_limit}"
    return sql_stripped


# ============================================================================
# Tools Schema 定义（用于LLM函数调用）
# ============================================================================

TOOLS_MAP = [
    {
        "name": "sql_inter",
        "description": "在SQLite数据库上执行SQL查询，返回JSON格式结果: {columns, rows, row_count}。SELECT查询默认自动添加LIMIT 50。",
        "parameters": {
            "type": "object",
            "properties": {
                "sql_query": {
                    "type": "string",
                    "description": "要执行的SQL语句"
                }
            },
            "required": ["sql_query"],
        },
    },
    {
        "name": "python_inter",
        "description": """执行Python代码进行数据处理、分析和可视化配置生成。
        
重要：如果需要生成图表或表格，请创建名为 'visualization_config' 的字典变量，格式如下：
{
    "type": "bar|line|pie|table",  # 图表类型
    "title": "图表标题",
    "displayType": "table|chart|both",  # 显示类型：仅表格、仅图表、两者都显示（默认：both）
    "xAxis": {"key": "数据字段名", "label": "X轴标签"},
    "yAxis": {"key": "数据字段名", "label": "Y轴标签"},  # 可选
    "data": [{"字段1": 值1, "字段2": 值2}, ...],  # 图表数据
    "series": [{"key": "字段名", "name": "系列名"}, ...]  # 可选，用于多系列图表
}

示例：
# 只显示图表，不显示表格
df = ...  # 从extract_data获取
visualization_config = {
    "type": "bar",
    "title": "各部门预算对比",
    "displayType": "chart",  # 只显示图表
    "xAxis": {"key": "dept_name", "label": "部门名称"},
    "yAxis": {"key": "budget", "label": "预算金额"},
    "data": df.to_dict('records')
}

# 只显示表格，不显示图表
visualization_config = {
    "type": "table",
    "title": "数据详情",
    "displayType": "table",  # 只显示表格
    "data": df.to_dict('records')
}

# 同时显示表格和图表（默认行为）
visualization_config = {
    "type": "pie",
    "title": "各系教师平均薪资占比",
    "displayType": "both",  # 同时显示表格和图表
    "data": df.to_dict('records')
}

前端会自动根据此配置渲染，无需使用matplotlib。""",
        "parameters": {
            "type": "object",
            "properties": {
                "py_code": {
                    "type": "string",
                    "description": "要执行的Python代码"
                }
            },
            "required": ["py_code"],
        },
    },
    {
        "name": "extract_data",
        "description": "将SQL查询结果加载到pandas DataFrame变量中，供后续Python代码使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "sql_query": {
                    "type": "string",
                    "description": "用于读取数据的SQL查询语句"
                },
                "df_name": {
                    "type": "string",
                    "description": "DataFrame变量名（默认: df）",
                    "default": "df"
                },
            },
            "required": ["sql_query"],
        },
    },
]


# ============================================================================
# 工具函数注册表（用于快速查找和调用）
# ============================================================================

TOOLS_FUNCTIONS = {
    "sql_inter": sql_inter,
    "python_inter": python_inter,
    "extract_data": extract_data,
}


def get_tool_function(tool_name: str):
    """
    根据工具名称获取工具函数
    
    参数:
        tool_name: 工具名称（"sql_inter", "python_inter", "extract_data"）
    
    返回:
        工具函数对象
    
    抛出:
        ValueError: 如果工具名称不存在
    """
    if tool_name not in TOOLS_FUNCTIONS:
        raise ValueError(f"未知的工具函数: {tool_name}")
    return TOOLS_FUNCTIONS[tool_name]


def execute_tool(tool_name: str, arguments: Dict[str, Any], db_path: str = None, session_id: str = None) -> str:
    """
    执行工具函数（统一接口）
    
    参数:
        tool_name: 工具名称
        arguments: 工具参数字典
        db_path: 数据库路径（对sql_inter和extract_data必需）
        session_id: 会话标识符（用于共享执行环境，如果不提供则使用db_path作为session_id）
    
    返回:
        工具执行结果（字符串）
    
    示例:
        execute_tool("sql_inter", {"sql_query": "SELECT * FROM users LIMIT 10"}, "/path/to/db.db")
        execute_tool("python_inter", {"py_code": "print('Hello')"})
    """
    tool_func = get_tool_function(tool_name)
    
    # 对于需要db_path的工具，自动添加db_path参数
    if tool_name in ("sql_inter", "extract_data"):
        if not db_path:
            raise ValueError(f"{tool_name} 需要 db_path 参数")
        arguments["db_path"] = db_path
    
    # 如果没有提供session_id，使用db_path作为session_id（确保同一数据库的请求共享环境）
    if session_id is None:
        session_id = db_path if db_path else "default"
    
    # 对于需要共享执行环境的工具，添加session_id参数
    if tool_name in ("python_inter", "extract_data"):
        arguments["session_id"] = session_id
    
    return tool_func(**arguments)
