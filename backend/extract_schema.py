"""
数据库结构信息提取模块
用于从MySQL数据库中提取表名、列名、数据类型、约束等关键信息
并格式化为适合输入大模型的格式
"""

import pymysql
import os
import json
from typing import List, Dict, Optional
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()


def extract_database_schema(
    db_name: str,
    host: str = 'localhost',
    user: str = 'root',
    password: Optional[str] = None
) -> List[Dict]:
    """
    从MySQL数据库中提取所有表的结构信息
    
    参数:
        db_name: 数据库名称
        host: MySQL主机地址，默认localhost
        user: MySQL用户名，默认root
        password: MySQL密码，如果为None则从环境变量MYSQL_PW读取
    
    返回:
        包含所有表结构信息的列表，每个元素格式为:
        {
            "tableName": "表名",
            "columns": [
                {
                    "name": "列名",
                    "type": "数据类型",
                    "nullable": "YES/NO",
                    "key": "PRI/UNI/MUL/空",
                    "default": "默认值",
                    "comment": "列注释"
                },
                ...
            ],
            "rowCount": 表的行数（可选）
        }
    """
    # 获取密码
    mysql_pw = password or os.getenv('MYSQL_PW')
    
    if not mysql_pw:
        raise ValueError("MySQL密码未设置！请检查.env文件中的MYSQL_PW配置")
    
    # 连接MySQL
    connection = pymysql.connect(
        host=host,
        user=user,
        passwd=mysql_pw,
        db=db_name,
        charset='utf8mb4'
    )
    
    try:
        with connection.cursor() as cursor:
            # 1. 获取所有表的列信息
            sql_columns = """
            SELECT 
                TABLE_NAME,
                COLUMN_NAME,
                DATA_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE,
                IS_NULLABLE,
                COLUMN_KEY,
                COLUMN_DEFAULT,
                COLUMN_COMMENT,
                ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
            cursor.execute(sql_columns, (db_name,))
            column_results = cursor.fetchall()
            
            # 2. 获取主键信息
            sql_primary_keys = """
            SELECT 
                TABLE_NAME,
                COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s
              AND CONSTRAINT_NAME = 'PRIMARY'
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
            cursor.execute(sql_primary_keys, (db_name,))
            primary_keys = {row[0]: [] for row in cursor.fetchall()}
            cursor.execute(sql_primary_keys, (db_name,))
            for row in cursor.fetchall():
                primary_keys.setdefault(row[0], []).append(row[1])
            
            # 3. 获取外键信息
            sql_foreign_keys = """
            SELECT 
                TABLE_NAME,
                COLUMN_NAME,
                REFERENCED_TABLE_NAME,
                REFERENCED_COLUMN_NAME,
                CONSTRAINT_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
            cursor.execute(sql_foreign_keys, (db_name,))
            foreign_keys = {}
            for row in cursor.fetchall():
                table_name = row[0]
                if table_name not in foreign_keys:
                    foreign_keys[table_name] = []
                foreign_keys[table_name].append({
                    "column": row[1],
                    "references_table": row[2],
                    "references_column": row[3],
                    "constraint_name": row[4]
                })
            
            # 4. 获取表的行数（可选，可能较慢）
            sql_tables = f"SHOW TABLES FROM `{db_name}`"
            cursor.execute(sql_tables)
            table_names = [row[0] for row in cursor.fetchall()]
            
            # 组织数据结构
            schema_dict = {}
            for row in column_results:
                table_name = row[0]
                if table_name not in schema_dict:
                    schema_dict[table_name] = {
                        "columns": [],
                        "primary_keys": primary_keys.get(table_name, []),
                        "foreign_keys": foreign_keys.get(table_name, [])
                    }
                
                # 构建数据类型字符串
                data_type = row[2]  # DATA_TYPE
                if row[3]:  # CHARACTER_MAXIMUM_LENGTH
                    data_type += f"({row[3]})"
                elif row[4] is not None:  # NUMERIC_PRECISION
                    if row[5] is not None:  # NUMERIC_SCALE
                        data_type += f"({row[4]},{row[5]})"
                    else:
                        data_type += f"({row[4]})"
                
                schema_dict[table_name]["columns"].append({
                    "name": row[1],  # COLUMN_NAME
                    "type": data_type,
                    "nullable": row[6],  # IS_NULLABLE
                    "key": row[7] or "",  # COLUMN_KEY
                    "default": str(row[8]) if row[8] is not None else "",  # COLUMN_DEFAULT
                    "comment": row[9] or ""  # COLUMN_COMMENT
                })
            
            # 5. 获取每个表的行数（可选，对于大表可能较慢）
            for table_name in table_names:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                    row_count = cursor.fetchone()[0]
                    schema_dict[table_name]["rowCount"] = row_count
                except Exception as e:
                    print(f"警告: 无法获取表 {table_name} 的行数: {e}")
                    schema_dict[table_name]["rowCount"] = None
            
            # 转换为列表格式
            schema_list = [
                {
                    "tableName": table_name,
                    **table_info
                }
                for table_name, table_info in schema_dict.items()
            ]
            
            return schema_list
            
    finally:
        connection.close()


def format_schema_for_llm(schema: List[Dict], include_statistics: bool = True) -> str:
    """
    将数据库模式格式化为适合输入大模型的文本格式
    
    参数:
        schema: extract_database_schema函数返回的schema列表
        include_statistics: 是否包含表的行数统计信息
    
    返回:
        格式化后的字符串，适合作为prompt输入大模型
    """
    formatted_text = "# 数据库结构说明\n\n"
    
    # 添加数据库概览
    table_count = len(schema)
    total_columns = sum(len(table["columns"]) for table in schema)
    formatted_text += f"## 数据库概览\n\n"
    formatted_text += f"- 表数量: {table_count}\n"
    formatted_text += f"- 总列数: {total_columns}\n\n"
    
    # 遍历每个表
    for table in schema:
        table_name = table["tableName"]
        columns = table["columns"]
        primary_keys = table.get("primary_keys", [])
        foreign_keys = table.get("foreign_keys", [])
        row_count = table.get("rowCount")
        
        formatted_text += f"## 表: {table_name}\n\n"
        
        # 添加行数信息（如果有）
        if include_statistics and row_count is not None:
            formatted_text += f"**数据行数**: {row_count:,}\n\n"
        
        # 添加主键信息
        if primary_keys:
            formatted_text += f"**主键**: {', '.join(primary_keys)}\n\n"
        
        # 添加外键信息
        if foreign_keys:
            formatted_text += f"**外键关系**:\n"
            for fk in foreign_keys:
                formatted_text += f"  - {fk['column']} → {fk['references_table']}.{fk['references_column']}\n"
            formatted_text += "\n"
        
        # 添加列信息表格
        formatted_text += "### 列信息:\n\n"
        formatted_text += "| 列名 | 数据类型 | 是否可空 | 键类型 | 默认值 | 说明 |\n"
        formatted_text += "|------|----------|----------|--------|--------|------|\n"
        
        for col in columns:
            col_name = col['name']
            col_type = col['type']
            col_nullable = col['nullable']
            col_key = col['key']
            col_default = col['default'] if col['default'] else "-"
            col_comment = col['comment'] if col['comment'] else "-"
            
            formatted_text += f"| {col_name} | {col_type} | {col_nullable} | {col_key} | {col_default} | {col_comment} |\n"
        
        formatted_text += "\n"
    
    return formatted_text


def save_schema_to_json(schema: List[Dict], output_file: str):
    """
    将schema信息保存为JSON文件
    
    参数:
        schema: extract_database_schema函数返回的schema列表
        output_file: 输出文件路径
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"Schema信息已保存到: {output_file}")


