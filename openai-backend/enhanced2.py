import json
import re
import sqlite3
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm.auto import tqdm
from openai import OpenAI
# from dotenv import load_dotenv

# load_dotenv()

# ============================================================================
# 1. 增强版 Schema 读取函数
# ============================================================================

def get_enhanced_schema_info(db_path: str, sample_rows: int = 3, max_distinct_values: int = 10) -> dict:
    """
    增强版 Schema 读取：
    - 表结构（列名、类型、是否主键）
    - 外键关系
    - 每张表的样例数据（前 N 行）
    - 每列的不同值统计（对于低基数列）
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall() if t[0] != 'sqlite_sequence']
    
    schema_info = {
        "tables": {},
        "foreign_keys": [],
        "sample_data": {},
        "column_values": {}  # 新增：列值统计
    }
    
    for table_name in tables:
        # 1. 获取列信息（名称、类型、是否主键）
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns_raw = cursor.fetchall()
        columns = []
        for col in columns_raw:
            col_info = {
                "name": col[1],
                "type": col[2] if col[2] else "TEXT",
                "is_pk": bool(col[5])
            }
            columns.append(col_info)
        schema_info["tables"][table_name] = columns
        
        # 2. 获取外键
        cursor.execute(f"PRAGMA foreign_key_list({table_name})")
        fks = cursor.fetchall()
        for fk in fks:
            schema_info["foreign_keys"].append(
                f"{table_name}.{fk[3]} = {fk[2]}.{fk[4]}"
            )
        
        # 3. 获取样例数据（前 N 行）
        try:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {sample_rows}")
            rows = cursor.fetchall()
            col_names = [col["name"] for col in columns]
            schema_info["sample_data"][table_name] = {
                "columns": col_names,
                "rows": rows
            }
        except Exception as e:
            schema_info["sample_data"][table_name] = {"columns": [], "rows": []}
        
        # 4. 获取每列的不同值（用于低基数列，如 semester, dept_name 等）
        schema_info["column_values"][table_name] = {}
        for col in columns:
            col_name = col["name"]
            try:
                # 先检查不同值的数量
                cursor.execute(f"SELECT COUNT(DISTINCT `{col_name}`) FROM {table_name}")
                distinct_count = cursor.fetchone()[0]
                
                # 只对低基数列（不同值 <= max_distinct_values）获取具体值
                if distinct_count <= max_distinct_values and distinct_count > 0:
                    cursor.execute(f"SELECT DISTINCT `{col_name}` FROM {table_name} WHERE `{col_name}` IS NOT NULL LIMIT {max_distinct_values}")
                    values = [row[0] for row in cursor.fetchall()]
                    schema_info["column_values"][table_name][col_name] = values
            except Exception:
                pass
    
    conn.close()
    return schema_info


def format_enhanced_schema(schema_info: dict) -> str:
    """
    将增强的 schema 信息格式化为 prompt 字符串
    """
    output_parts = []
    
    # 1. 表结构
    output_parts.append("=== DATABASE SCHEMA ===\n")
    for table_name, columns in schema_info["tables"].items():
        cols_desc = []
        for col in columns:
            pk_marker = " (PK)" if col["is_pk"] else ""
            cols_desc.append(f"{col['name']}: {col['type']}{pk_marker}")
        output_parts.append(f"Table: {table_name}\n  Columns: {', '.join(cols_desc)}\n")
    
    # 2. 外键
    if schema_info["foreign_keys"]:
        output_parts.append(f"\nForeign Keys: {', '.join(schema_info['foreign_keys'])}\n")
    
    # 3. 列值统计（关键改进！）
    output_parts.append("\n=== COLUMN VALUE EXAMPLES ===\n")
    for table_name, col_values in schema_info["column_values"].items():
        if col_values:
            output_parts.append(f"Table {table_name}:\n")
            for col_name, values in col_values.items():
                # 格式化值显示
                formatted_values = []
                for v in values[:8]:  # 最多显示8个
                    if isinstance(v, str):
                        formatted_values.append(f"'{v}'")
                    else:
                        formatted_values.append(str(v))
                values_str = ", ".join(formatted_values)
                if len(values) > 8:
                    values_str += ", ..."
                output_parts.append(f"  {col_name}: [{values_str}]\n")
    
    # 4. 样例数据
    output_parts.append("\n=== SAMPLE DATA (First 3 rows) ===\n")
    for table_name, data in schema_info["sample_data"].items():
        if data["rows"]:
            output_parts.append(f"Table {table_name}:\n")
            # 表头
            output_parts.append(f"  | {' | '.join(data['columns'])} |\n")
            # 数据行
            for row in data["rows"][:3]:
                row_str = " | ".join(str(v) if v is not None else "NULL" for v in row)
                output_parts.append(f"  | {row_str} |\n")
            output_parts.append("\n")
    
    return "".join(output_parts)


# ============================================================================
# 2. 优化后的 Prompts（强调使用实际数据值）
# ============================================================================

SCHEMA_LINKING_PROMPT = '''# Find the schema_links for generating SQL queries for each question based on the database schema.
# CRITICAL RULES:
# 1. Use EXACT column values from "COLUMN VALUE EXAMPLES" - copy them character-by-character including spaces, dots, apostrophes
# 2. DO NOT modify, normalize, or "fix" any values - use them AS-IS from the database
# 3. Pay special attention to abbreviations (e.g., "Comp. Sci." not "Computer Science")

Q: "Find the buildings which have rooms with capacity more than 50."
A: Let's think step by step. In the question "Find the buildings which have rooms with capacity more than 50.", we are asked:
"the buildings which have rooms" so we need column = [classroom.building]
"rooms with capacity" so we need column = [classroom.capacity]
Based on the columns and tables, we need these Foreign_keys = [].
Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [50]. So the Schema_links are:
Schema_links: [classroom.building,classroom.capacity,50]

Q: "Give the title of the course offered in Chandler during the Fall of 2010."
A: Let's think step by step. In the question "Give the title of the course offered in Chandler during the Fall of 2010.", we are asked:
"title of the course" so we need column = [course.title]
"course offered in Chandler" so we need column = [section.building]
"during the Fall" so we need column = [section.semester] - Looking at COLUMN VALUE EXAMPLES, I see semester has values like 'Fall', 'Spring' (exact case)
"of 2010" so we need column = [section.year]
Based on the columns and tables, we need these Foreign_keys = [course.course_id = section.course_id].
Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [Chandler,Fall,2010]. So the Schema_links are:
Schema_links: [course.title,course.course_id = section.course_id,section.building,section.year,section.semester,Chandler,Fall,2010]

Q: "Find the id of instructors who taught a class in Fall 2009 but not in Spring 2010."
A: Let's think step by step. In the question "Find the id of instructors who taught a class in Fall 2009 but not in Spring 2010.", we are asked:
"id of instructors who taught" so we need column = [teaches.ID]
"taught a class in" so we need column = [teaches.semester,teaches.year] - From COLUMN VALUE EXAMPLES: semester values are 'Fall', 'Spring'
"Fall 2009 but not in Spring 2010" indicates we need EXCEPT/set difference operation
Based on the columns and tables, we need these Foreign_keys = [].
Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [Fall,2009,Spring,2010]. So the Schema_links are:
Schema_links: [teaches.ID,teaches.semester,teaches.year,Fall,2009,Spring,2010]
'''

CLASSIFICATION_PROMPT = '''# For the given question, classify it as EASY, NON-NESTED, or NESTED based on nested queries and JOIN.
# CRITICAL: Look for keywords indicating set operations (EXCEPT, UNION, INTERSECT) or filtering against subquery results (IN, NOT IN)
# Pattern recognition:
# - "but not" / "except" → NESTED with EXCEPT
# - "both...and..." / "in...and also in..." → NESTED with INTERSECT
# - "either...or..." across different conditions → NESTED with UNION
# - "students who took courses" → likely needs JOIN
# - "courses that have prerequisite X" → likely needs subquery with IN

if need nested queries: predict NESTED
elif need JOIN and don't need nested queries: predict NON-NESTED
elif don't need JOIN and don't need nested queries: predict EASY

Q: "Find the buildings which have rooms with capacity more than 50."
schema_links: [classroom.building,classroom.capacity,50]
A: Let's think step by step. The SQL query for the question "Find the buildings which have rooms with capacity more than 50." needs these tables = [classroom], so we don't need JOIN.
Plus, it doesn't require nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN), and we need the answer to the questions = [""].
So, we don't need JOIN and don't need nested queries, then the the SQL query can be classified as "EASY".
Label: "EASY"

Q: "What are the names of all instructors who advise students in the math depart sorted by total credits of the student."
schema_links: [advisor.i_id = instructor.id,advisor.s_id = student.id,instructor.name,student.dept_name,student.tot_cred,math]
A: Let's think step by step. The SQL query for the question "What are the names of all instructors who advise students in the math depart sorted by total credits of the student." needs these tables = [advisor,instructor,student], so we need JOIN.
Plus, it doesn't need nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN), and we need the answer to the questions = [""].
So, we need JOIN and don't need nested queries, then the the SQL query can be classified as "NON-NESTED".
Label: "NON-NESTED"

Q: "Find the id of instructors who taught a class in Fall 2009 but not in Spring 2010."
schema_links: [teaches.id,teaches.semester,teaches.year,Fall,2009,Spring,2010]
A: Let's think step by step. The SQL query for the question "Find the id of instructors who taught a class in Fall 2009 but not in Spring 2010." needs these tables = [teaches], so we don't need JOIN.
Plus, the phrase "but not" indicates we need EXCEPT operation (set difference), so we need nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN), and we need the answer to the questions = ["Find the id of instructors who taught a class in Spring 2010"].
So, we don't need JOIN and need nested queries, then the the SQL query can be classified as "NESTED".
Label: "NESTED"

Q: "What are the names of students who took prerequisites of International Finance?"
schema_links: [student.name,student.id = takes.id,takes.course_id,course.title,prereq.course_id,prereq.prereq_id,International Finance]
A: Let's think step by step. The question asks for "students who took prerequisites", which means we need to:
1) Find prerequisites of 'International Finance' (requires subquery)
2) Find students who took those courses (filtering with IN)
This requires nested queries with IN to filter students based on subquery results, and we need the answer to the questions = ["What are the prerequisites of International Finance"].
So, we need nested queries, then the SQL query can be classified as "NESTED".
Label: "NESTED"
'''

EASY_PROMPT = '''# Use the schema links and the actual database values to generate SQL queries.
# CRITICAL RULES - READ CAREFULLY:
# 1. Copy column values EXACTLY from COLUMN VALUE EXAMPLES (character-by-character)
# 2. DO NOT normalize/fix values: use 'Comp. Sci.' not 'Computer Science', 'Fall' not 'fall'
# 3. For aggregation: ensure GROUP BY matches the SELECT and aggregate columns correctly
# 4. Use DISTINCT when finding unique values
# Output the final SQL inside a markdown code block: ```sql SELECT ... ```

Q: "Find the buildings which have rooms with capacity more than 50."
Schema_links: [classroom.building,classroom.capacity,50]
SQL:
```sql
SELECT DISTINCT building FROM classroom WHERE capacity > 50
```

Q: "Give the name of the student in the History department with the most credits."
Schema_links: [student.name,student.dept_name,student.tot_cred,History]
SQL:
```sql
SELECT name FROM student WHERE dept_name = 'History' ORDER BY tot_cred DESC LIMIT 1
```

Q: "How many instructors teach a course in the Spring of 2010?"
Schema_links: [teaches.ID,teaches.semester,teaches.YEAR,Spring,2010]
A: Looking at COLUMN VALUE EXAMPLES for semester, I see values like 'Spring', 'Fall' (exact case).
SQL:
```sql
SELECT COUNT(DISTINCT ID) FROM teaches WHERE semester = 'Spring' AND YEAR = 2010
```

Q: "Find the names of instructors in the Comp. Sci. department"
Schema_links: [instructor.name,instructor.dept_name,Comp. Sci.]
A: Looking at COLUMN VALUE EXAMPLES for dept_name, I see the EXACT value 'Comp. Sci.' (with dot and space).
SQL:
```sql
SELECT name FROM instructor WHERE dept_name = 'Comp. Sci.'
```
'''

MEDIUM_PROMPT = '''# Use the schema links, actual database values, and intermediate representation to generate SQL.
# CRITICAL RULES:
# 1. Use EXACT values from COLUMN VALUE EXAMPLES (copy character-by-character)
# 2. For aggregation queries: GROUP BY should include the column used for grouping, SELECT should have aggregate function
# 3. When joining tables, ensure foreign key relationships are correct
# 4. Use table aliases for clarity (T1, T2, etc.)
# Output the final SQL inside a markdown code block: ```sql SELECT ... ```

Q: "Find the total budgets of the Marketing or Finance department."
Schema_links: [department.budget,department.dept_name,Marketing,Finance]
A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.
Intermediate_representation: select sum(department.budget) from department where department.dept_name = "Marketing" or department.dept_name = "Finance"
SQL:
```sql
SELECT sum(budget) FROM department WHERE dept_name = 'Marketing' OR dept_name = 'Finance'
```

Q: "Find the title of courses that have two prerequisites?"
Schema_links: [course.title,course.course_id = prereq.course_id]
A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = [course,prereq]. First, create an intermediate representation, then use it to construct the SQL query.
Intermediate_representation: select course.title from course join prereq where count(prereq.*) = 2 group by prereq.course_id
SQL:
```sql
SELECT T1.title FROM course AS T1 JOIN prereq AS T2 ON T1.course_id = T2.course_id GROUP BY T2.course_id HAVING count(*) = 2
```

Q: "What is the average salary and count of instructors in each department?"
Schema_links: [instructor.dept_name,instructor.salary]
A: Let's think step by step. This requires grouping by department and calculating aggregates.
Intermediate_representation: select instructor.dept_name, avg(instructor.salary), count(instructor.id) from instructor group by instructor.dept_name
SQL:
```sql
SELECT dept_name, AVG(salary), COUNT(*) FROM instructor GROUP BY dept_name
```
'''

HARD_PROMPT = '''# Use the intermediate representation, schema links, and actual database values to generate SQL.
# CRITICAL RULES FOR NESTED QUERIES:
# 1. Use EXACT values from COLUMN VALUE EXAMPLES (copy them as-is)
# 2. When question asks "X but not Y" → use EXCEPT: (SELECT ... WHERE X) EXCEPT (SELECT ... WHERE Y)
# 3. When question asks "both X and Y" → use INTERSECT: (SELECT ... WHERE X) INTERSECT (SELECT ... WHERE Y)
# 4. For "courses in X or Y" across different time periods → use UNION (not OR) to avoid duplicates
# 5. **CRITICAL PREREQUISITE PATTERN**: When filtering by course title/name in prerequisite queries:
#    ALWAYS use JOIN in the subquery (NEVER use nested WHERE course_id = (SELECT...))
#    Example: WHERE course_id IN (SELECT T1.prereq_id FROM prereq T1 JOIN course T2 ON T1.course_id=T2.course_id WHERE T2.title='X')
#    Reason: Course titles may have multiple course_ids, nested subquery fails with "returns more than 1 row"
# 6. Understand prereq table direction: prereq.course_id = main course, prereq.prereq_id = required prerequisite
#    "Prerequisites OF course X" → SELECT prereq_id FROM prereq WHERE course_id IN (SELECT course_id WHERE title='X')
#    "Courses that REQUIRE X as prerequisite" → SELECT course_id FROM prereq WHERE prereq_id IN (SELECT course_id WHERE title='X')
# 7. Do NOT add column aliases like "AS avg_salary" unless specifically asked
# Output the final SQL inside a markdown code block: ```sql SELECT ... ```

Q: "Give the name and building of the departments with greater than average budget."
Schema_links: [department.dept_name,department.building,department.budget]
A: Let's think step by step. "Give the name and building of the departments with greater than average budget." can be solved by knowing the answer to the following sub-question "What is the average budget of departments?".
The SQL query for the sub-question "What is the average budget of departments?" is SELECT avg(budget) FROM department
So, the answer to the question "Give the name and building of the departments with greater than average budget." is =
Intermediate_representation: select department.dept_name , department.building from department where @.@ > avg ( department.budget )
SQL:
```sql
SELECT dept_name, building FROM department WHERE budget > (SELECT avg(budget) FROM department)
```

Q: "Find the id of instructors who taught a class in Fall 2009 but not in Spring 2010."
Schema_links: [teaches.id,teaches.semester,teaches.YEAR,Fall,2009,Spring,2010]
A: Let's think step by step. "Find the id of instructors who taught a class in Fall 2009 but not in Spring 2010." can be solved by knowing the answer to the following sub-question "Find the id of instructors who taught a class in Spring 2010".
The SQL query for the sub-question "Find the id of instructors who taught a class in Spring 2010" is SELECT id FROM teaches WHERE semester = 'Spring' AND YEAR = 2010
The phrase "but not" indicates EXCEPT operation (set difference).
Intermediate_representation: select teaches.ID from teaches where teaches.semester = "Fall" and teaches.year = 2009 EXCEPT select teaches.ID from teaches where teaches.semester = "Spring" and teaches.year = 2010
SQL:
```sql
SELECT id FROM teaches WHERE semester = 'Fall' AND YEAR = 2009 EXCEPT SELECT id FROM teaches WHERE semester = 'Spring' AND YEAR = 2010
```

Q: "What are the titles of the prerequisites for International Finance?"
Schema_links: [course.title,course.course_id,prereq.course_id,prereq.prereq_id,International Finance]
A: Let's think step by step. "What are the titles of the prerequisites for International Finance?" can be solved by knowing the answer to the following sub-question "What are the prerequisite course IDs for International Finance?".
CRITICAL: Since we're filtering by course title ('International Finance'), and course titles can appear multiple times (different sections/semesters), we MUST use JOIN in the subquery, NOT nested subquery with =.
The correct pattern: JOIN prereq with course to match on title.
Intermediate_representation: select course.title from course where course.course_id in (select prereq.prereq_id from prereq join course on prereq.course_id = course.course_id where course.title = "International Finance")
SQL:
```sql
SELECT title FROM course WHERE course_id IN (SELECT T1.prereq_id FROM prereq AS T1 JOIN course AS T2 ON T1.course_id = T2.course_id WHERE T2.title = 'International Finance')
```

Q: "Find courses that have Differential Geometry as prerequisite"
Schema_links: [course.title,course.course_id,prereq.course_id,prereq.prereq_id,Differential Geometry]
A: Let's think step by step. This asks for courses where 'Differential Geometry' is the prerequisite.
Direction: prereq.course_id is the main course, prereq.prereq_id is the required prerequisite.
We want: course_id WHERE prereq_id = 'Differential Geometry'
Again, use JOIN because course title may have multiple IDs.
Intermediate_representation: select course.title from course where course.course_id in (select prereq.course_id from prereq join course on prereq.prereq_id = course.course_id where course.title = "Differential Geometry")
SQL:
```sql
SELECT title FROM course WHERE course_id IN (SELECT T1.course_id FROM prereq AS T1 JOIN course AS T2 ON T1.prereq_id = T2.course_id WHERE T2.title = 'Differential Geometry')
```

Q: "Find the names of students who took prerequisites of International Finance"
Schema_links: [student.name,student.id = takes.id,takes.course_id,prereq.prereq_id,prereq.course_id,course.title,International Finance]
A: Let's think step by step. This requires:
1) Find prerequisites of 'International Finance' (subquery)
2) Find students who took those courses (filter with IN)
Sub-question: "What are the prerequisite course IDs for International Finance?"
Intermediate_representation: select student.name from student where student.id in (select takes.id from takes where takes.course_id in (select prereq.prereq_id from prereq where prereq.course_id = (select course.course_id from course where course.title = "International Finance")))
SQL:
```sql
SELECT T1.name FROM student AS T1 JOIN takes AS T2 ON T1.id = T2.id WHERE T2.course_id IN (SELECT T4.prereq_id FROM course AS T3 JOIN prereq AS T4 ON T3.course_id = T4.course_id WHERE T3.title = 'International Finance')
```

Q: "Which department has the highest average instructor salary?"
Schema_links: [instructor.dept_name,instructor.salary]
A: Let's think step by step. This requires grouping by department, calculating average salary, and finding the maximum.
Intermediate_representation: select instructor.dept_name from instructor group by instructor.dept_name order by avg(instructor.salary) desc limit 1
SQL:
```sql
SELECT dept_name FROM instructor GROUP BY dept_name ORDER BY avg(salary) DESC LIMIT 1
```

Q: "Find courses offered in Fall 2009 or Spring 2010"
Schema_links: [section.course_id,section.semester,section.year,Fall,2009,Spring,2010]
A: Let's think step by step. This asks for courses in two different time periods. Since a course might be offered in both semesters, we need to avoid duplicates.
CRITICAL: Use UNION (not OR) when combining results from different time periods to eliminate duplicates.
SQL:
```sql
SELECT course_id FROM section WHERE semester = 'Fall' AND YEAR = 2009 UNION SELECT course_id FROM section WHERE semester = 'Spring' AND YEAR = 2010
```
'''

DEBUG_PROMPT = """#### For the given question, use the provided tables, columns, foreign keys, and ACTUAL COLUMN VALUES to fix the given SQLite SQL QUERY.
#### CRITICAL FIXING RULES (Priority Order):
#### 1. **PREREQUISITE QUERY PATTERN**: If query involves course titles/names with prereq table:
####    - Check if using nested subquery: WHERE course_id = (SELECT course_id FROM course WHERE title='X')
####    - This FAILS if title has multiple course_ids (different sections/semesters)
####    - FIX: Use JOIN instead: SELECT T1.prereq_id FROM prereq T1 JOIN course T2 ON T1.course_id=T2.course_id WHERE T2.title='X'
#### 2. **VALUE MATCHING**: Check COLUMN VALUE EXAMPLES and use EXACT values (e.g., 'Comp. Sci.' not 'Computer Science', 'Fall' not 'fall')
#### 3. **UNION vs OR**: 
####    - If "courses in Fall 2009 or Spring 2010" → Use UNION (eliminates duplicates)
####    - If "students with GPA > 3.0 or honors = true" → Use OR (simple filtering)
#### 4. **EXCEPT vs NOT IN**: For "X but not Y" → Use EXCEPT for cleaner set difference
#### 5. **Remove Unnecessary Elements**:
####    - Remove column aliases like "AS avg_salary", "AS average_salary" unless needed
####    - Remove unnecessary table joins (e.g., joining section when takes already has course_id)
#### 6. **AGGREGATION**: 
####    - GROUP BY should include non-aggregated SELECT columns
####    - If SELECTing dept_name with AVG(salary), must GROUP BY dept_name
#### 7. **Use MAX/MIN not ALL**: "salary > (SELECT max(salary)...)" is better than "salary > ALL (SELECT salary...)"
#### If there are no issues, output the original SQL inside a code block.

