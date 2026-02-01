# import pandas as pd
# import sqlite3
# import os
# import uuid

# STORAGE_DIR = "storage"
# if not os.path.exists(STORAGE_DIR):
#     os.makedirs(STORAGE_DIR)

# def process_uploaded_file(file, filename: str) -> str:
#     """
#     处理上传文件。
#     如果是 CSV/Excel -> 转换为 SQLite 并保存。
#     如果是 SQLite -> 直接保存。
#     返回: 保存后的文件路径 (path to .db)
#     """
#     unique_name = f"{uuid.uuid4()}"
#     ext = filename.split('.')[-1].lower()
    
#     # 目标数据库路径
#     db_filename = f"{unique_name}.db"
#     db_path = os.path.join(STORAGE_DIR, db_filename)

#     if ext == 'csv':
#         # 读取 CSV 并存入 SQLite
#         df = pd.read_csv(file.file)
#         # 简单的清理：将列名中的空格替换为下划线
#         df.columns = [c.strip().replace(' ', '_') for c in df.columns]
        
#         conn = sqlite3.connect(db_path)
#         # 表名默认为文件名（去掉后缀）
#         table_name = filename.split('.')[0].replace(' ', '_')
#         df.to_sql(table_name, conn, if_exists='replace', index=False)
#         conn.close()
        
#     elif ext in ['xls', 'xlsx']:
#         df = pd.read_excel(file.file)
#         df.columns = [c.strip().replace(' ', '_') for c in df.columns]
        
#         conn = sqlite3.connect(db_path)
#         table_name = filename.split('.')[0].replace(' ', '_')
#         df.to_sql(table_name, conn, if_exists='replace', index=False)
#         conn.close()
        
#     elif ext in ['db', 'sqlite', 'sqlite3']:
#         # 如果已经是数据库，直接保存
#         with open(db_path, "wb") as f:
#             f.write(file.file.read())
            
#     else:
#         raise ValueError("Unsupported file format. Please upload CSV, Excel, or SQLite.")
        
#     return db_path


import pandas as pd
import sqlite3
import os

def convert_to_sqlite(source_path: str) -> str:
    """
    将指定路径的文件转换为 SQLite 数据库文件。
    如果是 CSV/Excel -> 转换为同名的 .db 文件并返回新路径。
    如果是 SQLite -> 直接返回原路径。
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source file not found: {source_path}")

    filename = os.path.basename(source_path)
    base_name, ext = os.path.splitext(filename)
    ext = ext.lower().lstrip('.')

    # 如果已经是 SQLite 数据库，直接返回
    if ext in ['db', 'sqlite', 'sqlite3']:
        return source_path

    # 生成目标数据库路径 (e.g. uploads/user_file.xlsx -> uploads/user_file.db)
    dir_name = os.path.dirname(source_path)
    target_db_path = os.path.join(dir_name, f"{base_name}.db")
    
    # 简单的表名处理：取文件名中第一个下划线后的部分（去除user_id前缀），或者直接用文件名
    # 只能包含字母数字和下划线
    raw_table_name = base_name.split('_', 1)[-1] if '_' in base_name else base_name
    table_name = "".join([c if c.isalnum() else "_" for c in raw_table_name])
    if not table_name:
        table_name = "data_table"

    df = None
    try:
        if ext == 'csv':
            try:
                df = pd.read_csv(source_path)
            except UnicodeDecodeError:
                # 尝试 GBK 编码 (常见于中文 CSV)
                df = pd.read_csv(source_path, encoding='gbk')
        elif ext in ['xls', 'xlsx']:
            df = pd.read_excel(source_path)
        else:
            # 不支持的格式，返回原路径，让后续流程处理（可能会报错）
            return source_path
    except Exception as e:
        raise ValueError(f"无法读取文件 {filename}: {str(e)}")

    if df is not None:
        # 清理列名：去除空格，替换为下划线，转字符串
        df.columns = [str(c).strip().replace(' ', '_').replace('.', '_') for c in df.columns]
        
        # 存入 SQLite
        conn = sqlite3.connect(target_db_path)
        try:
            df.to_sql(table_name, conn, if_exists='replace', index=False)
        finally:
            conn.close()
            
        return target_db_path
    
    return source_path