def save_schema_to_text(schema: List[Dict], output_file: str, include_statistics: bool = True):
    """
    将schema信息保存为文本文件（适合输入大模型）
    
    参数:
        schema: extract_database_schema函数返回的schema列表
        output_file: 输出文件路径
        include_statistics: 是否包含表的行数统计信息
    """
    formatted_text = format_schema_for_llm(schema, include_statistics)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(formatted_text)
    print(f"格式化后的Schema信息已保存到: {output_file}")


if __name__ == "__main__":
    # 使用示例
    import sys
    
    if len(sys.argv) < 2:
        print("使用方法: python extract_schema.py <数据库名> [输出JSON文件] [输出文本文件]")
        print("示例: python extract_schema.py college_db schema.json schema.txt")
        sys.exit(1)
    
    db_name = sys.argv[1]
    json_file = sys.argv[2] if len(sys.argv) > 2 else f"{db_name}_schema.json"
    text_file = sys.argv[3] if len(sys.argv) > 3 else f"{db_name}_schema.txt"
    
    print(f"正在提取数据库 '{db_name}' 的结构信息...")
    
    try:
        # 提取schema
        schema = extract_database_schema(db_name)
        
        # 保存为JSON
        save_schema_to_json(schema, json_file)
        
        # 保存为格式化文本
        save_schema_to_text(schema, text_file)
        
        # 打印摘要
        print(f"\n提取完成！")
        print(f"- 表数量: {len(schema)}")
        print(f"- 总列数: {sum(len(t['columns']) for t in schema)}")
        print(f"- JSON文件: {json_file}")
        print(f"- 文本文件: {text_file}")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

