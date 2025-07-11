import os
import time
import sqlite3
import json
import openai

SQL_DIR = "sqls"
SCHEMA_DIR = "schemas"
RESULT_DIR = "results"
API_KEY_PATH = "api_key.txt"

os.makedirs(RESULT_DIR, exist_ok=True)

def load_api_key():
    with open(API_KEY_PATH) as f:
        return f.read().strip()

def create_sample_table(conn, schema_json):
    try:
        schema = json.loads(schema_json)
        cols = [f"{k} TEXT" for k in schema.keys()]
        table_name = "sample"
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.execute(f"CREATE TABLE {table_name} ({', '.join(cols)})")
        for i in range(3):
            values = [f"'val{i}_{k}'" for k in schema.keys()]
            conn.execute(f"INSERT INTO {table_name} VALUES ({', '.join(values)})")
        return True
    except Exception as e:
        return False

def validate_sql(sql, conn, qtype):
    try:
        start = time.time()
        if qtype == "SELECT":
            conn.execute("EXPLAIN " + sql)
        else:
            conn.execute(sql)
        elapsed = time.time() - start
        return True, elapsed
    except Exception as e:
        return False, str(e)

def make_feedback_prompt_nbest(domain, schema, query, level, prev_sql, error_msg, n=3):
    return f"""
도메인: {domain['name']}
설명: {domain['description']}
테이블 스키마(JSON): {schema}
난이도: {level}
자연어 질의: "{query}"
이전 쿼리:
{prev_sql}
실행 오류 메시지:
{error_msg}
아래 조건을 모두 지키면서, 반드시 오류를 수정하여 SQL 쿼리 {n}개를 리스트로 반환하세요.
- 반드시 sample 테이블만 사용하세요.
- 컬럼명과 타입은 스키마와 완전히 일치해야 하며, 오타/대소문자/공백/특수문자 없이 정확히 사용하세요.
- 스키마에 없는 컬럼/테이블은 절대 사용하지 마세요.
- SQLite에서 지원하는 구문만 사용하세요. (JOIN, 서브쿼리, 집계함수, 윈도우함수, 복잡한 연산 금지)
- 설명, 코드블록, 주석, 불필요한 출력 없이 쿼리문만 한 줄씩 리스트로 반환하세요.
- 각 쿼리문 끝에 반드시 세미콜론(;)을 붙이세요.
- 반환 예시: ["SELECT ...;", "SELECT ...;", "SELECT ...;"]
"""

def extract_sqls_from_response_list(content):
    import re
    # JSON 리스트 추출
    match = re.search(r"\[(.*?)\]", content, re.DOTALL)
    if match:
        arr = match.group(0)
        try:
            sqls = json.loads(arr)
            return [s.strip() for s in sqls if s.strip()]
        except Exception:
            pass
    # 줄별로 세미콜론 있는 것만 추출
    lines = [line.strip().strip(',') for line in content.strip().splitlines() if ';' in line]
    return [line for line in lines if line]

def regenerate_sql_nbest(api_key, domain, schema, query, level, prev_sql, error_msg, n=3, temperature=0.5):
    openai.api_key = api_key
    prompt = make_feedback_prompt_nbest(domain, schema, query, level, prev_sql, error_msg, n)
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=512
    )
    content = response["choices"][0]["message"]["content"].strip()
    sqls = extract_sqls_from_response_list(content)
    return sqls

def main():
    api_key = load_api_key()
    with open("domains.json", encoding="utf-8") as f:
        domains = json.load(f)
    summary = {}
    for domain in domains:
        schema_path = os.path.join(SCHEMA_DIR, f"{domain['name']}.json")
        with open(schema_path, encoding="utf-8") as f:
            schema_json = f.read()
        sqls_path = os.path.join(SQL_DIR, f"{domain['name']}_sqls.json")
        if not os.path.exists(sqls_path):
            continue
        with open(sqls_path, encoding="utf-8") as f:
            sql_items = json.load(f)
        results = []
        type_stats = {}
        for item in sql_items:
            sql = item["sql"]
            qtype = item.get("type", "SELECT")
            conn = sqlite3.connect(":memory:")
            ok = create_sample_table(conn, schema_json)
            if not ok:
                results.append({"query": item["query"], "level": item["level"], "type": qtype, "status": "스키마 오류"})
                type_stats.setdefault(qtype, {"total": 0, "ok": 0, "fail": 0, "schema_error": 0})
                type_stats[qtype]["total"] += 1
                type_stats[qtype]["schema_error"] += 1
                conn.close()
                continue
            valid, info = validate_sql(sql, conn, qtype)
            if valid:
                results.append({"query": item["query"], "level": item["level"], "type": qtype, "status": "OK", "exec_time": info, "sql": sql})
                type_stats.setdefault(qtype, {"total": 0, "ok": 0, "fail": 0, "schema_error": 0})
                type_stats[qtype]["total"] += 1
                type_stats[qtype]["ok"] += 1
            else:
                results.append({"query": item["query"], "level": item["level"], "type": qtype, "status": "실패", "error": info, "sql": sql})
                type_stats.setdefault(qtype, {"total": 0, "ok": 0, "fail": 0, "schema_error": 0})
                type_stats[qtype]["total"] += 1
                type_stats[qtype]["fail"] += 1
            conn.close()
        # 결과 저장
        result_path = os.path.join(RESULT_DIR, f"{domain['name']}_result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        summary[domain['name']] = type_stats
    # summary 저장
    summary_path = os.path.join(RESULT_DIR, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("SQL 검증 및 요약 완료.")

if __name__ == "__main__":
    main() 