#### Output the fixed SQL query inside a markdown code block:
```sql
SELECT ...
```
"""

RANKING_PROMPT = """# You are a senior SQL expert.
# Select the BEST SQL query from candidates based on schema and actual database values.

Database Schema:
{schema}

Question: "{question}"

Candidate SQL Queries:
{candidates}

# Ranking Criteria (in priority order):
1. **Execution Success with Results** (HIGHEST PRIORITY): Prefer queries that executed successfully and returned data
2. **Correct Value Usage**: Uses EXACT values from COLUMN VALUE EXAMPLES (e.g., 'Comp. Sci.' not 'Computer Science')
3. **Query Pattern Match**: 
   - "X but not Y" → should use EXCEPT
   - "both X and Y" → should use INTERSECT
   - Filtering by related data → should use IN with subquery
4. **Syntax Correctness**: No SQL errors
5. **Logic Accuracy**: Matches the question's intent

# Common Patterns:
- "courses that have prerequisite X" → WHERE course_id IN (SELECT course_id FROM prereq WHERE prereq_id = ...)
- "students who took courses" → WHERE id IN (SELECT id FROM takes WHERE course_id IN ...)
- "instructors who taught X but not Y" → (SELECT ... WHERE X) EXCEPT (SELECT ... WHERE Y)

