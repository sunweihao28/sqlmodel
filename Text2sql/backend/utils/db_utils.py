import sqlite3
import pandas as pd

def get_db_schema(db_path: str) -> str:
    """连接 SQLite 数据库，提取所有表的建表语句作为 Schema"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 查询 sqlite_master 获取所有表的结构
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    schema_str = ""
    for table in tables:
        if table[0]: # 忽略空值
            schema_str += table[0] + ";\n"
            
    conn.close()
    return schema_str

def execute_query(db_path: str, sql_query: str):
    """执行 SQL 查询并返回结果 (字典列表格式)"""
    conn = sqlite3.connect(db_path)
    try:
        # 使用 pandas 读取最方便，直接转 dict
        df = pd.read_sql_query(sql_query, conn)
        columns = df.columns.tolist()
        data = df.to_dict(orient='records')
        return {"columns": columns, "data": data, "error": None}
    except Exception as e:
        return {"columns": [], "data": [], "error": str(e)}
    finally:
        conn.close()