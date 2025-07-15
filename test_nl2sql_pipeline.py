import json
import os
import openai
import re
import mysql.connector
from mysql.connector import Error
import sqlglot
# sqlparse import 제거
# from sqlparse.sql import IdentifierList, Identifier, Where, TokenList
# from sqlparse.tokens import Keyword, DML

def load_api_key():
    with open("api_key.txt") as f:
        return f.read().strip()

client = openai.OpenAI(api_key=load_api_key())

def call_openai_with_retry(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates natural language to SQL queries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            import time
            print(f"API 호출 실패, 재시도 중... ({attempt + 1}/{max_retries})")
            time.sleep(2 ** attempt)

def extract_json_from_response(response):
    json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
    if json_match:
        return json_match.group(1)
    json_match = re.search(r'\[.*\]', response, re.DOTALL)
    if json_match:
        return json_match.group(0)
    return response

def get_schema_ddl(schema_file):
    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"스키마 파일이 없습니다: {schema_file}")
    with open(schema_file, 'r', encoding='utf-8') as f:
        return f.read().strip()

def get_schema_fields(schema_ddl):
    create_match = re.search(r'CREATE TABLE.*?\((.*?)\)', schema_ddl, re.DOTALL | re.IGNORECASE)
    if not create_match:
        return set()
    columns_section = create_match.group(1)
    lines = [line.strip() for line in columns_section.split('\n') if line.strip()]
    fields = set()
    for line in lines:
        if any(keyword in line.upper() for keyword in ['PRIMARY KEY', 'KEY', 'CONSTRAINT', 'CHECK', 'INDEX']):
            continue
        col_match = re.search(r'`([^`]+)`', line)
        if col_match:
            fields.add(col_match.group(1).strip())
    print(f"[스키마 컬럼명] {fields}")
    return fields

def extract_column_names_from_sql(sql, schema_fields, table_name=None):
    """
    sqlglot을 활용해 SQL문에서 실제 컬럼명만 추출하여 반환한다.
    SELECT/UPDATE/INSERT/DELETE 모두 지원.
    반환값: (missing_fields, matched_fields)
    """
    try:
        parsed = sqlglot.parse_one(sql)
        columns = {col.name.strip() for col in parsed.find_all(sqlglot.expressions.Column)}
    except Exception as e:
        print(f"[sqlglot parse error] {e}\nSQL: {sql}")
        columns = set()
    print(f"[SQL 컬럼명] {columns}")
    schema_fields_set = set(f.strip() for f in schema_fields)
    missing = [col for col in columns if col not in schema_fields_set]
    matched = [col for col in columns if col in schema_fields_set]
    print(f"[missing_fields] {missing}")
    print(f"[matched_fields] {matched}")
    return missing, matched

def get_mysql_connection(db_name):
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="qwer",
            database=db_name
        )
        return conn
    except Error as e:
        return None

# UPDATE/INSERT/DELETE도 트랜잭션 롤백으로 안전하게 검증
def validate_sql_on_db(sql, db_name):
    sql_strip = sql.strip().lower()
    conn = get_mysql_connection(db_name)
    if conn is None:
        return False, "DB connection failed."
    try:
        with conn.cursor() as cursor:
            # 트랜잭션 시작
            cursor.execute("START TRANSACTION;")
            try:
                cursor.execute(sql)
                _ = cursor.fetchall() if sql_strip.startswith("select") else None
                # 롤백으로 데이터 변경 방지
                cursor.execute("ROLLBACK;")
                conn.close()
                return True, None
            except Exception as e:
                cursor.execute("ROLLBACK;")
                conn.close()
                return False, str(e)
    except Exception as e:
        return False, str(e)

def make_nl_prompt(schema_ddl, dml):
    return f"""
아래 [참조 스키마]와 DML 유형을 참고해서 다양한 조건(WHERE, HAVING, <, >, =, <=, >= 등 부호, 집계 등)이 반드시 포함된 자연어 질의(nl) 10개를 JSON 배열로 생성해줘.

[참조 스키마]
{schema_ddl}
DML 유형: {dml}

응답 형식:
```json
[
  {{"nl": "..."}},
  ... (총 10개)
]
```
설명 없이 JSON 배열로만 반환해줘.
"""

def make_sql_prompt(schema_ddl, dml, nl_list):
    nl_json = json.dumps([{"nl": nl} for nl in nl_list], ensure_ascii=False, indent=2)
    return f"""
아래 [참조 스키마], DML 유형, 자연어 질의(nl) 10개를 참고해서 각 nl에 맞는 SQL을 생성해줘.\n\n각 SQL에는 다양한 조건(WHERE, HAVING, <, >, =, <=, >= 등 부호, 집계 등)이 반드시 포함되어야 해.\n10개 모두 JSON 배열로 반환해.

[참조 스키마]
{schema_ddl}
DML 유형: {dml}
자연어 질의(nl) 10개:
{nl_json}

응답 형식:
```json
[
  {{"nl": "...", "sql": "...", "dml": "{dml}"}},
  ... (총 10개)
]
```
설명 없이 JSON 배열로만 반환해줘.
"""

def main():
    dml_types = ["SELECT", "INSERT", "UPDATE", "DELETE"]
    os.makedirs("queries", exist_ok=True)
    schema_dir = "sqls"
    for schema_file in os.listdir(schema_dir):
        if not schema_file.endswith("_schema.sql"):
            continue
        domain_name = schema_file.replace("_schema.sql", "").replace(" ", "_")
        # if domain_name != "날씨_정보":
        #     continue
        schema_path = os.path.join(schema_dir, schema_file)
        schema_ddl = get_schema_ddl(schema_path)
        schema_fields = get_schema_fields(schema_ddl)
        all_results = []
        for dml in dml_types:
            nl_prompt = make_nl_prompt(schema_ddl, dml)
            try:
                nl_content = call_openai_with_retry(nl_prompt)
                nl_json_str = extract_json_from_response(nl_content)
                nl_items = json.loads(nl_json_str)
                nl_list = [item.get("nl", "").strip() for item in nl_items if item.get("nl", "").strip()]
            except Exception as e:
                print(f"[ERROR] NL 생성 실패: {e}")
                continue
            if not nl_list:
                continue
            sql_prompt = make_sql_prompt(schema_ddl, dml, nl_list)
            try:
                sql_content = call_openai_with_retry(sql_prompt)
                sql_json_str = extract_json_from_response(sql_content)
                sql_items = json.loads(sql_json_str)
                for sql_item in sql_items:
                    nl = sql_item.get("nl", "").strip()
                    sql = sql_item.get("sql", "").strip()
                    dml_val = sql_item.get("dml", dml).strip()
                    if not nl or not sql or not dml_val:
                        continue
                    print(f"\n[NL] {nl}\n[SQL] {sql}")
                    missing_fields, matched_fields = extract_column_names_from_sql(sql, schema_fields, table_name=domain_name)
                    db_success, db_error = validate_sql_on_db(sql, domain_name)
                    all_results.append({
                        "nl": nl,
                        "sql": sql,
                        "dml": dml_val,
                        "db_success": db_success,
                        "db_error": db_error,
                        "missing_fields": missing_fields,
                        "matched_fields": matched_fields
                    })
            except Exception as e:
                print(f"[ERROR] SQL 생성 실패: {e}")
                continue
        if all_results:
            out_path = f"queries/{domain_name}_nl2sql.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"results": all_results}, f, ensure_ascii=False, indent=2)
            print(f"[+] {domain_name} NL2SQL 결과 저장 완료: {out_path}")

if __name__ == "__main__":
    main() 