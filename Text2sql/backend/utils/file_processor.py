import pandas as pd
import sqlite3
import os
import uuid

STORAGE_DIR = "storage"
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

def process_uploaded_file(file, filename: str) -> str:
    """
    处理上传文件。
    如果是 CSV/Excel -> 转换为 SQLite 并保存。
    如果是 SQLite -> 直接保存。
    返回: 保存后的文件路径 (path to .db)
    """
    unique_name = f"{uuid.uuid4()}"
    ext = filename.split('.')[-1].lower()
    
    # 目标数据库路径
    db_filename = f"{unique_name}.db"
    db_path = os.path.join(STORAGE_DIR, db_filename)

    if ext == 'csv':
        # 读取 CSV 并存入 SQLite
        df = pd.read_csv(file.file)
        # 简单的清理：将列名中的空格替换为下划线
        df.columns = [c.strip().replace(' ', '_') for c in df.columns]
        
        conn = sqlite3.connect(db_path)
        # 表名默认为文件名（去掉后缀）
        table_name = filename.split('.')[0].replace(' ', '_')
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        conn.close()
        
    elif ext in ['xls', 'xlsx']:
        df = pd.read_excel(file.file)
        df.columns = [c.strip().replace(' ', '_') for c in df.columns]
        
        conn = sqlite3.connect(db_path)
        table_name = filename.split('.')[0].replace(' ', '_')
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        conn.close()
        
    elif ext in ['db', 'sqlite', 'sqlite3']:
        # 如果已经是数据库，直接保存
        with open(db_path, "wb") as f:
            f.write(file.file.read())
            
    else:
        raise ValueError("Unsupported file format. Please upload CSV, Excel, or SQLite.")
        
    return db_path