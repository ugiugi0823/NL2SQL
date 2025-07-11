import os
import json
import openai
import random
import re
import time
from tqdm import tqdm

QUERY_DIR = "queries"
SCHEMA_DIR = "schemas"
DOMAIN_PATH = "domains.json"
API_KEY_PATH = "api_key.txt"

LEVELS = ["Basic", "Intermediate", "Advanced", "Expert"]
TYPES = ["SELECT", "INSERT", "UPDATE", "DELETE"]
TYPE_LEVEL_COUNTS = {
    "SELECT": {"Basic": 5, "Intermediate": 5, "Advanced": 5, "Expert": 5},
    "INSERT": {"Basic": 2, "Intermediate": 2, "Advanced": 3, "Expert": 3},
    "UPDATE": {"Basic": 5, "Intermediate": 5, "Advanced": 5, "Expert": 5},
    "DELETE": {"Basic": 5, "Intermediate": 5, "Advanced": 5, "Expert": 5},
}  # 총 70개

LEVEL_CRITERIA = {
    "Basic": "- 단일 테이블, 단순 조건(=, <, >, <=, >=)만 사용\n- 연산, 집계, 정렬, LIKE, IN, JOIN, 서브쿼리 등은 사용하지 마세요.",
    "Intermediate": "- 집계(COUNT, AVG, SUM, MAX, MIN), ORDER BY, LIMIT, LIKE, BETWEEN, DISTINCT, IN, NOT IN 사용 가능\n- 간단한 날짜 조건 사용 가능\n- 복잡한 다중 조건, JOIN, 서브쿼리, GROUP BY+HAVING, 복수 필드 UPDATE/INSERT는 사용하지 마세요.",
    "Advanced": "- 다중 조건(AND, OR, 괄호), !=, NOT, IS NULL, IS NOT NULL, ORDER BY+LIMIT, 복수 필드 UPDATE/INSERT, LIKE+복합조건 사용 가능\n- JOIN, 서브쿼리, GROUP BY+HAVING은 사용하지 마세요.",
    "Expert": "- 서브쿼리, JOIN, GROUP BY+HAVING, 복합 조건, INSERT 전체 칼럼 등 고급 SQL 구문 사용 가능\n- 모든 SQL 구문 허용"
}

def load_api_key():
    with open(API_KEY_PATH) as f:
        return f.read().strip()

def load_domains():
    with open(DOMAIN_PATH, encoding="utf-8") as f:
        return json.load(f)

