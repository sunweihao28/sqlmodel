"""
增强 SQL 生成服务：参考 openai-backend/enhanced2.py，支持单文件 db_path。
仅当数据源为上传的 SQLite 文件时使用；MySQL/Postgres 仍走模型生成。
"""

import os
import re
import sqlite3
from typing import Optional, List

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def get_enhanced_schema_info(db_path: str, sample_rows: int = 3, max_distinct_values: int = 10) -> dict:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall() if t[0] != "sqlite_sequence"]
    schema_info = {"tables": {}, "foreign_keys": [], "sample_data": {}, "column_values": {}}
    for table_name in tables:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns_raw = cursor.fetchall()
        columns = [{"name": c[1], "type": c[2] if c[2] else "TEXT", "is_pk": bool(c[5])} for c in columns_raw]
        schema_info["tables"][table_name] = columns
        cursor.execute(f"PRAGMA foreign_key_list({table_name})")
        for fk in cursor.fetchall():
            schema_info["foreign_keys"].append(f"{table_name}.{fk[3]} = {fk[2]}.{fk[4]}")
        try:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {sample_rows}")
            rows = cursor.fetchall()
            col_names = [c["name"] for c in columns]
            schema_info["sample_data"][table_name] = {"columns": col_names, "rows": rows}
        except Exception:
            schema_info["sample_data"][table_name] = {"columns": [], "rows": []}
        schema_info["column_values"][table_name] = {}
        for col in columns:
            col_name = col["name"]
            try:
                cursor.execute(f"SELECT COUNT(DISTINCT `{col_name}`) FROM {table_name}")
                distinct_count = cursor.fetchone()[0]
                if distinct_count <= max_distinct_values and distinct_count > 0:
                    cursor.execute(f"SELECT DISTINCT `{col_name}` FROM {table_name} WHERE `{col_name}` IS NOT NULL LIMIT {max_distinct_values}")
                    values = [row[0] for row in cursor.fetchall()]
                    schema_info["column_values"][table_name][col_name] = values
            except Exception:
                pass
    conn.close()
    return schema_info


def format_enhanced_schema(schema_info: dict) -> str:
    parts = ["=== DATABASE SCHEMA ===\n"]
    for table_name, columns in schema_info["tables"].items():
        cols_desc = [f"{c['name']}: {c['type']}" + (" (PK)" if c["is_pk"] else "") for c in columns]
        parts.append(f"Table: {table_name}\n  Columns: {', '.join(cols_desc)}\n")
    if schema_info["foreign_keys"]:
        parts.append(f"\nForeign Keys: {', '.join(schema_info['foreign_keys'])}\n")
    parts.append("\n=== COLUMN VALUE EXAMPLES ===\n")
    for table_name, col_values in schema_info["column_values"].items():
        if col_values:
            parts.append(f"Table {table_name}:\n")
            for col_name, values in col_values.items():
                formatted = [f"'{v}'" if isinstance(v, str) else str(v) for v in values[:8]]
                parts.append(f"  {col_name}: [{', '.join(formatted)}]\n")
    parts.append("\n=== SAMPLE DATA (First 3 rows) ===\n")
    for table_name, data in schema_info["sample_data"].items():
        if data["rows"]:
            parts.append(f"Table {table_name}:\n  | {' | '.join(data['columns'])} |\n")
            for row in data["rows"][:3]:
                parts.append("  | " + " | ".join(str(v) if v is not None else "NULL" for v in row) + " |\n")
    return "".join(parts)


def _clean_sql(sql: str) -> str:
    if not sql:
        return "SELECT 1;"
    sql = sql.strip()
    while sql.upper().startswith("SELECT SELECT"):
        sql = sql[7:].strip()
    if ";" in sql:
        sql = sql.split(";")[0] + ";"
    else:
        sql += ";"
    return " ".join(sql.split())


