import pymysql
import os
from dotenv import load_dotenv

# 加载.env文件（自动从当前目录或父目录查找）
load_dotenv()

def execute_sql_file(sql_file_path, db_name=None, host='localhost', 
                     user='root', password=None):
    """
    执行SQL文件创建数据库表
    
    :param sql_file_path: SQL文件路径
    :param db_name: 数据库名称（如果SQL文件中没有USE语句）
    :param host: MySQL主机地址
    :param user: MySQL用户名
    :param password: MySQL密码（如果为None，则从.env文件读取）
    """
    # 优先使用传入的password，其次从.env文件读取
    mysql_pw = password or os.getenv('MYSQL_PW')
    
    if not mysql_pw:
        raise ValueError("MySQL密码未设置！请检查.env文件中的MYSQL_PW配置")
    
    # 读取SQL文件
    with open(sql_file_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # 连接MySQL（不指定数据库）
    connection = pymysql.connect(
        host=host,
        user=user,
        passwd=mysql_pw,
        charset='utf8mb4'
    )
    
    try:
        with connection.cursor() as cursor:
            # 如果指定了数据库名，先创建并选择
            if db_name:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                cursor.execute(f"USE {db_name}")
            
            # 分割SQL语句（按分号分割，但要注意字符串中的分号）
            # 简单处理：按行分割，忽略注释
            sql_statements = []
            current_statement = ""
            
            for line in sql_content.split('\n'):
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith('--'):
                    continue
                current_statement += line + " "
                # 如果行以分号结尾，说明是一个完整的语句
                if line.endswith(';'):
                    sql_statements.append(current_statement.strip())
                    current_statement = ""
            
            # 执行所有SQL语句
            for sql in sql_statements:
                if sql:
                    try:
                        cursor.execute(sql)
                        connection.commit()
                    except Exception as e:
                        print(f"执行SQL时出错: {sql[:50]}...")
                        print(f"错误信息: {e}")
                        # 继续执行下一条语句
                        continue
            
            print(f"SQL文件执行完成！")
            if db_name:
                print(f"数据库 '{db_name}' 已创建")
            
    finally:
        connection.close()
        
if __name__ == "__main__":
    # 使用示例 - 现在会自动从.env文件读取密码
    execute_sql_file(
        sql_file_path='TextBookExampleSchema.sql',
        db_name='college_db',  # 根据你的SQL文件内容命名
        # password参数不需要了，会自动从.env读取
    )