def load_schema(domain):
    path = os.path.join(SCHEMA_DIR, f"{domain['name']}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def extract_json_from_response(content):
    match = re.search(r"```json\\s*(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()

def make_query_prompt(domain, schema_dict, level, qtype, n):
    columns_info = []
    for col_name, col_info in schema_dict.items():
        columns_info.append(f"- {col_name}: {col_info['comment']}")
    columns_text = "\n".join(columns_info)
    level_criteria = LEVEL_CRITERIA[level]
    return f"""
당신은 SQL 전문가입니다. 주어진 스키마를 정확히 이해하고 자연어 질의를 생성해주세요.

**도메인**: {domain['name']}
**설명**: {domain['description']}

**사용 가능한 필드 (반드시 이 필드만 사용하세요)**:
{columns_text}

**요청사항**:
- SQL 유형: {qtype}
- 난이도: {level}
- 위의 필드만 사용하여 {qtype} 유형의 자연어 질의 {n}개를 JSON 배열로 생성하세요.

**중요 규칙**:
1. 위에 나열된 필드만 사용하세요. 스키마에 없는 필드는 절대 사용하지 마세요.
2. 난이도 기준:\n{level_criteria}
3. SQL 구문(SELECT, INSERT, UPDATE, DELETE, FROM, WHERE 등)이 들어간 문장은 절대 생성하지 마세요.
4. SQL 코드, 쿼리문, SQL 키워드가 포함된 문장은 모두 금지
5. 각 질의는 한 문장으로 작성
6. 중복 없이 다양하게 생성
7. 실제 필드명을 자연스럽게 사용하세요 (예: product_name, stock_quantity, temperature 등)

**다양성 요구사항**:
- 조건을 다양하게 구성: 단일 조건, 복합 조건(AND/OR), 범위 조건, NULL 조건, LIKE 조건 등
- 표현 방식을 다양하게: "알려줘", "확인해줘", "조회해주세요", "찾아줘", "보여줘", "제공해줘", "리스트로", "상세히" 등
- 구체적인 값과 추상적인 조건을 혼합: "25도 이상" vs "높은 기온", "2020년 이후" vs "최근"
- 문장 구조 다양화: "A가 B인 경우 C를 D로 변경" vs "C를 D로 변경하는데 A가 B인 경우에만"
- 시간 조건, 수치 조건, 문자열 조건을 균형있게 사용
- 부정문, 의문문, 조건문 등 다양한 문장 형태 사용

**생성할 질의**:
- 설명 없이 JSON만 반환하세요. 코드블록도 사용하지 마세요.
- JSON 배열 예시: ["질의1", "질의2", ...]
"""

SQL_KEYWORDS = [
    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'FROM', 'WHERE', 'GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT',
    'JOIN', 'INTO', 'VALUES', 'SET', 'DISTINCT', 'COUNT', 'AVG', 'SUM', 'MIN', 'MAX', 'AND', 'OR', 'NOT',
    'IS NULL', 'IS NOT NULL', 'IN', 'BETWEEN', 'LIKE'
]

def contains_sql_keyword(text):
    upper = text.upper()
    for kw in SQL_KEYWORDS:
        if kw in upper:
            return True
    return False

def calculate_similarity(text1, text2):
    """간단한 유사도 계산 (공통 단어 기반)"""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)

def is_similar_to_existing(query, existing_queries, threshold=0.7):
    """기존 질의와 유사한지 확인"""
    for existing in existing_queries:
        similarity = calculate_similarity(query, existing['nl'])
        if similarity > threshold:
            return True
    return False

def get_openai_client():
    api_key = load_api_key()
    return openai.OpenAI(api_key=api_key)

client = get_openai_client()

def call_openai_with_retry(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=1024
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"API 오류 발생, {wait_time}초 후 재시도... ({attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                raise e

def generate_queries(domain):
    schema_dict = load_schema(domain)
    queries = []
    retry_counts = {qtype: {level: 0 for level in LEVELS} for qtype in TYPES}
    for qtype in TYPES:
        for level in LEVELS:
            n_target = TYPE_LEVEL_COUNTS[qtype][level]
            collected = []
            tried = 0
            while len(collected) < n_target and tried < 10:
                n = n_target - len(collected)
                prompt = make_query_prompt(domain, schema_dict, level, qtype, n)
                content = call_openai_with_retry(prompt)
                json_str = extract_json_from_response(content)
                if not json_str:
                    print(f"[ERROR] {domain['name']} {level} {qtype} LLM 응답이 비어있음.")
                    break
                try:
                    qlist = json.loads(json_str)
                    for q in qlist:
                        if (q not in [item['nl'] for item in collected] and 
                            not contains_sql_keyword(q) and 
                            not is_similar_to_existing(q, collected)):
                            collected.append({"nl": q, "level": level, "dml": qtype})
                except Exception as e:
                    print(f"[ERROR] {domain['name']} {level} {qtype} 질의 파싱 오류: {e}\n응답 내용: {content}")
                    break
                tried += 1
                time.sleep(1)
            retry_counts[qtype][level] = tried
            for q in collected[:n_target]:
                queries.append(q)
            print(f"[{domain['name']}] {qtype} {level} 생성: {len(collected[:n_target])}개, 시도: {tried}회")
    random.shuffle(queries)
    return queries, retry_counts

def main():
    os.makedirs(QUERY_DIR, exist_ok=True)
    domains = load_domains()
    for domain in tqdm(domains, desc="도메인별 질의 생성"):
        print(f"\n{'='*50}")
        print(f"도메인: {domain['name']}")
        print(f"설명: {domain['description']}")
        print(f"{'='*50}")
        queries, retry_counts = generate_queries(domain)
        fname = os.path.join(QUERY_DIR, f"{domain['name']}_queries.json")
        with open(fname, "w", encoding="utf-8") as f:
            json.dump({"queries": queries, "retry_counts": retry_counts}, f, ensure_ascii=False, indent=2)
        print(f"{domain['name']} 질의 저장 완료: {fname}")
        time.sleep(2)

if __name__ == "__main__":
    main() 