def _extract_pure_sql(text: str) -> str:
    if not text:
        return "SELECT 1;"
    m = re.findall(r"```sql\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        return _clean_sql(m[-1])
    m = re.findall(r"```\s*([\s\S]*?)\s*```", text)
    if m:
        return _clean_sql(m[-1])
    text = re.sub(r"^SQL:\s*", "", text, flags=re.IGNORECASE)
    for part in reversed(text.split(";")):
        if "SELECT" in part.upper():
            return _clean_sql(part)
    return _clean_sql(text)


def _validate_sql_sqlite(sql: str, db_path: str, timeout: float = 5.0) -> dict:
    out = {"valid": False, "error": None, "row_count": 0}
    try:
        conn = sqlite3.connect(db_path, timeout=timeout)
        conn.text_factory = str
        cur = conn.cursor()
        cur.execute(sql.strip().rstrip(";"))
        out["row_count"] = len(cur.fetchall())
        conn.close()
        out["valid"] = True
    except Exception as e:
        out["error"] = str(e)
    return out


EASY_PROMPT = """# Generate SQL using schema links and EXACT values from COLUMN VALUE EXAMPLES.
Schema:
{schema}
Q: "{question}"
Schema_links: {schema_links}
Output ONLY valid SQL inside ```sql ... ```"""

MEDIUM_PROMPT = """# Generate SQL for JOIN queries. Use EXACT values from COLUMN VALUE EXAMPLES.
Schema:
{schema}
Q: "{question}"
Schema_links: {schema_links}
A: One SQL in ```sql ... ```"""

HARD_PROMPT = """# Generate SQL for NESTED/subquery. Use EXACT values. For "but not" use EXCEPT.
Schema:
{schema}
Q: "{question}"
Schema_links: {schema_links}
A: One SQL in ```sql ... ```"""

RANKING_PROMPT = """# Select the BEST SQL from candidates. Prefer execution success.
Schema:
{schema}
Question: "{question}"
Candidates:
{candidates}
Output one line: Best_Candidate_Index: <0-based index>"""


def generate_sql_enhanced(
    question: str,
    db_path: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    num_candidates: int = 3,
) -> str:
    """增强 pipeline 生成 SQL。仅支持 OpenAI 兼容 API（base_url）；否则返回空表示回退模型 SQL。"""
    if not OpenAI or not base_url or not os.path.exists(db_path):
        return ""
    client = OpenAI(api_key=api_key or "sk-dummy", base_url=base_url)
    model = model or "gpt-4o"
    try:
        schema_info = get_enhanced_schema_info(db_path, sample_rows=3, max_distinct_values=10)
        schema_str = format_enhanced_schema(schema_info)
    except Exception:
        return ""

    def call_llm(prompt: str, temperature: float = 0.0, max_tokens: int = 1500, n: int = 1) -> List[str]:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            n=n,
        )
        return [c.message.content or "" for c in resp.choices]

    linking_prompt = f"Schema:\n{schema_str}\n\nQ: \"{question}\"\nA: Output Schema_links: [...]"
    linking_resp = call_llm(linking_prompt, temperature=0.0, max_tokens=500)
    schema_links = "[]"
    for r in linking_resp:
        if "Schema_links:" in r:
            schema_links = r.split("Schema_links:")[-1].strip().split("\n")[0].strip()
            break

    class_prompt = f"Classify Q as EASY, NON-NESTED, or NESTED. Schema_links: {schema_links}\nQ: \"{question}\"\nA: Label:"
    class_resp = call_llm(class_prompt, temperature=0.0, max_tokens=80)
    q_class = "EASY"
    for r in class_resp:
        if "NON-NESTED" in r:
            q_class = "NON-NESTED"
            break
        if "NESTED" in r:
            q_class = "NESTED"
            break

    if q_class == "EASY":
        gen_prompt = EASY_PROMPT.format(schema=schema_str, question=question, schema_links=schema_links)
    elif q_class == "NON-NESTED":
        gen_prompt = MEDIUM_PROMPT.format(schema=schema_str, question=question, schema_links=schema_links)
    else:
        gen_prompt = HARD_PROMPT.format(schema=schema_str, question=question, schema_links=schema_links)
    raw = call_llm(gen_prompt, temperature=0.5, max_tokens=800, n=num_candidates)
    candidates = list({_extract_pure_sql(r) for r in raw if _extract_pure_sql(r) and "SELECT" in _extract_pure_sql(r).upper()})
    if not candidates:
        return ""

    valid = [s for s in candidates if _validate_sql_sqlite(s, db_path)["valid"]]
    if not valid:
        valid = candidates

    if len(valid) == 1:
        return valid[0]
    candidates_str = "\n".join(f"Candidate {i}:\n{s}" for i, s in enumerate(valid))
    rank_prompt = RANKING_PROMPT.format(schema=schema_str, question=question, candidates=candidates_str)
    rank_resp = call_llm(rank_prompt, temperature=0.0, max_tokens=150)
    idx = 0
    for r in rank_resp:
        match = re.search(r"Best_Candidate_Index:\s*(\d+)", r, re.IGNORECASE) or re.search(r"\d+", r)
        if match:
            idx = min(int(match.group(1) if match.lastindex else match.group(0)), len(valid) - 1)
            break
    return valid[idx]
