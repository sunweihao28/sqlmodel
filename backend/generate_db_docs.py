"""
数据库文档生成模块
使用大模型API根据数据库结构信息生成详细的数据库文档说明
"""

import os
import json
from typing import Optional
from dotenv import load_dotenv
from openai import OpenAI
from extract_schema import extract_database_schema, format_schema_for_llm

# 加载.env文件
load_dotenv()

# 初始化OpenAI客户端（使用你的API配置）
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", "4ffbb99a1e52e4184b5a54433c03a3bc9e643d84c779ffa396768ceb99a000da"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://uni-api.cstcloud.cn/v1")
)


def generate_database_documentation(
    schema_text: str,
    model: str = "deepseek-v3:671b",
    language: str = "中文",
    additional_context: Optional[str] = None
) -> str:
    """
    使用大模型API生成数据库文档说明
    
    参数:
        schema_text: 格式化的数据库结构文本（由format_schema_for_llm生成）
        model: 使用的大模型名称，默认deepseek-v3:671b
        language: 生成文档的语言，默认中文
        additional_context: 额外的上下文信息（如业务背景等）
    
    返回:
        生成的数据库文档字符串
    """
    system_prompt = f"""你是一位专业的数据库文档编写专家，擅长根据数据库结构生成清晰易懂的文档说明。
请用{language}生成文档，格式清晰易读，包含以下内容：
1. 数据库的整体概述和用途
2. 每个表的业务含义和用途说明
3. 表之间的关联关系分析
4. 重要字段的业务含义说明
5. 数据约束和完整性说明
6. 使用建议和注意事项

请确保文档专业、准确、易于理解。"""

    user_prompt = f"""请根据以下数据库结构信息，生成一份详细的数据库文档说明。

数据库结构信息：
{schema_text}"""

    if additional_context:
        user_prompt += f"\n\n额外上下文信息：\n{additional_context}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000
        )
        
        documentation = response.choices[0].message.content
        return documentation
        
    except Exception as e:
        raise Exception(f"调用大模型API失败: {e}")


def generate_database_documentation_from_db(
    db_name: str,
    model: str = "deepseek-v3:671b",
    language: str = "中文",
    additional_context: Optional[str] = None,
    include_statistics: bool = True,
    host: str = 'localhost',
    user: str = 'root',
    password: Optional[str] = None
) -> str:
    """
    直接从数据库生成文档（一步完成）
    
    参数:
        db_name: 数据库名称
        model: 使用的大模型名称
        language: 生成文档的语言
        additional_context: 额外的上下文信息
        include_statistics: 是否包含表的行数统计信息
        host: MySQL主机地址
        user: MySQL用户名
        password: MySQL密码
    
    返回:
        生成的数据库文档字符串
    """
    print(f"正在提取数据库 '{db_name}' 的结构信息...")
    
    # 1. 提取数据库结构
    schema = extract_database_schema(db_name, host=host, user=user, password=password)
    
    # 2. 格式化为文本
    schema_text = format_schema_for_llm(schema, include_statistics=include_statistics)
    
    print(f"正在调用大模型生成文档...")
    
    # 3. 生成文档
    documentation = generate_database_documentation(
        schema_text=schema_text,
        model=model,
        language=language,
        additional_context=additional_context
    )
    
    return documentation


def save_documentation(documentation: str, output_file: str):
    """
    保存文档到文件
    
    参数:
        documentation: 文档内容
        output_file: 输出文件路径
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(documentation)
    print(f"文档已保存到: {output_file}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("使用方法: python generate_db_docs.py <数据库名> [输出文件] [模型名称]")
        print("示例: python generate_db_docs.py college_db college_db_docs.md deepseek-v3:671b")
        print("\n或者从已有的schema文本文件生成:")
        print("示例: python generate_db_docs.py --from-file schema.txt docs.md")
        sys.exit(1)
    
    # 检查是否从文件读取
    if sys.argv[1] == "--from-file":
        if len(sys.argv) < 3:
            print("错误: 请指定schema文本文件路径")
            sys.exit(1)
        
        schema_file = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else "database_docs.md"
        model = sys.argv[4] if len(sys.argv) > 4 else "deepseek-v3:671b"
        
        print(f"从文件 '{schema_file}' 读取schema信息...")
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_text = f.read()
        
        print("正在调用大模型生成文档...")
        documentation = generate_database_documentation(
            schema_text=schema_text,
            model=model
        )
        
        save_documentation(documentation, output_file)
        
    else:
        # 从数据库直接生成
        db_name = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else f"{db_name}_docs.md"
        model = sys.argv[3] if len(sys.argv) > 3 else "deepseek-v3:671b"
        
        try:
            documentation = generate_database_documentation_from_db(
                db_name=db_name,
                model=model
            )
            
            save_documentation(documentation, output_file)
            
            print(f"\n[成功] 文档生成完成！")
            print(f"[文件] 文件位置: {output_file}")
            
        except Exception as e:
            print(f"[错误] 错误: {e}")
            import traceback
            traceback.print_exc()

