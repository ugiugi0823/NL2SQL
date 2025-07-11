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
    "SELECT": {"Basic": 3, "Intermediate": 3, "Advanced": 3, "Expert": 3},
    "INSERT": {"Basic": 2, "Intermediate": 2, "Advanced": 2, "Expert": 2},
    "UPDATE": {"Basic": 3, "Intermediate": 3, "Advanced": 3, "Expert": 3},
    "DELETE": {"Basic": 3, "Intermediate": 3, "Advanced": 3, "Expert": 3},
}  # 총 48개 (테스트용으로 줄임)

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

def make_nl_sql_prompt(domain, schema_dict, level, qtype, n):
    columns_info = []
    for col_name, col_info in schema_dict.items():
        columns_info.append(f"- {col_name}: {col_info['comment']}")
    columns_text = "\n".join(columns_info)
    
    # 난이도별 요구사항 정의
    level_requirements = {
        "Basic": """
**Basic 난이도 요구사항**:
- 단일 테이블만 사용
- 단순 조건절만 사용 (=, <, >, <=, >=)
- 연산 없음, 집계 없음, 정렬 없음
- 예시: WHERE genre = '공포', WHERE rating >= 8.0""",
        
        "Intermediate": """
**Intermediate 난이도 요구사항**:
- 집계 함수 사용: COUNT, AVG, SUM, MAX, MIN
- 정렬 또는 제한: ORDER BY, LIMIT
- LIKE, BETWEEN, DISTINCT, IN, NOT IN 사용
- 간단한 날짜 조건
- 예시: GROUP BY genre, BETWEEN '2010-01-01' AND '2020-01-01'""",
        
        "Advanced": """
**Advanced 난이도 요구사항**:
- 다중 조건 (AND, OR, 괄호 포함된 조건식)
- 복잡한 조건 연산자: !=, NOT, IS NULL, IS NOT NULL
- 정렬 + 제한 조합 (ORDER BY ... LIMIT)
- 조건에 문자열 포함 검색 (LIKE + 복합 조건)
- 복수 필드 UPDATE / INSERT
- 예시: WHERE rating >= 8 AND genre != '로맨스'""",
        
        "Expert": """
**Expert 난이도 요구사항**:
- 서브쿼리 포함 (WHERE x IN (SELECT ...))
- JOIN 사용 (INNER/LEFT/RIGHT JOIN)
- GROUP BY + HAVING
- 복수 조건에 정렬, 집계, 서브쿼리 혼합
- INSERT 시 모든 칼럼 채움
- 예시: GROUP BY director HAVING COUNT(*) > 3"""
    }
    
    return f"""
당신은 SQL 전문가입니다. 주어진 스키마를 정확히 이해하고 자연어 질의와 SQL을 함께 생성해주세요.

**도메인**: {domain['name']}
**설명**: {domain['description']}

**사용 가능한 필드 (반드시 이 필드만 사용하세요)**:
{columns_text}

**요청사항**:
- SQL 유형: {qtype}
- 난이도: {level}
{level_requirements[level]}

**중요 규칙**:
1. 위에 나열된 필드만 사용하세요. 스키마에 없는 필드는 절대 사용하지 마세요.
2. SQL 구문(SELECT, INSERT, UPDATE, DELETE, FROM, WHERE 등)이 NL에 들어가면 안 됩니다.
3. SQL 코드, 쿼리문, SQL 키워드가 NL에 포함된 문장은 모두 금지
4. 각 질의는 한 문장으로 작성
5. 중복 없이 다양하게 생성
6. 실제 필드명을 자연스럽게 사용하세요
7. **난이도에 맞는 SQL 요소를 사용할 수 있도록 질의를 구성하세요**
8. **NL과 SQL이 반드시 일치해야 합니다** (NL이 INSERT면 SQL도 INSERT)

**다양성 요구사항**:
- 조건을 다양하게 구성: 단일 조건, 복합 조건(AND/OR), 범위 조건, NULL 조건 등
- 표현 방식을 다양하게: "알려줘", "확인해줘", "조회해주세요", "찾아줘", "보여줘", "제공해줘", "리스트로", "상세히" 등
- 구체적인 값과 추상적인 조건을 혼합
- 문장 구조 다양화

**생성할 형식**:
- 설명 없이 JSON만 반환하세요. 코드블록도 사용하지 마세요.
- JSON 배열 예시: [{{"nl": "질의1", "sql": "SQL1"}}, {{"nl": "질의2", "sql": "SQL2"}}]
- {n}개의 NL-SQL 쌍을 생성하세요.
"""

