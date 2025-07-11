import os
import json
import openai
from tqdm import tqdm
import sys
import re
import time
import sqlite3

SCHEMA_DIR = "schemas"
QUERY_DIR = "queries"
SQL_DIR = "sqls"
API_KEY_PATH = "api_key.txt"

def load_api_key():
    with open(API_KEY_PATH) as f:
        return f.read().strip()

def load_schema(domain):
    path = os.path.join(SCHEMA_DIR, f"{domain['name']}.json")
    with open(path, encoding="utf-8") as f:
        return f.read()

def load_queries(domain):
    path = os.path.join(QUERY_DIR, f"{domain['name']}_queries.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def extract_sql_from_response(content):
    match = re.search(r"```sql\s*(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    match2 = re.search(r"```\s*(.*?)```", content, re.DOTALL)
    if match2:
        return match2.group(1).strip()
    lines = [line for line in content.strip().splitlines() if line.strip() and not line.strip().startswith('--')]
    if lines:
        return lines[0].strip()
    return content.strip()

def make_sql_prompt(domain, schema, query, level, qtype):
    base = f"""
도메인: {domain['name']}
설명: {domain['description']}
테이블 스키마(JSON): {schema}
난이도: {level}
유형: {qtype}
자연어 질의: "{query}"
"""
    strong_sample_only = "- 반드시 sample 테이블만 사용하세요. sample 이외의 테이블(예: reviews 등)은 절대 사용하지 마세요. sample 이외의 테이블이 SQL에 등장하면 무조건 오답입니다."
    if qtype == "SELECT":
        extra = f"""
아래 조건을 모두 지켜서 SELECT SQL 쿼리만 생성하세요.
{strong_sample_only}
- 컬럼명과 타입은 스키마와 완전히 일치해야 하며, 오타/대소문자/공백/특수문자 없이 정확히 사용하세요.
- 스키마에 없는 컬럼/테이블은 절대 사용하지 마세요.
- SQLite에서 지원하는 구문만 사용하세요. (JOIN, 서브쿼리, 집계함수, 윈도우함수, 복잡한 연산 금지)
- 설명, 코드블록, 주석, 불필요한 출력 없이 쿼리문만 한 줄로 반환하세요.
- 쿼리문 끝에 반드시 세미콜론(;)을 붙이세요.
- 예시: SELECT 컬럼명 FROM sample WHERE 조건;
"""
    elif qtype == "INSERT":
        extra = f"""
아래 조건을 모두 지켜서 INSERT SQL 쿼리만 생성하세요.
{strong_sample_only}
- 컬럼명과 타입은 스키마와 완전히 일치해야 하며, 오타/대소문자/공백/특수문자 없이 정확히 사용하세요.
- 스키마에 없는 컬럼/테이블은 절대 사용하지 마세요.
- SQLite에서 지원하는 구문만 사용하세요.
- 설명, 코드블록, 주석, 불필요한 출력 없이 쿼리문만 한 줄로 반환하세요.
- 쿼리문 끝에 반드시 세미콜론(;)을 붙이세요.
- 예시: INSERT INTO sample (컬럼1, 컬럼2, ...) VALUES (...);
"""
    elif qtype == "UPDATE":
        extra = f"""
아래 조건을 모두 지켜서 UPDATE SQL 쿼리만 생성하세요.
{strong_sample_only}
- 컬럼명과 타입은 스키마와 완전히 일치해야 하며, 오타/대소문자/공백/특수문자 없이 정확히 사용하세요.
- 스키마에 없는 컬럼/테이블은 절대 사용하지 마세요.
- SQLite에서 지원하는 구문만 사용하세요.
- 설명, 코드블록, 주석, 불필요한 출력 없이 쿼리문만 한 줄로 반환하세요.
- 쿼리문 끝에 반드시 세미콜론(;)을 붙이세요.
- 예시: UPDATE sample SET 컬럼명=값 WHERE 조건;
"""
    else:  # DELETE
        extra = f"""
아래 조건을 모두 지켜서 DELETE SQL 쿼리만 생성하세요.
{strong_sample_only}
- 컬럼명과 타입은 스키마와 완전히 일치해야 하며, 오타/대소문자/공백/특수문자 없이 정확히 사용하세요.
- 스키마에 없는 컬럼/테이블은 절대 사용하지 마세요.
- SQLite에서 지원하는 구문만 사용하세요.
- 설명, 코드블록, 주석, 불필요한 출력 없이 쿼리문만 한 줄로 반환하세요.
- 쿼리문 끝에 반드시 세미콜론(;)을 붙이세요.
- 예시: DELETE FROM sample WHERE 조건;
"""
    return base + extra

def extract_sql_and_answer(content):
    # SQL과 답변을 분리
    lines = content.strip().splitlines()
    sql = ""
    answer = ""
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('--') or line.startswith('모범'):
            continue
            
        # SQL 문인지 확인 (세미콜론 포함)
        if ';' in line and not answer:
            sql = line
        elif not sql:
            # 아직 SQL을 찾지 못했다면
            sql = line
        else:
            # SQL 이후는 답변
            if answer:
                answer += " " + line
            else:
                answer = line
    
    # SQL에서 세미콜론 제거
    if sql and sql.endswith(';'):
        sql = sql[:-1]
    
    return sql.strip(), answer.strip()

def call_openai_with_retry(api_key, prompt, max_retries=3, return_attempts=False):
    openai.api_key = api_key
    for attempt in range(max_retries):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=256
            )
            if return_attempts:
                return response["choices"][0]["message"]["content"].strip(), attempt + 1
            return response["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 2초, 4초, 6초
                print(f"API 오류 발생, {wait_time}초 후 재시도... ({attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                raise e

def create_sample_table(conn, schema_json):
    schema = json.loads(schema_json)
    cols = [f"{k} TEXT" for k in schema.keys()]
    table_name = "sample"
    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.execute(f"CREATE TABLE {table_name} ({', '.join(cols)})")
    for i in range(3):
        values = [f"'val{i}_{k}'" for k in schema.keys()]
        conn.execute(f"INSERT INTO {table_name} VALUES ({', '.join(values)})")

def validate_sql(sql, conn, qtype):
    try:
        if qtype == "SELECT":
            conn.execute("EXPLAIN " + sql)
        else:
            conn.execute(sql)
        return True, None
    except Exception as e:
        return False, str(e)

def generate_sql(api_key, domain, schema, query, level, qtype, max_retries=5):
    attempts = 0
    last_error = None
    last_sql = None
    last_answer = None
    while attempts < max_retries:
        prompt = make_sql_prompt(domain, schema, query, level, qtype)
        content = call_openai_with_retry(api_key, prompt)
        sql, answer = extract_sql_and_answer(content)
        last_sql = sql
        last_answer = answer
        attempts += 1
        # 실제 실행 검증
        conn = sqlite3.connect(":memory:")
        try:
            create_sample_table(conn, schema)
            valid, error = validate_sql(sql, conn, qtype)
            if valid:
                conn.close()
                # 후처리: expected_answer가 비어있으면 기본값 설정
                if not answer and qtype in ["UPDATE", "DELETE", "INSERT"]:
                    if qtype == "UPDATE":
                        answer = "1개 레코드 수정됨"
                    elif qtype == "DELETE":
                        answer = "1개 레코드 삭제됨"
                    elif qtype == "INSERT":
                        answer = "1개 레코드 추가됨"
                elif not answer and qtype == "SELECT":
                    answer = "3개 레코드"  # SELECT의 기본값
                return sql, answer, attempts, None
            else:
                last_error = error
        finally:
            conn.close()
    # 실패 시 마지막 SQL, 오류 메시지 반환
    return last_sql, last_answer, attempts, last_error

def main():
    os.makedirs(SQL_DIR, exist_ok=True)
    api_key = load_api_key()
    with open("domains.json", encoding="utf-8") as f:
        domains = json.load(f)
    for domain in tqdm(domains, desc="도메인별 SQL 생성"):
        schema = load_schema(domain)
        # 각 도메인별 쿼리 파일에서 70개 쿼리 읽기
        with open(os.path.join(QUERY_DIR, f"{domain['name']}_queries.json"), encoding="utf-8") as f:
            queries_obj = json.load(f)
        queries = queries_obj["queries"]
        print(f"{domain['name']}: {len(queries)}개 쿼리 생성")
        sql_list = []
        for q in queries:
            sql, answer, retry_count, error_msg = generate_sql(api_key, domain, schema, q["query"], q["level"], q["type"])
            item = {
                "query": q["query"],
                "level": q["level"],
                "type": q["type"],
                "sql": sql,
                "retry_count": retry_count
            }
            if error_msg:
                item["error_msg"] = error_msg
            sql_list.append(item)
            time.sleep(0.5)
        fname = os.path.join(SQL_DIR, f"{domain['name']}_sqls.json")
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(sql_list, f, ensure_ascii=False, indent=2)
        print(f"{domain['name']} SQL 저장 완료: {fname}")
        time.sleep(1)
    print("모든 도메인 SQL 생성 완료.")

if __name__ == "__main__":
    main() 