# Red Flags:
- Wrong column values (check against COLUMN VALUE EXAMPLES)
- Using JOIN when subquery with IN is more appropriate
- Missing EXCEPT for "but not" questions
- Execution failures (unless ALL failed)

# Output:
Best_Candidate_Index: [Index 0 to {max_index}]
Reasoning: [One sentence explaining why this is best]
"""

# ============================================================================
# 3. 辅助工具函数
# ============================================================================

def clean_sql(sql: str) -> str:
    """清理SQL语句"""
    if not sql: return "SELECT 1;"
    sql = sql.strip()
    while sql.upper().startswith('SELECT SELECT'):
        sql = sql[7:].strip()
    if ';' in sql:
        sql = sql.split(';')[0] + ';'
    else:
        sql += ';'
    return ' '.join(sql.split())


# ============================================================================
# SQL 执行验证模块
# ============================================================================

class SQLValidator:
    """SQL 验证器：执行 SQL 并检查是否有效（线程安全版本）"""
    
    def __init__(self, db_root_path: str):
        self.db_root_path = db_root_path
    
    def _get_db_path(self, db_id: str) -> str:
        """获取数据库文件路径"""
        db_file = os.path.join(self.db_root_path, db_id, f"{db_id}.sqlite")
        if not os.path.exists(db_file):
            raise FileNotFoundError(f"Database not found: {db_file}")
        return db_file
    
    def validate_sql(self, sql: str, db_id: str, timeout: float = 5.0) -> dict:
        """
        验证 SQL 是否可执行（线程安全：每次创建新连接）
        
        返回:
        {
            "valid": bool,           # 是否有效
            "error": str | None,     # 错误信息
            "row_count": int,        # 返回行数
            "has_results": bool,     # 是否有结果
            "sample_results": list   # 前几行结果（用于调试）
        }
        """
        result = {
            "valid": False,
            "error": None,
            "row_count": 0,
            "has_results": False,
            "sample_results": []
        }
        
        conn = None
        try:
            # 每次创建新连接（线程安全）
            db_path = self._get_db_path(db_id)
            conn = sqlite3.connect(db_path, timeout=timeout)
            conn.text_factory = str
            cursor = conn.cursor()
            
            # 移除末尾分号
            clean = sql.strip().rstrip(';')
            
            # 执行查询
            cursor.execute(clean)
            rows = cursor.fetchall()
            
            result["valid"] = True
            result["row_count"] = len(rows)
            result["has_results"] = len(rows) > 0
            result["sample_results"] = rows[:3]  # 只保留前3行
            
        except sqlite3.OperationalError as e:
            result["error"] = f"OperationalError: {str(e)}"
        except sqlite3.IntegrityError as e:
            result["error"] = f"IntegrityError: {str(e)}"
        except FileNotFoundError as e:
            result["error"] = f"FileNotFoundError: {str(e)}"
        except Exception as e:
            result["error"] = f"Error: {str(e)}"
        finally:
            # 确保关闭连接
            if conn:
                try:
                    conn.close()
                except:
                    pass
        
        return result
    
    def validate_candidates(self, candidates: list, db_id: str) -> list:
        """
        批量验证候选 SQL，返回有效的候选列表
        
        返回: [(sql, validation_result), ...]
        """
        validated = []
        for sql in candidates:
            result = self.validate_sql(sql, db_id)
            validated.append((sql, result))
        return validated
    
    def filter_valid_candidates(self, candidates: list, db_id: str, 
                                 prefer_with_results: bool = True) -> list:
        """
        过滤出有效的候选 SQL
        
        Args:
            candidates: SQL 候选列表
            db_id: 数据库 ID
            prefer_with_results: 是否优先返回有结果的 SQL
            
        Returns:
            过滤后的有效 SQL 列表
        """
        validated = self.validate_candidates(candidates, db_id)
        
        # 分类：有结果的、有效但无结果的、无效的
        with_results = []
        valid_empty = []
        invalid = []
        
        for sql, result in validated:
            if result["valid"]:
                if result["has_results"]:
                    with_results.append(sql)
                else:
                    valid_empty.append(sql)
            else:
                invalid.append((sql, result["error"]))
        
        # 打印调试信息（可选）
        if invalid:
            print(f"  [Validator] Filtered out {len(invalid)} invalid SQL(s)")
            for sql, err in invalid[:2]:  # 只打印前2个错误
                print(f"    - Error: {err[:80]}...")
        
        # 优先返回有结果的，其次是有效但空的
        if prefer_with_results and with_results:
            return with_results
        elif with_results or valid_empty:
            return with_results + valid_empty
        else:
            # 全部无效时返回原始列表（让 ranking 决定）
            return candidates
    
    def close_all(self):
        """兼容旧接口（现在不需要了，因为每次都创建新连接）"""
        pass

def extract_pure_sql(text: str) -> str:
    """提取最后一个 SQL 代码块"""
    if not text: return "SELECT 1;"
    
    pattern_sql_block = r"```sql\s*([\s\S]*?)\s*```"
    matches = re.findall(pattern_sql_block, text, re.IGNORECASE)
    if matches:
        return clean_sql(matches[-1])

    pattern_code_block = r"```\s*([\s\S]*?)\s*```"
    matches = re.findall(pattern_code_block, text)
    if matches:
        return clean_sql(matches[-1])

    clean_text = re.sub(r'^SQL:\s*', '', text, flags=re.IGNORECASE)
    parts = clean_text.split(';')
    for part in reversed(parts):
        if 'SELECT' in part.upper():
            return clean_sql(part)
            
    return clean_sql(clean_text)


# ============================================================================
# 4. 核心生成类（使用增强 Schema）
# ============================================================================

class EnhancedText2SQL:
    def __init__(self, client: OpenAI, model: str = "gpt-4", db_root_path: str = None, 
                 use_execution_validation: bool = True):
        self.client = client
        self.model = model
        self.db_root_path = db_root_path
        self.schema_cache = {}
        self.use_execution_validation = use_execution_validation
        
        # 初始化 SQL 验证器
        if use_execution_validation and db_root_path:
            self.validator = SQLValidator(db_root_path)
        else:
            self.validator = None

    def _get_schema_str(self, db_id: str) -> str:
        """根据 db_id 动态加载增强的 schema string"""
        if db_id in self.schema_cache:
            return self.schema_cache[db_id]
        
        if not self.db_root_path:
            return ""
            
        db_file = os.path.join(self.db_root_path, db_id, f"{db_id}.sqlite")
        
        try:
            # 使用增强版 schema 读取
            schema_info = get_enhanced_schema_info(
                db_file, 
                sample_rows=3,           # 每表显示3行样例
                max_distinct_values=10   # 最多显示10个不同值
            )
            schema_str = format_enhanced_schema(schema_info)
            self.schema_cache[db_id] = schema_str
            return schema_str
        except Exception as e:
            print(f"Error loading schema for {db_id}: {e}")
            return ""

    def _call_llm(self, prompt: str, max_tokens: int = 1500, temperature: float = 0.0, stop=None, n: int = 1):
        """LLM 调用封装"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                stop=stop,
                n=n
            )
            return [choice.message.content for choice in response.choices]
        except Exception as e:
            print(f"LLM call error: {e}")
            return [""] * n

    def schema_linking(self, question: str, schema_str: str) -> str:
        prompt = SCHEMA_LINKING_PROMPT + "\n" + schema_str + '\nQ: "' + question + '"\nA: Let\'s think step by step.'
        responses = self._call_llm(prompt, stop=["Q:"], temperature=0.0, n=1)
        response = responses[0]
        try:
            if "Schema_links:" in response:
                return response.split("Schema_links:")[1].strip()
        except:
            pass
        return "[]"

    def classify_query(self, question: str, schema_str: str, schema_links: str) -> tuple:
        prompt = CLASSIFICATION_PROMPT + "\n" + schema_str + '\nQ: "' + question + '"\nschema_links: ' + schema_links + '\nA: Let\'s think step by step.'
        responses = self._call_llm(prompt, stop=["Q:"], temperature=0.0, n=1)
        response = responses[0]
        
        if '"EASY"' in response:
            q_class = "EASY"
        elif '"NON-NESTED"' in response:
            q_class = "NON-NESTED"
        else:
            q_class = "NESTED"
            
        sub_questions = ""
        if q_class == "NESTED":
            try:
                if 'questions = ["' in response:
                    sub_questions = response.split('questions = ["')[1].split('"]')[0]
            except: pass
        return q_class, sub_questions

    def _debug_sql(self, question: str, schema_str: str, sql: str) -> str:
        """Self-Correction with enhanced schema"""
        prompt = DEBUG_PROMPT + "\n" + schema_str + '\n#### Question: ' + question + '\n#### SQLite SQL QUERY\n' + sql +'\n#### SQLite FIXED SQL QUERY\n'
        responses = self._call_llm(prompt, stop=["####", "\n\n\n"], temperature=0.0, max_tokens=500, n=1)
        fixed_sql = extract_pure_sql(responses[0])
        return fixed_sql

    def generate_candidates(self, question: str, schema_str: str, schema_links: str, query_class: str, sub_questions: str, n: int = 5) -> list:
        """生成 N 个候选 SQL"""
        if query_class == "EASY":
            prompt_content = f"{EASY_PROMPT}\n{schema_str}\nQ: \"{question}\"\nSchema_links: {schema_links}\nSQL:"
        elif query_class == "NON-NESTED":
            prompt_content = f"{MEDIUM_PROMPT}\n{schema_str}\nQ: \"{question}\"\nSchema_links: {schema_links}\nA: Let's think step by step."
        else:
            stepping_intro = f"\nA: Let's think step by step. \"{question}\" can be solved by knowing the answer to the following sub-question \"{sub_questions}\"."
            prompt_content = f"{HARD_PROMPT}\n{schema_str}\nQ: \"{question}\"\nschema_links: {schema_links}{stepping_intro}\nThe SQL query for the sub-question\""

        raw_candidates = self._call_llm(
            prompt=prompt_content,
            max_tokens=1500,
            temperature=0.7,
            n=n
        )
        
        initial_sqls = [extract_pure_sql(raw) for raw in raw_candidates]
            
        # Debug each candidate
        debugged_sqls = []
        seen = set()
        for sql in initial_sqls:
            fixed_sql = self._debug_sql(question, schema_str, sql)
            fixed_sql = clean_sql(fixed_sql)
            if fixed_sql not in seen:
                debugged_sqls.append(fixed_sql)
                seen.add(fixed_sql)
                
        return debugged_sqls

    def rank_candidates(self, question: str, schema_str: str, candidates: list, db_id: str = None) -> str:
        """选择最佳候选（可选：附带执行结果信息）"""
        if not candidates: return "SELECT 1;"
        if len(candidates) == 1: return candidates[0]
        
        candidates_str = ""
        for i, sql in enumerate(candidates):
            candidates_str += f"Candidate {i}:\n{sql}\n"
            
            # 如果有验证器，附加执行结果信息
            if self.validator and db_id:
                result = self.validator.validate_sql(sql, db_id)
                if result["valid"]:
                    candidates_str += f"  [Execution: SUCCESS, {result['row_count']} rows returned]\n"
                    if result["sample_results"]:
                        # 显示前2行结果
                        sample = str(result["sample_results"][:2])
                        if len(sample) > 100:
                            sample = sample[:100] + "..."
                        candidates_str += f"  [Sample: {sample}]\n"
                else:
                    candidates_str += f"  [Execution: FAILED - {result['error'][:60]}]\n"
            candidates_str += "\n"
        
        prompt = RANKING_PROMPT.format(
            schema=schema_str,
            question=question,
            candidates=candidates_str,
            max_index=len(candidates)-1
        )
        
        responses = self._call_llm(prompt, temperature=0.0, max_tokens=150, n=1)
        result_text = responses[0]
        
        try:
            if "Best_Candidate_Index:" in result_text:
                idx_str = result_text.split("Best_Candidate_Index:")[1].strip()
                match = re.search(r'\d+', idx_str)
                idx = int(match.group()) if match else 0
            else:
                match = re.search(r'\d+', result_text)
                idx = int(match.group()) if match else 0
                
            if 0 <= idx < len(candidates):
                return candidates[idx]
        except Exception as e:
            print(f"Ranking parse error: {e}")
            pass
            
        return candidates[0]

    def generate(self, question: str, db_id: str, num_candidates: int = 5) -> str:
        """主生成流程"""
        schema_str = self._get_schema_str(db_id)
        if not schema_str:
            print(f"Schema not found for db_id: {db_id}")
            return "SELECT 1;"
        
        # Step 1: Schema Linking
        schema_links = self.schema_linking(question, schema_str)
        
        # Step 2: Classification
        query_class, sub_questions = self.classify_query(question, schema_str, schema_links)
        
        # Step 3: Generate Candidates
        candidates = self.generate_candidates(question, schema_str, schema_links, query_class, sub_questions, n=num_candidates)
        
        # Step 4: 执行验证 - 过滤无效 SQL
        if self.validator and candidates:
            valid_candidates = self.validator.filter_valid_candidates(
                candidates, 
                db_id, 
                prefer_with_results=True
            )
            # 如果过滤后还有候选，使用过滤后的
            if valid_candidates:
                candidates = valid_candidates
        
        # Step 5: Ranking（传入 db_id 以获取执行结果）
        final_sql = self.rank_candidates(question, schema_str, candidates, db_id=db_id)
        
        return final_sql