def make_sql_prompt(domain, schema_dict, nl_query, level, qtype):
    columns_info = []
    for col_name, col_info in schema_dict.items():
        columns_info.append(f"- {col_name}: {col_info['comment']}")
    columns_text = "\n".join(columns_info)
    
    # 난이도별 SQL 요구사항 정의
    level_sql_requirements = {
        "Basic": """
**Basic 난이도 SQL 요구사항**:
- 단일 테이블만 사용
- 단순 조건절만 사용 (=, <, >, <=, >=)
- 연산 없음, 집계 없음, 정렬 없음
- 예시: WHERE genre = '공포', WHERE rating >= 8.0""",
        
        "Intermediate": """
**Intermediate 난이도 SQL 요구사항**:
- 집계 함수 사용: COUNT, AVG, SUM, MAX, MIN
- 정렬 또는 제한: ORDER BY, LIMIT
- LIKE, BETWEEN, DISTINCT, IN, NOT IN 사용
- 간단한 날짜 조건
- 예시: GROUP BY genre, BETWEEN '2010-01-01' AND '2020-01-01'""",
        
        "Advanced": """
**Advanced 난이도 SQL 요구사항**:
- 다중 조건 (AND, OR, 괄호 포함된 조건식)
- 복잡한 조건 연산자: !=, NOT, IS NULL, IS NOT NULL
- 정렬 + 제한 조합 (ORDER BY ... LIMIT)
- 조건에 문자열 포함 검색 (LIKE + 복합 조건)
- 복수 필드 UPDATE / INSERT
- 예시: WHERE rating >= 8 AND genre != '로맨스'""",
        
        "Expert": """
**Expert 난이도 SQL 요구사항**:
- 서브쿼리 포함 (WHERE x IN (SELECT ...))
- JOIN 사용 (INNER/LEFT/RIGHT JOIN)
- GROUP BY + HAVING
- 복수 조건에 정렬, 집계, 서브쿼리 혼합
- INSERT 시 모든 칼럼 채움
- 예시: GROUP BY director HAVING COUNT(*) > 3"""
    }
    
    return f"""
당신은 SQL 전문가입니다. 주어진 스키마와 자연어 질의를 바탕으로 정확한 SQL을 생성해주세요.

**도메인**: {domain['name']}
**설명**: {domain['description']}

**스키마 정보**:
{columns_text}

**자연어 질의**: {nl_query}
**요청 SQL 유형**: {qtype}
**난이도**: {level}
{level_sql_requirements[level]}

**중요 규칙**:
1. 위에 나열된 필드만 사용하세요. 스키마에 없는 필드는 절대 사용하지 마세요.
2. 정확한 테이블명과 컬럼명을 사용하세요.
3. SQL 문법을 정확히 지켜주세요.
4. 자연어 질의의 의도를 정확히 반영하세요.
5. **반드시 난이도에 맞는 SQL 요소를 포함하세요**.
6. 난이도보다 높은 요소는 사용하지 마세요.

**생성할 SQL**:
- 설명 없이 SQL만 반환하세요. 코드블록도 사용하지 마세요.
- 단일 SQL 문장으로 작성하세요.
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
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)

def is_similar_to_existing(query, existing_queries, threshold=0.7):
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

def generate_nl_and_sql(domain):
    """자연어 질의와 SQL을 함께 생성"""
    schema_dict = load_schema(domain)
    results = []
    retry_counts = {qtype: {level: {"total_retries": 0, "total_attempts": 0} for level in LEVELS} for qtype in TYPES}
    
    for qtype in TYPES:
        for level in LEVELS:
            n_target = TYPE_LEVEL_COUNTS[qtype][level]
            collected = []
            total_retries = 0
            total_attempts = 0
            
            while len(collected) < n_target and total_attempts < 15:  # 최대 시도 횟수 증가
                n = n_target - len(collected)
                nl_sql_prompt = make_nl_sql_prompt(domain, schema_dict, level, qtype, n)
                nl_sql_content = call_openai_with_retry(nl_sql_prompt)
                total_retries += 1
                json_str = extract_json_from_response(nl_sql_content)
                
                if not json_str:
                    print(f"[ERROR] {domain['name']} {level} {qtype} NL-SQL 생성 실패 (시도 {total_retries}회)")
                    total_attempts += 1
                    continue
                    
                try:
                    nl_sql_pairs = json.loads(json_str)
                    for pair in nl_sql_pairs:
                        nl_query = pair["nl"]
                        sql_query = pair["sql"]
                        
                        # NL 유효성 검사 (중복, SQL 키워드 포함 여부)
                        if (nl_query in [item['nl'] for item in collected] or 
                            contains_sql_keyword(nl_query) or 
                            is_similar_to_existing(nl_query, collected)):
                            print(f"[WARNING] {domain['name']} {level} {qtype} NL 중복 또는 유사 질의 발견: {nl_query}")
                            continue
                        
                        # SQL 정리 (코드블록 제거)
                        if sql_query.startswith("```sql"):
                            sql_query = sql_query[6:]
                        if sql_query.endswith("```"):
                            sql_query = sql_query[:-3]
                        sql_query = sql_query.strip()
                        
                        # SQL 유효성 검사 (기본적인 검사)
                        if sql_query and len(sql_query) > 10:
                            # 생성된 SQL의 난이도와 타입을 검증
                            is_valid_difficulty, difficulty_reason = validate_sql_difficulty(sql_query, level)
                            is_valid_type, type_reason = validate_sql_type(sql_query, qtype)
                            
                            if is_valid_difficulty and is_valid_type:
                                collected.append({
                                    "nl": nl_query, 
                                    "sql": sql_query,
                                    "level": level, 
                                    "dml": qtype,
                                    "retries": total_retries
                                })
                            else:
                                print(f"[WARNING] {domain['name']} {level} {qtype} SQL 검증 실패: 난이도 문제 ({difficulty_reason}), 타입 문제 ({type_reason})")
                                print(f"     NL: {nl_query}")
                                print(f"     SQL: {sql_query}")
                                print()
                        else:
                            print(f"[WARNING] {domain['name']} {level} {qtype} SQL 생성 실패: 너무 짧거나 빈 쿼리")
                            
                except Exception as e:
                    print(f"[ERROR] {domain['name']} {level} {qtype} 파싱 오류: {e}")
                    total_attempts += 1
                    continue
                    
                total_attempts += 1
                time.sleep(1)
                
            retry_counts[qtype][level]["total_retries"] = total_retries
            retry_counts[qtype][level]["total_attempts"] = total_attempts
            
            for item in collected[:n_target]:
                results.append(item)
                
            print(f"[{domain['name']}] {qtype} {level} 생성: {len(collected[:n_target])}개")
            print(f"  - 총 시도: {total_retries}회, 총 반복: {total_attempts}회")
    
    random.shuffle(results)
    return results, retry_counts

def validate_sql_difficulty(sql, level):
    """SQL이 지정된 난이도에 맞는지 검증"""
    sql_upper = sql.upper()
    
    if level == "Basic":
        # Basic: 단순 조건만, 집계/정렬/서브쿼리 없음
        basic_forbidden = ['GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT', 'JOIN', 'IN (', 'EXISTS', 'COUNT', 'AVG', 'SUM', 'MAX', 'MIN', 'DISTINCT']
        for forbidden in basic_forbidden:
            if forbidden in sql_upper:
                return False, f"Basic 난이도에서 사용할 수 없는 요소: {forbidden}"
        return True, "Basic 난이도 적합"
    
    elif level == "Intermediate":
        # Intermediate: 집계, 정렬, LIKE, BETWEEN, IN 등 허용
        intermediate_allowed = ['COUNT', 'AVG', 'SUM', 'MAX', 'MIN', 'ORDER BY', 'LIMIT', 'LIKE', 'BETWEEN', 'IN', 'DISTINCT']
        has_intermediate_feature = any(feature in sql_upper for feature in intermediate_allowed)
        if not has_intermediate_feature:
            return False, "Intermediate 난이도에 필요한 요소가 없음 (집계, 정렬, LIKE, BETWEEN, IN 등)"
        
        # Expert 요소는 금지
        expert_forbidden = ['JOIN', 'HAVING', 'EXISTS', 'IN (SELECT']
        for forbidden in expert_forbidden:
            if forbidden in sql_upper:
                return False, f"Intermediate 난이도에서 사용할 수 없는 요소: {forbidden}"
        return True, "Intermediate 난이도 적합"
    
    elif level == "Advanced":
        # Advanced: 복합 조건, !=, IS NULL, ORDER BY + LIMIT 등
        advanced_allowed = ['AND', 'OR', '!=', 'IS NULL', 'IS NOT NULL', 'ORDER BY', 'LIMIT']
        has_advanced_feature = any(feature in sql_upper for feature in advanced_allowed)
        if not has_advanced_feature:
            return False, "Advanced 난이도에 필요한 요소가 없음 (복합조건, !=, IS NULL, ORDER BY + LIMIT 등)"
        
        # Expert 요소는 금지
        expert_forbidden = ['JOIN', 'HAVING', 'IN (SELECT', 'EXISTS']
        for forbidden in expert_forbidden:
            if forbidden in sql_upper:
                return False, f"Advanced 난이도에서 사용할 수 없는 요소: {forbidden}"
        return True, "Advanced 난이도 적합"
    
    elif level == "Expert":
        # Expert: 서브쿼리, JOIN, HAVING 등
        expert_allowed = ['JOIN', 'HAVING', 'IN (SELECT', 'EXISTS', 'GROUP BY']
        has_expert_feature = any(feature in sql_upper for feature in expert_allowed)
        if not has_expert_feature:
            return False, "Expert 난이도에 필요한 요소가 없음 (JOIN, HAVING, 서브쿼리 등)"
        return True, "Expert 난이도 적합"
    
    return True, "검증 완료"

def validate_sql_type(sql, expected_type):
    """SQL이 지정된 타입에 맞는지 검증"""
    sql_upper = sql.upper().strip()
    
    if expected_type == "SELECT":
        return sql_upper.startswith("SELECT"), "SELECT 문이어야 함"
    elif expected_type == "INSERT":
        return sql_upper.startswith("INSERT"), "INSERT 문이어야 함"
    elif expected_type == "UPDATE":
        return sql_upper.startswith("UPDATE"), "UPDATE 문이어야 함"
    elif expected_type == "DELETE":
        return sql_upper.startswith("DELETE"), "DELETE 문이어야 함"
    
    return True, "타입 검증 완료"

def main():
    os.makedirs(QUERY_DIR, exist_ok=True)
    domains = load_domains()
    
    # 테스트용으로 첫 번째 도메인만 실행
    test_domain = domains[0]  # 날씨 정보
    
    print(f"\n{'='*60}")
    print(f"NL2SQL 파이프라인 테스트")
    print(f"도메인: {test_domain['name']}")
    print(f"설명: {test_domain['description']}")
    print(f"{'='*60}")
    
    results, retry_counts = generate_nl_and_sql(test_domain)
    
    # 결과 분석
    print(f"\n📊 생성 결과 분석:")
    print(f"  - 총 생성된 쌍: {len(results)}개")
    
    # 타입별 통계
    type_counts = {}
    for item in results:
        qtype = item['dml']
        type_counts[qtype] = type_counts.get(qtype, 0) + 1
    print(f"  - 타입별 분포: {type_counts}")
    
    # 레벨별 통계
    level_counts = {}
    for item in results:
        level = item['level']
        level_counts[level] = level_counts.get(level, 0) + 1
    print(f"  - 레벨별 분포: {level_counts}")
    
    # 재시도 통계
    print(f"\n🔄 재시도 통계:")
    total_retries = 0
    total_attempts = 0
    
    for qtype in TYPES:
        for level in LEVELS:
            stats = retry_counts[qtype][level]
            total_retries += stats["total_retries"]
            total_attempts += stats["total_attempts"]
            print(f"  - {qtype} {level}: 총 시도 {stats['total_retries']}회, 총 반복 {stats['total_attempts']}회")
    
    print(f"\n📈 전체 재시도 요약:")
    print(f"  - 총 NL-SQL 생성 시도: {total_retries}회")
    print(f"  - 총 반복 횟수: {total_attempts}회")
    print(f"  - 평균 시도/타입레벨: {total_retries / (len(TYPES) * len(LEVELS)):.1f}회")
    
    # 예시 결과들
    print(f"\n📝 생성된 예시들:")
    for i, item in enumerate(results[:5], 1):
        print(f"  {i}. [{item['dml']}/{item['level']}]")
        print(f"     NL: {item['nl']}")
        print(f"     SQL: {item['sql']}")
        print()
    
    # 결과 저장
    output_file = os.path.join(QUERY_DIR, f"{test_domain['name']}_nl2sql_test.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "domain": test_domain,
            "results": results,
            "retry_counts": retry_counts,
            "statistics": {
                "total_pairs": len(results),
                "type_counts": type_counts,
                "level_counts": level_counts,
                "total_retries": total_retries,
                "total_attempts": total_attempts,
                "avg_retries_per_type_level": round(total_retries / (len(TYPES) * len(LEVELS)), 1)
            }
        }, f, ensure_ascii=False, indent=2)
    
    print(f"💾 결과 저장 완료: {output_file}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main() 