# ============================================================================
# 5. 批量处理
# ============================================================================

def batch_process_questions(client: OpenAI, questions: list, db_root_path: str, model: str, max_workers: int = 8):
    generator = EnhancedText2SQL(client, model, db_root_path)
    
    def process_one(idx_item):
        idx, item = idx_item
        question = item.get("question", "").strip()
        db_id = item.get("db_id", "").strip()
        
        if not question or not db_id:
            return idx, "SELECT 1;"
            
        try:
            sql = generator.generate(question, db_id, num_candidates=5)
        except Exception as e:
            print(f"Error processing {idx} (db: {db_id}): {e}")
            sql = "SELECT 1;"
            
        return idx, sql

    results_dict = {}
    indexed_items = [(i, q) for i, q in enumerate(questions)]
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_one, item): item[0] for item in indexed_items}
        
        for future in tqdm(as_completed(futures), total=len(questions), desc="Generating SQL"):
            idx, sql = future.result()
            results_dict[idx] = sql
            
    return [results_dict[i] for i in range(len(questions))]


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    API_KEY = os.getenv("OPENAI_API_KEY", "sk-voNjlAd5LKEGjyVLKDUqOxvM0uMKFNh7vif9bKCgd5M8kJCb")
    BASE_URL = os.getenv("OPENAI_BASE_URL", "https://open.xiaojingai.com/v1")
    DB_ROOT_PATH = "database"
    model = "gpt-4o"
    
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    
    # ========== 测试 4: 批量处理 ==========
    print("\n" + "=" * 60)
    print("TEST 4: Batch Processing")
    print("=" * 60)
    
    if os.path.exists("test.json"):
        with open("test.json", "r") as f:
            test_data = json.load(f)
        
        # 批量处理
        results = batch_process_questions(
            client, 
            test_data[:],  # 只测试10条
            DB_ROOT_PATH, 
            model, 
            max_workers=16
        )
        
        # 保存结果
        output_file = f"results_{model}_enhanced4.txt"
        with open(output_file, "w") as f:
            for sql in results:
                f.write(f"{sql}\n")
        
        print(f"Results saved to {output_file}")
        
        # 统计验证结果
        validator = SQLValidator(DB_ROOT_PATH)
        valid_count = 0
        for i, sql in enumerate(results):
            db_id = test_data[i]['db_id']
            result = validator.validate_sql(sql, db_id)
            if result['valid']:
                valid_count += 1
        validator.close_all()
        
        print(f"Validation: {valid_count}/{len(results)} queries are executable ({100*valid_count/len(results):.1f}%)")